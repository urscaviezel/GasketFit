"""Physical trial workflow: no inferred head mesh or collision claims."""
from pathlib import Path
from .localization import tr
import json
import numpy as np
import trimesh
from .meshio import Mesh
from .padfit import PadResult
from .profile import pose_matrix,transform
from .pad_alignment import pose_from_alignment
from . import forehead
from .assembly import _manifold

RADII=(140.,110.,85.)

def arc_filename(radius,mark):
    return f'Stirnbogen_R{radius:g}mm_{mark}_Punkte.3mf'

def radius_engraving(radius):
    """Shallow strokes on the front; readable without a companion file."""
    import manifold3d as mf
    strokes={'a':((0,3),(1.6,3)),'b':((1.6,3),(1.6,1.5)),
             'c':((1.6,1.5),(1.6,0)),'d':((0,0),(1.6,0)),
             'e':((0,0),(0,1.5)),'f':((0,1.5),(0,3)),'g':((0,1.5),(1.6,1.5))}
    digits=['abcdef','bc','abdeg','abcdg','bcfg','acdfg','acdefg','abc','abcdefg','abcdfg']
    text='R'+format(radius,'g');parts=[]
    for index,char in enumerate(text):
        paths=([((0,0),(0,3)),((0,3),(1.6,3)),((1.6,3),(1.6,1.5)),((0,1.5),(1.6,1.5)),((0,1.5),(1.6,0))] if char=='R'
               else [((.7,0),(.9,0))] if char=='.' else [strokes[k] for k in digits[int(char)]])
        for start,end in paths:
            a=np.array(start,dtype=float);b=np.array(end,dtype=float);a += [index*2.5-len(text)*1.25,132.5];b += [index*2.5-len(text)*1.25,132.5]
            vec=b-a;length=np.linalg.norm(vec);u=vec/length;mid=(a+b)/2
            y=10.5+radius-np.sqrt((radius+2.5)**2-mid[0]**2)
            parts.append(mf.Manifold.cube([length+.3,.65,.3],center=True).transform([
                [u[0],0,-u[1],mid[0]],[0,1,0,y+.1],[u[1],0,u[0],mid[1]]]))
    return mf.Manifold.batch_boolean(parts,mf.OpType.Add)

def validate(s):
    out=dict(preset=s.get('preset','vr_panda'),radius=float(s.get('radius',110)),distance=float(s.get('distance',5)),tilt=float(s.get('tilt',-15)),height_offset=float(s.get('height_offset',0)),width=float(s.get('width',198)),height=float(s.get('height',48)),strap=s.get('strap',False))
    if out['preset'] not in ('vr_panda','custom') or type(out['strap']) is not bool:raise ValueError(tr('Ungültige Vorlage.'))
    for key,lo,hi in [('radius',80,180),('distance',-15,30),('tilt',-25,0),('height_offset',-20,20),('width',140,240),('height',30,65)]:
        if not np.isfinite(out[key]) or not lo<=out[key]<=hi:raise ValueError(tr('Ungültige Einstellung: {v0}',v0=key))
    return out

def feedback(radius,answer):
    return float(np.clip(radius+{'centre':-10,'sides':10,'fits':0}[answer],80,180))

def support(settings,aligned=True):
    s=validate(settings)
    pose=pose_from_alignment([0]*6,[s['distance'],-6+s['height_offset'],s['tilt'],0],'open') if aligned else [0]*6
    p=forehead.validate(dict(pose=pose,base_pose=[0]*6,cushion_preset=s['preset'],forehead_width=s['width'],forehead_height=s['height'],forehead_radius=s['radius'],top_strap=s['strap']))
    d=forehead.reference(p);v=d['contact'];f=d['faces'];r=s['radius'];u=d['uv'][:,0]/r
    normal=np.c_[np.sin(u),-np.cos(u),np.zeros(len(u))]
    a=transform(v,pose_matrix(pose));b=transform(v+2.5*normal,pose_matrix(pose));n=len(a)
    edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);_,inv,counts=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True);edge=edges[counts[inv]==1]
    faces=np.vstack([f[:,::-1],f+n,[[i,j,j+n] for i,j in edge],[[i,j+n,i+n] for i,j in edge]])
    m=trimesh.Trimesh(np.vstack([a,b]),faces,process=False)
    if not m.is_volume:raise ValueError(tr('Die Auflage konnte nicht geschlossen werden.'))
    return PadResult(Mesh(m.vertices,m.faces,'Stirnauflage ohne Scan'),a,d['uv'].copy(),f.copy(),dict(parameters=p,mode='no_scan',warnings=[],head_clearance_verified=False))

def from_solid(s,name):
    d=s.to_mesh64();m=trimesh.Trimesh(d.vert_properties[:,:3],d.tri_verts,process=True)
    if not m.is_volume or len(m.split())!=1:raise ValueError(tr('Die Passprobe ist nicht zusammenhängend.'))
    return Mesh(m.vertices,m.faces,name)

def arc(settings,mark):
    r=support(settings,False);body=_manifold(r.mesh)
    import manifold3d as mf
    body=body^mf.Manifold.cube([400,400,10]).translate([-200,-200,127])
    # Recessed dots on the front identify the probes without touching the pad face.
    for x in np.linspace(-(mark-1)*1.5,(mark-1)*1.5,mark):
        y=10.5+settings['radius']-(settings['radius']+2.5)*np.sqrt(1-(x/(settings['radius']+2.5))**2)
        body-=mf.Manifold.sphere(.65,24).translate([x,y,129.5])
    body-=radius_engraving(settings['radius'])
    return from_solid(body,'Stirn-Passbogen')

def build(settings,trial=False,progress=None):
    s=validate(settings);r=support(s)
    a=forehead.build_assembly(r,[0]*6,progress,top_strap=s['strap'] and not trial)
    if not trial:return a.mesh
    import manifold3d as mf
    # Keep the complete proven mounting interface and a central forehead strip.
    base=_manifold(forehead.base_reference())
    central=mf.Manifold.cube([64,400,400]).translate([-32,-200,-100])
    # Crop only the carrier. Cropping the already united base and then adding
    # the same base again creates coincident OEM triangles at the cut planes.
    return from_solid((_manifold(a.bridges)^central)+base,'Montage-Passprobe')

def save(path,settings):
    Path(path).write_text(json.dumps(dict(format='gasketfit-no-scan',version=1,settings=validate(settings)),indent=2),encoding='utf-8')

def load(path):
    d=json.loads(Path(path).read_text(encoding='utf-8'))
    if d.get('format')!='gasketfit-no-scan' or d.get('version')!=1:raise ValueError(tr('Kein Projekt für den Assistenten ohne Scan.'))
    return validate(d['settings'])
