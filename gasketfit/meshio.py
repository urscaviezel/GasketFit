from __future__ import annotations
from .localization import tr

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import hashlib
import os
import tempfile
import uuid
import zipfile
import numpy as np
from . import __version__
from defusedxml import ElementTree as ET

STL_DTYPE = np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
UNITS = {"micron": .001, "millimeter": 1., "centimeter": 10., "meter": 1000., "inch": 25.4, "foot": 304.8}


@dataclass
class Mesh:
    vertices: np.ndarray
    faces: np.ndarray
    name: str
    source: str = ""
    note: str = ""

    @property
    def bounds(self):
        return np.array([self.vertices.min(0), self.vertices.max(0)])

    def validate(self):
        v, f = self.vertices, self.faces
        if v.ndim != 2 or v.shape[1] != 3 or not len(v) or not len(f):
            raise ValueError(tr('Die Datei enthält kein Dreiecksnetz.'))
        if not np.isfinite(v).all() or f.min() < 0 or f.max() >= len(v):
            raise ValueError(tr('Die Datei enthält ungültige Koordinaten oder Flächen.'))
        if len(f) > 6_000_000:
            raise ValueError(tr('Für Version 0.1 sind höchstens 6 Millionen Dreiecke vorgesehen.'))
        return self


def weld(vertices, faces):
    vertices, inverse = np.unique(np.asarray(vertices), axis=0, return_inverse=True)
    return vertices.astype(np.float64), inverse[np.asarray(faces)].astype(np.int32)


def load_mesh(filename: str, head=False) -> Mesh:
    path = Path(filename)
    if path.stat().st_size > 650_000_000:
        raise ValueError(tr('Die Datei ist für diese erste Version zu groß (maximal 650 MB).'))
    ext = path.suffix.lower()
    if ext == ".3mf":
        return load_3mf(path, head=head)
    if ext == ".stl":
        with path.open("rb") as stream:
            header = stream.read(84)
            if len(header) < 84:
                raise ValueError(tr('Die STL-Datei ist unvollständig.'))
            count = int.from_bytes(header[80:84], "little")
            if 84 + 50 * count == path.stat().st_size:
                if count > 6_000_000:
                    raise ValueError(tr('Das Netz enthält zu viele Dreiecke.'))
                tri = np.fromfile(stream, dtype=STL_DTYPE, count=count)["vertices"]
                vertices, faces = weld(tri.reshape(-1, 3), np.arange(count * 3).reshape(-1, 3))
                return Mesh(vertices, faces, path.name, str(path)).validate()
    if ext not in (".obj", ".stl", ".ply"):
        raise ValueError(tr('Bitte STL, 3MF, OBJ oder PLY auswählen.'))
    import trimesh
    mesh = trimesh.load(str(path), force="mesh", process=False)
    vertices, faces = weld(mesh.vertices, mesh.faces)
    return Mesh(vertices, faces, path.name, str(path)).validate()


def _transform(text):
    m = np.eye(4)
    if text:
        values = np.array([float(x) for x in text.split()])
        if values.shape != (12,) or not np.isfinite(values).all():
            raise ValueError(tr('Ungültige Lageinformation in der 3MF-Datei.'))
        m[:, :3] = values.reshape(4, 3)
    return m


def load_3mf(path: Path, head=False) -> Mesh:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if sum(x.file_size for x in infos) > 1_000_000_000:
            raise ValueError(tr('Die entpackte 3MF-Datei ist zu groß.'))
        names = [x.filename for x in infos if x.filename.lower().endswith(".model")]
        if "3D/3dmodel.model" in names:
            name = "3D/3dmodel.model"
        elif len(names) == 1:
            name = names[0]
        else:
            raise ValueError(tr('Diese mehrteilige 3MF-Datei wird noch nicht unterstützt. Bitte als STL exportieren.'))
        root = ET.fromstring(archive.read(name))
    ns = {"m": root.tag.split("}")[0][1:]}
    unit = root.get("unit", "millimeter")
    if unit not in UNITS:
        raise ValueError(f"Unbekannte 3MF-Einheit: {unit}")
    objects = {o.get("id"): o for o in root.findall("m:resources/m:object", ns)}
    cache = {}
    leaves = []

    def walk(objectid, parent, stack):
        if objectid in stack or len(stack) > 64:
            raise ValueError(tr("Zyklische oder zu tief verschachtelte 3MF-Struktur."))
        if objectid not in objects:
            raise ValueError(tr("Fehlendes Objekt in der 3MF-Datei."))
        obj = objects[objectid]
        mesh = obj.find("m:mesh", ns)
        if mesh is not None:
            if objectid not in cache:
                vs = mesh.findall("m:vertices/m:vertex", ns)
                fs = mesh.findall("m:triangles/m:triangle", ns)
                if len(fs) > 6_000_000:
                    raise ValueError(tr('Das Netz enthält zu viele Dreiecke.'))
                v = np.array([[float(q.get(k)) for k in ("x", "y", "z")] for q in vs])
                f = np.array([[int(q.get(k)) for k in ("v1", "v2", "v3")] for q in fs], dtype=np.int32)
                cache[objectid] = (v, f)
            v, f = cache[objectid]
            points = (np.c_[v, np.ones(len(v))] @ parent)[:, :3] * UNITS[unit]
            faces = f.copy()
            if np.linalg.det(parent[:3, :3]) < 0:
                faces = faces[:, [0, 2, 1]]
            leaves.append((points, faces))
        for child in obj.findall("m:components/m:component", ns):
            if any(k.endswith("}path") for k in child.attrib):
                raise ValueError(tr('Externe 3MF-Objekte werden noch nicht unterstützt. Bitte STL verwenden.'))
            walk(child.get("objectid"), _transform(child.get("transform")) @ parent, stack | {objectid})

    build = root.findall("m:build/m:item", ns)
    if not build:
        raise ValueError(tr('Die 3MF-Datei enthält keinen Bauauftrag.'))
    for item in build:
        walk(item.get("objectid"), _transform(item.get("transform")), set())
    if not leaves:
        raise ValueError(tr("Kein Netz in der 3MF-Datei gefunden."))
    note = ""
    if head and len(leaves) > 1:
        main = max(leaves, key=lambda x: len(x[1]))
        others = sum(len(f) for v, f in leaves) - len(main[1])
        if others < len(main[1]) * .01:
            note = tr('Hauptscan geladen; {v0} kleine zusätzliche Scanfragmente ausgelassen.', v0=len(leaves)-1)
            leaves = [main]
    vertices, faces, offset = [], [], 0
    for v, f in leaves:
        vertices.append(v)
        faces.append(f + offset)
        offset += len(v)
    v, f = weld(np.concatenate(vertices), np.concatenate(faces))
    return Mesh(v, f, path.name, str(path), note).validate()


def geometry_fingerprint(mesh):
    vertices = np.unique(mesh.vertices.astype("<f4"), axis=0)
    return hashlib.sha256(vertices.tobytes()).hexdigest()


def export_mesh(path: str, mesh: Mesh):
    """Atomic export in original gasket coordinates and millimetres."""
    target = Path(path)
    if target.suffix.lower() not in (".stl", ".3mf"):
        raise ValueError(tr('Bitte .stl oder .3mf als Dateiendung verwenden.'))
    temp = str(target.with_name("GasketFit-temp-" + uuid.uuid4().hex))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        if target.suffix.lower() == ".stl":
            triangles = mesh.vertices[mesh.faces]
            n = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
            n /= np.maximum(np.linalg.norm(n, axis=1)[:, None], 1e-30)
            data = np.zeros(len(triangles), dtype=STL_DTYPE)
            data["vertices"] = triangles
            data["normal"] = n
            # Binary STL only stores float32. Close but distinct OEM seam
            # vertices can collapse and break an otherwise closed mesh.
            # ASCII STL is standard STL too and preserves full coordinates.
            quantized=mesh.vertices.astype(np.float32)
            collapsed=len(np.unique(quantized,axis=0))<len(np.unique(mesh.vertices,axis=0))
            qt=data['vertices'].astype(np.float64)
            zero_area=np.any(np.linalg.norm(np.cross(qt[:,1]-qt[:,0],qt[:,2]-qt[:,0]),axis=1)==0)
            if collapsed or zero_area:
                with open(temp,'w',encoding='ascii',newline='\n') as stream:
                    stream.write('solid GasketFit_mm\n')
                    for normal,triangle in zip(n,triangles):
                        stream.write('facet normal '+' '.join(format(float(c),'.17g') for c in normal)+'\nouter loop\n')
                        for vertex in triangle:
                            stream.write('vertex '+' '.join(format(float(c),'.17g') for c in vertex)+'\n')
                        stream.write('endloop\nendfacet\n')
                    stream.write('endsolid GasketFit_mm\n')
            else:
                with open(temp, "wb") as stream:
                    stream.write(f"GasketFit {__version__} | PFDMR | millimetres".encode("ascii").ljust(80, b" "))
                    stream.write(len(triangles).to_bytes(4, "little"))
                    data.tofile(stream)
        else:
            vertices = "".join(f'<vertex x="{x:.17g}" y="{y:.17g}" z="{z:.17g}"/>' for x, y, z in mesh.vertices)
            faces = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces)
            xml = ('<?xml version="1.0" encoding="UTF-8"?>'
                   '<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
                   f'<resources><object id="1" type="model"><mesh><vertices>{vertices}</vertices>'
                   f'<triangles>{faces}</triangles></mesh></object></resources><build><item objectid="1"/></build></model>')
            from .thumbnail import render_thumbnail
            thumbnail = render_thumbnail(mesh)
            with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("Metadata/thumbnail.png", thumbnail)
                z.writestr("3D/3dmodel.model", xml)
                z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/><Relationship Target="/Metadata/thumbnail.png" Id="relThumbnail" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/></Relationships>')
                z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/><Default Extension="png" ContentType="image/png"/></Types>')
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
