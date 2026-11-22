"""Approved Neustart 06: thin, bounded nose arch between rectangular pad ends.

All inputs are the current workflow geometry, in world coordinates. No draft
meshes, user scans or cached placements are used here.
"""
import numpy as np
import trimesh
from scipy.interpolate import RBFInterpolator
from shapely.geometry import LineString
from .profile import transform
from .localization import tr


def make_nose_bridge(support, matrix, outer_surface, inner_surface, *, fill_pockets=False):
    from . import shell as sh
    from .assembly import base_reference
    inv = np.linalg.inv(matrix)
    mat = matrix
    surface = transform(outer_surface.reshape(-1, 3), inv).reshape(outer_surface.shape)
    n=len(support.contact);uv=support.flat;back=support.mesh.vertices[n:];field=RBFInterpolator(uv/50,back,neighbors=60,smoothing=1e-9);nf=RBFInterpolator(uv/50,back-support.contact,neighbors=60,smoothing=1e-9)
    boundary=uv[:420];following=np.roll(boundary,-1,axis=0);terminal=(abs(following[:,0]-boundary[:,0])<1e-7)&(abs(following[:,1]-boundary[:,1])>1)&(abs(boundary[:,0])<50)&(np.maximum(boundary[:,1],following[:,1])<55)
    def mapped(q,contact=False):
        values = field(q/50)
        if contact: values -= nf(q/50)
        return transform(values,inv)
    sides=[];tangents=[];inner_sides=[]
    old_inside=transform(inner_surface.reshape(-1,3),inv).reshape(inner_surface.shape)
    for row,neighbor,sign in [(-1,-2,-1),(0,1,1)]:
        seam=surface[row]+.05*(surface[neighbor]-surface[row])
        inner_seam=old_inside[row]+.05*(old_inside[neighbor]-old_inside[row])
        ids=np.flatnonzero(terminal&(np.sign(boundary[:,0])==sign))
        if not len(ids): raise ValueError(tr('Bitte zuerst die Polsterauflage mit rechteckigen Enden neu berechnen.'))
        points=np.vstack([boundary[ids],following[ids]])
        low=points[np.argmin(points[:,1])];high=points[np.argmax(points[:,1])]
        # The entire rectangular end face joins the new wall, including both skins.
        # Only 0.03 mm of overlap lies inside the existing pad.
        q=np.c_[np.full(65,low[0]+sign*.03),np.linspace(low[1]+.03,high[1]-.015,65)]
        edge=mapped(q,True);edge_inner=mapped(q)
        # First connecting section is buried in the pad; the exposed end face is exact.
        edge=np.vstack([seam[-1],edge]);edge_inner=np.vstack([inner_seam[-1],edge_inner])
        across=mapped(q+[sign*.15,0],True);end_der=(across-mapped(q,True))/(across[:,0]-mapped(q,True)[:,0])[:,None]
        old_der=(surface[neighbor]-seam)/(surface[neighbor,:,0]-seam[:,0])[:,None]
        sides.append(np.vstack([seam,edge[1:]]));tangents.append(np.vstack([old_der,end_der]))
        inner_sides.append(np.vstack([inner_seam,edge_inner[1:]]))
    left,right=sides;dl,dr=tangents;N=241;M=len(left);q=np.linspace(-1,1,N)
    if left[-1,0]>=-5 or right[-1,0]<=5:
        raise ValueError(tr('Der Nasenbogen findet die Auflagenenden nicht beidseits der Adaptermitte.'))
    cv,cf,footprint,chart=sh._rear_cap();querycap=trimesh.proximity.ProximityQuery(chart)
    central=cv[(abs(cv[:,0])<.6)&(cv[:,2]<75)];peak=float(central[:,2].max())-.18
    # Front edge lies on the actual outside edge of the existing rear collar.
    xf=np.linspace(left[0,0],right[0,0],N);front=[]
    for x in xf:
     segments=sh._segments(footprint.intersection(LineString([[x,0],[x,74]])))
     if not segments: raise ValueError(tr('Der Nasenbogen findet keinen Anschluss an der Basis.'))
     segment=max(segments,key=lambda v:v.length);z=min(np.asarray(segment.coords)[:,1])+.015
     near,dist,tri=querycap.on_surface([[x,0,z]]);
     if dist[0]>=1e-5: raise ValueError(tr('Der Nasenbogen findet keinen Anschluss an der Basis.'))
     bary=trimesh.triangles.points_to_barycentric(chart.triangles[tri],near)
     pt=(cv[cf[tri]]*bary[:,:,None]).sum(1)[0];pt[1]-=.4;front.append(pt)
    front=np.asarray(front);front[0]=left[0];front[-1]=right[0]
    base=base_reference()
    bquery=trimesh.proximity.ProximityQuery(trimesh.Trimesh(base.vertices,base.faces,process=False))

    def construct(apex_z):
        peak=apex_z
        # Determine the centre of the opening directly behind the adapter.
        lo=float(central[:,1].max());hi=lo+10
        for _ in range(20):
         middle=(lo+hi)/2
         if bquery.on_surface([[0,middle,peak]])[1][0]<4.0:lo=middle
         else:hi=middle
        centre_y=hi
        # The bell curve belongs to the opening in plan (X/Y), as in the photo.
        xr=np.where(q<0,-q*left[-1,0],q*right[-1,0]);L=(right[-1,0]-left[-1,0])/2
        bell=np.exp(-.5*(xr/13.5)**2);end_bell=np.exp(-.5*(L/13.5)**2);bell=(bell-end_bell)/(1-end_bell)
        rear=np.c_[xr,(left[-1,1]+right[-1,1])/2+(centre_y-(left[-1,1]+right[-1,1])/2)*bell,(left[-1,2]+right[-1,2])/2+(peak-(left[-1,2]+right[-1,2])/2)*bell]
        for index,adj,target,tangent in [(0,1,left[-1],dl[-1]),(-1,-2,right[-1],dr[-1])]:
         derivative=(rear[adj]-rear[index])/(xr[adj]-xr[index]);delta=target-rear[index];slope=tangent-derivative
         dx=xr-xr[index];a=np.clip(abs(dx)/7.,0,1);w=1-10*a**3+15*a**4-6*a**5
         rear+=w[:,None]*(delta[None,:]+dx[:,None]*slope[None,:]);rear[index]=target
        # A bounded parametric loft, not an unconstrained minimum-bending patch.
        # Depth always travels from the adapter to the bell-shaped opening: there is
        # no return loop hidden inside the wall that could block the nose.
        N=len(front);M=len(left)
        u=np.linspace(0.,1.,N);v=np.linspace(0.,1.,M)
        depth_progress=[]
        for side in (left,right):
            depth_progress.append((side[:,1]-side[0,1])/(side[-1,1]-side[0,1]))
        f=(1-u[:,None])*depth_progress[0]+u[:,None]*depth_progress[1]
        f=np.clip(f,0,1)
        grid=front[:,None,:]*(1-v[None,:,None])+rear[:,None,:]*v[None,:,None]
        grid[:,:,1]=front[:,None,1]+(rear[:,None,1]-front[:,None,1])*f
        # Use matched tangent collars only at the real shell/pad junctions. Central
        # rows remain strictly inside the front/opening boundary, rather than sagging.
        for index,adj,target,tangent in [(0,1,left,dl),(-1,-2,right,dr)]:
            dx=grid[:,:,0]-grid[index,:,0]
            step=grid[adj,:,0]-grid[index,:,0]
            derivative=(grid[adj]-grid[index])/step[:,None]
            delta=target-grid[index];slope=tangent-derivative
            a=np.clip(abs(dx)/12.,0,1);w=1-10*a**3+15*a**4-6*a**5
            correction=w[:,:,None]*(delta[None,:,:]+dx[:,:,None]*slope[None,:,:])
            # The two boundary curves are already fitted and must remain untouched.
            correction[:,0]=0;correction[:,-1]=0
            grid+=correction;grid[index]=target
    
        # Differential offset inward, with the outside shape kept exactly.
        du=np.gradient(grid,axis=0);dv=np.gradient(grid,axis=1);norm=np.cross(du,dv);norm/=np.maximum(np.linalg.norm(norm,axis=2)[:,:,None],1e-12)
    
        inside=grid+norm*1.5
        # Match the complete wall section at each seam, including the pad contact
        # face. Blend offset orientation over 8 mm instead of leaving a narrow lip.
        for index,target in [(0,inner_sides[0]),(-1,inner_sides[1])]:
            dx=abs(grid[:,:,0]-grid[index,:,0]);a=np.clip(dx/8.,0,1)
            w=1-10*a**3+15*a**4-6*a**5
            inside+=w[:,:,None]*(target-inside[index])[None,:,:]
            inside[index]=target
        return grid,inside

    # The outer crest alone does not bound the wall: the inward normal offset
    # can rise above it when the user translates or tilts the support/base.
    # Solve the crest height using BOTH skins. Re-lofting preserves tangents;
    # clipping mesh vertices here would flatten the arch and create a crease.
    initial_peak=peak
    profile_z=float(central[:,2].max())
    for attempt in range(8):
        grid,inside=construct(peak)
        maximum_z=float(max(grid[:,:,2].max(),inside[:,:,2].max()))
        if maximum_z<=profile_z:
            break
        peak-=maximum_z-profile_z+.04
        # At most one wall thickness can be caused by the differential offset.
        # A fixed connection beyond the profile cannot be repaired by moving it.
        if initial_peak-peak>1.5:
            break
    else:
        maximum_z=float('inf')
    if maximum_z>profile_z:
        raise ValueError(tr('Der Nasenbogen ragt bei dieser Position \u00fcber das Adapterprofil hinaus. Auflagenh\u00f6he oder Basiswinkel pr\u00fcfen.'))
    cells=(np.arange(N-1)[:,None]*M+np.arange(M-1)).ravel();faces=np.vstack([np.c_[cells,cells+M,cells+M+1],np.c_[cells,cells+M+1,cells+1]])
    arch=sh._solid_layers(transform(grid.reshape(-1,3),mat),transform(inside.reshape(-1,3),mat),faces)
    report = dict(nose_bridge_enabled=True, nose_bridge_design='Neustart 06',
                      nose_bridge_thickness_mm=1.5, nose_pockets_filled=False,
                      nose_bridge_maximum_z=maximum_z,
                      nose_adapter_profile_z=profile_z,
                      nose_profile_adjustment_mm=float(initial_peak-peak),
                      nose_apex_adapter_clearance_mm=float(bquery.on_surface(
                          np.vstack([grid[N//2,-1],inside[N//2,-1]]))[1].min()))
    if fill_pockets:
        from .nose_pockets import make_nose_pockets
        from .assembly import _manifold
        from .meshio import Mesh
        pockets, pocket_report = make_nose_pockets(support, mat, old_inside, grid, inside,
                                                   shell_outer=surface)
        union = (_manifold(arch) + _manifold(pockets)).to_mesh64()
        arch = Mesh(union.vert_properties[:, :3], union.tri_verts, 'Nose arch with contour fills')
        report.update(pocket_report)
    return arch, report
