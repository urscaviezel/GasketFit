"""Read-only upper-centre depth gauge, in the magnetic base's coordinate frame."""
from dataclasses import dataclass
from functools import lru_cache
import numpy as np
import trimesh
from .profile import transform


@lru_cache(maxsize=1)
def upper_mating_point():
    """Actual upper-centre plastic seating land, just above the magnet pocket.

    The pocket floor and the raised locating lip are not the mating surface.
    Use the verified magnet location to find the narrow flat land between them.
    This lookup is independent of head scans and current workflow positioning.
    """
    from .assembly import base_reference, base_metadata
    seat = max(base_metadata()['magnet_seats'], key=lambda s: s['center'][2])
    rotation = np.asarray(seat['magnet_box_matrix'])[:3, :3]
    extents = np.asarray(seat['magnet_box_extents_mm'])
    # Vertical half-span of the box, plus pocket allowance and 0.25 mm of land.
    z = seat['center'][2] + np.dot(abs(rotation[2]), extents) / 2 + .1 + .25
    base = base_reference()
    mesh = trimesh.Trimesh(base.vertices, base.faces, process=False)
    origin = [0., float(base.vertices[:, 1].min()) - 10., z]
    points, _, triangles = mesh.ray.intersects_location([origin], [[0., 1., 0.]])
    if not len(points):
        raise ValueError('Upper magnetic seating land not found')
    i = int(np.argmin(points[:, 1]))
    if mesh.face_normals[triangles[i], 1] > -.95:
        raise ValueError('Upper reference must lie on the seating land')
    return points[i].copy()


@dataclass(frozen=True)
class DepthMeasurement:
    millimetres: float
    base_point: np.ndarray
    pad_point: np.ndarray
    dimension_points: np.ndarray
    line_segments: np.ndarray
    mode: str = 'axial'


class UpperDepthGauge:
    def __init__(self, surface_faces, base_point=None):
        self.faces = np.asarray(surface_faces)
        self.base_point = np.array(upper_mating_point() if base_point is None else base_point, copy=True)

    def measure(self, vertices, base_matrix):
        """Inner pad-surface intersection straight behind the seating point.

        The ray follows base +Y and retains the anchor's X/Z coordinates.
        The caller supplies only the face/cushion-facing contact surface, not
        the closed support mesh. This selects the adhesive face explicitly,
        without a nominal thickness correction or guessing between ray hits.
        This read-only vectorized ray test needs no fitting or spatial-tree build.
        """
        matrix = np.asarray(base_matrix)
        origin = transform(self.base_point[None, :], matrix)[0]
        direction = matrix[:3, 1]
        triangles = np.asarray(vertices)[self.faces]
        a = triangles[:, 0]
        e1, e2 = triangles[:, 1] - a, triangles[:, 2] - a
        h = np.cross(direction, e2)
        determinant = np.einsum('ij,ij->i', e1, h)
        valid = abs(determinant) > 1e-12
        if not valid.any():
            return None
        a, e1, e2, h = a[valid], e1[valid], e2[valid], h[valid]
        inverse = 1. / determinant[valid]
        offset = origin - a
        u = inverse * np.einsum('ij,ij->i', offset, h)
        q = np.cross(offset, e1)
        v = inverse * (q @ direction)
        distance = inverse * np.einsum('ij,ij->i', e2, q)
        hits = (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (distance >= 0)
        if not hits.any():
            return None
        depth = float(distance[hits].min())
        if not np.isfinite(depth):
            return None
        end = origin + direction * depth
        tick = matrix[:3, 2] * 1.2
        lines = np.array([origin, end, origin - tick, origin + tick, end - tick, end + tick])
        return DepthMeasurement(depth, origin, end, np.array([origin, end]), lines)

    def measure_with_lower_edge_projection(self, vertices, base_matrix, outer_vertices=None):
        """Horizontal depth in the HMD frame, with a vertical witness line.

        When the contact surface is above the axial ray, project the actual
        outer lower edge at the centre plane onto the base anchor's height.
        Height never contributes to the reported depth. The ordinary contact
        surface measurement remains unchanged whenever the ray hits it.
        """
        axial=self.measure(vertices,base_matrix)
        if axial is not None:return axial
        matrix=np.asarray(base_matrix)
        outside=vertices if outer_vertices is None else outer_vertices
        local=transform(np.asarray(outside),np.linalg.inv(matrix))
        mesh=trimesh.Trimesh(local,self.faces,process=False)
        segments=trimesh.intersections.mesh_plane(mesh,[1.,0.,0.],self.base_point)
        if not len(segments):return None
        points=segments.reshape(-1,3)
        # Lowest point of the real outer centre contour, not a closest-point
        # search that could select an arbitrary position farther up the face.
        bottom=points[np.isclose(points[:,2],points[:,2].min(),rtol=0,atol=1e-8)]
        target=bottom[np.argmin(bottom[:,1])]
        if target[2]<=self.base_point[2] or target[1]<self.base_point[1]:return None
        depth=float(target[1]-self.base_point[1])
        projected=np.array([self.base_point[0],target[1],self.base_point[2]])
        origin,finish,edge=transform(np.array([self.base_point,projected,target]),matrix)
        tick=matrix[:3,2]*1.2
        lines=np.array([origin,finish,origin-tick,origin+tick,finish-tick,finish+tick,finish,edge])
        return DepthMeasurement(depth,origin,edge,np.array([origin,finish]),lines,'projected_lower_edge')
