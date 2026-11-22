"""Support pose relative to HMD, centred at its local pivot (no independent Y rotation)."""
from .localization import tr
import numpy as np
from scipy.spatial.transform import Rotation
from .profile import pose_matrix

def anchor(workflow):
    return np.array([0.,0.,132. if workflow=='open' else 78.])

def pose_from_alignment(base_pose, alignment, workflow):
    vals=np.asarray(alignment,dtype=float)
    if vals.shape!=(4,) or not np.isfinite(vals).all():raise ValueError(tr('Ungültige relative Auflagenausrichtung.'))
    y,z,rx,rz=vals
    local=pose_matrix([0,y,z,rx,0,rz]);pivot=anchor(workflow)
    local[:3,3]+=pivot-local[:3,:3]@pivot
    world=pose_matrix(base_pose)@local
    angles=Rotation.from_matrix(world[:3,:3]).as_euler('xyz',degrees=True)
    return np.r_[world[:3,3],angles].tolist()

def alignment_from_pose(base_pose, pose, workflow):
    relative=np.linalg.inv(pose_matrix(base_pose))@pose_matrix(pose)
    angles=Rotation.from_matrix(relative[:3,:3]).as_euler('xyz',degrees=True)
    pivot=anchor(workflow);offset=relative[:3,:3]@pivot+relative[:3,3]-pivot
    return [float(offset[1]),float(offset[2]),float(angles[0]),float(angles[2])]
