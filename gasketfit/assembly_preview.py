"""Display the final boolean surface; source meshes supply colours only."""
import numpy as np
from scipy.spatial import cKDTree


class AssemblyPreview:
    def __init__(self, mesh, base, pad):
        self.mesh, self.base, self.pad = mesh, base, pad
        # Most final vertices are unchanged source vertices. Boolean split
        # triangles without an exact source match keep the shell colour.
        # This lookup never moves, simplifies or joins any display geometry.
        base_distance = cKDTree(base.vertices).query(mesh.vertices)[0]
        pad_distance, self.pad_vertex = cKDTree(pad.vertices).query(mesh.vertices)
        self.base_faces = np.all(base_distance[mesh.faces] < .001, axis=1)
        self.pad_faces = np.all(pad_distance[mesh.faces] < .001, axis=1)

    def colors(self, pad_colors=None):
        colors = np.tile([.87, .68, .26, 1.], (len(self.mesh.faces), 1)).astype(np.float32)
        colors[self.base_faces] = [.25, .57, .90, 1.]
        colors[self.pad_faces] = [.29, .82, .62, 1.]
        if pad_colors is not None:
            ids = self.pad_vertex[self.mesh.faces[self.pad_faces]]
            colors[self.pad_faces] = pad_colors[ids].mean(axis=1)
        return colors
