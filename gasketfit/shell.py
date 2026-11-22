"""A 1.5 mm U-shaped light shield between rear base cap and pad backing.

Nose and viewing aperture remain open. Nothing is projected onto the head.
The actual fitted adhesive surface and magnetic base are immutable inputs.
"""
from functools import lru_cache
import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union
from shapely.prepared import prep
from .meshio import Mesh
from .profile import contour_angle,depth_curve,transform
from .localization import tr


def _segments(geometry):
    if geometry.geom_type=='LineString':
        return [geometry] if geometry.length>1e-8 else []
    return [s for g in getattr(geometry,'geoms',[]) for s in _segments(g)]


@lru_cache(maxsize=1)
def _rear_cap():
    from .assembly import base_reference,base_metadata
    if base_metadata().get('rear_collar_rebuilt'):
        from pathlib import Path
        data=np.load(Path(__file__).with_name('pfd_rear_cap.npz'))
        vertices=data['vertices'];faces=data['faces']
        footprint=unary_union([Polygon(q[:,[0,2]]) for q in vertices[faces]])
        chart_vertices=vertices.copy();chart_vertices[:,1]=0
        return vertices,faces,footprint,trimesh.Trimesh(chart_vertices,faces,process=False)
    base=base_reference()
    mesh=trimesh.Trimesh(base.vertices,base.faces,process=False)
    offset=base.vertices[:,1]-depth_curve(contour_angle(base.vertices),'front_depth')
    keep=(offset[base.faces].min(1)>11.8)&(mesh.face_normals[:,1]>.2)
    if base_metadata().get('profile')=='oem_v2':
        keep&=base.vertices[base.faces,2].max(1)<113.
    if base_metadata().get('rear_collar_rebuilt'):
        keep&=(offset[base.faces].min(1)>12.7)&(offset[base.faces].max(1)<13.3)
    faces=base.faces[keep]
    polygons=[Polygon(q[:,[0,2]]) for q in base.vertices[faces]]
    footprint=unary_union([p for p in polygons if p.area>1e-10])
    chart_vertices=base.vertices.copy();chart_vertices[:,1]=0
    chart=trimesh.Trimesh(chart_vertices,faces,process=False)
    return base.vertices,faces,footprint,chart


def _pad_path(support,count=241):
    polygon=Polygon(support.flat[:420])
    angles=np.linspace(-np.pi/2,3*np.pi/2,1441)
    points=[];valid=[]
    for angle in angles:
        line=LineString([[0,78],[330*np.cos(angle),78+150*np.sin(angle)]])
        pieces=_segments(polygon.intersection(line))
        piece=max(pieces,key=lambda p:p.length) if pieces else None
        valid.append(piece is not None and piece.length>5)
        points.append(piece.interpolate(.5,normalized=True).coords[0] if piece is not None else [0,78])
    valid=np.asarray(valid)
    # Keep the single long route around forehead/temples/cheeks, excluding nose.
    changes=np.diff(np.r_[False,valid,False].astype(int))
    starts=np.flatnonzero(changes==1);ends=np.flatnonzero(changes==-1)
    if not len(starts):
        raise ValueError(tr('Keine durchgehende Hüllenauflage gefunden.'))
    i=np.argmax(ends-starts);start,end=starts[i],ends[i]-1
    if angles[end]-angles[start]<np.pi:
        raise ValueError(tr('Keine durchgehende Hüllenauflage gefunden.'))
    position=np.linspace(start,end,count)
    points=np.asarray(points)
    uv=np.column_stack([np.interp(position,np.arange(len(points)),points[:,k]) for k in (0,1)])
    return uv


def _solid_layers(a,b,faces):
    n=len(a)
    edges=np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
    _,inverse,counts=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
    boundary=edges[counts[inverse]==1]
    ff=np.vstack([faces,faces[:,::-1]+n,
                  np.c_[boundary[:,0],boundary[:,1]+n,boundary[:,1]],
                  np.c_[boundary[:,0],boundary[:,0]+n,boundary[:,1]+n]])
    mesh=trimesh.Trimesh(np.vstack([a,b]),ff,process=False)
    if mesh.volume<0:mesh.invert()
    return Mesh(mesh.vertices,mesh.faces,'Closed shell')


def _lower_pad_ends(route, boundary, span=32.):
    """Continue each rear shell edge to its rectangular pad's lower corner.

    Only the terminal strip changes. Hermite endpoints share position and
    tangent with the existing route; no added flange or separate end patch.
    """
    from scipy.interpolate import CubicHermiteSpline
    from shapely.geometry import Point
    route = np.asarray(route).copy()
    boundary = np.asarray(boundary)
    following = np.roll(boundary, -1, axis=0)
    terminal = ((abs(following[:, 0]-boundary[:, 0]) < 1e-7)
                & (abs(following[:, 1]-boundary[:, 1]) > 1.)
                & (abs(boundary[:, 0]) < 50.)
                & (np.maximum(boundary[:, 1], following[:, 1]) < 55.))
    polygon = Polygon(boundary)
    changed = np.zeros(len(route), dtype=bool)
    for reverse in (False, True):
        work = route[::-1].copy() if reverse else route.copy()
        sign = np.sign(work[0, 0])
        ids = np.flatnonzero(terminal & (np.sign(boundary[:, 0]) == sign))
        if not len(ids):
            raise ValueError('Rectangular pad terminal edge not found')
        corners = np.vstack([boundary[ids], following[ids]])
        corner = corners[np.argmin(corners[:, 1])].copy()
        # Bury the shell skin 0.03 mm inside the pad boundary for a solid union.
        corner += [sign*.03, .03]
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(work, axis=0), axis=1))]
        j = int(np.searchsorted(arc, span))
        tangent = (work[j+1]-work[j-1])/(arc[j+1]-arc[j-1])
        curve = CubicHermiteSpline([0., arc[j]], [corner, work[j]],
                                  [[sign*.8, 0.], tangent])
        work[:j+1] = curve(arc[:j+1])
        if not all(polygon.covers(Point(q)) for q in work[:j+1]):
            raise ValueError('Lower shell edge leaves pad boundary')
        if np.min(np.diff(work[:j+1, 1])) < -1e-8:
            raise ValueError('Lower shell edge rises before reaching pad corner')
        if reverse:
            route[-j-1:] = work[:j+1][::-1]
            changed[-j-1:] = True
        else:
            route[:j+1] = work[:j+1]
            changed[:j+1] = True
    return route, changed


def make_shell(support,matrix,*,reinforced=False,head=None,nose_settings=None):
    uv=_pad_path(support,count=481 if reinforced else 241)
    # Keep the narrow attachment as the main wall's lateral guide. Only
    # the last short section reaches the rear rim of the actual pad backing.
    from shapely.geometry import Point
    temple_weight=np.clip((np.abs(uv[:,0])-60.)/30.,0.,1.)
    temple_weight=temple_weight**2*(3.-2.*temple_weight)
    temple_weight*=np.exp(-((uv[:,1]-78.)/23.)**4)
    rear_uv=uv.copy();pad_polygon=Polygon(support.flat[:420])
    for i,(point,weight) in enumerate(zip(uv,temple_weight)):
        if weight<=0:continue
        ray=LineString([[0,78],np.array([0.,78.])+(point-[0,78])*5])
        piece=min(_segments(pad_polygon.intersection(ray)),key=lambda q:q.distance(Point(point)))
        ends=np.asarray(piece.coords)[[0,-1]]
        outer=ends[np.argmax(np.linalg.norm(ends-[0,78],axis=1))]
        direction=outer-point;direction/=np.linalg.norm(direction)
        rear_uv[i]=(1-weight)*point+weight*(outer-direction*1.)
    n=len(support.contact)
    backing=support.mesh.vertices[n:]
    normals=backing-support.contact
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    chart=trimesh.Trimesh(np.c_[support.flat,np.zeros(n)],support.surface_faces,process=False)
    def pad_attachment(points):
        near,distance,tri=trimesh.proximity.ProximityQuery(chart).on_surface(np.c_[points,np.zeros(len(points))])
        if distance.max()>1e-5:
            raise ValueError(tr('Die Hüllenauflage verlässt die Polsterkante.'))
        bary=trimesh.triangles.points_to_barycentric(chart.triangles[tri],near)
        ids=support.surface_faces[tri]
        norm=(normals[ids]*bary[:,:,None]).sum(1)
        norm/=np.linalg.norm(norm,axis=1)[:,None]
        return (backing[ids]*bary[:,:,None]).sum(1)-norm*.4,norm
    narrow_foot,_=pad_attachment(uv)
    foot,norm=pad_attachment(rear_uv)
    # Preserve the approved base route, independent of the rear rim target.
    local=transform(narrow_foot,np.linalg.inv(matrix))
    angle=np.unwrap(contour_angle(local))
    if (np.diff(angle)<-.01).any():
        raise ValueError(tr('Basis und Auflage sind für eine durchgehende Hülle zu stark gegeneinander verdreht.'))
    if reinforced:angle=gaussian_filter1d(angle,6.,mode='nearest')
    # Base registration still uses the untouched original route above.
    # Both shell guides now use the same new pad end, so there is no delayed
    # downward jog or stacked connection at the rectangular terminal face.
    previous_rear_uv = rear_uv.copy()
    rear_uv, lowered_ends = _lower_pad_ends(rear_uv, support.flat[:420])
    narrow_uv = uv + rear_uv-previous_rear_uv
    narrow_foot, _ = pad_attachment(narrow_uv)
    foot, norm = pad_attachment(rear_uv)

    vertices,cap_faces,footprint,cap_chart=_rear_cap()
    candidates=[]
    for a in angle:
        line=LineString([[0,78],[231*np.cos(a),78+144*np.sin(a)]])
        pieces=_segments(footprint.intersection(line))
        if not pieces:
            raise ValueError(tr('Die Hülle findet keinen Anschluss an der Magnetbasis.'))
        candidates.append(np.array([s.interpolate(t,normalized=True).coords[0]
                                    for s in pieces for t in (.12,.3,.5,.7,.88)]))
    # Follow the continuous cap corridor, rather than jumping to headband
    # stubs or across vent notches when the longest radial interval changes.
    prepared=prep(footprint)
    costs=np.zeros(len(candidates[0]));parents=[]
    for previous,current in zip(candidates[:-1],candidates[1:]):
        new=np.full(len(current),np.inf);parent=np.full(len(current),-1,dtype=int)
        for j,q in enumerate(current):
            for k,p in enumerate(previous):
                cost=costs[k]+np.square(q-p).sum()
                if cost<new[j] and prepared.covers(LineString([p,q])):
                    new[j]=cost;parent[j]=k
        if not np.isfinite(new).any():
            raise ValueError(tr('Die Hülle findet keinen durchgehenden Anschluss an der Magnetbasis.'))
        parents.append(parent);costs=new
    index=int(np.argmin(costs));path=[candidates[-1][index]]
    for i,parent in reversed(list(enumerate(parents))):
        index=parent[index];path.append(candidates[i][index])
    path=np.asarray(path[::-1]);queries=np.c_[path[:,0],np.zeros(len(path)),path[:,1]]
    from .assembly import base_metadata
    if base_metadata().get('rear_collar_rebuilt'):
        from shapely.geometry import Point
        centred=[]
        for point,a in zip(path,angle):
            pieces=_segments(footprint.intersection(LineString([[0,78],[231*np.cos(a),78+144*np.sin(a)]])))
            piece=min(pieces,key=lambda s:s.distance(Point(point)))
            centred.append(piece.interpolate(.5,normalized=True).coords[0])
        path=np.asarray(centred)
    # The outer skin terminates at the actual outer edge of the approved
    # rear build-up. Do not blur this contour back toward the cap centre.
    edge_path=[]
    for point,a in zip(path,angle):
        pieces=_segments(footprint.intersection(LineString([[0,78],[231*np.cos(a),78+144*np.sin(a)]])))
        piece=min(pieces,key=lambda s:s.distance(Point(point)))
        ends=np.asarray(piece.coords)[[0,-1]]
        outer=ends[np.argmax(np.linalg.norm(ends-[0,78],axis=1))]
        inward=np.asarray(piece.interpolate(.5,normalized=True).coords[0])-outer
        inward/=np.linalg.norm(inward)
        edge_path.append(outer+inward*.005)
    path=np.asarray(edge_path)
    smoothing_sigma=0.
    attachment_step_change=float(np.linalg.norm(np.diff(path,n=2,axis=0),axis=1).max())
    queries=np.c_[path[:,0],np.zeros(len(path)),path[:,1]]
    near,distance,tri=trimesh.proximity.ProximityQuery(cap_chart).on_surface(queries)
    if distance.max()>1e-5:
        raise ValueError(tr('Die Hülle findet keinen Anschluss an der Magnetbasis.'))
    bary=trimesh.triangles.points_to_barycentric(cap_chart.triangles[tri],near)
    ports=(vertices[cap_faces[tri]]*bary[:,:,None]).sum(1)
    ports[:,1]-=.4
    ports=transform(ports,matrix)
    from .assembly import base_reference
    source=base_reference()
    base_mesh=trimesh.Trimesh(transform(source.vertices,matrix),source.faces,process=False)
    pad_mesh=trimesh.Trimesh(support.mesh.vertices,support.mesh.faces,process=False)
    # Check both seam centres and the segments between them, not just global
    # connectedness through the existing upper ribs.
    base_seam=np.vstack([ports,(ports[:-1]+ports[1:])/2])
    pad_seam=np.vstack([foot,(foot[:-1]+foot[1:])/2])
    if not base_mesh.contains(base_seam).all() or not pad_mesh.contains(pad_seam).all():
        raise ValueError(tr('Die Hülle schließt nicht lückenlos an Basis und Auflage an. Bitte Basisposition prüfen.'))
    length=np.linalg.norm(foot-ports,axis=1)
    if length.min()<3 or length.max()>85:
        raise ValueError(tr('Basis und Auflage liegen für die Hülle zu nah oder zu weit auseinander.'))
    # The outer skin controls the appearance; thickness and ribs face inward.
    t=np.linspace(0,1,65)
    # Start parallel to the outer base wall, so there is no ledge or abrupt
    # change of direction. Keep longitudinal depth monotonic in base space.
    h=t*t*(3-2*t)
    local_ports=transform(ports,np.linalg.inv(matrix))
    local_foot=transform(foot,np.linalg.inv(matrix))
    local_narrow_foot=transform(narrow_foot,np.linalg.inv(matrix))
    local_skin=local_ports[:,None,:]*(1-h[None,:,None])+local_narrow_foot[:,None,:]*h[None,:,None]
    local_skin[:,:,1]=local_ports[:,None,1]*(1-t)+local_foot[:,None,1]*t
    # A single smooth monotone transition; no local squeeze or flare shoulder.
    # Cubic growth keeps the extra lateral movement small through the body.
    delta=local_foot-local_narrow_foot;delta[:,1]=0
    local_skin+=delta[:,None,:]*(t**3)[None,:,None]
    surface=transform(local_skin.reshape(-1,3),matrix).reshape(local_skin.shape)
    u_count=len(surface);nose_report={}
    du=np.gradient(surface,axis=0);dv=np.gradient(surface,axis=1)
    normal=np.cross(du,dv)
    normal/=np.maximum(np.linalg.norm(normal,axis=2)[:,:,None],1e-12)
    ribs=np.zeros(surface.shape[:2])
    rib_profiles=[]
    rib_probes=[]
    if reinforced:
        radial=transform(surface.reshape(-1,3),np.linalg.inv(matrix)).reshape(surface.shape)
        radial[:,:,1]=0;radial[:,:,2]-=78
        radial=radial@matrix[:3,:3].T
        if np.median((normal[:u_count]*radial[:u_count]).sum(2))<0:normal*=-1
        arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(surface[:u_count].mean(1),axis=0),axis=1))]
        local_surface=transform(surface.reshape(-1,3),np.linalg.inv(matrix)).reshape(surface.shape)
        for fraction in [.375,.5,.625]:
            centres=np.full(len(t),fraction*arc[-1])
            distance=abs(arc[:,None]-centres[None,:])
            # Flat-topped rectangular ribs continue to both interfaces.
            # A narrow triangulated shoulder represents a square edge without
            # separate coincident side faces or rounded/fading end caps.
            bump=2.5*np.clip((3.-distance)/.15,0.,1.)
            ribs+=bump
            rib_profiles.append(bump)
    rows=np.arange(len(surface)-1)
    cells=(rows[:,None]*len(t)+np.arange(len(t)-1)).ravel()
    next_cells=(((rows+1)%len(surface))[:,None]*len(t)+np.arange(len(t)-1)).ravel()
    faces=np.vstack([np.c_[cells,next_cells,next_cells+1],np.c_[cells,next_cells+1,cells+1]])
    outer=surface.reshape(-1,3)
    inner_grid=surface-normal*(1.5+ribs)[:,:,None]
    # The entire inner side is a true inward offset of the outer skin.
    # Keep rib end material continuous; exact source guards trim only the
    # adhesive-side excess during the assembly union.
    signed_depth=((surface-inner_grid)*normal).sum(2)
    if signed_depth.min()<1.49:
        raise ValueError(tr('Die Hülle würde lokal zu dünn. Bitte Basisposition prüfen.'))
    inner=inner_grid.reshape(-1,3)
    shell=_solid_layers(inner,outer,faces)
    if reinforced:
        for bump in rib_profiles:
            for j in range(1,len(t)-1):
                k=int(np.argmax(bump[:,j]))
                rib_probes.append((surface[k,j]*.5+inner_grid[k,j]*.5).tolist())
    opposite=trimesh.Trimesh(outer,faces,process=False)
    checks=(surface-normal*1.5)[4:-4:4][:,[16,32,48]].reshape(-1,3)
    distances=[]
    query=trimesh.proximity.ProximityQuery(opposite)
    for i in range(0,len(checks),40):
        distances.extend(query.on_surface(checks[i:i+40])[1])
    minimum=float(np.min(distances))
    if minimum<1.4:
        import logging
        logging.error('Thin inner sections %s',np.c_[checks,np.asarray(distances)][np.asarray(distances)<1.4].tolist())
        raise ValueError(tr('Die Hülle würde lokal zu dünn. Bitte Basisposition prüfen.'))
    attachments=[];rib_solids=[]
    if reinforced:
        # Ribs are the inward thickness of the same continuous shell, including
        # the two end sections buried in the base and pad. No separate feet.
        from .assembly import _manifold
        base_solid=_manifold(Mesh(base_mesh.vertices,base_mesh.faces,'Base'))
        pad_solid=_manifold(support.mesh)
        for bump in rib_profiles:
            selected=np.flatnonzero((bump>0).any(1))
            lo=max(0,selected[0]-1);hi=min(u_count,selected[-1]+2)
            # Verify the continuous load-bearing root, below the crown.
            # A cap-only diagnostic can split after legitimate rounding.
            a=(surface[lo:hi]-normal[lo:hi]*1.6).reshape(-1,3)
            b=(surface[lo:hi]-normal[lo:hi]*1.9).reshape(-1,3)
            rr=np.arange(hi-lo-1);cc=(rr[:,None]*len(t)+np.arange(len(t)-1)).ravel()
            ff=np.vstack([np.c_[cc,cc+len(t),cc+len(t)+1],np.c_[cc,cc+len(t)+1,cc+1]])
            rib_mesh=_solid_layers(a,b,ff)
            rib_solids.append(rib_mesh)
            ridge=_manifold(rib_mesh)
            volumes=[float((ridge^body).volume()) for body in (base_solid,pad_solid)]
            if min(volumes)<.01:
                import logging
                logging.error('Rib join volumes %s, index %s',volumes,len(attachments))
                raise ValueError(tr('Eine Verbindung berührt Basis oder Auflage nicht sicher. Bitte Position ändern.'))
            attachments.append(volumes)
    if reinforced:
        # Full circular crown, retaining the existing 6 mm foot width,
        # 2.5 mm total height and a 0.5 mm uncut lower rib root. The two
        # corner cuts meet at the apex: there is no flat central strip.
        from .assembly import _manifold
        import manifold3d as mf
        corner_cutters=[]
        half_width=3.;root_height=.5;rise=2.5-root_height
        radius=(half_width**2+rise**2)/(2*rise)
        theta=np.linspace(0,np.arcsin(half_width/radius),25)
        distance=np.r_[radius*np.sin(theta),half_width+.025,5.]
        cap_height=np.r_[2.5-radius+radius*np.cos(theta),0.,0.]
        for fraction in [.375,.5,.625]:
            centre=fraction*arc[-1]
            for side in (-1,1):
                sample=centre+side*distance
                skin=np.empty((len(sample),len(t),3));nn=np.empty_like(skin)
                for j in range(len(t)):
                    for k in range(3):
                        skin[:,j,k]=np.interp(sample,arc,surface[:,j,k])
                        nn[:,j,k]=np.interp(sample,arc,normal[:,j,k])
                nn/=np.linalg.norm(nn,axis=2)[:,:,None]
                ceiling=skin-nn*(1.5+cap_height)[:,None,None]
                deep=skin-nn*6.5
                cells=(np.arange(len(sample)-1)[:,None]*len(t)+np.arange(len(t)-1)).ravel()
                ff=np.vstack([np.c_[cells,cells+len(t),cells+len(t)+1],np.c_[cells,cells+len(t)+1,cells+1]])
                corner_cutters.append(_manifold(_solid_layers(ceiling.reshape(-1,3),deep.reshape(-1,3),ff)))
        # Clean all of the old triangulated shoulder outside the intended
        # crown width. Restore the exact existing wall beneath the cuts, so
        # the cleanup can never gouge its inner or outer surface.
        wall=_manifold(_solid_layers((surface-normal*1.5).reshape(-1,3),outer,faces))
        rounded=wall+(_manifold(shell)-mf.Manifold.batch_boolean(corner_cutters,mf.OpType.Add))
        data=rounded.to_mesh64();shell=Mesh(data.vert_properties[:,:3],data.tri_verts,'Shell with upper rib-edge fillets')
    # Exact adhesive-side guard, extruded along its original face direction.
    pose=np.asarray(support.report.get('parameters',{}).get('pose',[0,0,0,0,0,0]))
    from .profile import pose_matrix
    direction=pose_matrix(pose)[:3,1]
    guard=_solid_layers(support.contact,support.contact+direction*100,support.surface_faces)
    nose_report={'nose_bridge_enabled': False}
    if reinforced and (nose_settings or {}).get('bridge_enabled', True):
        from .nose_bridge import make_nose_bridge
        bridge, nose_report = make_nose_bridge(support, matrix, surface, inner_grid,
            fill_pockets=(nose_settings or {}).get('fill_pockets', True))
        nose_report['_nose_bridge_mesh'] = bridge
    return shell,guard,dict(nominal_shell_thickness_mm=1.5,sampled_shell_thickness_min_mm=minimum,
                            shell_seams_checked=True,shell_path_samples=len(uv),
                            shell_attachment_max_step_change_mm=attachment_step_change,
                            shell_attachment_smoothing_sigma=smoothing_sigma,
                            ribs_inside=True,separate_rib_feet=False,base_attachment_outer_edge=True,
                            temple_main_wall_narrow=True,temple_transition="monotone_cubic",temple_pad_rim_target_mm=1.,
                            inner_skin_min_inward_offset_mm=float(signed_depth.min()),
                            lower_shell_ends_to_pad_corner=True,lower_shell_end_transition_mm=32.,
                            nose_open=True,connection_span_mm=[float(length.min()),float(length.max())],
                            integral_rounded_ribs=False,integral_square_ribs=reinforced,rib_count=3 if reinforced else 0,side_ribs_enabled=False,
                            rib_added_height_mm=2.5 if reinforced else 0.,
                            rib_top_edge_radius_mm=3.25 if reinforced else 0.,rib_flat_top_width_mm=0.,
                            rib_uncut_root_height_mm=.5,lower_ribs_enabled=False,rib_side_rails_removed=True,
                            rib_attachment_volumes_mm3=attachments,
                            _rib_probe_points=rib_probes,_rib_solids=rib_solids,
                            nose_seam_base_local=transform(ports[[0,-1]],np.linalg.inv(matrix)).tolist(),
                            nose_seam_pad_local=transform(foot[[0,-1]],np.linalg.inv(matrix)).tolist(),
                            **nose_report)
