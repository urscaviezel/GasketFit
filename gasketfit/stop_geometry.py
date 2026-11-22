"""Bound the lateral stops by the magnetic base's actual mounting section."""
from .localization import tr
import numpy as np
import trimesh
import manifold3d as mf
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


def mounting_profile(base):
    mesh = trimesh.Trimesh(base.vertices, base.faces, process=False)
    # Sample the outer bearing strip, not a fixed X slice through the
    # recessed magnet/loading channel. Both sides share the stricter limits.
    levels = np.linspace(56., 69., 261)
    fronts, backs = [], []
    for z in levels:
        segments = trimesh.intersections.mesh_plane(mesh, [0, 0, 1], [0, 0, z])
        if not len(segments):
            raise ValueError(tr('Die Auflagekante fehlt auf Hoehe des Kippanschlags.'))
        x_values = segments[:, :, 0]
        side_limits = []
        for x in (x_values.min()+.1, x_values.max()-.1):
            hits, _, _ = mesh.ray.intersects_location(
                [[x, 30, z]], [[0, -1, 0]], multiple_hits=True)
            if len(hits) < 2:
                raise ValueError(tr('Die Auflageflaeche konnte nicht bestimmt werden.'))
            side_limits.append((hits[:, 1].min(), hits[:, 1].max()))
        fronts.append(max(item[0] for item in side_limits))
        backs.append(min(item[1] for item in side_limits))
    profile = Polygon(np.vstack([np.c_[fronts, levels], np.c_[backs, levels][::-1]]))
    if not profile.is_valid:
        raise ValueError(tr('Die gemeinsame Auflagekontur ist ungueltig.'))
    return orient(profile, sign=1.)


def mounting_envelope(base):
    profile = mounting_profile(base)
    contours = [np.asarray(profile.exterior.coords)[:-1]]
    contours += [np.asarray(ring.coords)[:-1] for ring in profile.interiors]
    # Extrude the measured YZ contour sideways, along X. This limits the
    # whole bracket, including its lower brace, rather than just the root.
    return mf.CrossSection(contours).extrude(200).transform(
        [[0, 0, 1, -100], [1, 0, 0, 0], [0, 1, 0, 0]])
