"""Bounded, smooth fitting of the physically confirmed Probe 04 support.

Only XY bending is allowed in the support frame. Z routing is immutable.
Edge lengths are compared with the proven curved support, not its UV chart.
These experimental limits are geometry checks, not leather or pressure models.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import numpy as np
import trimesh
from scipy.optimize import least_squares
from .meshio import Mesh
from .padfit import PadResult, _close
from .profile import pose_matrix, transform
from .localization import tr


@lru_cache(maxsize=1)
def reference():
    with np.load(Path(__file__).with_name('vrcover_probe04.npz'), allow_pickle=False) as data:
        return {key: data[key].copy() for key in data.files}


def validate(params):
    p = dict(params)
    if 'pad_alignment' in p:
        relative=np.asarray(p['pad_alignment'],dtype=float)
        if relative.shape!=(4,) or not np.isfinite(relative).all() or (abs(relative)>2000).any():
            raise ValueError(tr('Ungültige relative Auflagenausrichtung.'))
        p['pad_alignment']=relative.tolist()
    if any(key in p and not isinstance(p[key], bool) for key in ('nose_bridge', 'nose_pockets')):
        raise ValueError(tr('Ungültige Einstellung für den Nasenbogen.'))
    if 'top_strap' in p and not isinstance(p['top_strap'], bool):
        raise ValueError(tr('Ungültige Einstellung für die Kopfbandhalterung.'))
    if 'nose_enabled' in p and not isinstance(p['nose_enabled'],bool):
        raise ValueError(tr('Ungültige Einstellungen der Nasenöffnung.'))
    for key,lo,hi in [('nose_width',16,65),('nose_height',8,45),('nose_clearance',1,8)]:
        if key in p:
            p[key]=float(p[key])
            if not np.isfinite(p[key]) or not lo<=p[key]<=hi:
                raise ValueError(tr('Ungültige Einstellungen der Nasenöffnung.'))
    pose = np.asarray(p.get('pose'), dtype=float)
    if pose.shape != (6,) or not np.isfinite(pose).all() or (abs(pose) > 2000).any():
        raise ValueError(tr('Ungültige Position der Polsterauflage.'))
    for key, low, high, default in (('padding', 3.5, 10, 6.5), ('velcro', 0, 3, 0),
                                     ('max_adjustment', 0, 20, 12)):
        p[key] = float(p.get(key, default))
        if not np.isfinite(p[key]) or not low <= p[key] <= high:
            raise ValueError(tr('Ungültige Einstellungen der Polsterauflage.'))
    if not isinstance(p.get('refine_pose', False), bool):
        raise ValueError(tr('Ungültige Einstellungen der Polsterauflage.'))
    if 'include_base' in p and not isinstance(p['include_base'],bool):
        raise ValueError(tr('Ungültige Einstellungen der Polsterauflage.'))
    if 'closed_shell' in p and not isinstance(p['closed_shell'],bool):
        raise ValueError(tr('Ungültige Einstellungen der Polsterauflage.'))
    if 'base_pose' in p:
        base=np.asarray(p['base_pose'],dtype=float)
        if base.shape!=(6,) or not np.isfinite(base).all() or (abs(base)>2000).any():
            raise ValueError(tr('Ungültige Position der magnetischen Basis.'))
        p['base_pose']=base.tolist()
    radius=float(p.get('radius',90.))
    if not np.isfinite(radius) or not 55<=radius<=180:raise ValueError(tr('Ungültiger Radius.'))
    p.update(pose=pose.tolist(), solver='reference04', thickness=1.5,
             radius=radius, smoothing=1.5, refine_pose=p.get('refine_pose', False))
    return p


def initial_parameters(head):
    v = head.vertices
    lo, hi = head.bounds
    cx = float((lo[0] + hi[0]) / 2)
    height = hi[2] - lo[2]
    central = (abs(v[:, 0]-cx) < 10) & (v[:, 2] > lo[2]+.25*height) & (v[:, 2] < lo[2]+.8*height)
    vv = v[central]
    nose = vv[np.argmin(vv[:, 1])] if len(vv) else (lo+hi)/2
    forehead = (abs(v[:, 0]-cx) < 15) & (abs(v[:, 2]-(nose[2]+60)) < 6)
    y = float(np.percentile(v[forehead, 1], 5)) if forehead.any() else float(lo[1]+20)
    return validate(dict(pose=[cx, y-6.5, float(nose[2]+25-78), 0, 0, 0]))


def wrapped_preview(unused, params):
    return transform(reference_for_parameters(params)['contact'], pose_matrix(validate(params)['pose']))


def reference_for_parameters(params):
    radius=validate(params)['radius']
    d=reference()
    if radius==90.:return d
    v=d['contact'].copy();theta=np.arctan2(v[:,0],90.-v[:,1])
    radial=np.hypot(v[:,0],90.-v[:,1])-90.+radius
    v[:,0]=radial*np.sin(theta*90./radius)
    v[:,1]=radius-radial*np.cos(theta*90./radius)
    return {**d,'contact':v}


def _closest(query, points, progress, stage):
    batches = []
    for start in range(0, len(points), 40):
        if start % 400 == 0:
            progress(stage, tr('Polsterabstand an der Kopfoberfläche prüfen …'))
        batches.append(query.on_surface(points[start:start+40]))
    return tuple(np.concatenate([b[i] for b in batches]) for i in range(3))


def _basis(data):
    uv = data['uv']
    # Broad overlapping controls avoid copying scan texture into the backing.
    centres = np.array([(u, z) for u in np.linspace(-100, 100, 5) for z in (40, 85, 125)])
    weights = np.exp(-.5 * (((uv[:, None]-centres)/[48., 60.])**2).sum(2))
    weights /= weights.sum(1)[:, None]
    return weights


def fit_pad(unused_outline, head, params, progress=None, *, reference_data=None):
    progress = progress or (lambda *_: None)
    if reference_data is None:
        p = validate(params)
    else:
        from .forehead import validate as validate_forehead
        p = validate_forehead(params)
    extent = np.ptp(head.vertices, axis=0)
    if extent.min() < 30 or extent.max() > 550:
        raise ValueError(tr('Bitte Maßstab und Ausrichtung des Kopfscans prüfen.'))
    d = reference_for_parameters(p) if reference_data is None else reference_data
    rest, faces = d['contact'], d['faces']
    weights = _basis(d)
    if reference_data is not None:
        uv=d['uv']
        centres=np.array([(u,z) for u in np.linspace(uv[:,0].min(),uv[:,0].max(),7)
                          for z in np.linspace(uv[:,1].min(),uv[:,1].max(),3)])
        weights=np.exp(-.5*(((uv[:,None]-centres)/[35.,22.])**2).sum(2))
        weights/=weights.sum(1)[:,None]
    ref_surface = trimesh.Trimesh(rest, faces, process=False)
    edges = ref_surface.edges_unique
    a, b = edges.T
    rest_length = np.linalg.norm(rest[a]-rest[b], axis=1)
    edge_ids = np.flatnonzero(rest_length >= 1.)
    # Include all boundary vertices and an evenly distributed interior sample.
    ids = np.unique(np.r_[np.arange(0, 420, 2), np.linspace(0, len(rest)-1, 450).astype(int)])
    query = trimesh.proximity.ProximityQuery(trimesh.Trimesh(head.vertices, head.faces, process=False))
    initial = np.asarray(p['pose'])
    pose = initial.copy()
    coeff = np.zeros(weights.shape[1]*2)
    target = p['padding'] + p['velcro']
    limit = p['max_adjustment']
    normals = ref_surface.vertex_normals
    lower = initial - [12, 20, 12, 12, 8, 8]
    upper = initial + [12, 20, 12, 12, 8, 8]
    active = limit > 0

    def local(c):
        delta = np.c_[weights @ c[:weights.shape[1]], weights @ c[weights.shape[1]:], np.zeros(len(rest))]
        return rest + delta

    for iteration in range(8 if active or p['refine_pose'] else 1):
        progress(8+iteration*7, tr('Bewährte Polsterform begrenzt anpassen …'))
        current = local(coeff)
        matrix = pose_matrix(pose)
        world = transform(current[ids], matrix)
        near, distance, _ = _closest(query, world, progress, 10+iteration*7)
        away = normals[ids] @ matrix[:3, :3].T
        unit = (world-near)/np.maximum(distance[:, None], 1e-10)
        unit[(unit*away).sum(1) < 0] *= -1

        def residual(x):
            pp = pose.copy()
            if p['refine_pose']:
                pp[1] = x[0]
            cc = x[1:] if p['refine_pose'] else x
            cand = local(cc) if active else rest
            sample = transform(cand[ids], pose_matrix(pp))
            gap = ((sample-near)*unit).sum(1)
            lengths = np.linalg.norm(cand[a[edge_ids]]-cand[b[edge_ids]], axis=1)
            strain = lengths/rest_length[edge_ids]-1
            # Penalise all metric changes, with a strong barrier near 4%.
            barrier = np.maximum(abs(strain)-.035, 0)*np.sign(strain)
            clearance_barrier = np.minimum(gap-(3.8+p['velcro']), 0)*3
            reach_barrier = np.maximum(gap-(9.7+p['velcro']), 0)*2
            return np.r_[(gap-target), clearance_barrier, reach_barrier, (strain*35), (barrier*250), cc*.05,
                         (pp-initial)*np.array([.03, .03, .06, .1, .15, .15])]

        if active or p['refine_pose']:
            c_low, c_high = (-limit if active else -1e-10), (limit if active else 1e-10)
            x = np.r_[pose[1], coeff] if p['refine_pose'] else coeff
            bounds = (np.r_[lower[1], np.full(len(coeff), c_low)], np.r_[upper[1], np.full(len(coeff), c_high)]) if p['refine_pose'] else (c_low, c_high)
            answer = least_squares(residual, x, bounds=bounds, max_nfev=45, ftol=2e-4, xtol=2e-4)
            if p['refine_pose']:
                pose[1], coeff = answer.x[0], answer.x[1:]
            else:
                coeff = answer.x

    # Hard metric limit: never export an unconstrained face projection.
    alpha = 1.
    for _ in range(40):
        contact_local = local(coeff*alpha)
        strains = np.linalg.norm(contact_local[a]-contact_local[b], axis=1)/rest_length-1
        if abs(strains).max() <= .04 and np.linalg.norm(contact_local-rest, axis=1).max() <= limit+1e-8:
            break
        alpha *= .85
    else:
        raise ValueError(tr('Die Anpassungsgrenze konnte nicht eingehalten werden.'))
    world = transform(contact_local, pose_matrix(pose))
    surface = trimesh.Trimesh(world, faces, process=False)
    # Reference normals transported by a local affine differential. This avoids
    # introducing tessellation creases at skinny boundary triangles.
    uv = d['uv']
    from scipy.interpolate import RBFInterpolator
    selected = np.linspace(0, len(uv)-1, 1000).astype(int)
    field = RBFInterpolator(uv[selected]/50, contact_local[selected], smoothing=1e-7)
    du = field((uv+[.02, 0])/50)-field((uv-[.02, 0])/50)
    dv = field((uv+[0, .02])/50)-field((uv-[0, .02])/50)
    out = np.cross(du, dv)
    out /= np.linalg.norm(out, axis=1)[:, None]
    if np.mean((out*normals).sum(1)) < 0:
        out *= -1
    out = out @ pose_matrix(pose)[:3, :3].T
    wall = p.get('thickness', 1.5)
    backing = world + out*wall
    n = len(world)
    pairs = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    _, inv, counts = np.unique(np.sort(pairs, axis=1), axis=0, return_inverse=True, return_counts=True)
    boundary = pairs[counts[inv] == 1]
    volume_faces = np.vstack([faces[:, ::-1], faces+n,
                             [[a, b, b+n] for a, b in boundary], [[a, b+n, a+n] for a, b in boundary]])
    solid = trimesh.Trimesh(np.vstack([world, backing]), volume_faces, process=False)
    if not solid.is_watertight or not solid.is_winding_consistent or solid.volume <= 0 or solid.area_faces.min() < 1e-10:
        raise ValueError(tr('Die Auflage konnte nicht als geschlossener Körper berechnet werden.'))
    face_agreement = np.einsum('ij,ij->i', solid.face_normals[len(faces):2*len(faces)], surface.face_normals)
    reference_agreement = np.einsum('ij,ij->i', surface.face_normals, ref_surface.face_normals @ pose_matrix(pose)[:3, :3].T)
    if min(face_agreement.min(), reference_agreement.min()) < .5:
        raise ValueError(tr('Die Auflage würde sich falten. Bitte die Anpassung verringern.'))
    samples = np.vstack([world, world[faces].mean(1)])
    near, distances, triangles = _closest(query, samples, progress, 78)
    sample_normals = np.vstack([out, out[faces].mean(1)])
    gaps = distances*np.sign(((samples-near)*sample_normals).sum(1))
    # A nearest point on an open scan rim is not measured facial coverage.
    scan = query._mesh
    edge_counts = np.bincount(scan.edges_unique_inverse, minlength=len(scan.edges_unique))
    rim_vertices = np.unique(scan.edges_unique[edge_counts == 1])
    rim_faces = np.any(np.isin(scan.faces, rim_vertices), axis=1)
    if np.any(rim_faces[triangles]):
        raise ValueError(tr('Die Auflage reicht an einen offenen Scanrand. Bitte Position ändern oder einen vollständigeren Scan verwenden.'))
    if gaps.min() < 1.:
        raise ValueError(tr('Die Auflage liegt zu nah am Gesicht oder schneidet den Scan. Bitte Position oder Polsterabstand ändern.'))
    thickness = _close(trimesh.proximity.ProximityQuery(trimesh.Trimesh(backing, faces, process=False)), world, progress, 90)
    if thickness.min() < wall-.05:
        raise ValueError(tr('Die Materialstärke wird an einer Krümmung unterschritten. Bitte Anpassung verringern.'))
    baseline = transform(rest, pose_matrix(pose))
    before_near, before_distance, _ = _closest(query, np.vstack([baseline, baseline[faces].mean(1)]), progress, 94)
    before = before_distance*np.sign(((np.vstack([baseline, baseline[faces].mean(1)])-before_near)*sample_normals).sum(1))
    warning = []
    if gaps.min() < 3.5+p['velcro'] or gaps.max() > 10+p['velcro']:
        warning.append('gap')
    if alpha < .99 or (limit and np.linalg.norm(contact_local-rest, axis=1).max() > limit*.95):
        warning.append('limit')
    strain = strains*100
    # Colour values compare with confirmed Probe04 curved edge lengths.
    vertex_strain = np.zeros(len(rest))
    np.maximum.at(vertex_strain, a, abs(strains)*100)
    np.maximum.at(vertex_strain, b, abs(strains)*100)
    report = dict(mode='reference04_bounded', reference='VRcover Probe 04 - physically confirmed cushion attachment',
                  reference_sha256=hashlib.sha256(rest.tobytes()+faces.tobytes()).hexdigest(),
                  parameters={**p, 'pose': pose.tolist()}, requested_pose=p['pose'], alignment_policy='Manual pose locked; optional Y depth refinement only', closed=True, consistent_winding=True,
                  nominal_thickness_mm=1.5, sampled_thickness_min_mm=float(thickness.min()),
                  padding_min_mm=float(gaps.min()), padding_max_mm=float(gaps.max()),
                  padding_p05_mm=float(np.percentile(gaps, 5)), padding_p95_mm=float(np.percentile(gaps, 95)),
                  gap_rms_error_mm=float(np.sqrt(np.mean((gaps-target)**2))),
                  baseline_gap_rms_error_same_pose_mm=float(np.sqrt(np.mean((before-target)**2))),
                  edge_strain_min_percent=float(strain.min()), edge_strain_max_percent=float(strain.max()),
                  edge_strain_p95_absolute_percent=float(np.percentile(abs(strain),95)),
                  displacement_max_mm=float(np.linalg.norm(contact_local-rest, axis=1).max()),
                  local_z_change_max_mm=float(abs(contact_local[:,2]-rest[:,2]).max()),
                  metric_limit_percent=4., deformation_scale=alpha, warnings=warning,
                  pressure_predicted=False, mechanical_stiffness_included=False, optics_aligned=False,
                  scope='Probe 05 cushion support only. No adapter, magnets, headband, nose or shell.',
                  validation='Sampled nearest-surface gaps and wall distances; no exhaustive self-intersection or leather model.')
    result = PadResult(Mesh(solid.vertices.copy(), solid.faces.copy(), 'VRcover Probe 05'), world,
                       d['uv'].copy(), faces.copy(), report)
    result.reference_lengths = rest_length
    result.edge_vertices = edges
    result.vertex_strain = vertex_strain
    result.vertex_gap = gaps[:len(world)]
    progress(100, tr('Polsterauflage berechnet.'))
    return result
