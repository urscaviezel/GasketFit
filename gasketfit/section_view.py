"""Display-only sagittal half-section; never applied to model/export meshes."""
import numpy as np


NO_SECTION = (0., 0., 0., 1.)


def section_plane(matrix, side):
    """Keep the far half when looking from +X (right) or -X (left).

    The central YZ plane follows the current support/base frame. Positive
    signed distances are kept, including the centre-plane measurement line.
    """
    if side == 'off':
        return np.array(NO_SECTION)
    if side not in ('right', 'left'):
        raise ValueError('Unknown section side')
    matrix = np.asarray(matrix)
    normal = matrix[:3, 0] * (-1. if side == 'right' else 1.)
    return np.r_[normal, -np.dot(normal, matrix[:3, 3])]


def section_mask(points, plane):
    return np.asarray(points) @ np.asarray(plane)[:3] + plane[3] >= -1e-4
