"""A scan-guided lower light shield with an adjustable, non-contact opening."""
import numpy as np
import trimesh
import manifold3d as mf
from functools import lru_cache
from shapely.geometry import Polygon
from shapely.geometry import LineString
from scipy.ndimage import gaussian_filter1d
from scipy.special import logsumexp
from shapely import contains_xy
from .meshio import Mesh
from .profile import transform
from .localization import tr


@lru_cache(maxsize=1)
def nose_base_geometry():
    from .assembly import base_reference
    base=base_reference()
    mesh=trimesh.Trimesh(base.vertices,base.faces,process=False)
    solid=mf.Manifold(mf.Mesh64(np.array(base.vertices,dtype=np.float64,order='C'),np.array(base.faces,dtype=np.uint64,order='C')))
    projected=solid.rotate((90,0,0)).project()
    projected=mf.CrossSection(projected.to_polygons(),mf.FillRule.Positive)
    footprint=Polygon()
    for contour in projected.to_polygons():
        contour=np.asarray(contour)
        footprint=footprint.symmetric_difference(Polygon(np.c_[contour[:,0],-contour[:,1]]))
    return mesh,footprint


class NoseSurface:
    def __init__(self,head,matrix):
        self.mesh=None if head is None else trimesh.Trimesh(transform(head.vertices,np.linalg.inv(matrix)),head.faces,process=False)

    def depth(self,xz):
        result=np.full(len(xz),np.nan)
        if self.mesh is None:return result
        origins=np.c_[xz[:,0],np.full(len(xz),-500.),xz[:,1]]
        hits,rays,triangles=self.mesh.ray.intersects_location(origins,np.tile([0.,1.,0.],(len(xz),1)),multiple_hits=False)
        hits=np.asarray(hits).reshape(-1,3)
        good=self.mesh.face_normals[triangles,1]<-.1
        result[rays[good]]=hits[good,1]
        return result


def suggest_nose(left,right,projector,clearance=3.):
    bottom=float((left[2]+right[2])/2)
    x=np.linspace(max(left[0],-30),min(right[0],30),61)
    z=np.linspace(bottom+2,bottom+34,33)
    xx,zz=np.meshgrid(x,z);xz=np.c_[xx.ravel(),zz.ravel()]
    depth=projector.depth(xz)
    plane=np.interp(xz[:,0],[left[0],right[0]],[left[1],right[1]])
    nose=np.isfinite(depth)&(depth<plane-clearance)
    if nose.sum()<8:return {'width':36.,'height':24.,'clearance':clearance,'scan_guided':False}
    points=xz[nose]
    width=float(np.clip(2*abs(points[:,0]).max()+2*clearance,24,52))
    height=float(np.clip(points[:,1].max()-bottom+clearance,16,36))
    return {'width':round(width,1),'height':round(height,1),'clearance':clearance,'scan_guided':True}


def settings_from_head(support,head,matrix,clearance=3.):
    from .shell import _pad_path
    uv=_pad_path(support)[[0,-1]]
    chart=trimesh.Trimesh(np.c_[support.flat,np.zeros(len(support.flat))],support.surface_faces,process=False)
    near,dist,tri=trimesh.proximity.ProximityQuery(chart).on_surface(np.c_[uv,np.zeros(2)])
    bary=trimesh.triangles.points_to_barycentric(chart.triangles[tri],near)
    back=support.mesh.vertices[len(support.contact):]
    points=(back[support.surface_faces[tri]]*bary[:,:,None]).sum(1)
    points=transform(points,np.linalg.inv(matrix));points=points[np.argsort(points[:,0])]
    result=suggest_nose(points[0],points[1],NoseSurface(head,matrix),clearance)
    _,outline=nose_base_geometry()
    section=outline.intersection(LineString([[0,10],[0,85]]))
    parts=[section] if section.geom_type=='LineString' else list(getattr(section,'geoms',[]))
    parts=[s for s in parts if s.geom_type=='LineString' and s.length>.2]
    if parts:
        lower=min(parts,key=lambda s:np.asarray(s.coords)[:,1].min())
        result['height']=float(np.clip(min(result['height'],np.asarray(lower.coords)[:,1].max()-min(points[:,2])-3),8,45))
    return result


def make_nose_baffle(support,matrix,head,settings):
    """Smooth nasal tunnel from the actual OEM bridge to the cheek backing.

    Both boundaries are single arches, never a scan-displaced curtain. The scan
    controls only a smooth depth amplitude; it cannot imprint folds in the wall.
    """
    from .shell import _pad_path,_solid_layers
    uv=_pad_path(support)[[0,-1]]
    chart=trimesh.Trimesh(np.c_[support.flat,np.zeros(len(support.flat))],support.surface_faces,process=False)
    near,_,tri=trimesh.proximity.ProximityQuery(chart).on_surface(np.c_[uv,np.zeros(2)])
    bary=trimesh.triangles.points_to_barycentric(chart.triangles[tri],near)
    back=support.mesh.vertices[len(support.contact):]
    ends=(back[support.surface_faces[tri]]*bary[:,:,None]).sum(1)
    ends=transform(ends,np.linalg.inv(matrix));ends=ends[np.argsort(ends[:,0])]
    seams=settings.get('_shell_seams')
    if seams:
        ends=np.array(seams['nose_seam_pad_local']);ends=ends[np.argsort(ends[:,0])]
    left,right=ends;projector=NoseSurface(head,matrix)
    p={**settings_from_head(support,head,matrix,float(settings.get('clearance',3.))),**settings}
    if not (16<=p['width']<=65 and 8<=p['height']<=45 and 1<=p['clearance']<=8):
        raise ValueError(tr('Ungültige Einstellungen der Nasenöffnung.'))
    base,footprint=nose_base_geometry()
    from .assembly import base_metadata
    if base_metadata().get('rear_collar_rebuilt'):
        from .shell import _rear_cap
        footprint=_rear_cap()[2]
    x=np.linspace(left[0],right[0],161)
    if seams:
        a=np.array(seams['nose_seam_base_local']);a=a[np.argsort(a[:,0])]
        front_x=np.linspace(a[0,0],a[1,0],len(x))
    else:front_x=x.copy()
    zfront=[]
    for value in front_x:
        part=footprint.intersection(LineString([[value,10],[value,85]]))
        pieces=[part] if part.geom_type=='LineString' else list(getattr(part,'geoms',[]))
        pieces=[q for q in pieces if q.geom_type=='LineString' and q.length>.2]
        if not pieces:raise ValueError(tr('Kein Anschluss für die Nasenblende an der Basis gefunden.'))
        q=min(pieces,key=lambda q:np.asarray(q.coords)[:,1].min())
        zfront.append(q.interpolate(.55,normalized=True).y)
    zfront=gaussian_filter1d(zfront,3.)
    front=np.c_[front_x,np.zeros(len(x)),zfront]
    if seams:
        a=np.array(seams['nose_seam_base_local']);a=a[np.argsort(a[:,0])]
        # Blend only the cheek joins; the central nasal bridge stays on OEM.
        for side,end in [(0,a[0]),(-1,a[1])]:
            weight=np.exp(-((np.linspace(0,1,len(x))-(0 if side==0 else 1))/.13)**2)
            front+=weight[:,None]*(end-front[side])[None,:]
    origins=front.copy();origins[:,1]=100
    hits,rays,_=base.ray.intersects_location(origins,np.tile([0.,-1.,0.],(len(x),1)),multiple_hits=False)
    if len(rays)!=len(x):raise ValueError(tr('Kein Anschluss für die Nasenblende an der Basis gefunden.'))
    front[rays,1]=hits[:,1]-1.
    front[:,1]=gaussian_filter1d(front[:,1],5.,mode='nearest')
    if seams:
        for index,end in [(0,a[0]),(-1,a[1])]:
            weight=np.exp(-((np.linspace(0,1,len(x))-(0 if index==0 else 1))/.15)**2)
            front+=weight[:,None]*(end-front[index])[None,:]
    # Blending to the cheek side seams must never pull this boundary out of
    # the ring. A smooth minimum keeps a real 1 mm insertion along the arch.
    limit=np.empty(len(front));limit[rays]=hits[:,1]-1.
    front[:,1]=-.08*np.logaddexp(-front[:,1]/.08,-limit/.08)
    # Rounded, single-peaked opening. Width determines the breadth of the arch,
    # while height is measured from the lower cheek endpoints.
    span=(right[0]-left[0])/2;centre=(right[0]+left[0])/2
    q=(x-centre)/span
    exponent=float(np.clip((2*span/p['width'])**2, .7,8.))
    bell=np.maximum(0,1-q*q)**exponent
    depth_bell=np.maximum(0,1-q*q)
    rear=np.column_stack([x,np.interp(x,[left[0],right[0]],[left[1],right[1]]),
                          np.interp(x,[left[0],right[0]],[left[2],right[2]])+p['height']*bell])
    rear[[0,-1]]=ends
    depth=projector.depth(rear[:,[0,2]])
    valid=np.isfinite(depth)
    if head is not None and valid.mean()<.6:
        raise ValueError(tr('Im Nasenbereich fehlen Scanflächen. Bitte Ausrichtung prüfen oder die Nasenblende ausschalten.'))
    movable=valid&(depth_bell>.2)
    amplitude=0.
    if movable.any():amplitude=max(0.,float(np.max((rear[movable,1]-depth[movable]+p['clearance']*2.5+1.)/depth_bell[movable])))
    amplitude+=float(settings.get('_depth_extra',0.))
    rear[:,1]-=amplitude*depth_bell
    if np.any(rear[2:-2,1]-front[2:-2,1]<2.):
        raise ValueError(tr('Die Nasenblende würde den Kopf berühren. Bitte Basisposition prüfen.'))
    # Straight generators between two smooth curves produce a coherent tunnel.
    # No min/max over unrelated forehead or cheek samples is allowed here.
    t=np.linspace(0,1,25)
    surface=front[:,None,:]*(1-t[None,:,None])+rear[:,None,:]*t[None,:,None]
    normal=np.cross(np.gradient(surface,axis=0),np.gradient(surface,axis=1))
    norm=np.linalg.norm(normal,axis=2)
    if (norm<1e-8).any():raise ValueError(tr('Die Nasenblende konnte nicht geschlossen aufgebaut werden.'))
    normal/=norm[:,:,None]
    seam=np.vstack([front[2:-2],front[2:-2]+normal[2:-2,0]*.35,
                    front[2:-2]-normal[2:-2,0]*.35])
    if not base.contains(seam).all():
        raise ValueError(tr('Kein Anschluss für die Nasenblende an der Basis gefunden.'))
    rows=np.arange(len(x)-1);cells=(rows[:,None]*len(t)+np.arange(len(t)-1)).ravel()
    nxt=(((rows+1)[:,None])*len(t)+np.arange(len(t)-1)).ravel()
    faces=np.vstack([np.c_[cells,nxt,nxt+1],np.c_[cells,nxt+1,cells+1]])
    # Slightly reinforced nasal wall; high curvature must still retain at
    # least 1.4 mm measured normal thickness after offsetting.
    inner=(surface-normal*.825).reshape(-1,3);outer=(surface+normal*.825).reshape(-1,3)
    model=_solid_layers(transform(inner,matrix),transform(outer,matrix),faces)
    volume=trimesh.Trimesh(model.vertices,model.faces,process=False)
    if not volume.is_volume:raise ValueError(tr('Die Nasenblende konnte nicht geschlossen aufgebaut werden.'))
    opposite=trimesh.Trimesh(outer,faces,process=False)
    sampled=inner.reshape(surface.shape)[3:-3:3,3:-3:3].reshape(-1,3)
    thickness_min=float(trimesh.proximity.ProximityQuery(opposite).on_surface(sampled)[1].min())
    if not np.isfinite(thickness_min) or thickness_min<1.4:
        raise ValueError(tr('Die Nasenblende würde lokal zu dünn. Bitte Nasenöffnung oder Basisposition ändern.'))
    gap=None
    if head is not None:
        # Check the complete tunnel, not just its face-side edge.
        probes=np.vstack([inner,outer,surface.reshape(-1,3)])
        front_depth=projector.depth(probes[:,[0,2]])
        known=np.isfinite(front_depth)
        if np.any(probes[known,1]>front_depth[known]+.1):
            raise ValueError(tr('Die Nasenblende würde den Kopf berühren. Bitte Basisposition prüfen.'))
        measured=trimesh.proximity.ProximityQuery(projector.mesh).on_surface(probes)[1]
        gap=float(measured.min())
        if np.isfinite(measured).all() and gap<p['clearance']-.05 and settings.get('_depth_extra',0.)<12:
            options=dict(settings);options['_depth_extra']=settings.get('_depth_extra',0.)+2.
            return make_nose_baffle(support,matrix,head,options)
        if not np.isfinite(measured).all() or gap<p['clearance']-.05:
            raise ValueError(tr('Die Nasenblende würde den Kopf berühren. Bitte Basisposition prüfen.'))
    return model,dict(nose_opening_width_mm=float(p['width']),nose_opening_height_mm=float(p['height']),
                      nose_clearance_mm=float(p['clearance']),nose_sampled_gap_min_mm=gap,
                      nose_scan_coverage=float(valid.mean()),nose_scan_guided=head is not None,
                      nose_sampled_thickness_min_mm=thickness_min,nose_tunnel=True,
                      nose_nominal_wall_mm=1.65,
                      nose_base_seam_checked=True,
                      nose_depth_amplitude_mm=amplitude)
