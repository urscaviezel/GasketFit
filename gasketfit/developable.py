"""Isometric cushion supports: a plane can bend onto these without stretching.

The adhesive face is either a generalized cylinder (a unit-speed planar curve
extruded along a straight generator) or an exact circular cone unfolding.
Head conformity is a soft objective; developability is a hard construction.
"""
from __future__ import annotations
import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.interpolate import CubicSpline
from scipy.optimize import least_squares
import trimesh
from .profile import pose_matrix, transform
from .meshio import Mesh


def local_surface(flat, shape, kind="cylinder"):
    uv = np.asarray(flat, dtype=float)
    u, z = uv.T
    if kind == "wings":
        a1, a2, a3, central_width, angle_left, angle_right, height_left, height_right = shape
        grid = np.linspace(-160., 160., 6401)
        t = np.clip(grid / central_width, -1., 1.)
        theta = a1 * t + a2 * t*t + a3 * t*t*t
        xx = cumulative_trapezoid(np.cos(theta), grid, initial=0.)
        yy = cumulative_trapezoid(np.sin(theta), grid, initial=0.)
        xx -= xx[len(grid)//2]
        yy -= yy[len(grid)//2]
        cx, cy = CubicSpline(grid, xx), CubicSpline(grid, yy)
        result = np.c_[cx(u), cy(u), z]
        # Side bends occupy only the otherwise planar shoulder regions of the
        # U. Distal curved portions move rigidly; bend regions do not overlap.
        for sign, bend, height in ((-1, angle_left, height_left), (1, angle_right, height_right)):
            ids = u * sign > 0
            endpoint_angle = a1 * sign + a2 + a3 * sign
            along = np.array([np.cos(endpoint_angle), np.sin(endpoint_angle), 0.])
            outward = np.array([np.sin(endpoint_angle), -np.cos(endpoint_angle), 0.])
            down = np.array([0., 0., -1.])
            origin = np.array([cx(sign * central_width), cy(sign * central_width), height])
            q = result[ids] - origin
            aa, bb, cc = q @ down, q @ along, q @ outward
            width, start = 20., -10.
            if abs(bend) < 1e-8:
                continue
            curvature = bend / width
            s = np.clip(aa-start, 0., width)
            angle = s * curvature
            bent_a = start + np.sin(angle) / curvature
            bent_c = (1-np.cos(angle)) / curvature
            before, after = aa < start, aa > start+width
            bent_a[before], bent_c[before] = aa[before], 0.
            bent_a[after] += (aa[after] - start-width) * np.cos(bend)
            bent_c[after] += (aa[after] - start-width) * np.sin(bend)
            result[ids] = (origin + (bent_a - cc*np.sin(angle))[:,None] * down
                           + bb[:,None]*along + (bent_c+cc*np.cos(angle))[:,None]*outward)
        return result
    if kind == "cone":
        radius, taper = shape
        if abs(taper) < 1e-5:
            angle = u / radius
            return np.c_[radius * np.sin(angle), radius * (1 - np.cos(angle)), z]
        s, sign = abs(taper), np.sign(taper)
        apex = radius / s
        rho = np.hypot(u, apex - sign * z)
        phi = np.arctan2(u, apex - sign * z) / s
        return np.c_[rho * s * np.sin(phi), radius - rho * s * np.cos(phi),
                     sign * np.sqrt(1 - s * s) * (apex - rho)]
    if kind not in ("cylinder", "fan", "fan_up"):
        raise ValueError("Unknown developable surface")
    # The coordinate u is arc length in millimetres, never an angle or scale.
    grid = np.linspace(-200., 200., 8001) if kind.startswith("fan") else np.linspace(-130., 130., 5201)
    t = np.clip(grid / 118., -1.3, 1.3)
    theta = sum(coefficient * t ** (i + 1) for i, coefficient in enumerate(shape[:5]))
    xx = cumulative_trapezoid(np.cos(theta), grid, initial=0.)
    yy = cumulative_trapezoid(np.sin(theta), grid, initial=0.)
    xx -= xx[len(grid) // 2]
    yy -= yy[len(grid) // 2]
    if kind == "cylinder":
        return np.c_[CubicSpline(grid, xx)(u), CubicSpline(grid, yy)(u), z]
    # A generalized cone: arbitrary cross-section, common apex. Its unit
    # spherical directrix is parameterised by spherical arc length. Thus
    # dP² = d(rho)² + rho² d(phi)², exactly the flat polar metric.
    apex_y, inverse_height = shape[5:]
    apex_z = 1. / inverse_height
    apex = np.array([0., apex_y, apex_z])
    direction = np.c_[xx, yy, np.zeros(len(grid))] - apex
    direction /= np.linalg.norm(direction, axis=1)[:, None]
    angle_step = np.arctan2(np.linalg.norm(np.cross(direction[:-1], direction[1:]), axis=1),
                            np.einsum("ij,ij->i", direction[:-1], direction[1:]))
    arc = np.r_[0., np.cumsum(angle_step)]
    arc -= arc[len(grid) // 2]
    length = np.linalg.norm(apex)
    sign = np.sign(apex_z)
    rho = np.hypot(u, length - sign * z)
    phi = np.arctan2(u, length - sign * z)
    if phi.min() < arc[0] or phi.max() > arc[-1]:
        raise ValueError("Developable cone extrapolation is not allowed")
    gamma = CubicSpline(arc, direction)(phi)
    gamma /= np.linalg.norm(gamma, axis=1)[:, None]
    return apex + rho[:, None] * gamma


def mapped(flat, values, kind):
    return transform(local_surface(flat, values[6:], kind), pose_matrix(values[:6]))


def normals(flat, values, kind):
    eps = .005
    du = (mapped(flat + [eps, 0], values, kind) - mapped(flat - [eps, 0], values, kind)) / (2 * eps)
    dz = (mapped(flat + [0, eps], values, kind) - mapped(flat - [0, eps], values, kind)) / (2 * eps)
    normal = np.cross(du, dz)
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    return normal


def metric_check(flat, values, kind):
    eps = .005
    du = (mapped(flat + [eps, 0], values, kind) - mapped(flat - [eps, 0], values, kind)) / (2 * eps)
    dz = (mapped(flat + [0, eps], values, kind) - mapped(flat - [0, eps], values, kind)) / (2 * eps)
    jacobian = np.stack([du, dz], axis=2)
    singular = np.linalg.svd(jacobian, compute_uv=False)
    return dict(maximum_analytic_length_error_percent=float(abs(singular - 1).max() * 100),
                maximum_generator_orthogonality_error=float(abs((du * dz).sum(1)).max()))


def fit_to_targets(flat, targets, initial_pose, kind="cylinder", target_normals=None, initial=None):
    # Deterministic subsampling includes the outline and both forehead/cheeks.
    ids = np.unique(np.r_[np.arange(min(320, len(flat))),
                          np.linspace(0, len(flat) - 1, min(1000, len(flat))).astype(int)])
    q, goal = flat[ids], targets[ids]
    if kind == "wings":
        shape = [1.15, 0., 0., 65., .15, .15, 0., 0.]
        lower_shape = [.4, -.2, -.6, 45., -.5, -.5, -14., -14.]
        upper_shape = [2., .2, .6, 72., .5, .5, 8., 8.]
    elif kind == "cylinder" or kind.startswith("fan"):
        shape = [118 / 90, 0., 0., 0., 0.]
        lower_shape, upper_shape = [.4, -.5, -1.5, -.5, -1.], [3., .5, 1.5, .5, 1.]
        if kind.startswith("fan"):
            shape += [90., -.002 if kind == "fan" else .002]
            lower_shape += [-200., -.005 if kind == "fan" else .0003]
            upper_shape += [200., -.0003 if kind == "fan" else .005]
    else:
        shape = [90., -.12]
        lower_shape, upper_shape = [55., -.38], [150., .38]
    values = np.r_[initial_pose, shape] if initial is None else np.asarray(initial).copy()
    pose = np.asarray(initial_pose)
    lo = np.r_[pose[:3] - [20, 30, 20], pose[3:] - [25, 15, 15], lower_shape]
    hi = np.r_[pose[:3] + [20, 30, 20], pose[3:] + [25, 15, 15], upper_shape]
    def residual(parameters):
        delta = mapped(q, parameters, kind) - goal
        if target_normals is not None:
            nn = target_normals[ids]
            delta = delta * .15 + np.sum(delta * nn, axis=1)[:, None] * nn * .85
        penalty = []
        if kind == "wings":
            tt = np.linspace(-1., 1., 81)
            a, b, c = parameters[6:9]
            theta = a*tt + b*tt*tt + c*tt*tt*tt
            derivative = a+2*b*tt+3*c*tt*tt
            penalty = np.r_[np.maximum(0.,abs(theta)-1.65)*50, np.minimum(0.,derivative-.05)*50]
        if kind == "cylinder" or kind.startswith("fan"):
            tt = np.linspace(-1., 1., 81)
            theta = sum(a * tt ** (i + 1) for i, a in enumerate(parameters[6:11]))
            derivative = sum((i + 1) * a * tt ** i for i, a in enumerate(parameters[6:11]))
            penalty = np.r_[np.maximum(0., abs(theta) - 1.65) * 50,
                            np.minimum(0., derivative - .05) * 50,
                            np.asarray(parameters[7:11]) * 1.5]
        return np.r_[delta.ravel(), penalty]
    answer = least_squares(residual, np.clip(values, lo + 1e-9, hi - 1e-9), bounds=(lo, hi),
                           loss="soft_l1", f_scale=2., max_nfev=150,
                           ftol=1e-7, xtol=1e-7, gtol=1e-7)
    return answer.x


def fit_gap_envelope(flat, near, directions, initial_pose, values, kind):
    """Prioritise the foam's usable clearance envelope over mean face fidelity."""
    pose = np.asarray(initial_pose)
    if kind == "wings":
        lower_shape = [.4, -.2, -.6, 45., -.5, -.5, -14., -14.]
        upper_shape = [2., .2, .6, 72., .5, .5, 8., 8.]
    elif kind == "cylinder" or kind.startswith("fan"):
        lower_shape, upper_shape = [.4, -.5, -1.5, -.5, -1.], [3., .5, 1.5, .5, 1.]
        if kind.startswith("fan"):
            lower_shape += [-200., -.005 if kind == "fan" else .0003]
            upper_shape += [200., -.0003 if kind == "fan" else .005]
    else:
        lower_shape, upper_shape = [55., -.38], [150., .38]
    lo = np.r_[pose[:3] - [20, 30, 20], pose[3:] - [25, 15, 15], lower_shape]
    hi = np.r_[pose[:3] + [20, 30, 20], pose[3:] + [25, 15, 15], upper_shape]
    reference = mapped(flat, values, kind)
    def residual(parameters):
        candidate = mapped(flat, parameters, kind)
        gap = np.sum((candidate - near) * directions, axis=1)
        violation = np.minimum(gap - 4., 0.) + np.maximum(gap - 9.5, 0.)
        # L4-style envelope loss pushes isolated pressure/gap extrema back in,
        # instead of sacrificing them to a good-looking average distance.
        residuals = [violation * (abs(violation) + .25) * 5., (gap - 6.75) * .025,
                     ((candidate - reference) * .015).ravel()]
        if kind == "wings":
            tt = np.linspace(-1., 1., 81)
            a,b,c = parameters[6:9]
            theta=a*tt+b*tt*tt+c*tt*tt*tt
            derivative=a+2*b*tt+3*c*tt*tt
            residuals += [np.maximum(0.,abs(theta)-1.65)*100,np.minimum(0.,derivative-.05)*100]
        if kind == "cylinder" or kind.startswith("fan"):
            tt = np.linspace(-1., 1., 81)
            theta = sum(a * tt ** (i + 1) for i, a in enumerate(parameters[6:11]))
            derivative = sum((i + 1) * a * tt ** i for i, a in enumerate(parameters[6:11]))
            residuals += [np.maximum(0., abs(theta) - 1.65) * 100,
                          np.minimum(0., derivative - .05) * 100]
        return np.concatenate(residuals)
    return least_squares(residual, np.clip(values, lo + 1e-9, hi - 1e-9), bounds=(lo, hi),
                         loss="linear", x_scale="jac", max_nfev=200,
                         ftol=1e-7, xtol=1e-7, gtol=1e-7).x


def thicken(flat, faces, values, kind, thickness=1.5):
    contact = mapped(flat, values, kind)
    nn = normals(flat, values, kind)
    outer = contact + nn * thickness
    n = len(flat)
    edges = np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    _, inverse, counts = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    boundary = edges[counts[inverse] == 1]
    solid_faces = np.vstack([faces[:, ::-1], faces + n,
                             np.array([[a, b, b+n] for a, b in boundary]),
                             np.array([[a, b+n, a+n] for a, b in boundary])])
    solid = trimesh.Trimesh(np.vstack([contact, outer]), solid_faces, process=False)
    if not solid.is_watertight or not solid.is_winding_consistent or solid.volume <= 0:
        raise ValueError("Developable support is not a closed, consistently oriented solid")
    if (solid.area_faces < 1e-10).any():
        raise ValueError("Collapsed support triangles")
    surface = trimesh.Trimesh(contact, faces, process=False)
    if (np.einsum("ij,ij->i", surface.face_normals, nn[faces].mean(axis=1)) < .1).any():
        raise ValueError("Folded contact surface")
    if (np.einsum("ij,ij->i", solid.face_normals[len(faces):2*len(faces)], surface.face_normals) < .1).any():
        raise ValueError("Folded backing surface")
    return Mesh(solid.vertices.copy(), solid.faces.copy(), "VRcover developable test support"), contact
