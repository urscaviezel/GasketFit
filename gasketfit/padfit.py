"""New cushion-first design. All output is independent of the V2 gasket.

A cylindrical layout wraps the measured flat outline around the head. Exact
ray hits supply a smooth radial surface; no head holes are silently filled.
The original flat metric remains available to quantify cushion stretch.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import trimesh
from scipy.interpolate import RBFInterpolator, RegularGridInterpolator
from .meshio import Mesh
from .profile import pose_matrix, transform
from .padtemplate import triangulate
from .localization import tr


@dataclass
class PadResult:
    mesh: Mesh
    contact: np.ndarray
    flat: np.ndarray
    surface_faces: np.ndarray
    report: dict


def validate_parameters(params):
    if params.get('solver') == 'forehead':
        from .forehead import validate
        return validate(params)
    if params.get('solver') == 'reference04':
        from .referencefit import validate
        return validate(params)
    p = dict(params)
    pose = np.asarray(p.get("pose"), dtype=float)
    if pose.shape != (6,) or not np.isfinite(pose).all() or (abs(pose) > 2000).any():
        raise ValueError(tr("Ungültige Position der Polsterauflage."))
    for key, low, high in (("radius", 55, 180), ("padding", 1, 15),
                           ("smoothing", .2, 3), ("thickness", .5, 5)):
        p[key] = float(p[key])
        if not np.isfinite(p[key]) or not low <= p[key] <= high:
            raise ValueError(tr("Ungültige Einstellungen der Polsterauflage."))
    p["pose"] = pose.tolist()
    return p


def initial_parameters(head):
    lo, hi = head.bounds
    return dict(pose=[float((lo[0] + hi[0]) / 2), float(lo[1] + .60 * (hi[1] - lo[1])),
                      float(lo[2] + .57 * (hi[2] - lo[2])), 0., 0., 0.],
                radius=90., padding=5., smoothing=1.5, thickness=1.5)


def _improve_triangles(points, faces, passes=30):
    """Delaunay edge flips inside the polygon; boundary segments never move."""
    faces = faces.copy()
    for _ in range(passes):
        uses = {}
        for i, (a, b, c) in enumerate(faces):
            for u, v, w in ((a, b, c), (b, c, a), (c, a, b)):
                uses.setdefault(tuple(sorted((u, v))), []).append((i, w))
        touched, changed = set(), False
        for (a, b), pair in uses.items():
            if len(pair) != 2:
                continue
            (i, c), (j, d) = pair
            if i in touched or j in touched:
                continue
            pa, pb, pc, pd = points[[a, b, c, d]]
            cross = lambda u, v: u[0] * v[1] - u[1] * v[0]
            if cross(pd - pc, pa - pc) * cross(pd - pc, pb - pc) >= -1e-12:
                continue
            ac, bc, ad, bd = pa - pc, pb - pc, pa - pd, pb - pd
            opposite = np.arctan2(abs(cross(ac, bc)), ac @ bc) + np.arctan2(abs(cross(ad, bd)), ad @ bd)
            if opposite <= np.pi + 1e-8:
                continue
            for index, ids in ((i, [c, d, a]), (j, [d, c, b])):
                q = points[ids]
                if cross(q[1] - q[0], q[2] - q[0]) < 0:
                    ids.reverse()
                faces[index] = ids
            touched.update((i, j))
            changed = True
        if not changed:
            break
    return faces


def surface_reference(outline, maximum_edge=6.):
    """Conforming midpoint subdivision preserves every approved boundary edge."""
    points, faces = np.asarray(outline, dtype=float).copy(), triangulate(outline)
    faces = _improve_triangles(points, faces, 60)
    for _ in range(9):
        edges = np.sort(np.stack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=1), axis=2)
        unique, inverse = np.unique(edges.reshape(-1, 2), axis=0, return_inverse=True)
        split = np.linalg.norm(points[unique[:, 0]] - points[unique[:, 1]], axis=1) > maximum_edge
        if not split.any():
            break
        midpoint = np.full(len(unique), -1, dtype=np.int32)
        midpoint[split] = len(points) + np.arange(split.sum())
        points = np.vstack([points, points[unique[split]].mean(axis=1)])
        mids = midpoint[inverse].reshape(-1, 3)
        count = (mids >= 0).sum(axis=1)
        output = faces[count == 0].tolist()
        for ids, mid, n in zip(faces[count > 0], mids[count > 0], count[count > 0]):
            if n == 1:
                start = np.flatnonzero(mid >= 0)[0]
                a, b, c = np.roll(ids, -start)
                m = mid[start]
                output.extend([[a, m, c], [m, b, c]])
            elif n == 2:
                start = (np.flatnonzero(mid < 0)[0] + 1) % 3
                a, b, c = np.roll(ids, -start)
                ab, bc, _ = np.roll(mid, -start)
                output.extend([[b, bc, ab], [a, ab, c], [ab, bc, c]])
            else:
                a, b, c = ids
                ab, bc, ca = mid
                output.extend([[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]])
        faces = _improve_triangles(points, np.asarray(output, dtype=np.int32), 8)
    return points, faces


def wrapped_preview(outline, params):
    p = validate_parameters(params)
    angle = np.asarray(outline)[:, 0] / p["radius"]
    local = np.c_[p["radius"] * np.sin(angle), -p["radius"] * np.cos(angle), np.asarray(outline)[:, 1]]
    return transform(local, pose_matrix(p["pose"]))


def _close(query, points, progress, stage):
    distances = []
    for start in range(0, len(points), 40):
        if start % 400 == 0:
            progress(stage, tr("Polsterabstand an der Kopfoberfläche prüfen …"))
        distances.append(query.on_surface(points[start:start + 40])[1])
    return np.concatenate(distances)


def _smooth_radius(coordinates, radius, tolerance):
    selected = [0]
    distance = np.full(len(coordinates), np.inf)
    for _ in range(min(600, len(coordinates)) - 1):
        distance = np.minimum(distance, ((coordinates - coordinates[selected[-1]]) ** 2).sum(1))
        selected.append(int(np.argmax(distance)))
    selected = np.asarray(selected)
    smoothing = .3 * tolerance ** 2
    for _ in range(9):
        model = RBFInterpolator(coordinates[selected] / 20, radius[selected],
                                kernel="thin_plate_spline", smoothing=smoothing)
        fitted = model(coordinates / 20)
        error = abs(fitted - radius)
        if error.max() <= tolerance:
            return model, fitted, error
        smoothing *= .25
    raise ValueError(tr("Der Scan ist hier zu unregelmäßig für eine glatte Klebefläche. Bitte Position oder Glättung ändern."))


def _arc_angles(model, flat, radius, padding):
    """Invert horizontal surface arc length rather than shrinking flat X.

    A flat foam pad cannot fit an arbitrary doubly curved face isometrically.
    This removes the avoidable horizontal shrinkage; residual strain in the
    complete surface is measured separately and must remain visible to users.
    """
    theta = np.linspace(-2.15, 2.15, 701)
    heights = np.linspace(flat[:, 1].min(), flat[:, 1].max(), 51)
    xx = np.linspace(flat[:, 0].min(), flat[:, 0].max(), 241)
    coordinates = np.array([[t * radius, z] for z in heights for t in theta])
    rr = np.concatenate([model(coordinates[i:i + 1500] / 20)
                         for i in range(0, len(coordinates), 1500)]).reshape(len(heights), -1) + padding
    if not np.isfinite(rr).all():
        raise ValueError(tr("Die Biegung konnte nicht zuverlässig berechnet werden."))
    mapping = []
    for row in rr:
        curve = np.c_[row * np.sin(theta), -row * np.cos(theta)]
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(curve, axis=0), axis=1))]
        arc -= arc[len(theta) // 2]
        if arc[0] > xx[0] or arc[-1] < xx[-1]:
            raise ValueError(tr("Die Polsterlänge lässt sich hier nicht um den Kopf legen. Bitte Position ändern."))
        mapping.append(np.interp(xx, arc, theta))
    return RegularGridInterpolator((heights, xx), np.asarray(mapping))(
        np.c_[flat[:, 1], flat[:, 0]])


def _relax_on_surface(model, flat, faces, angle, radius, padding, progress):
    """Redistribute the cloth on the smooth face, penalising flat-edge strain."""
    theta_grid = np.linspace(-2.25, 2.25, 301)
    heights = np.linspace(flat[:, 1].min() - 15, flat[:, 1].max() + 15, 121)
    q = np.array([[t * radius, z] for t in theta_grid for z in heights])
    values = np.concatenate([model(q[i:i + 1500] / 20) for i in range(0, len(q), 1500)])
    field = RegularGridInterpolator((theta_grid, heights), values.reshape(len(theta_grid), -1),
                                   bounds_error=False, fill_value=None)
    edges = np.unique(np.sort(np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0)
    a, b = edges.T
    rest = np.linalg.norm(flat[a] - flat[b], axis=1)
    degree = np.bincount(edges.ravel(), minlength=len(flat))
    z = flat[:, 1].copy()
    r = model(np.c_[angle * radius, z] / 20) + padding
    v = np.c_[r * np.sin(angle), -r * np.cos(angle), z]
    reference = v.copy()
    parameter_reference = np.c_[angle, z]
    tri = parameter_reference[faces]
    minimum_area = ((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1])
                    - (tri[:, 1, 1] - tri[:, 0, 1]) * (tri[:, 2, 0] - tri[:, 0, 0])) * .10
    if (minimum_area <= 0).any():
        raise ValueError(tr("Die Auflage würde sich falten. Bitte Biegeradius oder Position ändern."))
    for step in range(240):
        if step % 40 == 0:
            progress(40 + step // 40, tr("Polsterlängen auf der glatten Fläche ausgleichen …"))
        delta = v[a] - v[b]
        length = np.linalg.norm(delta, axis=1)
        force = delta * ((length - rest) / np.maximum(length, 1e-12))[:, None]
        correction = np.zeros_like(v)
        np.add.at(correction, a, -force)
        np.add.at(correction, b, force)
        correction /= degree[:, None]
        correction += (reference - v) * .001
        correction *= np.minimum(1., .5 / np.maximum(np.linalg.norm(correction, axis=1), 1e-12))[:, None]
        trial = v + correction * .9
        previous = np.c_[angle, z]
        proposed = np.c_[np.arctan2(trial[:, 0], -trial[:, 1]),
                         np.clip(trial[:, 2], flat[:, 1].min() - 12, flat[:, 1].max() + 12)]
        # A local barrier keeps the cloth from folding during relaxation.
        for _ in range(25):
            tri = proposed[faces]
            area = ((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1])
                    - (tri[:, 1, 1] - tri[:, 0, 1]) * (tri[:, 2, 0] - tri[:, 0, 0]))
            bad = area < minimum_area
            if not bad.any():
                break
            ids = np.unique(faces[bad])
            proposed[ids] = previous[ids]
        else:
            proposed = previous
        angle, z = proposed.T
        r = field(np.c_[angle, z]) + padding
        v = np.c_[r * np.sin(angle), -r * np.cos(angle), z]
    # Evaluate the final positions on the actual smooth interpolant, not on
    # the acceleration grid used by the relaxation iterations.
    r = model(np.c_[angle * radius, z] / 20)
    return angle, z, r


def fit_pad(outline, head, params, progress=None):
    progress = progress or (lambda *_: None)
    p = validate_parameters(params)
    pose = pose_matrix(p["pose"])
    extent = np.ptp(head.vertices, axis=0)
    if extent.min() < 30 or extent.max() > 550:
        raise ValueError(tr("Bitte Maßstab und Ausrichtung des Kopfscans prüfen."))
    progress(3, tr("Freigegebene Polsterkontur vorbereiten …"))
    flat, faces = surface_reference(outline)
    angle = flat[:, 0] / p["radius"]
    if abs(angle).max() >= np.pi * .85:
        raise ValueError(tr("Der Biegeradius ist für diese Polsterkontur zu klein."))
    axis = np.c_[np.zeros((len(flat), 2)), flat[:, 1]]
    scan = trimesh.Trimesh(head.vertices, head.faces, process=False)
    for iteration in range(4):
        radial = np.c_[np.sin(angle), -np.cos(angle), np.zeros(len(flat))]
        origins = transform(axis + 400 * radial, pose)
        directions = -radial @ pose[:3, :3].T
        hit = np.full((len(flat), 3), np.nan)
        for start in range(0, len(flat), 250):
            progress(8 + iteration * 8 + int(7 * start / len(flat)), tr("Polsterkontur auf den Kopfscan projizieren …"))
            locations, rays, _ = scan.ray.intersects_location(origins[start:start + 250],
                                                            directions[start:start + 250], multiple_hits=False)
            hit[start + rays] = locations
        missing = ~np.isfinite(hit).all(axis=1)
        if missing.any():
            raise ValueError(tr("Für {v0} Auflagepunkte fehlt Scanfläche. Bitte Höhe, Drehung oder Biegeradius ändern; fehlende Flächen werden nicht erfunden.", v0=int(missing.sum())))
        local_hit = (hit - pose[:3, 3]) @ pose[:3, :3]
        radius = ((local_hit - axis) * radial).sum(1)
        if radius.min() < 15 or radius.max() > 220:
            raise ValueError(tr("Die Polsterauflage liegt nicht zuverlässig vor dem Gesicht. Bitte Position und Ausrichtung prüfen."))
        coordinates = np.c_[angle * p["radius"], flat[:, 1]]
        model, fitted, smoothed_error = _smooth_radius(coordinates, radius, p["smoothing"])
        if iteration == 3:
            break
        progress(16 + iteration * 8, tr("Biegung an die ursprüngliche Polsterlänge angleichen …"))
        angle = _arc_angles(model, flat, p["radius"], p["padding"] + .15)
    angle, adjusted_height, fitted = _relax_on_surface(model, flat, faces, angle,
                                                      p["radius"], p["padding"] + .15, progress)
    radial = np.c_[np.sin(angle), -np.cos(angle), np.zeros(len(flat))]
    axis[:, 2] = adjusted_height
    # Relaxation may move the outline slightly up/down. Verify that those new
    # points still have measured scan support rather than extrapolated holes.
    origins = transform(axis + 400 * radial, pose)
    directions = -radial @ pose[:3, :3].T
    hit = np.full((len(flat), 3), np.nan)
    for start in range(0, len(flat), 250):
        progress(47, tr("Scanabdeckung der geglätteten Auflage prüfen …"))
        locations, rays, _ = scan.ray.intersects_location(origins[start:start + 250], directions[start:start + 250], multiple_hits=False)
        hit[start + rays] = locations
    if not np.isfinite(hit).all():
        raise ValueError(tr("Für die geglättete Auflage fehlt Scanfläche. Bitte Position ändern."))
    measured = (((hit - pose[:3, 3]) @ pose[:3, :3] - axis) * radial).sum(1)
    smoothed_error = abs(fitted - measured)
    if smoothed_error.max() > p["smoothing"]:
        raise ValueError(tr("Die geglättete Auflage entfernt sich zu weit vom gemessenen Scan. Bitte Position oder Glättung ändern."))
    fitted += p["padding"] + .15
    query = trimesh.proximity.ProximityQuery(scan)
    # A global radial clearance correction preserves the smooth surface. Never
    # imprint the individual scan triangles back into the adhesive surface.
    clearance = None
    for attempt in range(9):
        local = axis + fitted[:, None] * radial
        world = transform(local, pose)
        # Include triangle interiors; checking vertices alone misses collisions.
        samples = np.vstack([world, world[faces].mean(axis=1)])
        clearance = _close(query, samples, progress, 50 + attempt * 3)
        shortfall = p["padding"] - clearance.min()
        if shortfall <= .02:
            break
        fitted += max(.1, shortfall * 1.4)
    else:
        raise ValueError(tr("Der gewünschte Polsterabstand konnte nicht sicher erreicht werden. Bitte die Position ändern."))
    progress(80, tr("Materialstärke und Polsterdehnung prüfen …"))
    surface = trimesh.Trimesh(world, faces, process=False)
    # Use the smooth surface's differential normals. Tessellation-averaged
    # normals can introduce a false crease at a very skinny boundary triangle.
    coordinates = np.c_[angle * p["radius"], axis[:, 2]]
    epsilon_theta, epsilon_height = .001, .05
    derivative_theta = (model((coordinates + [epsilon_theta * p["radius"], 0]) / 20)
                        - model((coordinates - [epsilon_theta * p["radius"], 0]) / 20)) / (2 * epsilon_theta)
    derivative_z = (model((coordinates + [0, epsilon_height]) / 20)
                    - model((coordinates - [0, epsilon_height]) / 20)) / (2 * epsilon_height)
    tangent_theta = np.c_[derivative_theta * np.sin(angle) + fitted * np.cos(angle),
                           -derivative_theta * np.cos(angle) + fitted * np.sin(angle), np.zeros(len(flat))]
    tangent_z = np.c_[derivative_z * np.sin(angle), -derivative_z * np.cos(angle), np.ones(len(flat))]
    normals = np.cross(tangent_theta, tangent_z)
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    normals = normals @ pose[:3, :3].T
    expected = radial @ pose[:3, :3].T
    agreement = (surface.face_normals * expected[faces].mean(axis=1)).sum(1)
    if agreement.min() < .05:
        raise ValueError(tr("Die Auflage würde sich falten. Bitte Biegeradius oder Position ändern."))
    outer = world + normals * p["thickness"]
    n = len(world)
    edge_pairs = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    unique, inverse, counts = np.unique(np.sort(edge_pairs, axis=1), axis=0, return_inverse=True, return_counts=True)
    boundary = edge_pairs[counts[inverse] == 1]
    volume_faces = np.vstack([faces[:, ::-1], faces + n,
                             np.array([[a, b, b + n] for a, b in boundary]),
                             np.array([[a, b + n, a + n] for a, b in boundary])])
    solid = trimesh.Trimesh(np.vstack([world, outer]), volume_faces, process=False)
    if not solid.is_watertight or not solid.is_winding_consistent or solid.volume <= 0:
        raise ValueError(tr("Die Auflage konnte nicht als geschlossener Körper berechnet werden."))
    if (solid.area_faces < 1e-10).any():
        raise ValueError(tr("Die Auflage enthält zusammengefallene Flächen. Bitte die Position ändern."))
    # Normal offset can collapse at a sharp bend even if the contact layer is OK.
    if (np.einsum("ij,ij->i", solid.face_normals[len(faces):2 * len(faces)], surface.face_normals) < .1).any():
        raise ValueError(tr("Die Materialstärke ist für diese Krümmung zu groß."))
    # All-edge strain is reported rather than hiding changes by rescaling the
    # accepted template. Very short edges amplify numerical noise; use >=1 mm.
    rest = np.linalg.norm(flat[unique[:, 0]] - flat[unique[:, 1]], axis=1)
    length = np.linalg.norm(world[unique[:, 0]] - world[unique[:, 1]], axis=1)
    strain = length[rest >= 1] / rest[rest >= 1] - 1
    if abs(strain).max() > .50:
        raise ValueError(tr("Das Polster würde örtlich um mehr als 50 Prozent verzerrt. Bitte Biegeradius oder Position ändern."))
    warnings = []
    if np.percentile(abs(strain), 95) > .08 or abs(strain).max() > .15:
        warnings.append("strain")
    if clearance.max() > p["padding"] + p["smoothing"] + .75:
        warnings.append("gap")
    # This is the measured distance between offset layers, not a claim that an
    # arbitrary normal offset yields an exact printable minimum wall thickness.
    backing_query = trimesh.proximity.ProximityQuery(trimesh.Trimesh(outer, faces, process=False))
    backing_distance = _close(backing_query, world, progress, 93)
    if backing_distance.min() < p["thickness"] * .85:
        raise ValueError(tr("Die Materialstärke wird an einer Krümmung unterschritten. Bitte Position oder Biegeradius ändern."))
    report = dict(mode="cushion_first", template_dimensions_mm=np.ptp(outline, axis=0).tolist(),
                  parameters=p, vertex_count=len(solid.vertices), face_count=len(solid.faces),
                  closed=True, consistent_winding=True, nominal_thickness_mm=p["thickness"],
                  sampled_thickness_min_mm=float(backing_distance.min()),
                  padding_min_mm=float(clearance.min()), padding_max_mm=float(clearance.max()),
                  smoothing_radial_error_max_mm=float(smoothed_error.max()),
                  smoothing_radial_error_p99_mm=float(np.percentile(smoothed_error, 99)),
                  edge_strain_min_percent=float(strain.min() * 100),
                  edge_strain_max_percent=float(strain.max() * 100),
                  edge_strain_p95_absolute_percent=float(np.percentile(abs(strain), 95) * 100),
                  warnings=warnings, scope="Cushion support only; no HMD adapter or connecting shell.",
                  validation="Sampled contact clearance and layer distance; not exhaustive solid self-intersection validation.")
    progress(100, tr("Polsterauflage berechnet."))
    return PadResult(Mesh(solid.vertices.copy(), solid.faces.copy(), "VRcover fitted support"),
                     world.copy(), flat, faces, report)
