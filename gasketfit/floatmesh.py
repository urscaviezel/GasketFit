"""Preserve mesh topology while encoding coordinates in STL float32.
Only coordinates which would collapse or create zero-area facets are separated
by micrometres; no surfaces are reconstructed and no holes are filled.
"""
import numpy as np,trimesh
def float_safe(vertices,faces,max_change=.00015):
    raw=np.asarray(vertices,dtype=float);faces=np.asarray(faces,dtype=np.int64)
    q=raw.astype(np.float32).astype(float);step=.00002
    adjusted=np.zeros(len(q),bool)
    for iteration in range(40):
        unique,inv,counts=np.unique(q,axis=0,return_inverse=True,return_counts=True)
        groups=np.flatnonzero(counts>1)
        for group in groups:
            ids=np.flatnonzero(inv==group);pts=raw[ids];mid=pts.mean(axis=0)
            _,_,v=np.linalg.svd(pts-mid,full_matrices=False)
            direction=v[0]
            order=np.argsort((pts-mid)@direction)
            for j,idx in enumerate(ids[order]):
                shift=(j-(len(ids)-1)/2)*step*1.5
                q[idx]=(mid+direction*shift).astype(np.float32).astype(float)
            adjusted[ids]=True
        tri=q[faces];n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);zero=np.flatnonzero(np.linalg.norm(n,axis=1)==0)
        if not len(groups) and not len(zero):break
        for fidx in zero:
            ids=faces[fidx];p=q[ids];rp=raw[ids]
            lengths=np.linalg.norm(p[[1,2,0]]-p,axis=1);edge=int(lengths.argmax());a=edge;b=(edge+1)%3;c=(edge+2)%3
            normal=np.cross(rp[1]-rp[0],rp[2]-rp[0]);normal/=np.linalg.norm(normal)
            along=p[b]-p[a];along/=np.linalg.norm(along)
            direction=np.cross(normal,along);direction/=np.linalg.norm(direction)
            # Keep the longitudinal location, only restore a representable height.
            projection=p[a]+along*np.dot(p[c]-p[a],along)
            q[ids[c]]=(projection+direction*step).astype(np.float32).astype(float)
            adjusted[ids[c]]=True
        if np.linalg.norm(q-raw,axis=1).max()>max_change:
            raise AssertionError('Finite precision mesh exceeds movement budget')
    else:raise AssertionError('Finite precision mesh did not converge')
    assert len(np.unique(q,axis=0))==len(q)
    tri=q[faces];assert np.all(np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)>0)
    original=trimesh.Trimesh(raw,faces,process=False);encoded=trimesh.Trimesh(q,faces,process=False)
    assert encoded.is_volume and encoded.euler_number==original.euler_number
    assert len(encoded.split(only_watertight=False))==len(original.split(only_watertight=False))
    return q,faces,dict(adjusted_vertices=int(adjusted.sum()),iterations=iteration+1,max_coordinate_change_mm=float(np.linalg.norm(q-raw,axis=1).max()),euler_number=encoded.euler_number)
