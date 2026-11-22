"""Independent, millimetre-calibrated cushion outline; no V2 deformation."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
from .meshio import Mesh


def load_template(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    points = np.asarray(data["outline_xz_mm"], dtype=float)
    if (data.get("schema") != 1 or points.ndim != 2 or points.shape[1] != 2
            or not 3 <= len(points) <= 4096 or not np.isfinite(points).all()):
        raise ValueError("Invalid cushion outline")
    dimensions = np.asarray(data["outer_dimensions_mm"], dtype=float)
    if dimensions.shape != (2,) or (dimensions <= 0).any() or not np.allclose(
            np.ptp(points, axis=0), dimensions, atol=1e-6):
        raise ValueError("Outline does not match its calibration")
    return points, data


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def triangulate(points):
    """Ear clipping preserves the open U recess; a convex hull would fill it."""
    points = np.asarray(points, dtype=float)
    area = np.sum(points[:, 0] * np.roll(points[:, 1], -1)
                  - points[:, 1] * np.roll(points[:, 0], -1)) / 2
    if abs(area) < 1e-8:
        raise ValueError("Degenerate cushion outline")
    remaining = list(range(len(points)))
    if area < 0:
        remaining.reverse()
    faces = []
    while len(remaining) > 3:
        for k, b in enumerate(remaining):
            a, c = remaining[k - 1], remaining[(k + 1) % len(remaining)]
            pa, pb, pc = points[[a, b, c]]
            if _cross(pb - pa, pc - pa) <= 1e-10:
                continue
            others = [i for i in remaining if i not in (a, b, c)]
            q = points[others]
            inside = ((_cross(pb - pa, (q - pa).T) >= -1e-10)
                      & (_cross(pc - pb, (q - pb).T) >= -1e-10)
                      & (_cross(pa - pc, (q - pc).T) >= -1e-10))
            if inside.any():
                continue
            faces.append([a, b, c])
            remaining.pop(k)
            break
        else:
            raise ValueError("Cushion outline is self-intersecting or degenerate")
    faces.append(remaining)
    return np.asarray(faces, dtype=np.int32)


def flat_support(points, thickness=1.5):
    """Closed flat reference plate in X/Z, thickness along Y, all units mm."""
    if not np.isfinite(thickness) or not .5 <= thickness <= 5:
        raise ValueError("Support thickness must be between 0.5 and 5 mm")
    points = np.asarray(points, dtype=float)
    cap = triangulate(points)
    n = len(points)
    vertices = np.zeros((2 * n, 3))
    vertices[:n, 0] = vertices[n:, 0] = points[:, 0]
    vertices[:n, 2] = vertices[n:, 2] = points[:, 1]
    vertices[n:, 1] = thickness
    faces = [*cap.tolist(), *(cap[:, ::-1] + n).tolist()]
    # Use cap winding to obtain the oriented polygon boundary.
    area = np.sum(points[:, 0] * np.roll(points[:, 1], -1)
                  - points[:, 1] * np.roll(points[:, 0], -1))
    boundary = list(range(n)) if area > 0 else list(reversed(range(n)))
    for i, a in enumerate(boundary):
        b = boundary[(i + 1) % n]
        faces.extend([[b, a, a + n], [b, a + n, b + n]])
    return Mesh(vertices, np.asarray(faces, dtype=np.int32), "VRcover flat support").validate()
