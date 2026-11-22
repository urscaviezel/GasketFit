"""Independent forehead-only design and single-body upper-shell construction."""
from .localization import tr
from functools import lru_cache
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import Delaunay
from scipy.interpolate import UnivariateSpline, LinearNDInterpolator
from .meshio import Mesh
from .profile import transform, pose_matrix


def validate(params):
    from .referencefit import validate as common
    p=common(params)
    from .cushion_presets import preset
    key=params.get('cushion_preset','custom')
    template=preset(key)
    p['cushion_preset']=key
    params=dict(params)
    if key!='custom':params.update(forehead_width=template['width_mm'],forehead_height=template['height_mm'])
    for key,default,lo,hi in [('forehead_width',200.,140,240),('forehead_height',48.,30,65),('forehead_radius',105.,80,180)]:
        value=float(params.get(key,default))
        if not np.isfinite(value) or not lo<=value<=hi: raise ValueError(tr('Ungültige Stirnauflagen-Abmessung.'))
        p[key]=value
    p.update(solver='forehead',thickness=2.5,include_base=True,closed_shell=True,nose_bridge=False,nose_pockets=False,top_strap=bool(params.get('top_strap',False)))
    return p


def initial_parameters(head, previous=None):
    from .referencefit import initial_parameters as initial
    p=dict(previous or initial(head))
    p['pose']=list(p.get('base_pose',p['pose']))
    p['base_pose']=list(p['pose'])
    p.pop('pad_alignment',None)
    p.update(forehead_width=198.,forehead_height=48.,forehead_radius=105.,cushion_preset='vr_panda',refine_pose=False,top_strap=False)
    return validate(p)


@lru_cache(maxsize=32)
def _reference(width,height,radius):
    r=height/2; c=width/2-r
    boundary=np.array([[center+r*np.cos(a),132+r*np.sin(a)] for center,start in [(c,-np.pi/2),(-c,np.pi/2)] for a in np.linspace(start,start+np.pi,49,endpoint=False)])
    from shapely.geometry import Polygon, Point
    poly=Polygon(boundary)
    interior=np.array([[x,z] for x in np.arange(-width/2+2,width/2,3) for z in np.arange(132-r+2,132+r,3) if poly.buffer(-.5).contains(Point(x,z))])
    # Subdivide the straight edges BEFORE wrapping. A single long boundary
    # chord would cut through the curved forehead at triangle centres.
    edge=np.array([[x,132+sign*r] for sign in [-1,1] for x in np.linspace(-c,c,max(3,int(2*c/2)+1))])
    uv=np.unique(np.round(np.vstack([boundary,edge,interior]),9),axis=0); faces=Delaunay(uv).simplices
    vertices=np.column_stack([radius*np.sin(uv[:,0]/radius),10.5+radius*(1-np.cos(uv[:,0]/radius)),uv[:,1]])
    return dict(contact=vertices,faces=faces,uv=uv)


def reference(params):
    p=validate(params)
    if p['cushion_preset']!='custom':return _preset_reference(p['cushion_preset'],p['forehead_radius'])
    return _reference(p['forehead_width'],p['forehead_height'],p['forehead_radius'])


@lru_cache(maxsize=32)
def _preset_reference(key,radius):
    from .cushion_presets import preset
    from shapely.geometry import Polygon,Point
    d=preset(key);boundary=d['outline'].copy();boundary[:,1]+=132
    poly=Polygon(boundary);lo=boundary.min(0);hi=boundary.max(0)
    interior=np.array([[x,z] for x in np.arange(lo[0]+1,hi[0],3) for z in np.arange(lo[1]+1,hi[1],3) if poly.buffer(-.6).contains(Point(x,z))])
    uv=np.vstack([boundary,interior]);faces=Delaunay(uv).simplices
    faces=np.asarray([f for f in faces if poly.buffer(1e-6).covers(Polygon(uv[f]))])
    vertices=np.c_[radius*np.sin(uv[:,0]/radius),10.5+radius*(1-np.cos(uv[:,0]/radius)),uv[:,1]]
    return dict(contact=vertices,faces=faces,uv=uv)


def fit_pad(outline,head,params,progress=None):
    from .referencefit import fit_pad as fit
    result=fit(outline,head,params,progress,reference_data=reference(params))
    result.mesh.name='Stirnauflage · 2,5 mm'
    result.report.update(mode='forehead_bounded',reference='Capsule forehead cushion',nominal_thickness_mm=2.5,
                         scope='Forehead support only',reference_sha256=None)
    return result


@lru_cache(maxsize=1)
def base_reference():
    with np.load(Path(__file__).with_name('pfd_open_base.npz'),allow_pickle=False) as d:
        return Mesh(d['vertices'].copy(),d['faces'].copy(),'Offene Magnetbasis · Testanschläge')


def _solid(vertices,faces):
    m=trimesh.Trimesh(vertices,faces,process=True)
    m.fix_normals()
    if not m.is_volume: raise ValueError(tr('Die Oberschale faltet sich. Headset und Stirnauflage näher zusammen ausrichten.'))
    return Mesh(m.vertices,m.faces,'Oberschale')


def _single_body(mesh):
    """Discard only sub-10-micron Boolean debris, never a real loose part."""
    components=mesh.split(only_watertight=False)
    meaningful=[part for part in components if not (
        np.linalg.norm(np.ptp(part.vertices,axis=0))<.01 and
        part.area<1e-4 and abs(part.volume)<1e-8)]
    removed=len(components)-len(meaningful)
    if len(meaningful)!=1 or not meaningful[0].is_volume:
        raise ValueError(tr('Verbindung erreicht Basis oder Stirnträger nicht durchgehend. Positionen näher zusammen ausrichten.'))
    return (meaningful[0] if removed else mesh),removed


@lru_cache(maxsize=4)
def _full_width_roots(count):
    """Rear upper-rim footprint from outer edge through the inner/lower edge.

    Project the immutable base to XZ, then sample radial cross sections.
    Actual rear-surface rays give the depth, avoiding a rectangular overhang.
    """
    import shapely
    from shapely.geometry import Polygon, LineString
    from .assembly import base_reference as magnetic_base, _front_guard
    base=magnetic_base()
    mesh=trimesh.Trimesh(base.vertices,base.faces,process=False)
    guard=_front_guard()
    guarded=trimesh.Trimesh(guard.vertices,guard.faces,process=False) if guard is not None else None
    triangles=shapely.polygons(base.vertices[base.faces][:,:,[0,2]])
    footprint=shapely.union_all(triangles[shapely.area(triangles)>1e-8])
    aperture=max(footprint.interiors,key=lambda ring:Polygon(ring).area)
    footprint=Polygon(footprint.exterior,[aperture])
    roots=[[],[]]
    for u in np.linspace(-1,1,count):
        centre=np.array([0.,78.])
        direction=np.array([72*np.sin(u*1.35),35*np.cos(u*1.35)])
        cut=footprint.intersection(LineString([centre,centre+direction*2]))
        if cut.geom_type!='LineString':raise ValueError(tr('Oberer Basisrand konnte nicht eindeutig bestimmt werden.'))
        ends=np.array(cut.coords)[[0,-1]]
        ends=ends[np.argsort(np.linalg.norm(ends-centre,axis=1))]
        inward=(ends[1]-ends[0])/np.linalg.norm(ends[1]-ends[0])
        # 0.1 mm inset avoids tangent ray misses; all original rim geometry
        # remains in the union. The root penetrates to the protected depth.
        for target,xz in zip(roots,(ends[1]-.1*inward,ends[0]+.1*inward)):
            hit,_,_=mesh.ray.intersects_location([[xz[0],200.,xz[1]]],[[0.,-1.,0.]],multiple_hits=False)
            if not len(hit):raise ValueError(tr('Die Verbindung erreicht den Basisrand nicht.'))
            point=hit[0].copy();point[1]-=2.0
            if target is roots[0]:
                # The projected silhouette includes bevels at other depths.
                # Match the actual outer skin where the connector starts,
                # avoiding a recessed root and its visible emergence crease.
                if guarded is not None:
                    boundary,_,_=guarded.ray.intersects_location(
                        [[point[0],200.,point[2]]],[[0.,-1.,0.]],multiple_hits=False)
                    if len(boundary):point[1]=max(point[1],boundary[0,1]-.02)
                start=centre+inward*150.
                surface,_,_=mesh.ray.intersects_location(
                    [[start[0],point[1],start[1]]],
                    [[-inward[0],0.,-inward[1]]],multiple_hits=False)
                if not len(surface):
                    raise ValueError(tr('Die äußere Anschlussfläche der Magnetbasis wurde nicht gefunden.'))
                point=surface[0]-.003*np.array([inward[0],0.,inward[1]])
            target.append(point)
    return np.asarray(roots[0]),np.asarray(roots[1])


def build_assembly(support,base_pose,progress=None,*,top_strap=False,**unused):
    from .assembly import AssemblyResult, _manifold, _front_guard
    progress=progress or (lambda *_:None)
    progress(5,tr('Offene Basiskopie mit Testanschlägen vorbereiten …'))
    original=base_reference(); matrix=pose_matrix(base_pose)
    # Construct in base coordinates so the magnet interface never moves.
    inv=np.linalg.inv(matrix)
    contact=transform(support.contact,inv)
    n=len(contact); backing=transform(support.mesh.vertices[n:],inv)
    from .forehead_connection import stitched_carrier
    outer_roots,inner_roots=_full_width_roots(257)
    cylindrical_frame = None
    if support.report.get('mode') == 'no_scan':
        parameters = support.report['parameters']
        cylindrical_frame = (parameters['forehead_radius'], inv @ pose_matrix(parameters['pose']))
    carrier,construction=stitched_carrier(support,contact,backing,outer_roots,inner_roots,
                                         cylindrical_frame=cylindrical_frame)
    shell=Mesh(carrier.vertices,carrier.faces,'Gemeinsame Stirnträger-Verbindung')
    progress(45,tr('Durchgehende Oberschale und Stirnträger vereinigen …'))
    support_local=Mesh(transform(support.mesh.vertices,inv),support.mesh.faces,'Stirnträger')
    addition=_manifold(shell)
    guard=_front_guard()
    support_solid=_manifold(support_local)
    if guard is not None:
        guard_solid=_manifold(guard)
        if (support_solid ^ guard_solid).volume()>.001:
            raise ValueError(tr('Die Stirnauflage liegt im geschützten Magnetanschluss. Headset weiter nach vorne ausrichten.'))
        addition=addition-guard_solid
    base_solid=_manifold(original)
    base_overlap=addition ^ base_solid
    support_overlap=addition ^ support_solid
    # A single connected component can still hide a near-point attachment.
    # Require volumetric attachment across the width at both ends of the loft.
    root_volumes=[];pad_volumes=[]
    for left,right in zip(np.linspace(-64,64,14)[:-1],np.linspace(-64,64,14)[1:]):
        box=trimesh.creation.box(extents=[right-left,600,400])
        box.apply_translation([(left+right)/2,0,100])
        band=_manifold(Mesh(box.vertices,box.faces,'Attachment band'))
        root_volumes.append((base_overlap ^ band).volume())
        pad_volumes.append((support_overlap ^ band).volume())
    if min(root_volumes)<.5 or min(pad_volumes)<.5:
        raise ValueError(tr('Die Verbindung hat nicht über die ganze Breite ausreichend Kontakt. Ausrichtung der Stirnauflage prüfen.'))
    strap_report=dict(top_strap_enabled=False)
    if top_strap:
        from .forehead_strap import make_forehead_strap
        loop,opening,ears,strap_report=make_forehead_strap(support,matrix)
        loop_solid=_manifold(loop)
        joins=[float((_manifold(ear)^support_solid).volume()) for ear in ears]
        if min(joins)<3.:
            raise ValueError(tr('Die Kopfbandhalterung erreicht die Stirnauflage nicht ausreichend.'))
        if guard is not None and (loop_solid^guard_solid).volume()>.001:
            raise ValueError(tr('Die Kopfbandhalterung liegt im geschützten Magnetanschluss. Ausrichtung prüfen.'))
        addition+=loop_solid
        obstruction=float(((base_solid+addition)^_manifold(opening)).volume())
        if obstruction>.001:
            raise ValueError(tr('Der Durchlass der Kopfbandhalterung ist nicht frei. Ausrichtung prüfen.'))
        strap_report.update(top_strap_pad_attachment_volumes_mm3=joins,top_strap_opening_obstruction_mm3=obstruction)
    union=base_solid+addition
    if cylindrical_frame is not None:
        # Eliminate sub-micron Boolean slivers at the analytic carrier join.
        # Bound movement to 0.01 micrometres, far below export precision.
        union=union.simplify(1e-5)
    out=union.to_mesh64();m=trimesh.Trimesh(np.asarray(out.vert_properties)[:,:3],np.asarray(out.tri_verts),process=False)
    m,removed_specks=_single_body(m)
    # The cushion glue face must remain exposed, even with independently tilted parts.
    progress(75,tr('Klebefläche und Magnetbasis prüfen …'))
    query=trimesh.proximity.ProximityQuery(m)
    samples=np.vstack([contact,contact[support.surface_faces].mean(1)])
    for start in range(0,len(samples),200):
        if query.on_surface(samples[start:start+200])[1].max()>.02:raise ValueError(tr('Die Verbindung überdeckt die Klebefläche. Headset-Position ändern.'))
    mesh=Mesh(transform(m.vertices,matrix),m.faces,'Offenes Gasket')
    base=Mesh(transform(original.vertices,matrix),original.faces,'Offene Magnetbasis')
    clipped=addition.to_mesh64()
    shell=Mesh(transform(np.asarray(clipped.vert_properties)[:,:3],matrix),np.asarray(clipped.tri_verts),'Oberschale')
    report=dict(mode='open_forehead',base_pose=list(base_pose),support=support.report,closed=True,connected_components=1,
                provisional_stops=True,usb_clearance_verified=False,mechanical_load_tested=False,**strap_report,
                root_profile='full_upper_rim_outer_to_inner',outer_bulge_mm=0.,lower_edge_followed=True,removed_boolean_specks=removed_specks,**construction,
                base_overlap_mm3=float(base_overlap.volume()),support_overlap_mm3=float(support_overlap.volume()),
                minimum_base_band_overlap_mm3=float(min(root_volumes)),
                minimum_support_band_overlap_mm3=float(min(pad_volumes)),
                protected_front_added_volume_mm3=float((addition ^ guard_solid).volume()) if guard is not None else None)
    progress(100,tr('Offenes Gasket als ein Druckkörper berechnet.'))
    return AssemblyResult(mesh,shell,base,report)
