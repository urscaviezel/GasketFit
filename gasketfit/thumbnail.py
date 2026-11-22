"""Small CPU-rendered previews, safe in export workers without an OpenGL context."""
import numpy as np
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage


def render_thumbnail(mesh, size=256):
    """Return a transparent PNG of the exported mesh; never modify its arrays."""
    resolution = size * 2
    vertices = np.asarray(mesh.vertices, dtype=float)
    eye = np.array([1., -2., 1.4])
    eye /= np.linalg.norm(eye)
    right = np.cross(eye, [0., 0., 1.])
    right /= np.linalg.norm(right)
    up = np.cross(right, eye)
    projected = vertices @ np.array([right, up, eye]).T
    lo, hi = projected.min(0), projected.max(0)
    scale = resolution * .86 / max(float(np.max(hi[:2]-lo[:2])), 1e-12)
    projected[:, :2] = (projected[:, :2]-(lo[:2]+hi[:2])/2)*scale
    projected[:, 0] += resolution/2
    projected[:, 1] = resolution/2-projected[:, 1]
    triangles = projected[mesh.faces]
    xyz = vertices[mesh.faces]
    normals = np.cross(xyz[:, 1]-xyz[:, 0], xyz[:, 2]-xyz[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-30)
    light = eye + up * .7 - right * .4
    light /= np.linalg.norm(light)
    brightness = .32 + .68*np.abs(normals @ light)
    colours = np.clip(brightness[:, None]*[65, 190, 220], 0, 255).astype(np.uint8)
    pixels = np.zeros((resolution, resolution, 4), dtype=np.uint8)
    depth = np.full((resolution, resolution), -np.inf)
    # Pixel centres and a Z buffer handle openings and overlapping triangles,
    # unlike painter-order previews. No simplification of the export is needed.
    for triangle, colour in zip(triangles, colours):
        lower = np.maximum(np.ceil(triangle[:, :2].min(0)-.5).astype(int), 0)
        upper = np.minimum(np.floor(triangle[:, :2].max(0)-.5).astype(int), resolution-1)
        if np.any(lower > upper):
            continue
        a, b, c = triangle
        denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(denominator) < 1e-12:
            continue
        x = np.arange(lower[0], upper[0]+1)[None, :]+.5
        y = np.arange(lower[1], upper[1]+1)[:, None]+.5
        u = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
        v = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
        w = 1-u-v
        z = u*a[2]+v*b[2]+w*c[2]
        region = np.s_[lower[1]:upper[1]+1, lower[0]:upper[0]+1]
        visible = (u >= -1e-9) & (v >= -1e-9) & (w >= -1e-9) & (z > depth[region])
        depth[region][visible] = z[visible]
        pixels[region][visible] = [*colour, 255]
    image = QImage(pixels.data, resolution, resolution, pixels.strides[0],
                   QImage.Format.Format_RGBA8888).copy()
    image = image.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise RuntimeError('PNG thumbnail encoding failed')
    return bytes(data)
