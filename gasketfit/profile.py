from __future__ import annotations
import numpy as np
import json
from pathlib import Path
from .meshio import geometry_fingerprint, Mesh
from .localization import tr

FINGERPRINT = "f3f186632d6bd29bfd9b250f6afdbde4a9783caad48c21a62dfb7f0e42a3a34b"
NAME = "Pfd 108Fov Face Gasket mod V2 · Sir Dominik"
FRAME_ANGLE = np.deg2rad(42.)
FRAME = np.array([[1., 0, 0], [0, np.cos(FRAME_ANGLE), -np.sin(FRAME_ANGLE)], [0, np.sin(FRAME_ANGLE), np.cos(FRAME_ANGLE)]])
CENTER_X = 77.53700256347656


def supported(mesh: Mesh):
    return len(mesh.faces) == 236104 and geometry_fingerprint(mesh) == FINGERPRINT


def frame_vertices(vertices):
    v = vertices.copy()
    v[:, 0] -= CENTER_X
    return v @ FRAME.T


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def smooth_derivative(x):
    return np.where((x > 0) & (x < 1), 6 * x * (1 - x), 0.)


def weights(frame):
    x, d, h = frame.T
    return (smooth((d - 15) / 20) * smooth((abs(x) - 40) / 25)
            * smooth((h - 45) / 20) * (1 - smooth((h - 110) / 15)))


FULL_PROFILE = json.loads((Path(__file__).parent / "pfd_profile.json").read_text(encoding="utf-8"))


def contour_angle(frame):
    return np.arctan2((frame[:, 2] - 78.) / 48., frame[:, 0] / 77.)


def depth_curve(angle, key):
    values = np.asarray(FULL_PROFILE[key])
    centers = -np.pi + (np.arange(len(values)) + .5) * (2 * np.pi / len(values))
    return np.interp(angle, centers, values, period=2 * np.pi)


def validate_regions(config=None):
    config = config or {}
    width = float(config.get("strip_mm", 6.))
    spheres = np.asarray(config.get("protected_spheres", []), dtype=float)
    if spheres.size == 0:
        spheres = np.empty((0, 4))
    if (not 2 <= width <= 12 or spheres.ndim != 2 or spheres.shape[1] != 4
            or len(spheres) > 1000 or not np.isfinite(spheres).all()
            or (len(spheres) and ((spheres[:, 3] < 1).any() or (spheres[:, 3] > 30).any()))):
        raise ValueError(tr("Ungültige Schutzbereiche."))
    return {"strip_mm": width, "protected_spheres": spheres.tolist()}


def permanent_features(frame):
    x, _, height = frame.T
    return {"headband": (abs(x) <= 36.) & (height >= 96.),
            "nose_vents": (abs(x) <= 55.) & (height <= 82.)}


def full_weights(frame, region_config=None):
    config = validate_regions(region_config)
    angle = contour_angle(frame)
    fixed = depth_curve(angle, "front_depth") + FULL_PROFILE["fixed_depth_mm"]
    rear = depth_curve(angle, "rear_depth")
    base = smooth((frame[:, 1] - fixed) / np.maximum(3., rear - fixed - 1.))
    # Only the rear contact strip is permitted to move. The body, details and
    # all material farther forward are fixed, regardless of the solver field.
    strip = smooth((frame[:, 1] - rear + config["strip_mm"]) / max(1., config["strip_mm"] - 1.))
    result = base * strip
    # Deliberately generous source-frame guards around the strap attachment
    # and the entire nose opening/vent assembly. No UI can unlock these.
    upper = (1 - smooth((abs(frame[:, 0]) - 36.) / 3.)) * smooth((frame[:, 2] - 93.) / 3.)
    lower = (1 - smooth((abs(frame[:, 0]) - 55.) / 3.)) * (1 - smooth((frame[:, 2] - 82.) / 3.))
    result *= (1 - upper) * (1 - lower)
    for mask in permanent_features(frame).values():
        result[mask] = 0
    for x, depth, height, radius in config["protected_spheres"]:
        distance = np.linalg.norm(frame - [x, depth, height], axis=1)
        result *= smooth((distance - radius) / 1.5)
    # The renderer uses the same cutoff. A vertex shown as fixed must never
    # become a free solver variable because of tiny interpolation roundoff.
    result[result <= 1e-6] = 0
    return result


def contact_indices(frame, bins=240):
    """Sample both edges of the existing rear contact lip; never fill V2 vents."""
    angles = contour_angle(frame)
    bucket = np.floor((angles + np.pi) * bins / (2 * np.pi)).astype(int).clip(0, bins - 1)
    radial = np.hypot(frame[:, 0] / 77., (frame[:, 2] - 78.) / 48.)
    result = []
    for i in range(bins):
        ids = np.flatnonzero(bucket == i)
        if not len(ids):
            continue
        depth = frame[ids, 1]
        candidates = ids[depth >= depth.max() - .65]
        result.extend([ids[np.argmax(depth)], candidates[np.argmin(radial[candidates])], candidates[np.argmax(radial[candidates])]])
    return np.unique(result).astype(np.int32)


def inverse_frame(frame):
    vertices = frame @ FRAME
    vertices[:, 0] += CENTER_X
    return vertices


def legacy_hmd_matrix(mesh):
    if geometry_fingerprint(mesh) != FULL_PROFILE["hmd_fingerprint"]:
        raise ValueError(tr("Dieses HMD-Modell passt nicht zum geprüften PFDM-Profil."))
    return np.asarray(FULL_PROFILE["hmd_to_frame"], dtype=float)


def hmd_matrix(mesh):
    raise ValueError(tr("Die bisherige HMD-Kopplung ist deaktiviert. Eine verlässliche Referenz fehlt noch."))


def pose_matrix(values):
    tx, ty, tz, ax, ay, az = values
    ax, ay, az = np.deg2rad([ax, ay, az])
    rx = np.array([[1., 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    ry = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1., 0], [-np.sin(ay), 0, np.cos(ay)]])
    rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1.]])
    result = np.eye(4)
    result[:3, :3] = rz @ ry @ rx
    result[:3, 3] = [tx, ty, tz]
    return result


def transform(points, matrix):
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def initial_pose(head: Mesh):
    lo, hi = head.bounds
    span = hi - lo
    return [(lo[0] + hi[0]) / 2, float(np.percentile(head.vertices[:, 1], 1) + 25),
            lo[2] + .56 * span[2] - 78, 8., 0., 0.]
