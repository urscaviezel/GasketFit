"""Conforming subdivision of long edges in the movable source surface only."""
import numpy as np
from .profile import frame_vertices, full_weights


def refined_reference(mesh, maximum_edge=2., region_config=None):
    vertices, faces = mesh.vertices.copy(), mesh.faces.copy()
    for _ in range(8):
        fixed = full_weights(frame_vertices(vertices), region_config) == 0
        edges = np.sort(np.stack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=1), axis=2)
        unique, inverse = np.unique(edges.reshape(-1, 2), axis=0, return_inverse=True)
        lengths = np.linalg.norm(vertices[unique[:, 0]] - vertices[unique[:, 1]], axis=1)
        split = (lengths > maximum_edge) & ~fixed[unique].all(axis=1)
        if not split.any():
            break
        midpoint = np.full(len(unique), -1, dtype=np.int32)
        midpoint[split] = len(vertices) + np.arange(split.sum())
        vertices = np.vstack([vertices, vertices[unique[split]].mean(axis=1)])
        mids = midpoint[inverse].reshape(-1, 3)
        count = (mids >= 0).sum(axis=1)
        output = faces[count == 0].tolist()
        for ids, mid, n in zip(faces[count > 0], mids[count > 0], count[count > 0]):
            if n == 1:
                start = np.flatnonzero(mid >= 0)[0]
                a, b, c = np.roll(ids, -start)
                m = mid[start]
                output.extend([[a, m, c], [m, b, c]])
            elif n == 2:
                start = (np.flatnonzero(mid < 0)[0] + 1) % 3
                a, b, c = np.roll(ids, -start)
                ab, bc, _ = np.roll(mid, -start)
                output.extend([[b, bc, ab], [a, ab, c], [ab, bc, c]])
            else:
                a, b, c = ids
                ab, bc, ca = mid
                output.extend([[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]])
        faces = np.asarray(output, dtype=np.int32)
    return vertices, faces
