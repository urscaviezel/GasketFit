"""Optional forehead-mounted loop, following the fitted support pose."""
from .localization import tr
import numpy as np
import trimesh
import manifold3d as mf
from scipy.interpolate import RegularGridInterpolator
from .meshio import Mesh
from .profile import pose_matrix, transform
from .top_strap import WIDTH, GAP, BAR_RADIUS, EAR_WIDTH, _mesh


def make_forehead_strap(support, base_matrix):
    # Work in support coordinates: independent X/Z tilt must carry the loop.
    matrix = pose_matrix(support.report['parameters']['pose'])
    inverse = np.linalg.inv(matrix)
    n = len(support.contact)
    backing = trimesh.Trimesh(transform(support.mesh.vertices[n:], inverse),
                              support.surface_faces, process=False)
    tri = backing.triangles
    central = (tri[:, :, 0].min(1) < WIDTH/2+EAR_WIDTH) & (tri[:, :, 0].max(1) > -WIDTH/2-EAR_WIDTH)
    roof = float(tri[central, :, 2].max())
    # Sample the fitted backing across the whole loop, not one planar foot.
    # Continue its upper curvature through the crossbar and both cheeks.
    xs=np.linspace(-WIDTH/2-EAR_WIDTH,WIDTH/2+EAR_WIDTH,91)
    bottom=roof-24.
    zs=np.linspace(bottom-1.,roof-1.,97)
    xx,zz=np.meshgrid(xs,zs,indexing='ij')
    origins=np.c_[xx.ravel(),np.full(xx.size,-300.),zz.ravel()]
    hits,rays,_=backing.ray.intersects_location(origins,np.tile([0.,1.,0.],(len(origins),1)))
    if len(np.unique(rays))!=len(origins):
        raise ValueError(tr('Die Kopfbandhalterung findet keinen Anschluss an der Stirnauflage.'))
    depths=np.empty(len(origins));depths[rays]=hits[:,1]
    surface=RegularGridInterpolator((xs,zs),depths.reshape(xx.shape))
    def curved(solid,foot=False):
        data=solid.refine_to_length(.4).to_mesh64()
        vertices=np.asarray(data.vert_properties)[:,:3].copy()
        x=np.clip(vertices[:,0],xs[0],xs[-1]);z=vertices[:,2]
        backing_y=surface(np.c_[x,np.clip(z,zs[0],zs[-1])])
        if foot:
            # Extend the crown's front directly to the lower attachment.
            # Only the final four mm ease into the actual fitted surface.
            low=surface(np.c_[x,np.full(len(x),bottom)])
            top=surface(np.c_[x,np.full(len(x),roof-1.)])-5.5
            t=np.clip((z-bottom)/(axis_z-bottom),0.,1.)
            line=low+(top-low)*t
            depth=np.maximum(0.,backing_y-line)
            blend=np.clip((z-bottom)/4.,0.,1.)
            depth*=blend*(2.-blend)
            u=np.clip((z-(roof-2.))/(axis_z-(roof-2.)),0.,1.)
            rear=.65-1.15*u*u*(3.-2*u)
            weight=np.clip((rear-vertices[:,1])/(rear+5.5),0.,1.)
            vertices[:,1]+=weight*(5.5-depth)
        vertices[:,1]+=backing_y
        from .assembly import _manifold
        return _manifold(Mesh(vertices,np.asarray(data.tri_verts),'Curved strap'))
    axis_y = -3.
    floor = roof+.2
    axis_z = floor+GAP+BAR_RADIUS
    ears = []
    # The nominal front is straight. The fitted mapping above keeps it straight
    # in support coordinates instead of following every bend of the backing.
    front=np.array([[-5.5,bottom],[-5.5,roof-2.]])
    back_z=np.linspace(roof-2.,axis_z,40)
    u=(back_z-back_z[0])/(back_z[-1]-back_z[0])
    back_y=.65-1.15*u*u*(3.-2*u)
    crown_angle=np.linspace(np.pi,0,65)
    crown=np.c_[axis_y+2.5*np.cos(crown_angle),axis_z+2.5*np.sin(crown_angle)]
    profile=np.vstack([front,[[-5.5,axis_z]],crown[1:],np.c_[back_y,back_z][::-1][1:],[[.65,bottom]]])
    for sign in (-1, 1):
        x = sign*(WIDTH/2+EAR_WIDTH/2)
        ears.append(curved(mf.CrossSection([profile[::-1]]).extrude(EAR_WIDTH).transform([
            [0, 0, 1, x-EAR_WIDTH/2], [1, 0, 0, 0], [0, 1, 0, 0]]),foot=True))
    bar = mf.Manifold.cylinder(WIDTH+EAR_WIDTH, BAR_RADIUS, circular_segments=96).transform([
        [0, 0, 1, -(WIDTH+EAR_WIDTH)/2], [1, 0, 0, axis_y], [0, 1, 0, axis_z]])
    bar=curved(bar)
    loop = mf.Manifold.batch_boolean([bar]+ears, mf.OpType.Add)
    clearance = mf.Manifold.cube([WIDTH-.002, 2*BAR_RADIUS+.6, GAP-.002]).translate([
        -WIDTH/2+.001, axis_y-BAR_RADIUS-.3, floor+.001])
    clearance=curved(clearance)
    local = np.linalg.inv(base_matrix) @ matrix
    report = dict(top_strap_enabled=True, top_strap_width_mm=WIDTH, top_strap_gap_mm=GAP,
                  top_strap_bar_diameter_mm=2*BAR_RADIUS, top_strap_mount='forehead_front_upper_edge',
                  top_strap_follows_backing=True,top_strap_blend_height_mm=4.,
                  top_strap_foot_drop_mm=24.,top_strap_straight_front=True)
    return (_mesh(loop, local, 'Stirn-Kopfbandhalterung'),
            _mesh(clearance, local, 'Kopfbanddurchlass'),
            [_mesh(ear, local, 'Kopfbandfuß') for ear in ears], report)
