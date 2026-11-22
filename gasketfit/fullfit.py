"""Smooth 3D deformation of the existing contact lip, with a fixed front band."""
from __future__ import annotations
import hashlib
import numpy as np
from . import __version__
from .localization import tr
from .meshio import Mesh
from .profile import (supported, frame_vertices, inverse_frame, transform, full_weights,
                      contour_angle, contact_indices, FULL_PROFILE, validate_regions, permanent_features)
from .fitting import FitResult, Surface, _topology, ring_indices
from .refinement import refined_reference


def outward(surface, points):
    closest, distance, triangles = surface.close(points)
    normals = surface.mesh.face_normals[triangles]
    signed = ((points - closest) * normals).sum(1)
    delta = points - closest
    direction = delta / np.maximum(distance[:, None], 1e-12)
    direction[signed < 0] *= -1
    direction[distance < 1e-8] = normals[distance < 1e-8]
    return closest, distance, signed, direction


def quality_check(frame, faces, modified, field, fixed):
    before_correction = modified.copy()
    tri = frame[faces]
    source_normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    expected = source_normals.copy()
    lengths = np.linalg.norm(expected, axis=1)
    expected /= np.maximum(lengths[:, None], 1e-30)
    corrected = set()
    for _ in range(160):
        target_tri = modified[faces]
        normal = np.cross(target_tri[:, 1] - target_tri[:, 0], target_tri[:, 2] - target_tri[:, 0])
        norm = np.linalg.norm(normal, axis=1)
        agreement = (normal * expected).sum(1) / np.maximum(norm, 1e-30)
        bad = np.flatnonzero((agreement < .08) | (norm < 1e-10))
        if not len(bad):
            correction = np.linalg.norm(modified - before_correction, axis=1).max()
            if correction > 1.:
                raise ValueError(tr("Die Netzkorrektur wäre zu groß. Bitte die Ausrichtung ändern."))
            area = np.linalg.norm(normal, axis=1) / np.maximum(np.linalg.norm(source_normals, axis=1), 1e-30)
            return {"method": "oriented_surface_triangles", "minimum_area_ratio": float(area.min()), "minimum_normal_agreement": float(agreement.min()), "quality_corrected_vertices": len(corrected), "maximum_quality_correction_mm": float(correction)}
        for index in bad:
            ids = faces[index]
            p0, p1, p2 = modified[ids]
            e1, e2 = p1 - p0, p2 - p0
            n = expected[index]
            gradients = np.array([np.cross(e1 - e2, n), np.cross(e2, n), np.cross(n, e1)])
            gradients[fixed[ids]] = 0
            numerator = max(1e-10, .2 * norm[index]) - np.dot(normal[index], n)
            change = gradients * numerator / max((gradients * gradients).sum(), 1e-30)
            if np.max(np.linalg.norm(change, axis=1)) > .5:
                raise ValueError(tr("Der Übergang zur Aufnahme wäre nicht ausreichend stabil. Bitte weniger stark anpassen."))
            modified[ids] += change
            corrected.update(ids[np.linalg.norm(change, axis=1) > 0].tolist())
    raise ValueError(tr("Die Netzprüfung konnte keinen stabilen Übergang herstellen. Bitte Ausrichtung ändern."))


def fit_full_face(gasket, head, pose, pad, progress=None, region_config=None):
    progress = progress or (lambda *_: None)
    if not supported(gasket):
        raise ValueError(tr("Dieses Modell passt nicht zum PFDMR-V2-Profil. Bitte das unveränderte Original laden."))
    if not 1 <= pad <= 15:
        raise ValueError(tr("Die Polsterdicke muss zwischen 1 und 15 mm liegen."))
    if not np.isfinite(pose).all() or pose.shape != (4, 4) or not np.allclose(pose[:3, :3].T @ pose[:3, :3], np.eye(3), atol=1e-7) or np.linalg.det(pose[:3, :3]) < .99:
        raise ValueError(tr("Die Gasket-Ausrichtung darf nur Verschiebung und Drehung enthalten."))
    extent = np.ptp(head.vertices, axis=0)
    if extent.min() < 45 or extent.max() > 550:
        raise ValueError(tr("Der Kopf-Scan scheint nicht in Lebensgröße vorzuliegen. Bitte die Einheit/Skalierung prüfen."))
    progress(2, tr("Bewegliche Auflageflächen vorbereiten …"))
    config = validate_regions(region_config)
    reference, faces = refined_reference(gasket, region_config=config)
    frame = frame_vertices(reference)
    weights = full_weights(frame, config)
    fixed = weights == 0
    samples = contact_indices(frame)
    samples = samples[weights[samples] > .15]
    if len(samples) < 40:
        raise ValueError(tr("Die Auflagekante konnte im PFDMR-Modell nicht zuverlässig erkannt werden."))
    progress(5, tr("Gesamte Gesichtsauflage vorbereiten …"))
    surface = Surface(head)
    points = transform(frame[samples], pose)
    _, initial_distance, _, _ = outward(surface, points)
    if np.median(initial_distance) > 25 or initial_distance.max() > 40:
        raise ValueError(tr("Das Gasket liegt zu weit vom Gesicht entfernt. Bitte zuerst näher an Stirn und Wangen ausrichten."))
    # Positive graph Laplacian with Dirichlet constraints on every protected
    # vertex. Unlike a global RBF field, harmonic displacements cannot overshoot
    # their control values into unrelated parts of the model.
    from scipy.sparse import coo_matrix, diags
    from scipy.sparse.linalg import factorized
    edges = np.unique(np.sort(np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0)
    row = np.r_[edges[:, 0], edges[:, 1]]
    col = np.r_[edges[:, 1], edges[:, 0]]
    graph = coo_matrix((np.ones(len(row)), (row, col)), shape=(len(frame), len(frame))).tocsr()
    laplacian = diags(np.asarray(graph.sum(axis=1)).ravel()) - graph
    free = np.flatnonzero(~fixed)
    local = np.full(len(frame), -1, dtype=int)
    local[free] = np.arange(len(free))
    pins = local[samples]
    strength = np.zeros(len(free))
    strength[pins] = 100.
    solve = factorized((laplacian[free][:, free] + diags(strength + 1e-6)).tocsc())
    displacement = np.zeros_like(frame)
    for iteration in range(12):
        progress(12 + iteration * 4, tr("Stirn, Wangen, Nase und Schläfen anpassen …"))
        world = transform(frame[samples] + displacement[samples], pose)
        closest, distance, signed, normals = outward(surface, world)
        desired = closest + normals * (pad + .45)
        targets = (desired - pose[:3, 3]) @ pose[:3, :3] - frame[samples]
        rhs = np.zeros((len(free), 3))
        rhs[pins] = targets * 100.
        displacement[free] = solve(rhs)
        if iteration > 2 and signed.min() >= pad + .08 and distance.max() <= pad + 1.7:
            break
    field = None
    progress(62, tr("Weiche Übergänge zur festen Aufnahme formen …"))
    modified = frame + displacement
    modified[fixed] = frame[fixed]
    if np.linalg.norm(modified - frame, axis=1).max() > 25:
        raise ValueError(tr("Mehr als 25 mm Änderung wäre nötig. Bitte die Lage des HMD zum Gesicht prüfen."))
    progress(70, tr("Netz und Übergänge prüfen …"))
    try:
        quality = quality_check(frame, faces, modified, field, fixed)
    except ValueError as exc:
        raise ValueError(tr("Die Anpassung passt nicht in den freigegebenen Bereich. Bitte Ausrichtung oder Polsterabstand ändern. Geschützte Teile werden nicht automatisch freigegeben.")) from exc
    output = inverse_frame(modified)
    output[fixed] = reference[fixed]
    # Export in original source coordinates. The exact fixed source values win
    # over any rounding in frame transformations.
    assert np.array_equal(output[fixed], reference[fixed])
    progress(85, tr("Gesamte Auflage und unveränderte Aufnahme prüfen …"))
    samples = contact_indices(frame)
    samples = samples[weights[samples] > .15]
    world = transform(frame_vertices(output)[samples], pose)
    _, distance, signed, _ = outward(surface, world)
    if signed.min() < pad - .03 or distance.max() > pad + 2.2:
        raise ValueError(tr("Die gesamte Auflage erreicht den Polsterabstand noch nicht gleichmäßig. Bitte die Ausrichtung leicht ändern."))
    topology = _topology(output, faces)
    if any(topology.values()):
        raise ValueError(tr("Die Prüfung hat eine offene oder fehlerhafte Stelle im Netz erkannt. Kein Export freigegeben."))
    change = np.linalg.norm(output - reference, axis=1)
    if change.max() > 25:
        raise ValueError(tr("Mehr als 25 mm Änderung wäre nötig. Bitte die Lage des HMD zum Gesicht prüfen."))
    forehead = frame[samples, 2] > 108
    nose = (abs(frame[samples, 0]) < 20) & (frame[samples, 2] < 80)
    cheeks = (frame[samples, 2] < 56) & ~nose
    regions = {"forehead": forehead, "nose": nose, "cheeks": cheeks, "temples": ~(forehead | nose | cheeks)}
    report = {"app_version": __version__, "profile": FULL_PROFILE["profile"], "mode": "full_face",
              "source_author": "Sir Dominik", "source_url": FULL_PROFILE["source_url"],
              "region_config": config,
              "permanent_features_unchanged": {},
              "source_gasket": gasket.name, "source_head": head.name, "pad_mm": float(pad),
              "pose_frame_to_head": pose.tolist(), "mount_vertices_unchanged": True,
              "protected_vertex_count": int(fixed.sum()), "protected_mask_sha256": hashlib.sha256(fixed.tobytes()).hexdigest(),
              "triangles": len(faces), "source_triangles": len(gasket.faces), "topology": topology, "quality": quality,
              "regions": {}, "sides": {}, "maximum_change_mm": float(change.max()),
              "minimum_gap_mm": float(distance.min()), "maximum_gap_mm": float(distance.max()),
              "checks_scope": "Only the approved rear contact strip is fitted. Headband attachment, nose/vents, mounting interface and additional protection marks remain fixed.",
              "limitations": ["No exhaustive self-intersection or wall-thickness validation.", "Physical fit and padding compression require a test print."]}
    for name, mask in regions.items():
        values = distance[mask]
        if not len(values):
            report["regions"][name] = {"sample_count": 0, "protected": True}
            continue
        report["regions"][name] = {"sample_count": len(values), "minimum_gap_mm": float(values.min()), "maximum_gap_mm": float(values.max()), "median_gap_mm": float(np.median(values))}
    for name, sign in (("links", -1), ("rechts", 1)):
        values = distance[sign * frame[samples, 0] >= 0]
        if not len(values):
            report["sides"][name] = {"sample_count": 0, "protected": True}
            continue
        report["sides"][name] = {"sample_count": len(values), "minimum_gap_mm": float(values.min()), "maximum_gap_mm": float(values.max()), "median_gap_mm": float(np.median(values)), "maximum_change_mm": float(change[sign * frame[:, 0] >= 0].max())}
    for name, feature in permanent_features(frame).items():
        exact = np.array_equal(output[feature], reference[feature])
        if not exact:
            raise ValueError("Permanent feature protection failed")
        report["permanent_features_unchanged"][name] = {"unchanged": exact, "vertex_count": int(feature.sum())}
    progress(100, tr("Anpassung abgeschlossen"))
    return FitResult(Mesh(output, faces, "PFDMR_FullFace", gasket.source), report, change, reference)
