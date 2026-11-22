"""Stitch a continuous connector into the forehead carrier's original skin.

The adhesive surface is retained exactly. Only the lower backing is
replaced, sharing the original cut vertices instead of overlapping solids.
"""
from .localization import tr
import numpy as np
import trimesh
from scipy.interpolate import LinearNDInterpolator
from shapely.geometry import Polygon
import shapely


def stitched_carrier(support, contact, backing, outer_roots, inner_roots, *, cylindrical_frame=None):
    if cylindrical_frame is not None:
        return cylindrical_carrier(support, contact, backing, outer_roots, inner_roots, cylindrical_frame)
    uv = support.flat
    n = len(uv)
    cut = float(uv[:, 1].min() + .70 * np.ptp(uv[:, 1]))
    vertices = list(np.vstack([contact, backing]))
    coordinates = list(np.vstack([uv, uv]))
    faces, intersections = [], {}

    def intersection(a, b):
        key = tuple(sorted((a, b)))
        if key not in intersections:
            za, zb = coordinates[a][1], coordinates[b][1]
            if abs(za-cut) < 1e-10:
                return a
            if abs(zb-cut) < 1e-10:
                return b
            t = (cut-za)/(zb-za)
            intersections[key] = len(vertices)
            vertices.append((1-t)*vertices[a] + t*vertices[b])
            coordinates.append((1-t)*coordinates[a] + t*coordinates[b])
        return intersections[key]

    def clip(face, sign):
        polygon = []
        for a, b in zip(face, np.roll(face, -1)):
            ina = sign*(coordinates[a][1]-cut) >= -1e-10
            inb = sign*(coordinates[b][1]-cut) >= -1e-10
            if ina:
                polygon.append(a)
            if ina != inb:
                polygon.append(intersection(a, b))
        polygon = list(dict.fromkeys(polygon))
        for i in range(1, len(polygon)-1):
            faces.append([polygon[0], polygon[i], polygon[i+1]])

    for face in support.mesh.faces:
        clip(face, 1)
        if not np.all(face >= n):
            # Retain contact and perimeter walls, splitting at the same cut.
            clip(face, -1)

    # Subdivide open boundary edges before lofting; the corresponding retained
    # triangles share every new vertex, including the narrow side-wall cuts.
    def boundary_edges(fs):
        edges = np.concatenate([np.asarray(fs)[:, [0, 1]],
                                np.asarray(fs)[:, [1, 2]],
                                np.asarray(fs)[:, [2, 0]]])
        _, inv, counts = np.unique(np.sort(edges, axis=1), axis=0,
                                   return_inverse=True, return_counts=True)
        return edges[counts[inv] == 1]

    splits = {}
    for a, b in boundary_edges(faces):
        steps = max(1, int(np.ceil(np.linalg.norm(vertices[b]-vertices[a])/.75)))
        ids = [int(a)]
        for t in np.linspace(0, 1, steps+1)[1:-1]:
            ids.append(len(vertices))
            vertices.append((1-t)*vertices[a] + t*vertices[b])
            coordinates.append((1-t)*coordinates[a] + t*coordinates[b])
        ids.append(int(b))
        splits[(a, b)] = ids
        splits[(b, a)] = ids[::-1]
    refined = []
    for face in faces:
        polygon = []
        for a, b in zip(face, np.roll(face, -1)):
            polygon.extend(splits.get((a, b), [a, b])[:-1])
        if len(polygon) == 3:
            refined.append(face)
        else:
            centre = len(vertices)
            vertices.append(np.asarray(vertices)[face].mean(0))
            coordinates.append(np.asarray(coordinates)[face].mean(0))
            refined.extend([[centre, a, b] for a, b in zip(polygon, polygon[1:]+polygon[:1])])
    faces = refined
    edges = boundary_edges(faces)
    following = {int(a): int(b) for a, b in edges}
    if len(following) != len(edges):
        raise ValueError(tr('Die Anschlusskontur ist nicht eindeutig geschlossen.'))
    loop = [int(edges[0, 0])]
    while following[loop[-1]] != loop[0]:
        loop.append(following[loop[-1]])
        if len(loop) > len(edges):
            raise ValueError(tr('Die Anschlusskontur hat mehrere offene Ränder.'))
    if len(loop) != len(edges):
        raise ValueError(tr('Die Anschlusskontur hat mehrere offene Ränder.'))
    coordinates = np.asarray(coordinates)
    positions = {v: i for i, v in enumerate(loop)}

    # Retain the full contact surface and original perimeter wall. Only the
    # lower backing patch is replaced. Both loft boundaries therefore meet
    # the very same backing skin, without wrapping around the adhesive edge.
    ids = [v for v in loop if coordinates[v, 1] <= uv[:, 1].min() + .02*np.ptp(uv[:, 1])]
    left, right = min(ids, key=lambda v: coordinates[v, 0]), max(ids, key=lambda v: coordinates[v, 0])
    ia, ib = positions[left], positions[right]
    paths = ([loop[(ia+j) % len(loop)] for j in range((ib-ia) % len(loop)+1)],
             [loop[(ia-j) % len(loop)] for j in range((ia-ib) % len(loop)+1)])
    back_path = max(paths, key=lambda ids: np.max(coordinates[ids, 1]))
    lower_path = paths[1] if back_path is paths[0] else paths[0]
    interpolation = LinearNDInterpolator(uv, backing)
    targets, roots, tangents, reaches = [], [], [], []
    for ids, curve, upper in ((back_path, outer_roots, True), (lower_path[::-1], inner_roots[::-1], False)):
        points = coordinates[ids]
        distance = np.r_[0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
        for j, (v, t) in enumerate(zip(ids, distance / distance[-1])):
            targets.append(v)
            roots.append(np.array([np.interp(t, np.linspace(0, 1, len(curve)), curve[:, k]) for k in range(3)]))
            along = points[min(j+1, len(points)-1)] - points[max(j-1, 0)]
            direction = np.array([-along[1], along[0]])
            direction /= np.linalg.norm(direction)
            simplex = interpolation.tri.find_simplex(coordinates[v], tol=1e-8)
            if simplex < 0:
                raise ValueError(tr("Die Anschlussstelle liegt ausserhalb der Stirnkontur."))
            tri = interpolation.tri.simplices[simplex]
            gradient = np.linalg.solve(np.c_[uv[tri], np.ones(3)], interpolation.values[tri])[:2]
            tangent = direction @ gradient
            tangents.append(tangent / np.linalg.norm(tangent))
            # Fade the top tangent at the rounded ends; never send a control
            # point beyond the retained perimeter, which causes folded lips.
            reaches.append((10. * np.clip((coordinates[v, 1]-(cut-12))/12, 0, 1)**2 if upper else 0.) * np.sin(np.pi*t)**.5)
    loop = targets
    nt = 51
    strips = []
    for index, v in enumerate(loop):
        a, end = roots[index], vertices[v]
        c1 = a + [0, max(4., (end[1]-a[1])*.35), 0]
        c2 = end - tangents[index]*min(reaches[index], np.linalg.norm(end-a)*.4)
        ids = []
        for t in np.linspace(0, 1, nt)[:-1]:
            ids.append(len(vertices))
            vertices.append((1-t)**3*a+3*(1-t)**2*t*c1+3*(1-t)*t*t*c2+t**3*end)
        ids.append(v)
        strips.append(ids)
    for i in range(len(loop)):
        a, b = strips[i], strips[(i+1) % len(loop)]
        for j in range(nt-1):
            faces.extend([[a[j], a[j+1], b[j]], [b[j], a[j+1], b[j+1]]])

    faces = [f for f in faces if len(set(f)) == 3]
    root_ids = [strip[0] for strip in strips]
    root_points = np.asarray(vertices)[root_ids][:, [0, 2]]
    polygon = Polygon(root_points)
    if not polygon.is_valid:
        raise ValueError(tr('Der Anschluss an die Magnetbasis überschneidet sich.'))
    lookup = {tuple(np.round(p, 8)): v for p, v in zip(root_points, root_ids)}
    for triangle in shapely.constrained_delaunay_triangles(polygon).geoms:
        faces.append([lookup[tuple(np.round(p, 8))] for p in list(triangle.exterior.coords)[:3]])
    mesh = trimesh.Trimesh(vertices, faces, process=True)
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    if not mesh.is_volume:
        raise ValueError(tr('Der gemeinsame Stirnträger ist nicht vollständig geschlossen.'))
    return mesh, dict(shared_seam_vertices=len(set(loop)), backing_cut_height_mm=cut,
                      connection_construction='stitched_original_skin')



def cylindrical_carrier(support, contact, backing, outer_roots, inner_roots, frame_info):
    """Positive-volume loft for an analytic, cylindrical no-scan support.

    Adjacent upper/lower tracks share the same unwrapped width coordinate.
    Small convex cells are united rather than feeding a self-intersecting
    boundary to the Boolean engine. The original adhesive skin is retained.
    """
    import manifold3d as mf
    from .profile import transform
    from .assembly import _manifold
    from .meshio import Mesh
    from shapely.geometry import LineString
    # Fair the longitudinal depth before constructing the broad surface.
    # The protected interface is subtracted later; its local depth steps must
    # not become control points for the visible connector surface.
    rim_curves=(outer_roots.copy(),inner_roots.copy())
    curves=[]
    for curve in rim_curves:
        curve=curve.copy()
        x=curve[:,0]/70.
        basis=np.c_[np.ones(len(x)),x*x,x**4]
        fair=basis@np.linalg.lstsq(basis,curve[:,1],rcond=None)[0]
        # Virtual guide stays behind every actual rim point. Blending into it
        # then always advances away from the base, without a return fold.
        curve[:,1]=fair+np.max(curve[:,1]-fair)+.1
        curves.append(curve)
    outer_roots,inner_roots=curves
    radius, frame = frame_info
    inverse = np.linalg.inv(frame)
    uv = support.flat
    cut = float(uv[:, 1].min()+.70*np.ptp(uv[:, 1]))
    edges=np.concatenate([support.surface_faces[:,[0,1]],support.surface_faces[:,[1,2]],support.surface_faces[:,[2,0]]])
    _,inv,counts=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
    boundary=edges[counts[inv]==1]
    following={int(a):int(b) for a,b in boundary}
    loop=[int(boundary[0,0])]
    while following[loop[-1]]!=loop[0]:
        loop.append(following[loop[-1]])
    outline = Polygon(uv[loop])
    # Read the actual triangulated backing, not a fresh approximation of the
    # preset. This preserves the existing rim vertices and the cushion fit.
    sample = LinearNDInterpolator(uv, backing)
    def unwrap(points):
        q = transform(np.asarray(points), inverse)
        return np.c_[radius*np.arctan2(q[:, 0], 10.5+radius-q[:, 1]),
                     np.hypot(q[:, 0],10.5+radius-q[:, 1]),q[:, 2]]
    def wrap(points):
        a = points[:, 0]/radius
        return transform(np.c_[points[:, 1]*np.sin(a),10.5+radius-points[:, 1]*np.cos(a),points[:, 2]],frame)
    us = np.linspace(uv[:,0].min()+.001,uv[:,0].max()-.001,193)
    tracks=[]
    ts=np.linspace(0,1,49)[:,None]
    for i,u in enumerate(us):
        section=outline.intersection(LineString([(u,uv[:,1].min()-1),(u,cut)]))
        zs=np.asarray(section.coords)[:,1]
        ends=np.asarray(sample([[u,zs.max()],[u,zs.min()+min(3.,.25*(zs.max()-zs.min()))]]))
        t=i/(len(us)-1)
        roots=np.array([[np.interp(t,np.linspace(0,1,len(curve)),curve[:,k]) for k in range(3)] for curve in (outer_roots,inner_roots)])
        a,b=unwrap(roots),unwrap(ends)
        # Keep the lower closure inside the backing. A nearly tangent lower
        # closure leaves a thin folded lip where it crosses the rounded rim.
        # The adhesive surface is 2.5 mm inward, so this remains inside the
        # carrier thickness rather than reaching the cushion face.
        b[:,1]-=.025
        b[1,1]-=1.0
        ends=wrap(b)
        pair=[]
        for j in range(2):
            # Leave the actual base rim in its depth direction: a diagonal
            # first control point amplified variations in rim depth as waves.
            c1=unwrap([roots[j]+[0,max(4.,(ends[j,1]-roots[j,1])*.35),0]])[0]
            c2=b[j].copy()
            # The upper track approaches along the backing height; fade towards
            # the capsule ends, where both tracks converge to a single edge.
            if j==0:
                reach=min(10.,max(0.,zs.max()-zs.min())*.3)*np.sin(np.pi*t)**2
                c2[2]-=reach
            c1[1]=max(c1[1],radius+2.5)
            c2[1]=b[j,1]
            if j==1:
                # Turn the hidden underside into the carrier early; do not
                # skim the outside cylinder all the way to the side tip.
                c1[1]=radius+1.5
                c1[2]=b[j,2]
            q=(1-ts)**3*a[j]+3*(1-ts)**2*ts*c1+3*(1-ts)*ts**2*c2+ts**3*b[j]
            points=wrap(q)
            actual=np.array([np.interp(t,np.linspace(0,1,len(rim_curves[j])),rim_curves[j][:,k]) for k in range(3)])
            fade=np.clip(ts/.35,0,1)
            fade=1-fade*fade*(3-2*fade)
            points+=fade*(actual-roots[j])
            points[0]=actual;points[-1]=ends[j]
            pair.append(points)
        tracks.append(pair)
    tracks=np.asarray(tracks)
    cells=[]
    for i in range(len(us)-1):
        for j in range(len(ts)-1):
            points=tracks[i:i+2,:,j:j+2,:].reshape(-1,3)
            cell=mf.Manifold.hull_points(points)
            if cell.volume()>1e-10:cells.append(cell)
    # A slight overlap at the backing avoids a merely tangent Boolean join.
    original=_manifold(Mesh(np.vstack([contact,backing]),support.mesh.faces,'support'))
    joined=mf.Manifold.batch_boolean(cells+[original],mf.OpType.Add)
    joined=joined.simplify(1e-5)
    data=joined.to_mesh64()
    mesh=trimesh.Trimesh(np.asarray(data.vert_properties)[:,:3],np.asarray(data.tri_verts),process=False)
    return mesh,dict(shared_seam_vertices=0,backing_cut_height_mm=cut,
                     connection_construction='cylindrical_positive_cells')

