"""Self-contained local projects, backwards compatible with versions 0.1/0.2."""
from pathlib import Path
import io
import json
import os
import uuid
import zipfile
import numpy as np
from .localization import tr
from .meshio import Mesh
from .fitting import FitResult
from .profile import supported, weights, full_weights, frame_vertices, pose_matrix, legacy_hmd_matrix, validate_regions, FULL_PROFILE


def save_project(filename, gasket, head, pose_values, pad, result=None, *, hmd=None, hmd_to_frame=None,
                 fit_mode='full_face', hmd_opacity=.18, hmd_visible=True, region_config=None):
    path = Path(filename)
    metadata = {'format': 'gasketfit', 'version': 2, 'pose': list(pose_values), 'pad_mm': pad,
                'gasket_name': gasket.name, 'head_name': head.name,
                'fit_mode': result.report.get('mode', 'temples') if result else fit_mode,
                'hmd_opacity': hmd_opacity, 'hmd_visible': hmd_visible}
    metadata['region_config'] = validate_regions(region_config)
    if hmd is not None:
        metadata.update(hmd_name=hmd.name, hmd_to_frame=np.asarray(hmd_to_frame).tolist())
    temp = str(path.with_name('GasketFit-temp-' + uuid.uuid4().hex))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, mesh in (('gasket', gasket), ('head', head), ('hmd', hmd)):
                if mesh is None:
                    continue
                stream = io.BytesIO()
                np.savez(stream, vertices=mesh.vertices, faces=mesh.faces)
                archive.writestr(name + '.npz', stream.getvalue())
            if result:
                stream = io.BytesIO()
                payload = dict(vertices=result.mesh.vertices, faces=result.mesh.faces, displacement=result.displacement)
                if result.reference_vertices is not None:
                    payload['reference'] = result.reference_vertices
                np.savez(stream, **payload)
                archive.writestr('result.npz', stream.getvalue())
                archive.writestr('report.json', json.dumps(result.report, ensure_ascii=False))
            archive.writestr('project.json', json.dumps(metadata, ensure_ascii=False))
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_project(filename, with_extras=False):
    with zipfile.ZipFile(filename) as archive:
        if sum(i.file_size for i in archive.infolist()) > 1_200_000_000:
            raise ValueError(tr('Diese Projektdatei ist zu groß.'))
        meta = json.loads(archive.read('project.json'))
        if meta.get('format') != 'gasketfit' or meta.get('version') not in (1, 2):
            raise ValueError(tr('Nicht unterstützte GasketFit-Projektversion.'))
        meshes = []
        for name in ('gasket', 'head'):
            with np.load(io.BytesIO(archive.read(name + '.npz')), allow_pickle=False) as data:
                meshes.append(Mesh(data['vertices'].astype(float), data['faces'].astype(np.int32), meta[name + '_name']).validate())
        result = None
        if 'result.npz' in archive.namelist():
            with np.load(io.BytesIO(archive.read('result.npz')), allow_pickle=False) as data:
                v = data['vertices'].astype(float)
                change = data['displacement'].astype(float)
                faces = data['faces'].astype(np.int32) if 'faces' in data else meshes[0].faces.copy()
                reference = data['reference'].astype(float) if 'reference' in data else None
            if change.shape != (len(v),) or not np.isfinite(change).all():
                raise ValueError(tr('Ungültiges Ergebnis im Projekt.'))
            result = FitResult(Mesh(v, faces, 'PFDMR_Scanfit').validate(), json.loads(archive.read('report.json')), change, reference)
        pose = np.array(meta['pose'], dtype=float)
        pad = float(meta['pad_mm'])
        config = validate_regions(meta.get('region_config'))
        if pose.shape != (6,) or not np.isfinite(pose).all() or not 1 <= pad <= 15:
            raise ValueError(tr('Ungültige Einstellungen im Projekt.'))
        if result:
            base = meshes[0]
            full = result.report.get('mode') == 'full_face'
            valid = supported(base)
            if full:
                valid = valid and result.report.get('profile') == FULL_PROFILE['profile'] and result.report.get('region_config') == config
            if full and valid:
                from .refinement import refined_reference
                expected_v, expected_f = refined_reference(base, region_config=config)
                valid = (result.reference_vertices is not None
                         and np.array_equal(expected_v, result.reference_vertices)
                         and np.array_equal(expected_f, result.mesh.faces)
                         and result.mesh.vertices.shape == expected_v.shape)
                protected = full_weights(frame_vertices(expected_v), config) == 0
                if valid:
                    valid = (np.array_equal(result.mesh.vertices[protected], expected_v[protected])
                             and np.allclose(np.linalg.norm(result.mesh.vertices - expected_v, axis=1), result.displacement, atol=1e-7)
                             and result.displacement.max() <= 25.1)
            elif valid and not full:
                protected = weights(frame_vertices(base.vertices)) == 0
                valid = (result.mesh.vertices.shape == base.vertices.shape
                         and np.array_equal(result.mesh.faces, base.faces)
                         and np.array_equal(result.mesh.vertices[protected], base.vertices[protected])
                         and np.array_equal(result.mesh.vertices[:, 1:], base.vertices[:, 1:])
                         and np.allclose(abs(result.mesh.vertices[:, 0] - base.vertices[:, 0]), result.displacement, atol=1e-7)
                         and result.displacement.max() <= 12.1)
            saved_pose = np.asarray(result.report.get('pose_frame_to_head', []))
            valid = (valid and result.report.get('mount_vertices_unchanged') is True
                     and result.report.get('pad_mm') == pad and saved_pose.shape == (4, 4)
                     and np.allclose(saved_pose, pose_matrix(pose), atol=1e-7))
            if not valid:
                result = None
        extras = {'hmd': None, 'hmd_to_frame': None, 'hmd_docking_valid': False,
                  'cached_result_discarded': 'result.npz' in archive.namelist() and result is None,
                  'region_config': config, 'fit_mode': meta.get('fit_mode', 'temples'),
                  'hmd_opacity': meta.get('hmd_opacity', .18), 'hmd_visible': meta.get('hmd_visible', True)}
        if extras['fit_mode'] not in ('temples', 'full_face') or not isinstance(extras['hmd_visible'], bool) or not isinstance(extras['hmd_opacity'], (int, float)) or not .05 <= extras['hmd_opacity'] <= .85:
            raise ValueError(tr('Ungültige Einstellungen im Projekt.'))
        if 'hmd.npz' in archive.namelist():
            with np.load(io.BytesIO(archive.read('hmd.npz')), allow_pickle=False) as data:
                hmd = Mesh(data['vertices'].astype(float), data['faces'].astype(np.int32), meta.get('hmd_name', 'PFDM HMD')).validate()
            saved = np.asarray(meta.get('hmd_to_frame', []), dtype=float)
            verified = legacy_hmd_matrix(hmd)
            if saved.shape != (4, 4) or not np.allclose(saved, verified, atol=1e-10):
                raise ValueError(tr('Ungültige HMD-Kopplung im Projekt.'))
            extras.update(hmd=hmd, hmd_to_frame=verified)
        payload = (*meshes, pose.tolist(), pad, result)
        return (*payload, extras) if with_extras else payload
