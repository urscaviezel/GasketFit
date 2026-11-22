"""Directional clearance of the front HMD envelope against an open face scan.

No watertightness or inside/outside test is assumed: rays start in front of
the HMD and measure the first head surface along the HMD's local +Y axis.
Side arms and back plate are explicitly excluded in base-local coordinates.
"""
from functools import lru_cache
import numpy as np
import trimesh
from .hmd_reference import hmd_reference,hmd_reference_samples


def front_samples(mesh, spacing=2.):
    x,z=np.meshgrid(np.arange(-68.,68.01,spacing),np.arange(38.,118.01,spacing))
    origins=np.c_[x.ravel(),np.full(x.size,-300.),z.ravel()]
    directions=np.tile([0.,1.,0.],(len(origins),1))
    surface=trimesh.Trimesh(mesh.vertices,mesh.faces,process=False)
    points,rays,_=surface.ray.intersects_location(origins,directions,multiple_hits=True)
    points=np.asarray(points).reshape(-1,3)
    # This fixed front zone is attached to the magnetic base, so neither
    # repositioning nor rotation can bring side arms into the test region.
    keep=(points[:,1]<=20.) & (points[:,1]>=-100.)
    points,rays=points[keep],rays[keep]
    rear=np.full(len(origins),-np.inf)
    np.maximum.at(rear,rays,points[:,1])
    valid=np.isfinite(rear)
    samples=origins[valid].copy()
    samples[:,1]=rear[valid]
    return samples


@lru_cache(maxsize=1)
def hmd_front_samples():
    exact=hmd_reference_samples()
    return exact if exact is not None else front_samples(hmd_reference())


def middle_zone(samples):
    """Geometric hint only; the scan does not identify flexible materials."""
    return (np.abs(samples[:,0])<=12.) & (samples[:,2]>=45.) & (samples[:,2]<=105.)


def collision_patch(samples,collision):
    """Join adjacent colliding samples without bridging missing ray coverage."""
    cells={tuple(np.round(p[[0,2]],6)):i for i,p in enumerate(samples)}
    faces=[]
    for i,p in enumerate(samples):
        x,z=np.round(p[[0,2]],6)
        j=cells.get((x+2,z));k=cells.get((x,z+2));m=cells.get((x+2,z+2))
        if j is None or k is None or m is None:
            continue
        for triangle in ((i,j,m),(i,m,k)):
            if collision[list(triangle)].all():
                faces.append(triangle)
    return np.asarray(faces,dtype=np.int32).reshape(-1,3)


class FrontClearance:
    def __init__(self,head):
        self.mesh=trimesh.Trimesh(head.vertices,head.faces,process=False)
        # Build spatial index once, outside repeated position checks.
        self.mesh.triangles_tree

    def check(self,matrix,samples=None):
        samples=hmd_front_samples() if samples is None else np.asarray(samples)
        origins=samples.copy()
        origins[:,1]=-500.
        world_origins=origins@matrix[:3,:3].T+matrix[:3,3]
        direction=matrix[:3,1]
        directions=np.tile(direction,(len(samples),1))
        points,rays,triangles=self.mesh.ray.intersects_location(world_origins,directions,multiple_hits=False)
        points=np.asarray(points).reshape(-1,3)
        # A ray through a scan hole may hit the far side of the head. Do not
        # mistake such an exiting/back-facing or grazing hit for facial coverage.
        valid_hit=(self.mesh.face_normals[triangles]@direction)<-.1
        points,rays=points[valid_hit],rays[valid_hit]
        depth=np.full(len(samples),np.nan)
        depth[rays]=(points-world_origins[rays])@direction-500.
        gaps=depth-samples[:,1]
        valid=np.isfinite(gaps)
        collision=valid & (gaps<0)
        world=samples@matrix[:3,:3].T+matrix[:3,3]
        # Mark on the visible face surface, not behind opaque head geometry.
        marks=world[collision]+(gaps[collision]-.4)[:,None]*direction
        middle=middle_zone(samples)
        colors=np.tile([1.,.12,.07,.85],(len(samples),1))
        colors[middle]=[1.,.63,.08,.85]
        patch_points=world+(np.nan_to_num(gaps)-.6)[:,None]*direction
        patch_faces=collision_patch(samples,collision)
        def minimum(mask):
            return float(gaps[valid & mask].min()) if (valid & mask).any() else None
        return dict(gaps=gaps,minimum=float(np.min(gaps[valid])) if valid.any() else None,
                    coverage=float(valid.mean()) if len(valid) else 0.,
                    collision_count=int(collision.sum()),sample_count=len(samples),marks=marks,
                    middle_minimum=minimum(middle),outer_minimum=minimum(~middle),
                    mark_colors=colors[collision],patch_vertices=patch_points,
                    patch_faces=patch_faces,patch_colors=colors)
