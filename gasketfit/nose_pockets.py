"""Contour fill 01, built from the current shell, pad and nose surfaces.

The exposed nose wall and its rim are the existing boundaries. The new roof
ends on those boundaries; the adhesive face and magnetic interface are also
protected by the assembly's existing guards.
"""
import numpy as np
import trimesh
from scipy.interpolate import RBFInterpolator
from shapely.geometry import LineString, Point, Polygon
from .meshio import Mesh
from .profile import transform
from .localization import tr


def grid_faces(rows, columns):
    cells = (np.arange(rows - 1)[:, None] * columns + np.arange(columns - 1)).ravel()
    return np.vstack([np.c_[cells, cells + columns, cells + columns + 1],
                      np.c_[cells, cells + columns + 1, cells + 1]])


def make_nose_pockets(support, matrix, shell_inside, arch_outer, arch_inside, *, shell_outer):
    """Return a world-space addition. Surface grids are in the base's frame."""
    from .shell import _rear_cap, _segments, _solid_layers
    from .assembly import _manifold

    inv = np.linalg.inv(matrix)
    uv = support.flat
    back = support.mesh.vertices[len(support.contact):]
    field = RBFInterpolator(uv / 50, back, neighbors=60, smoothing=1e-9)
    contact_field = RBFInterpolator(uv / 50, support.contact, neighbors=60, smoothing=1e-9)
    polygon = Polygon(uv[:420])
    pad_query = trimesh.proximity.ProximityQuery(
        trimesh.Trimesh(back, support.surface_faces, process=False))
    extra_columns = arch_inside.shape[1] - shell_inside.shape[1]

    def extend(row, outer=False):
        side = shell_inside[row]
        near, _, tri = pad_query.on_surface(transform(side[-1:], matrix))
        bary = trimesh.triangles.points_to_barycentric(back[support.surface_faces[tri]], near)
        q0 = (uv[support.surface_faces[tri]] * bary[:, :, None]).sum(1)[0]
        pieces = _segments(polygon.intersection(LineString([[q0[0], 0], [q0[0], 75]])))
        if not pieces:
            raise ValueError(tr('Die Nasentaschen finden keinen Anschluss an der Auflage.'))
        segment = min(pieces, key=lambda p: p.distance(Point(q0)))
        coords = np.asarray(segment.coords)
        q1 = coords[np.argmax(coords[:, 1])].copy()
        q1[1] -= .015
        t = np.linspace(0, 1, extra_columns + 1)[:, None]
        if outer:
            side = shell_outer[row]
        strip = transform((contact_field if outer else field)(
            (q0 * (1 - t) + q1 * t) / 50), inv)
        strip[0] = side[-1]
        return np.vstack([side, strip[1:]])

    # Start with the approved 50-row side transition. For narrower heads extend
    # it until the spatial fade is zero, so no cropped step appears at the end.
    left = [extend(i) for i in range(len(shell_inside) - 51, len(shell_inside) - 1)]
    right = [extend(i) for i in range(1, 51)]
    for rows, index, step in ((left, len(shell_inside) - 52, -1), (right, 51, 1)):
        while np.min(abs(rows[0 if step < 0 else -1][:, 0])) < 63.3:
            if not 0 < index < len(shell_inside) - 1 or len(rows) >= 100:
                raise ValueError(tr('Die Nasentaschen finden keinen glatten Auslauf an der Hülle.'))
            row = extend(index)
            if step < 0:
                rows.insert(0, row)
            else:
                rows.append(row)
            index += step
    floor = np.concatenate([np.asarray(left), arch_inside, np.asarray(right)])
    cv, cf, footprint, chart = _rear_cap()
    query = trimesh.proximity.ProximityQuery(chart)
    front = []
    for row in floor:
        x = row[0, 0]
        pieces = _segments(footprint.intersection(LineString([[x, 0], [x, 74]])))
        if not pieces:
            raise ValueError(tr('Die Nasentaschen finden keinen Anschluss an der Basis.'))
        segment = min(pieces, key=lambda p: p.distance(Point([x, row[0, 2]])))
        z = np.max(np.asarray(segment.coords)[:, 1]) - .025
        near, distance, tri = query.on_surface([[x, 0, z]])
        if distance[0] >= 1e-5:
            raise ValueError(tr('Die Nasentaschen finden keinen Anschluss an der Basis.'))
        bary = trimesh.triangles.points_to_barycentric(chart.triangles[tri], near)
        p = (cv[cf[tri]] * bary[:, :, None]).sum(1)[0]
        p[1] -= .04
        front.append(p)
    front = np.asarray(front)
    t = np.linspace(0, 1, floor.shape[1])[None, :, None]
    roof = front[:, None, :] * (1 - t) + floor[:, -1:, :] * t
    fade = np.clip((abs(floor[:, :, 0]) - 44.) / 20., 0, 1)
    weight = 1 - (10 * fade**3 - 15 * fade**4 + 6 * fade**5)
    weight[0] = weight[-1] = 0
    roof = floor + (roof - floor) * weight[:, :, None]
    roof[:, -1] = floor[:, -1]
    outer_floor = np.concatenate([
        [extend(i, True) for i in range(len(shell_inside) - len(left) - 1,
                                       len(shell_inside) - 1)],
        arch_outer, [extend(i, True) for i in range(1, len(right) + 1)]])
    # The normal-offset inner skin can fold at the shell/pad corner when their
    # relative pitch increases. Using that skin as the bottom of a fill makes
    # a self-intersecting solid: a Boolean union can then SUBTRACT its negative
    # winding from the arch's pad attachment. Bury the fill bottom inside the
    # existing wall instead (one quarter of the way from outer to inner skin).
    # The roof, opening guard and zero-thickness side fade stay unchanged.
    bottom = floor + .75 * (outer_floor - floor) * weight[:, :, None]
    bottom[:, -1] = floor[:, -1]
    if (roof[:, :, 2] - floor[:, :, 2]).min() < -1e-6:
        raise ValueError(tr('Die Nasentaschen überschneiden bei dieser Position die Hülle. Bitte Basisposition prüfen.'))
    profile_z = float(cv[(abs(cv[:, 0]) < .6) & (cv[:, 2] < 75), 2].max())
    # The adapter crest bounds the nose span. Existing pad corners farther
    # sideways can be higher; they are unchanged boundaries, not a protrusion
    # introduced by filling the nose pockets.
    nose_roof = roof[len(left):len(left) + len(arch_inside)]
    if nose_roof[:, :, 2].max() > profile_z + 1e-6:
        raise ValueError(tr('Die Nasentaschen ragen über das Adapterprofil hinaus. Bitte Basisposition prüfen.'))
    boundary_ceiling = np.maximum(front[:, 2], floor[:, :, 2].max(axis=1))
    if (roof[:, :, 2] - boundary_ceiling[:, None]).max() > 1e-6:
        raise ValueError(tr('Die Nasentaschen ragen über das Adapterprofil hinaus. Bitte Basisposition prüfen.'))

    raw = _solid_layers(bottom.reshape(-1, 3), roof.reshape(-1, 3),
                        grid_faces(*floor.shape[:2]))
    # Coincident roof/floor edges collapse exactly. Tolerance-based vertex
    # merging here can delete tiny valid triangles and leave holes.
    vertices, indices = np.unique(raw.vertices, axis=0, return_inverse=True)
    faces = indices[raw.faces]
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) &
                  (faces[:, 0] != faces[:, 2])]
    _, inverse, counts = np.unique(np.sort(faces, axis=1), axis=0,
                                    return_inverse=True, return_counts=True)
    faces = faces[counts[inverse] == 1]
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    mesh.remove_unreferenced_vertices()
    if not mesh.is_volume or not (mesh.area_faces > 0).all():
        raise ValueError(tr('Die Nasentaschen konnten nicht als geschlossener Körper berechnet werden.'))

    curtain = arch_outer[:, shell_inside.shape[1] - 1:]
    guard = _solid_layers(curtain.reshape(-1, 3),
                          (curtain + [0, 100, 0]).reshape(-1, 3),
                          grid_faces(*curtain.shape[:2]))
    bounded = _manifold(Mesh(mesh.vertices, mesh.faces, 'Contour pockets')) - _manifold(guard)
    result = bounded.to_mesh64()
    return Mesh(transform(result.vert_properties[:, :3], matrix), result.tri_verts,
                'Contour pockets'), dict(nose_pockets_filled=True,
                nose_pocket_design='Contour fill 02 - embedded floor', nose_pocket_volume_mm3=float(bounded.volume()),
                nose_pocket_maximum_z=float(nose_roof[:, :, 2].max()),
                nose_pocket_side_boundary_excess_mm=float(np.maximum(
                    roof[:, :, 2] - boundary_ceiling[:, None], 0).max()))
