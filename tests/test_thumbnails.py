import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import numpy as np
import trimesh
from PySide6.QtGui import QImage
from gasketfit.meshio import Mesh, export_mesh, load_mesh


class Thumbnails(unittest.TestCase):
    def test_worker_export_contains_linked_png_and_unchanged_geometry(self):
        box = trimesh.creation.box(extents=[12, 8, 4])
        mesh = Mesh(box.vertices.copy(), box.faces.copy(), 'test')
        before = mesh.vertices.copy()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'preview.3mf'
            # Export workers must not need a QApplication or OpenGL context.
            with ThreadPoolExecutor(max_workers=1) as worker:
                worker.submit(export_mesh, str(path), mesh).result()
            with zipfile.ZipFile(path) as archive:
                relationships = ET.fromstring(archive.read('_rels/.rels'))
                thumbnail = next(r for r in relationships if r.attrib['Type'].endswith('/metadata/thumbnail'))
                image = QImage.fromData(archive.read(thumbnail.attrib['Target'].lstrip('/')))
                self.assertFalse(image.isNull())
                self.assertEqual((image.width(), image.height()), (256, 256))
                self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
                self.assertGreater(image.pixelColor(128, 128).alpha(), 0)
                types = ET.fromstring(archive.read('[Content_Types].xml'))
                self.assertTrue(any(t.attrib.get('Extension') == 'png' and
                                    t.attrib.get('ContentType') == 'image/png' for t in types))
            restored = load_mesh(path)
            np.testing.assert_allclose(np.sort(restored.vertices, axis=0), np.sort(before, axis=0))
            np.testing.assert_array_equal(restored.vertices[restored.faces], mesh.vertices[mesh.faces])
            np.testing.assert_array_equal(mesh.vertices, before)

    def test_thumbnail_failure_keeps_existing_export_and_removes_temp(self):
        box = trimesh.creation.box()
        mesh = Mesh(box.vertices, box.faces, 'test')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'existing.3mf'
            path.write_bytes(b'previous export')
            with patch('gasketfit.thumbnail.render_thumbnail', side_effect=RuntimeError('test failure')):
                with self.assertRaises(RuntimeError):
                    export_mesh(str(path), mesh)
            self.assertEqual(path.read_bytes(), b'previous export')
            self.assertEqual(list(Path(directory).iterdir()), [path])
