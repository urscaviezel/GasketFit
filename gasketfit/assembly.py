"""Probe 06: unchanged magnetic band and seven rear-only solid bridges."""
from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass
import json
import numpy as np
import trimesh
import manifold3d as mf
from shapely.geometry import Polygon, Point
from scipy.spatial import cKDTree
from .meshio import Mesh
from .profile import pose_matrix, transform, contour_angle, depth_curve
from .referencefit import reference
from .localization import tr


@lru_cache(maxsize=1)
def base_reference():
    with np.load(Path(__file__).with_name('pfd_magnetic_base.npz'),allow_pickle=False) as data:
        return Mesh(data['vertices'].copy(),data['faces'].copy(),'PFDMR magnetic base')


def base_metadata():
    return json.loads(Path(__file__).with_name('pfd_magnetic_base.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def _connector_guard():
    if base_metadata().get('reference_revision')==16:return None
    if not base_metadata().get('profile','').startswith('oem_'):
        return None
    with np.load(Path(__file__).with_name('pfd_hmd_connector_guard.npz'),allow_pickle=False) as data:
        return Mesh(data['vertices'].copy(),data['faces'].copy(),'OEM HMD connector clearance')


@lru_cache(maxsize=1)
def _feature_voids():
    if base_metadata().get('profile')!='oem_v2':return None
    with np.load(Path(__file__).with_name('pfd_base_feature_voids.npz'),allow_pickle=False) as data:
        return Mesh(data['vertices'].copy(),data['faces'].copy(),'Magnet and strap loading clearances')


def _manifold(mesh):
    result=mf.Manifold(mf.Mesh64(np.array(mesh.vertices,dtype=np.float64,order='C',copy=True),np.array(mesh.faces,dtype=np.uint64,order='C',copy=True)))
    if result.status()!=mf.Error.NoError:
        raise ValueError(tr('Ein Verbindungskörper ist geometrisch ungültig. Bitte Basis neu positionieren.'))
    return result


@lru_cache(maxsize=1)
def _front_guard(depth=None):
    """Same 2-mm front-contour grid as the base extractor, at depth 8 mm."""
    if base_metadata().get('reference_revision')==16:
        with np.load(Path(__file__).with_name('pfd_oem16_front_guard.npz')) as d:
            return Mesh(d['vertices'].copy(),d['faces'].copy(),'Stand 16 protected contact envelope')
    x,z=np.meshgrid(np.linspace(-160,160,161),np.linspace(-20,180,101))
    q=np.c_[x.ravel(),np.zeros(x.size),z.ravel()]
    if depth is None:depth=base_metadata().get('protected_front_band_mm',8.)
    top=q.copy();top[:,1]=depth_curve(contour_angle(q),'front_depth')+depth
    bottom=top.copy();bottom[:,1]=-200
    cells=(np.arange(100)[:,None]*161+np.arange(160)).ravel()
    f=np.vstack([np.c_[cells,cells+161,cells+162],np.c_[cells,cells+162,cells+1]])
    edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]])
    _,inv,counts=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
    b=edges[counts[inv]==1];n=len(top)
    ff=np.vstack([f,f[:,::-1]+n,np.c_[b[:,0],b[:,1]+n,b[:,1]],np.c_[b[:,0],b[:,0]+n,b[:,1]+n]])
    mesh=trimesh.Trimesh(np.vstack([top,bottom]),ff,process=False)
    if mesh.volume<0:mesh.invert()
    return Mesh(mesh.vertices,mesh.faces,'Protected magnetic envelope')


def _near(mesh,points,progress,stage):
    query=trimesh.proximity.ProximityQuery(mesh)
    result=[]
    for i in range(0,len(points),40):
        if i%400==0:progress(stage,tr('Unveränderte Magnetaufnahme und Polsterfläche prüfen …'))
        batch=points[i:i+40]
        with np.errstate(divide='ignore',invalid='ignore'):
            distance=np.array(query.on_surface(batch)[1],copy=True)
        # Nearly collinear boolean-seam triangles can make the barycentric
        # closest-point calculation inaccurate. An exact segment projection
        # supplies the distance to their edges without changing any geometry.
        for j in np.flatnonzero(~np.isfinite(distance)|(distance>1e-6)):
            point=batch[j];radius=max(1e-5,float(distance[j])+1e-8) if np.isfinite(distance[j]) else 1e-5
            try:
                ids=list(mesh.triangles_tree.intersection(np.r_[point-radius,point+radius]))
                triangles=mesh.triangles[ids]
                a=triangles[:,[0,1,2]].reshape(-1,3);b=triangles[:,[1,2,0]].reshape(-1,3)
                ab=b-a;denom=(ab*ab).sum(1)
                fraction=np.divide(((point-a)*ab).sum(1),denom,out=np.zeros(len(a)),where=denom>0)
                closest=a+np.clip(fraction,0,1)[:,None]*ab
                edge=np.linalg.norm(closest-point,axis=1).min(initial=np.inf)
                distance[j]=min(distance[j],edge) if np.isfinite(distance[j]) else edge
            except (AttributeError,ValueError):pass
        result.append(distance)
    distances=np.concatenate(result)
    if not np.isfinite(distances).all():
        raise ValueError(tr('Der Rahmen enthält ungültige Druckgeometrie.'))
    return distances


@dataclass
class AssemblyResult:
    mesh: Mesh
    bridges: Mesh
    base: Mesh
    report: dict


def build_assembly(support,base_pose,progress=None,*,closed_shell=False,head=None,nose_settings=None,top_strap=False):
    progress=progress or (lambda *_:None)
    pose=np.asarray(base_pose,dtype=float)
    if pose.shape!=(6,) or not np.isfinite(pose).all() or (abs(pose)>2000).any():
        raise ValueError(tr('Ungültige Position der magnetischen Basis.'))
    progress(3,tr('Unveränderte magnetische Basis vorbereiten …'))
    original=base_reference()
    integral=closed_shell and base_metadata().get('profile')=='oem_v2'
    matrix=pose_matrix(pose)
    connector_guard=_connector_guard()
    protected_solid=None
    clearance_solid=None
    if connector_guard is not None or base_metadata().get('reference_revision')==16:
        guard=_front_guard()
        # A tiny rearward margin avoids coincident cut faces at the exact
        # protection boundary; the complete original base is added separately.
        clip_vertices=guard.vertices+np.array([0.,.02,0.])
        protected_solid=_manifold(Mesh(transform(clip_vertices,matrix),guard.faces,guard.name))
        clearance_solid=(_manifold(Mesh(transform(connector_guard.vertices,matrix),connector_guard.faces,connector_guard.name)) if connector_guard is not None else mf.Manifold())
    bv=transform(original.vertices,matrix)
    base=Mesh(bv,original.faces.copy(),original.name)
    if clearance_solid is not None:
        clearance_solid=clearance_solid-_manifold(base)
    base_mesh=trimesh.Trimesh(bv,base.faces,process=False)
    n=len(support.contact)
    if len(support.mesh.vertices)!=2*n:
        raise ValueError(tr('Bitte zuerst die Polsterauflage neu berechnen.'))
    back=support.mesh.vertices[n:]
    normal=back-support.contact
    normal/=np.linalg.norm(normal,axis=1)[:,None]
    uv=support.flat
    chart=trimesh.Trimesh(np.c_[uv,np.zeros(n)],support.surface_faces,process=False)
    chart_query=trimesh.proximity.ProximityQuery(chart)
    polygon=Polygon(uv[:420])
    # Leave an adhesive-border margin; all feet are on the HMD-facing side.
    targets=[(-58,118),(0,118),(58,118),(-99,83),(99,83),(-62,44),(62,44)]
    candidates=np.array([polygon.boundary.distance(Point(q)) for q in uv])>4
    candidate_ids=np.flatnonzero(candidates)
    if not len(candidate_ids):
        raise ValueError(tr('Die Auflage bietet keine geeigneten Verbindungsflächen.'))
    base_offset=original.vertices[:,1]-depth_curve(contour_angle(original.vertices),'front_depth')
    rear=np.flatnonzero(base_offset>11.2)
    if base_metadata().get('profile')=='oem_v2':
        from .shell import _rear_cap
        if base_metadata().get('reference_revision')==16:
            cv,cf,_,_= _rear_cap()
            cap=trimesh.Trimesh(cv,cf,process=False)
            rear=np.flatnonzero(trimesh.proximity.ProximityQuery(cap).on_surface(original.vertices)[1]<.02)
        elif base_metadata().get('rear_collar_rebuilt'):
            rear=np.flatnonzero((base_offset>12.7)&(base_offset<13.3))
        else:rear=np.unique(_rear_cap()[1])
        # The strap frame is not a structural attachment port for pad ribs.
        rear=rear[original.vertices[rear,2]<114.]
    bridges=[]
    for index,target in enumerate([] if integral else targets):
        progress(8+index*7,tr('Stabile Verbindungen zur Auflage aufbauen …'))
        anchor=candidate_ids[np.argmin(np.linalg.norm(uv[candidate_ids]-target,axis=1))]
        centre=uv[anchor]
        # A short strip in the actual UV mesh, with exact barycentric backing
        # positions. Never approximate the foot by an unconstrained flat plate.
        q=centre+np.array([(u,z) for u in np.linspace(-4,4,5) for z in (-1.2,0,1.2)])
        if not all(polygon.covers(Point(p)) for p in q):
            raise ValueError(tr('Eine Verbindung reicht über die Polsterkante. Bitte Auflagenposition prüfen.'))
        near,dd,tri=chart_query.on_surface(np.c_[q,np.zeros(len(q))])
        if dd.max()>.001:
            raise ValueError(tr('Die Verbindungsfläche liegt außerhalb der Auflage.'))
        bary=trimesh.triangles.points_to_barycentric(chart.triangles[tri],near)
        ids=support.surface_faces[tri]
        foot=(back[ids]*bary[:,:,None]).sum(1)
        normals=(normal[ids]*bary[:,:,None]).sum(1)
        normals/=np.linalg.norm(normals,axis=1)[:,None]
        # Pick a rear-cut base port nearest this attachment, not a magnet lip.
        j=rear[np.argmin(np.linalg.norm(bv[rear]-foot.mean(0),axis=1))]
        source_point=original.vertices[j]
        distance=np.linalg.norm(bv[j]-foot.mean(0))
        if not 3<distance<85:
            raise ValueError(tr('Basis und Auflage liegen zu nah oder zu weit auseinander. Bitte Basis vor der Auflage positionieren.'))
        close=rear[np.linalg.norm(original.vertices[rear]-source_point,axis=1)<3.5]
        port=original.vertices[close]
        if len(port)<4:
            raise ValueError(tr('Keine tragfähige Verbindung an der Basis gefunden. Bitte Position ändern.'))
        ports=np.vstack([port+[0,-1.0,0],port+[0,1.,0]])
        if base_metadata().get('rear_collar_rebuilt'):
            radial=np.array([source_point[0]/77.**2,0.,(source_point[2]-78.)/48.**2])
            radial/=np.linalg.norm(radial)
            ports=np.vstack([ports+radial*.8,ports-radial*.8])
        # Stay behind the protected 8-mm front band, including the foot itself.
        offset=ports[:,1]-depth_curve(contour_angle(ports),'front_depth')
        if base_metadata().get('reference_revision')!=16 and offset.min()<8.5:
            raise ValueError(tr('Eine Verbindung würde die Magnetaufnahme berühren. Bitte Basis neu positionieren.'))
        points=np.vstack([transform(ports,matrix),foot-normals*.45,foot+normals*.9])
        hull=trimesh.convex.convex_hull(points)
        body=Mesh(hull.vertices,hull.faces,f'Bridge {index+1}')
        solid=_manifold(body)
        if protected_solid is not None:
            solid=(solid-protected_solid)-clearance_solid
            trimmed=solid.to_mesh64()
            body=Mesh(trimmed.vert_properties[:,:3],trimmed.tri_verts,body.name)
        if (solid^_manifold(base)).volume()<.05 or (solid^_manifold(support.mesh)).volume()<.05:
            raise ValueError(tr('Eine Verbindung berührt Basis oder Auflage nicht sicher. Bitte Position ändern.'))
        bridges.append(body)
    shell_report={}
    strap_opening = None
    strap_report = {'top_strap_enabled': False}
    if closed_shell:
        progress(62,tr('Geschlossene 1,5-mm-Hülle berechnen …'))
        from .shell import make_shell
        shell,adhesive_guard,shell_report=make_shell(support,matrix,reinforced=integral,head=head,nose_settings=nose_settings)
        shell_solid=_manifold(shell)-_manifold(adhesive_guard)
        if protected_solid is not None:
            shell_solid=(shell_solid-protected_solid)-clearance_solid
        if shell_solid.is_empty() or shell_solid.status()!=mf.Error.NoError:
            raise ValueError(tr('Die Hülle konnte nicht erzeugt werden. Bitte Basisposition prüfen.'))
        sm=shell_solid.to_mesh64()
        bridges.append(Mesh(sm.vert_properties[:,:3],sm.tri_verts,'Light shield'))
        nose = shell_report.pop('_nose_bridge_mesh', None)
        shell_report['nose_baffle_enabled'] = False
        if nose is not None:
            progress(64, tr('Nasenbogen mit Auflage und Basis verbinden …'))
            nose_solid = _manifold(nose)-_manifold(adhesive_guard)
            if protected_solid is not None:
                nose_solid = (nose_solid-protected_solid)-clearance_solid
            voids = _feature_voids()
            if voids is not None:
                nose_solid -= _manifold(Mesh(transform(voids.vertices,matrix),voids.faces,voids.name))
            joins = [float((nose_solid^_manifold(part)).volume()) for part in (base,support.mesh)]
            if nose_solid.status()!=mf.Error.NoError or min(joins)<.1:
                raise ValueError(tr('Der Nasenbogen schließt nicht sicher an Basis und Auflage an.'))
            nm=nose_solid.to_mesh64()
            bridges.append(Mesh(nm.vert_properties[:,:3],nm.tri_verts,'Nose arch'))
            shell_report['nose_attachment_volumes_mm3']=joins
        if top_strap:
            from .top_strap import make_top_strap
            loop, strap_opening, bar, ears, strap_report = make_top_strap(base, shell, matrix, support)
            cutters = [_manifold(adhesive_guard)]
            if protected_solid is not None:
                cutters += [protected_solid, clearance_solid]
            voids = _feature_voids()
            if voids is not None:
                cutters.append(_manifold(Mesh(transform(voids.vertices,matrix),voids.faces,voids.name)))
            def strap_trim(part):
                body = _manifold(part)
                for cutter in cutters:
                    body -= cutter
                return body
            loop_solid = strap_trim(loop)
            root_joins = [[float((strap_trim(ear)^body).volume())
                           for body in (_manifold(base), shell_solid)] for ear in ears]
            rear_joins = [float((strap_trim(ear)^_manifold(support.mesh)).volume()) for ear in ears]
            bar_lost = sum(max(0., p.volume()) for p in (_manifold(bar)-loop_solid).decompose())
            if (loop_solid.status()!=mf.Error.NoError or len(loop_solid.decompose())!=1 or
                    min(min(pair) for pair in root_joins)<1. or min(rear_joins)<1. or bar_lost>1e-4):
                raise ValueError(tr('Die Kopfbandhalterung hat bei dieser Position keinen freien, tragenden Anschluss.'))
            detail = loop_solid.to_mesh64()
            bridges.append(Mesh(detail.vert_properties[:,:3], detail.tri_verts, '37 mm top-strap loop'))
            strap_report['top_strap_root_attachment_volumes_mm3'] = root_joins
            strap_report['top_strap_pad_attachment_volumes_mm3'] = rear_joins
            strap_report['top_strap_bar_trimmed_volume_mm3'] = bar_lost
    shell_report.update(strap_report)
    progress(65,tr('Basis, Verbindungen und Auflage zu einem Druckkörper verbinden …'))
    voids=_feature_voids()
    additions=[_manifold(b) for b in bridges]
    if voids is not None:
        feature_clearance=_manifold(Mesh(transform(voids.vertices,matrix),voids.faces,voids.name))
        additions=[body-feature_clearance for body in additions]
    solid=mf.Manifold.batch_boolean([_manifold(base),_manifold(support.mesh)]+additions,mf.OpType.Add)
    if strap_opening is not None:
        obstruction = sum(max(0., p.volume()) for p in (solid^_manifold(strap_opening)).decompose())
        if obstruction>1e-4:
            raise ValueError(tr('Der 37 × 4 mm große Durchlass der Kopfbandhalterung ist bei dieser Position nicht frei.'))
        shell_report['top_strap_opening_obstruction_mm3'] = obstruction
    pieces=solid.decompose()
    positive=[p for p in pieces if p.volume()>0]
    discarded_offcuts=0.
    if len(positive)>1:
        # Trimming the rounded landing pads can leave offcuts outside both
        # original bodies. Retain only anchored material, never an unattached
        # sphere cap; no source base or cushion material may be discarded.
        anchored=[]
        for part in positive:
            overlap=(part^_manifold(base)).volume()+(part^_manifold(support.mesh)).volume()
            if overlap>1e-5:anchored.append(part)
            else:discarded_offcuts+=part.volume()
        if len(anchored)==1:
            positive=anchored;solid=anchored[0]
    filled_cavities=sum(-p.volume() for p in pieces if p.volume()<0)
    if len(positive)==1 and filled_cavities:
        # Intersecting skins may enclose a tiny sealed air pocket. Fill it;
        # open magnet/strap apertures are not enclosed components. The complete
        # protected-material check below must still pass after this operation.
        solid=positive[0]
    if solid.status()!=mf.Error.NoError or len(solid.decompose())!=1:
        raise ValueError(tr('Der Rahmen konnte nicht zu einem zusammenhängenden Druckkörper verbunden werden.'))
    # Remove sub-micron boolean seams that float32 slicers otherwise split
    # into isolated fragments. All protected-surface checks run afterwards.
    solid=solid.simplify(1e-6)
    output=solid.to_mesh64()
    exact_mesh=trimesh.Trimesh(output.vert_properties[:,:3],output.tri_verts,process=False)
    # Validate at the same precision used by Windows mesh tools and slicers.
    # Manifold resolves triangles collapsed by float32 before serialization.
    printable=solid
    for _ in range(3):
        raw=printable.to_mesh64()
        # Drop boolean provenance boundaries before simplifying numerical
        # seams; those IDs are not part of the printable geometry.
        printable=mf.Manifold(mf.Mesh64(np.array(raw.vert_properties[:,:3],dtype=np.float64,order='C'),
                                        np.array(raw.tri_verts,dtype=np.uint64,order='C')))
        print_mesh=printable.set_tolerance(2e-5).simplify(2e-5).to_mesh()
        rounded=mf.Mesh(np.array(print_mesh.vert_properties,dtype=np.float32,order='C'),
                        np.array(print_mesh.tri_verts,dtype=np.uint32,order='C'))
        rounded.merge();printable=mf.Manifold(rounded)
        print_parts=printable.decompose()
        print_positive=[part for part in print_parts if part.volume()>0]
        if printable.status()==mf.Error.NoError and len(print_positive)>1:
            main=max(print_positive,key=lambda part:part.volume())
            detail=main.to_mesh64()
            main_mesh=trimesh.Trimesh(detail.vert_properties[:,:3],detail.tri_verts,process=False)
            removable=True
            for part in print_positive:
                if part is main:continue
                part_mesh=part.to_mesh64();points=part_mesh.vert_properties[:,:3]
                distance=float(_near(main_mesh,points,lambda *_:None,0).max())
                triangles=points[part_mesh.tri_verts]
                area=float(np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1).sum()/2)
                film_thickness=2*part.volume()/max(area,1e-20)
                # No intentional 1.5-mm wall or magnet housing can be an
                # unattached fragment below 0.001 mm³ / 0.05 mm mean thickness.
                # Protected source vertices and glue surfaces are checked below.
                if part.volume()>.001 or (distance>1e-4 and film_thickness>.05):
                    import logging
                    logging.error('Numerical fragment volume %s, maximum surface distance %s',part.volume(),distance)
                    removable=False;break
            if removable:
                printable=main;print_parts=[main];print_positive=[main]
        if printable.status()==mf.Error.NoError and len(print_positive)==1 and len(print_parts)>1:
            printable=print_positive[0]
        if printable.status()!=mf.Error.NoError or len(printable.decompose())!=1:
            import logging
            logging.error('Print mesh status %s; component volumes %s',printable.status(),[p.volume() for p in printable.decompose()])
            raise ValueError(tr('Der Rahmen enthält ungültige Druckgeometrie.'))
        output=printable.to_mesh64()
        mesh=trimesh.Trimesh(output.vert_properties[:,:3],output.tri_verts,process=False)
        if mesh.area_faces.min()>0:break
    # Positive-area sliver triangles are valid. Reject zero-area faces;
    # serialization is separately checked by the STL/3MF roundtrip tests.
    if not mesh.is_volume or not mesh.is_winding_consistent or mesh.area_faces.min()<=0:
        raise ValueError(tr('Der Rahmen enthält ungültige Druckgeometrie.'))
    # Indexed 3MF may hide coincident distinct vertices which STL welds.
    # Separate only those numeric seams, preserving topology and geometry
    # within the same 0.0001 mm interface tolerance checked below.
    from .floatmesh import float_safe
    try:
        safe_vertices,safe_faces,encoding=float_safe(mesh.vertices,mesh.faces,max_change=.00009)
    except AssertionError as exc:
        raise ValueError(tr('Der Rahmen enthält ungültige Druckgeometrie.')) from exc
    mesh=trimesh.Trimesh(safe_vertices,safe_faces,process=False)
    shell_report['float_export']=encoding
    rib_probes=np.asarray(shell_report.pop('_rib_probe_points',[]))
    rib_solids=shell_report.pop('_rib_solids',[])
    if rib_solids:
        verified_joins=[]
        for rib_mesh in rib_solids:
            # The slice is a diagnostic envelope, not separately added
            # material. Interpolated slice faces can extend micrometres past
            # the triangulated shell. Verify the actual rib in the shell.
            rib=_manifold(rib_mesh)^shell_solid
            if voids is not None:rib=rib-feature_clearance
            positive=[p for p in rib.decompose() if p.volume()>1e-5]
            joins=[float((rib^_manifold(b)).volume()) for b in (base,support.mesh)]
            if len(positive)!=1 or min(joins)<.01:
                import logging
                logging.error('Trimmed rib components %s; end joins %s',[p.volume() for p in positive],joins)
                raise ValueError(tr('Eine Verbindung berührt Basis oder Auflage nicht sicher. Bitte Position ändern.'))
            residual=rib-solid
            residual_volume=sum(max(0.,p.volume()) for p in residual.decompose())
            if residual_volume>.001:
                import logging
                logging.error('Rib residual volume %s; rib volume %s; index %s',residual_volume,rib.volume(),len(verified_joins))
                raise ValueError(tr('Eine Verbindung berührt Basis oder Auflage nicht sicher. Bitte Position ändern.'))
            verified_joins.append(joins)
        shell_report['rib_attachment_volumes_mm3']=verified_joins
        shell_report['rib_spines_after_trimming_checked']=True
        shell_report['rib_connected_solids_after_trimming_checked']=True
    elif len(rib_probes):
        if not mesh.contains(rib_probes).all():
            raise ValueError(tr('Eine Verbindung berührt Basis oder Auflage nicht sicher. Bitte Position ändern.'))
        shell_report['rib_spines_after_trimming_checked']=True
    progress(72,tr('Unveränderte Magnetaufnahme und Polsterfläche prüfen …'))
    mating_depth=base_metadata().get('mating_surface_depth_mm',base_metadata().get('protected_front_band_mm',8.))
    guard=_front_guard(mating_depth)
    guard_world=Mesh(transform(guard.vertices,matrix),guard.faces,guard.name)
    # A union cannot remove original material. Reject any added material in the
    # protected envelope, rather than relying only on a few surface samples.
    intrusion=(solid-_manifold(base))^_manifold(guard_world)
    # Coincident OEM facets may leave inverted zero-thickness residual shells
    # after a boolean subtraction. They cannot represent added material.
    # Sum positive components separately so a negative residual cannot cancel
    # a real intrusion. Exact protected vertices and surface checks follow.
    added_volume=sum(max(0.,part.volume()) for part in intrusion.decompose())
    # Coincident faces can leave a thin positive residual over a large area.
    # Bound its actual protrusion, rather than treating a picometre-thick sheet
    # as equivalent to a real bump of the same volume.
    added_offset=0.
    if added_volume>1e-5:
        for part in intrusion.decompose():
            if part.volume()<=1e-9:continue
            detail=part.to_mesh64();points=detail.vert_properties[:,:3]
            faces=detail.tri_verts
            probes=np.vstack([points,points[faces].mean(1),points[faces[:,[0,1]]].mean(1),
                              points[faces[:,[1,2]]].mean(1),points[faces[:,[2,0]]].mean(1)])
            added_offset=max(added_offset,float(_near(base_mesh,probes,progress,73).max()))
        if added_offset>.001:
            raise ValueError(tr('Die Magnetaufnahme würde verändert. Diese Basisposition kann nicht exportiert werden.')+f' ({added_offset:.6g} mm)')
    # The rear construction cut is not an HMD contact face. Check all source
    # vertices and face centres in the actual mating band, including faces
    # crossing its boundary, rather than including the artificial rear cap.
    fixed=bv[base_offset<mating_depth]
    # Preserve geometry rather than requiring identical tessellation. Planar
    # vertices may disappear when a boolean seam is retriangulated.
    nearest_vertex=cKDTree(mesh.vertices).query(fixed)[0]
    missing=nearest_vertex>1e-6
    vertex_error=float(nearest_vertex[~missing].max(initial=0.))
    if missing.any():
        vertex_error=max(vertex_error,float(_near(mesh,fixed[missing],progress,75).max()))
    local_centres=original.vertices[original.faces].mean(1)
    centre_offset=local_centres[:,1]-depth_curve(contour_angle(local_centres),'front_depth')
    centres=bv[original.faces[centre_offset<mating_depth]].mean(1)
    centres=centres[np.linspace(0,len(centres)-1,min(2000,len(centres))).astype(int)]
    error=_near(mesh,centres,progress,75)
    # The remeshed OEM collar contains near-coplanar boolean seams. Bound
    # their numerical surface comparison to at most 0.0001 mm (0.1 micron),
    # while retaining the independent added-volume and pocket checks.
    interface_tolerance=min(1e-4,max(1e-6,base_metadata().get('interface_verification_tolerance_mm',1e-6)))
    if max(error.max(),vertex_error)>interface_tolerance:
        import logging
        logging.error('Interface source vertex error %s; source face error %s',vertex_error,float(error.max()))
        if missing.any():
            distances=_near(mesh,fixed[missing],lambda *_:None,0)
            worst=transform(fixed[missing][[int(np.argmax(distances))]],np.linalg.inv(matrix))
            logging.error('Worst source point %s; front depth offset %s',worst.tolist(),(worst[:,1]-depth_curve(contour_angle(worst),'front_depth')).tolist())
        raise ValueError(tr('Die Magnetaufnahme würde verändert. Diese Basisposition kann nicht exportiert werden.'))
    # Check the complete adhesive surface, including triangle interiors.
    adhesive=np.vstack([support.contact,support.contact[support.surface_faces].mean(1)])
    pad_error=_near(exact_mesh,adhesive,progress,90)
    print_pad_error=_near(mesh,adhesive,progress,90)
    if pad_error.max()>1e-5 or print_pad_error.max()>1e-4:
        raise ValueError(tr('Eine Verbindung überdeckt die Polsterfläche. Bitte Basis neu positionieren.'))
    combined=trimesh.util.concatenate([trimesh.Trimesh(b.vertices,b.faces,process=False) for b in bridges])
    report=dict(mode='probe07_closed_shell' if closed_shell else 'probe06_stability_frame',base_pose=pose.tolist(),support=support.report,
                base_source=base_metadata(),bridge_count=shell_report.get("rib_count",7),closed=True,connected_components=1,
                nominal_support_thickness_mm=1.5,magnetic_surface_max_error_mm=float(error.max()),
                interface_verification_tolerance_mm=float(interface_tolerance),
                filled_internal_cavities_mm3=float(filled_cavities),
                trimmed_unattached_offcuts_mm3=float(discarded_offcuts),
                protected_vertex_max_error_mm=float(vertex_error),protected_added_volume_mm3=float(added_volume),
                protected_added_material_max_offset_mm=float(added_offset),
                protected_added_material_tolerance_mm=.001,
                protected_boolean_signed_residual_mm3=float(intrusion.volume()),
                adhesive_surface_max_error_mm=float(pad_error.max()),vertices=len(mesh.vertices),faces=len(mesh.faces),
                print_adhesive_surface_max_error_mm=float(print_pad_error.max()),
                print_surface_tolerance_mm=1e-4,
                optical_registration=False,hmd_scan_registration=False,mechanical_strength_verified=False,
                scope=('Closed U-shaped light shield with open nose and viewing aperture. Magnet and adhesive surfaces unchanged.' if closed_shell else 'Open stability prototype, not the final closed light shield. Magnet and adhesive surfaces unchanged.'),
                **shell_report,
                warnings=list(support.report['warnings']))
    progress(100,tr('Probe 07 mit geschlossener Hülle berechnet.') if closed_shell else tr('Probe 06 als geschlossener Druckkörper berechnet.'))
    return AssemblyResult(Mesh(mesh.vertices.copy(),mesh.faces.copy(),'PFDMR Probe 07' if closed_shell else 'PFDMR Probe 06'),
                          Mesh(combined.vertices,combined.faces,'Rear bridges'),base,report)
