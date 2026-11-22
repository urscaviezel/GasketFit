"""Additive 37 x 4 mm top-strap loop, braced to the cushion backing."""
import numpy as np
import trimesh
import manifold3d as mf
from shapely.geometry import MultiPoint
from shapely.geometry.polygon import orient
from .meshio import Mesh
from .profile import transform
from .localization import tr

WIDTH = 37.
GAP = 4.
BAR_RADIUS = 2.
EAR_WIDTH = 4.


def _mesh(solid, matrix, name):
    data = solid.to_mesh64()
    return Mesh(transform(data.vert_properties[:, :3], matrix), data.tri_verts, name)


def make_top_strap(base, shell, matrix, support):
    """Return loop, threading clearance, bar and two roots in world coordinates.

    The bar is outside the shell. Its height follows the actual upper shell,
    rather than burying a fixed-height strap hole in a tilted/short assembly.
    The complete magnetic interface is protected by the caller's usual guards.
    """
    from .assembly import _front_guard
    from .shell import _rear_cap
    inverse = np.linalg.inv(matrix)
    local = trimesh.util.concatenate([
        trimesh.Trimesh(transform(m.vertices, inverse), m.faces, process=False)
        for m in (base, shell)])
    n = len(support.contact)
    backing = trimesh.Trimesh(transform(support.mesh.vertices[n:], inverse),
                              support.surface_faces, process=False)
    guard = _front_guard()
    guarded = trimesh.Trimesh(guard.vertices, guard.faces, process=False)
    xs = np.linspace(-WIDTH/2-EAR_WIDTH, WIDTH/2+EAR_WIDTH, 51)
    origins = np.c_[xs, np.full(len(xs), 100.), np.full(len(xs), 125.)]
    hits, _, _ = guarded.ray.intersects_location(origins, np.tile([0., -1., 0.], (len(xs), 1)))
    if not len(hits):
        raise ValueError(tr('Die Kopfbandhalterung findet keinen geschützten Platz hinter der Basis.'))
    axis_y = float(hits[:, 1].max()) + BAR_RADIUS + .7
    triangles = local.triangles
    lo, hi = triangles.min(1), triangles.max(1)
    # Triangle bounds conservatively include the complete threading corridor,
    # even between samples. No shell or pad surface is cut to make this gap.
    region = ((lo[:, 0] < WIDTH/2) & (hi[:, 0] > -WIDTH/2) &
              (lo[:, 1] < axis_y+BAR_RADIUS+.3) & (hi[:, 1] > axis_y-BAR_RADIUS-.3) &
              (hi[:, 2] > 100.))
    if not region.any():
        raise ValueError(tr('Die Kopfbandhalterung findet keinen Anschluss an der oberen Hülle.'))
    floor_z = float(hi[region, 2].max()) + .2
    axis_z = floor_z + GAP + BAR_RADIUS
    cap_vertices, _, _, _ = _rear_cap()
    ears = []
    for sign in (-1, 1):
        x = sign * (WIDTH/2 + EAR_WIDTH/2)
        anchor = cap_vertices[(abs(cap_vertices[:, 0]-x) < EAR_WIDTH/2) &
                              (cap_vertices[:, 2] > 109.)]
        if len(anchor) < 3:
            raise ValueError(tr('Die Kopfbandhalterung findet keinen Anschluss an der Basis.'))
        roots = anchor[:, 1:].copy()
        roots[:, 0] -= .7
        rear_y = axis_y + 4.5
        points, _, _ = local.ray.intersects_location([[x, rear_y, 180.]], [[0., 0., -1.]])
        if not len(points):
            raise ValueError(tr('Die Kopfbandhalterung findet keinen Anschluss an der oberen Hülle.'))
        rear_z = float(points[:, 2].max())
        theta = np.linspace(0, 2*np.pi, 97)[:-1]
        round_top = np.c_[axis_y+3.*np.cos(theta), axis_z+3.*np.sin(theta)]
        # Continue each side cheek to a six-mm-high foot on the actual cushion
        # backing. Sampling across its full width accounts for pad tilt/curvature.
        # These gussets are outside the 37-mm passage, not a plate behind the bar.
        sample_x = np.linspace(x-EAR_WIDTH/2, x+EAR_WIDTH/2, 9)
        tri = backing.triangles
        roof = []
        for sx in sample_x:
            cross = (tri[:, :, 0].min(1) <= sx) & (tri[:, :, 0].max(1) >= sx)
            if not cross.any():
                raise ValueError(tr('Die Kopfbandhalterung findet keinen Anschluss an der Auflagenrückseite.'))
            roof.append(tri[cross, :, 2].max())
        pad_top = min(axis_z+2., min(roof)-2.)
        pad_points = []
        for z in (pad_top-6., pad_top):
            starts = np.c_[sample_x, np.full(len(sample_x), -100.), np.full(len(sample_x), z)]
            hit, rays, _ = backing.ray.intersects_location(starts, np.tile([0., 1., 0.], (len(starts), 1)))
            if len(np.unique(rays)) != len(starts):
                raise ValueError(tr('Die Kopfbandhalterung findet keinen Anschluss an der Auflagenrückseite.'))
            # Embed the foot within the pad; the caller trims its far side with
            # the unchanged adhesive-surface guard and checks both attachments.
            pad_points.extend(np.c_[hit[:, 1]+.75, hit[:, 2]])
        # One continuous profile joins collar, shell and rear foot, without
        # separate connection patches. Its rounded crown encloses the 4-mm bar.
        rear_root = [[rear_y-2., rear_z-.9], [rear_y, rear_z-.9],
                     [rear_y, rear_z+.2]]
        profile = np.asarray(orient(MultiPoint(np.vstack([roots, round_top, rear_root, pad_points])).convex_hull,
                                    sign=1.).exterior.coords)[:-1]
        ear = mf.CrossSection([profile]).extrude(EAR_WIDTH).transform([
            [0., 0., 1., x-EAR_WIDTH/2], [1., 0., 0., 0.], [0., 1., 0., 0.]])
        ears.append(ear)
    # Ends extend 2 mm into each ear. The free span BETWEEN inner ear faces is 37.
    bar = mf.Manifold.cylinder(WIDTH+EAR_WIDTH, BAR_RADIUS, circular_segments=96).transform([
        [0., 0., 1., -(WIDTH+EAR_WIDTH)/2], [1., 0., 0., axis_y], [0., 1., 0., axis_z]])
    loop = mf.Manifold.batch_boolean([bar]+ears, mf.OpType.Add)
    clearance = mf.Manifold.cube([WIDTH-.002, 2*BAR_RADIUS+.6, GAP-.002]).translate([
        -WIDTH/2+.001, axis_y-BAR_RADIUS-.3, floor_z+.001])
    report = dict(top_strap_enabled=True, top_strap_width_mm=WIDTH,
                  top_strap_gap_mm=GAP, top_strap_bar_diameter_mm=2*BAR_RADIUS,
                  top_strap_ear_width_mm=EAR_WIDTH,
                  top_strap_bar_axis_base_local=[0., axis_y, axis_z])
    return (_mesh(loop, matrix, '37 mm top-strap loop'),
            _mesh(clearance, matrix, '37 x 4 mm threading clearance'),
            _mesh(bar, matrix, 'Top-strap bar'),
            [_mesh(ear, matrix, 'Top-strap root') for ear in ears], report)
