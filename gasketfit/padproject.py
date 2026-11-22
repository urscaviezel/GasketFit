"""Portable cushion-design projects, separate from legacy V2 projects.

Store inputs only. Results are deliberately recomputed by the current solver
instead of trusting stale geometry after design algorithm changes.
"""
from pathlib import Path
import io
import json
import os
import uuid
import zipfile
import numpy as np
from .meshio import Mesh
from .padfit import validate_parameters
from .localization import tr


def save_pad_project(filename, head, outline, params, *, workflows=None, active=None, simple=None):
    p = validate_parameters(params)
    meta = dict(format="gasketfit-cushion", version=1, head_name=head.name if head else None, parameters=p)
    if workflows is not None:
        variants = {key: validate_parameters(value) for key, value in workflows.items()}
        if active not in variants or set(variants) - {'closed', 'open'}:
            raise ValueError('Invalid project workflows')
        meta.update(version=2, workflows=variants, active=active)
        if simple is not None:
            from .simple_fit import validate
            meta['simple'] = validate(simple)
    target = Path(filename)
    temp = str(target.with_name("GasketFit-pad-" + uuid.uuid4().hex))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
            stream = io.BytesIO()
            np.savez(stream, vertices=head.vertices if head else np.empty((0,3)),
                     faces=head.faces if head else np.empty((0,3),dtype=np.int32), outline=outline)
            archive.writestr("inputs.npz", stream.getvalue())
            archive.writestr("design.json", json.dumps(meta, ensure_ascii=False))
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_pad_project(filename, approved_outline, *, with_workflows=False):
    with zipfile.ZipFile(filename) as archive:
        if sum(item.file_size for item in archive.infolist()) > 1_200_000_000:
            raise ValueError(tr("Diese Projektdatei ist zu groß."))
        meta = json.loads(archive.read("design.json"))
        if meta.get("format") != "gasketfit-cushion" or meta.get("version") not in (1, 2):
            raise ValueError(tr("Nicht unterstütztes Polsterprojekt."))
        params = validate_parameters(meta["parameters"])
        mode = 'open' if params.get('solver') == 'forehead' else 'closed'
        variants = {mode: params}
        active = mode
        simple = None
        if meta['version'] == 2:
            variants = {key: validate_parameters(value) for key, value in meta['workflows'].items()}
            active = meta['active']
            if active not in variants or set(variants) - {'closed', 'open'}:
                raise ValueError('Invalid project workflows')
            for key, value in variants.items():
                if value.get('solver') != ('forehead' if key == 'open' else 'reference04'):
                    raise ValueError('Invalid workflow parameters')
            params = variants[active]
            if meta.get('simple') is not None:
                from .simple_fit import validate
                simple = validate(meta['simple'])
        with np.load(io.BytesIO(archive.read("inputs.npz")), allow_pickle=False) as data:
            outline = np.asarray(data["outline"], dtype=float)
            if outline.shape != approved_outline.shape or not np.array_equal(outline, approved_outline):
                raise ValueError(tr("Das Projekt verwendet eine andere Polsterkontur."))
            head = (Mesh(np.asarray(data["vertices"], dtype=float), np.asarray(data["faces"], dtype=np.int32),
                         str(meta["head_name"])).validate() if meta.get('head_name') is not None else None)
    if with_workflows:
        return head, params, dict(version=meta['version'], workflows=variants, active=active, simple=simple)
    return head, params
