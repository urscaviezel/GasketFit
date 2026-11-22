from __future__ import annotations
from .localization import tr
from . import __version__
from dataclasses import dataclass, asdict
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from .meshio import Mesh
from .profile import frame_vertices, weights, supported, smooth, smooth_derivative, transform


@dataclass
class FitResult:
    mesh: Mesh
    report: dict
    displacement: np.ndarray
    reference_vertices: np.ndarray | None = None


class Surface:
    def __init__(self, head):
        self.mesh = trimesh.Trimesh(head.vertices, head.faces, process=False)
        self.tree = cKDTree(head.vertices)
        self.query = trimesh.proximity.ProximityQuery(self.mesh)

    def close(self, points):
        closest, distance, triangles = [], [], []
        # Bound temporary candidate arrays on very dense scans.
        for i in range(0, len(points), 12):
            c, d, t = self.query.on_surface(points[i:i + 12])
            closest.append(c)
            distance.append(d)
            triangles.append(t)
        return np.concatenate(closest), np.concatenate(distance), np.concatenate(triangles)


def ring_indices(frame):
    angle = np.arctan2((frame[:, 2] - 78) / 48, frame[:, 0] / 77)
    bins = np.minimum(239, np.floor((angle + np.pi) * 240 / (2 * np.pi)).astype(int))
    selected = []
    for b in range(240):
        ids = np.flatnonzero(bins == b)
        if len(ids):
            selected.append(ids[np.argmax(frame[ids, 1])])
    return np.array(selected, dtype=np.int32)


def first_surface_crossing(surface, points, direction, target, steps, progress=None):
    progress = progress or (lambda *_: None)
    # Exact surface distance is 1-Lipschitz along a unit direction. Skip only
    # grid samples which provably cannot reach the target yet. This keeps the
    # first crossing correct on sparse meshes without thousands of expensive
    # dense-scan triangle queries.
    spacing = float(steps[1] - steps[0])
    if spacing <= 0 or not np.allclose(np.diff(steps), spacing) or not np.allclose(np.linalg.norm(direction, axis=1), 1):
        raise ValueError("Invalid surface search grid")
    indices = np.zeros(len(points), dtype=int)
    first = np.full(len(points), -1, dtype=int)
    active = np.ones(len(points), dtype=bool)
    while active.any():
        progress(17, tr('Dreiecksfl?chen des Kopfmodells pr?fen ?'))
        ids = np.flatnonzero(active)
        _, exact, _ = surface.close(points[ids] + direction[ids] * steps[indices[ids], None])
        reached = exact <= target + 1e-9
        first[ids[reached]] = indices[ids[reached]]
        active[ids[reached]] = False
        waiting = ids[~reached]
        # Positive floor safely skips impossible samples; at least one step
        # allows a crossing within the next grid interval.
        jumps = np.maximum(1, np.floor(np.maximum(0, exact[~reached] - target - 1e-8) / spacing).astype(int))
        indices[waiting] += jumps
        active[waiting[indices[waiting] >= len(steps)]] = False
    if (first < 0).any():
        failed = np.flatnonzero(first < 0)
        raise ValueError(tr('{v0} von {v1} Auflagepunkten erreichen den Polsterabstand nicht. Die seitliche Suche ist auf 16 mm begrenzt. Bitte Gasket n?her an das Gesicht setzen und die Drehung pr?fen. Der Schl?fenmodus kann die Tiefe an Stirn und Wangen nicht ?ndern.', v0=len(failed), v1=len(points)))
    return first


def _topology(vertices, faces):
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    tri = vertices[faces]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    return {"boundary_edges": int(np.count_nonzero(counts == 1)),
            "nonmanifold_edges": int(np.count_nonzero(counts > 2)),
            "collapsed_triangles": int(np.count_nonzero(area < 1e-10))}


def _quality_correct(frame, faces, modified, coefficients):
    """Constrain tiny sliver triangles against the analytical deformation normal.

    The source has very skinny triangles. Interpolation of a nonlinear field can
    reverse those even when the continuous map has a positive Jacobian. Minimal
    shared-vertex corrections avoid that without changing mesh connectivity.
    """
    tri = frame[faces]
    nt = modified[faces]
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    center = tri.mean(1)
    x, depth, h = center.T
    s, sp = smooth((abs(x) - 40) / 25), smooth_derivative((abs(x) - 40) / 25) / 25
    d, dp = smooth((depth - 15) / 20), smooth_derivative((depth - 15) / 20) / 20
    low, high = smooth((h - 45) / 20), 1 - smooth((h - 110) / 15)
    hh = low * high
    hp = smooth_derivative((h - 45) / 20) / 20 * high - low * smooth_derivative((h - 110) / 15) / 15
    amp, derivative = np.zeros(len(center)), np.zeros(len(center))
    for side, sign in (("links", -1), ("rechts", 1)):
        mask = sign * x > 0
        c = coefficients[side]
        amp[mask] = np.polynomial.polynomial.polyval((h[mask] - 85) / 30, c)
        derivative[mask] = np.polynomial.polynomial.polyval((h[mask] - 85) / 30, np.polynomial.polynomial.polyder(c)) / 30
    a = 1 - sp * d * hh * amp
    b = -np.sign(x) * s * dp * hh * amp
    c = -np.sign(x) * s * d * (hp * amp + hh * derivative)
    if a.min() < .25:
        raise ValueError(tr('Die Anpassung wäre zu stark. Bitte Ausrichtung und Polsterdicke prüfen.'))
    expected = np.c_[normal[:, 0], a * normal[:, 1] - b * normal[:, 0], a * normal[:, 2] - c * normal[:, 0]]
    corrected = set()
    for iteration in range(150):
        nt = modified[faces]
        nn = np.cross(nt[:, 1] - nt[:, 0], nt[:, 2] - nt[:, 0])
        cosine = (nn * expected).sum(1) / np.maximum(np.linalg.norm(nn, axis=1) * np.linalg.norm(expected, axis=1), 1e-30)
        bad = np.flatnonzero(cosine < .1)
        if not len(bad):
            break
        for k in bad:
            ids = faces[k]
            if np.any(weights(frame[ids]) == 0):
                raise ValueError(tr('Der Übergang zur Aufnahme wäre nicht ausreichend stabil. Bitte weniger stark anpassen.'))
            p0, p1, p2 = modified[ids]
            e1, e2 = p1 - p0, p2 - p0
            ey, ez = expected[k, 1:]
            gradient = np.array([ey * (-e1[2] + e2[2]) + ez * (-e2[1] + e1[1]),
                                 -ey * e2[2] + ez * e2[1], ey * e1[2] - ez * e1[1]])
            target = .3 * np.linalg.norm(expected[k]) * np.linalg.norm(nn[k])
            step = (target - np.dot(expected[k], nn[k])) / max(np.dot(gradient, gradient), 1e-30)
            modified[ids, 0] += gradient * step
            corrected.update(ids.tolist())
    else:
        raise ValueError(tr('Die Netzprüfung konnte keinen stabilen Übergang herstellen. Bitte Ausrichtung ändern.'))
    if np.linalg.norm(nn, axis=1).min() < 1e-10:
        raise ValueError(tr('Bei der Anpassung ist eine Fläche zusammengefallen. Kein Export freigegeben.'))
    return {"minimum_jacobian": float(a.min()), "minimum_normal_agreement": float(cosine.min()),
            "quality_corrected_vertices": len(corrected)}


def fit_gasket(gasket: Mesh, head: Mesh, pose: np.ndarray, pad: float, progress=None) -> FitResult:
    progress = progress or (lambda value, text: None)
    if not supported(gasket):
        raise ValueError(tr('Dieses Modell passt nicht zum PFDMR-V2-Profil. Bitte das unveränderte Original laden.'))
    if not 1 <= pad <= 15:
        raise ValueError(tr('Die Polsterdicke muss zwischen 1 und 15 mm liegen.'))
    extent = np.ptp(head.vertices, axis=0)
    if extent.min() < 45 or extent.max() > 550:
        raise ValueError(tr('Der Kopf-Scan scheint nicht in Lebensgröße vorzuliegen. Bitte die Einheit/Skalierung prüfen.'))
    if not np.allclose(pose[:3, :3].T @ pose[:3, :3], np.eye(3), atol=1e-7) or np.linalg.det(pose[:3, :3]) < .99:
        raise ValueError(tr('Die Gasket-Ausrichtung darf nur Verschiebung und Drehung enthalten.'))
    frame = frame_vertices(gasket.vertices)
    w = weights(frame)
    ring = ring_indices(frame)
    rw = w[ring]
    rf = frame[ring]
    selection = (abs(rf[:, 0]) > 61) & (rw > .45) & (rf[:, 2] > 56) & (rf[:, 2] < 118)
    ring = ring[selection]
    if len(ring) < 30:
        raise ValueError(tr('Die Auflagekante konnte im PFDMR-Modell nicht zuverlässig erkannt werden.'))
    progress(5, tr('Kopfoberfläche vorbereiten …'))
    surface = Surface(head)
    points = transform(frame[ring], pose)
    sign = np.sign(frame[ring, 0])
    direction = -sign[:, None] * pose[:3, 0]
    progress(15, tr('Abstände zu beiden Schläfen bestimmen …'))
    closest, initial_distance, triangle_ids = surface.close(points)
    if np.median(initial_distance) > 22 or initial_distance.max() > 40:
        raise ValueError(tr('Das Gasket liegt zu weit vom Gesicht entfernt. Bitte zuerst näher an Stirn und Wangen ausrichten.'))
    normals = surface.mesh.face_normals[triangle_ids]
    signed = ((points - closest) * normals).sum(1)
    if np.count_nonzero(signed < -.7) > len(points) * .15:
        raise ValueError(tr('Die Auflagekante scheint im Kopf-Scan zu liegen. Bitte das Gasket weiter vom Gesicht weg bewegen.'))
    # Find the FIRST approach to the surface; do not use unsigned distance at
    # an endpoint that might already be far inside the head.
    steps = np.arange(-4., 16.01, .5)
    target = pad + .25
    first = first_surface_crossing(surface, points, direction, target, steps, progress)
    if (first == 0).any():
        raise ValueError(tr('Das Polster hätte bereits außerhalb des Suchbereichs zu wenig Platz. Bitte die Ausrichtung korrigieren.'))
    low = steps[first - 1]
    high = steps[first]
    # Vertex distances slightly overestimate exact surface distance. Expand
    # the outward side of the bracket, then refine on actual triangles.
    low -= 1.
    for iteration in range(15):
        progress(20 + iteration * 2, tr('5-mm-Abstand berechnen …') if pad == 5 else tr('Polsterabstand berechnen …'))
        middle = (low + high) / 2
        _, dist, _ = surface.close(points + direction * middle[:, None])
        low = np.where(dist > target, middle, low)
        high = np.where(dist <= target, middle, high)
    inward = (low + high) / 2
    coefficients = {}
    for side, sgn in (("links", -1), ("rechts", 1)):
        mask = sign == sgn
        if mask.sum() < 12:
            raise ValueError(tr('Zu wenige Auflagepunkte auf einer Seite.'))
        height = (frame[ring[mask], 2] - 85) / 30
        matrix = np.vander(height, 5, increasing=True)
        coefficients[side] = np.linalg.lstsq(matrix, inward[mask] / w[ring[mask]], rcond=None)[0]
    progress(55, tr('Weiche Übergänge formen …'))
    for attempt in range(10):
        amplitude = np.zeros(len(frame))
        for side, sgn in (("links", -1), ("rechts", 1)):
            mask = sgn * frame[:, 0] > 0
            amplitude[mask] = np.polynomial.polynomial.polyval((frame[mask, 2] - 85) / 30, coefficients[side])
        modified = frame.copy()
        modified[:, 0] -= np.sign(frame[:, 0]) * w * amplitude
        _, distances, _ = surface.close(transform(modified[ring], pose))
        if distances.min() >= pad + .08:
            break
        for side, sgn in (("links", -1), ("rechts", 1)):
            if distances[sign == sgn].min() < pad + .08:
                coefficients[side][0] -= .2
    else:
        raise ValueError(tr('Der gewünschte Polsterabstand konnte nicht gleichmäßig erreicht werden.'))
    if distances.max() > pad + 2.2:
        raise ValueError(tr('Die Abstände sind zu ungleichmäßig. Bitte die Ausrichtung an Stirn und Wangen verbessern.'))
    if abs(modified[:, 0] - frame[:, 0]).max() > 12:
        raise ValueError(tr('Mehr als 12 mm Änderung wäre nötig. Bitte die Ausrichtung kontrollieren.'))
    progress(68, tr('Netz und Übergänge prüfen …'))
    quality = _quality_correct(frame, gasket.faces, modified, coefficients)
    output = gasket.vertices.copy()
    output[:, 0] += modified[:, 0] - frame[:, 0]
    protected = w == 0
    # Copy protected vertices, including the mounting interface, exactly.
    output[protected] = gasket.vertices[protected]
    assert np.array_equal(output[protected], gasket.vertices[protected])
    assert np.array_equal(output[:, 1:], gasket.vertices[:, 1:])
    progress(80, tr('Aufnahme und Polsterabstand nachprüfen …'))
    actual_frame = frame_vertices(output)
    _, final_distance, _ = surface.close(transform(actual_frame[ring], pose))
    if final_distance.min() < pad - .03:
        raise ValueError(tr('Nach der Netzkorrektur wäre der Polsterabstand zu klein. Bitte Ausrichtung leicht ändern.'))
    topology = _topology(output, gasket.faces)
    if any(topology.values()):
        raise ValueError(tr('Die Prüfung hat eine offene oder fehlerhafte Stelle im Netz erkannt. Kein Export freigegeben.'))
    report = {
        "app_version": __version__, "profile": tr('PFDMR Face Gasket Mod V2 · Schläfen'),
        "pad_mm": float(pad), "source_gasket": gasket.name, "source_head": head.name,
        "pose_frame_to_head": pose.tolist(), "mount_vertices_unchanged": True,
        "protected_vertex_count": int(protected.sum()), "triangles": len(gasket.faces),
        "topology": topology, "quality": quality, "sides": {},
        "checks_scope": tr('Polsterabstand an der abgetasteten zentralen Schläfen-Auflagekante. Die übrigen Bereiche laufen weich zum Original aus.'),
        "limitations": [tr('Keine vollständige Prüfung aller Selbstüberschneidungen oder Wandstärken.'),
                        tr('Scanmaßstab, Trageposition und tatsächliche Polsterkompression durch Anprobe prüfen.')]}
    change = abs(output[:, 0] - gasket.vertices[:, 0])
    for side, sgn in (("links", -1), ("rechts", 1)):
        values = final_distance[sign == sgn]
        report["sides"][side] = {"sample_count": len(values), "minimum_gap_mm": float(values.min()),
                                  "median_gap_mm": float(np.median(values)), "maximum_gap_mm": float(values.max()),
                                  "maximum_change_mm": float(change[sgn * frame[:, 0] > 0].max())}
    progress(100, tr('Anpassung abgeschlossen'))
    return FitResult(Mesh(output, gasket.faces.copy(), "PFDMR_Scanfit", gasket.source), report, change)
