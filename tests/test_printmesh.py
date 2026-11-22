import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import trimesh
from gasketfit.meshio import Mesh
from gasketfit.printmesh import validate_repair, prepare_print_mesh, export_print_mesh


def model(solid):
    return Mesh(np.array(solid.vertices), np.array(solid.faces), 'Test')


class PrintPreparation(unittest.TestCase):
    def setUp(self):
        self.solid = trimesh.creation.box(extents=[20, 30, 10])
        self.mesh = model(self.solid)

    def test_valid_print_geometry_bypasses_repair(self):
        with patch('gasketfit.printmesh.subprocess.run',side_effect=AssertionError('Unnecessary repair')):
            result,report=prepare_print_mesh(self.mesh)
        self.assertFalse(report['repair_applied'])
        np.testing.assert_array_equal(result.faces,self.mesh.faces)
        np.testing.assert_array_equal(result.vertices,self.mesh.vertices)

    def test_rejects_moving_even_a_closed_body(self):
        moved = self.solid.copy()
        moved.apply_translation([.02, 0, 0])
        with self.assertRaises(ValueError):
            validate_repair(self.mesh, model(moved))

    def test_final_float_encoding_preserves_small_seams_without_repair(self):
        solid = self.solid.copy()
        solid.apply_translation([50, 50, 50])
        a, b, c = solid.faces[0]
        point = solid.vertices[a] + 1e-7 * (solid.triangles_center[0] - solid.vertices[a])
        n = len(solid.vertices)
        vertices = np.vstack([solid.vertices, point])
        faces = np.vstack([solid.faces[1:], [a, b, n], [b, c, n], [c, a, n]])
        mesh = Mesh(vertices, faces, 'Tiny valid seam')
        with patch('gasketfit.printmesh.subprocess.run', side_effect=AssertionError('Unnecessary repair')):
            result, report = prepare_print_mesh(mesh)
        np.testing.assert_array_equal(result.faces, faces)
        self.assertLess(report['max_vertex_movement_mm'], 1e-4)
        self.assertFalse(report['repair_applied'])
        # STL has no indices. Weld equal coordinates as a slicer would do.
        unique, inverse = np.unique(result.vertices, axis=0, return_inverse=True)
        welded = trimesh.Trimesh(unique, inverse[result.faces], process=True)
        self.assertTrue(welded.is_volume)
        self.assertTrue((welded.area_faces > 0).all())

    def test_rejects_missing_faces(self):
        opened = Mesh(self.mesh.vertices, self.mesh.faces[:-1], 'Open')
        with self.assertRaises(ValueError):
            validate_repair(self.mesh, opened)

    def test_rejects_extra_body(self):
        other = self.solid.copy()
        other.apply_translation([50, 0, 0])
        with self.assertRaises(ValueError):
            validate_repair(self.mesh, model(trimesh.util.concatenate([self.solid, other])))

    def test_failed_preparation_preserves_existing_export(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'tmp') as folder:
            path = Path(folder)/'existing.stl'
            path.write_bytes(b'existing print')
            with patch('gasketfit.printmesh.prepare_print_mesh', side_effect=ValueError('Rejected')):
                with self.assertRaises(ValueError):
                    export_print_mesh(path, self.mesh)
            self.assertEqual(path.read_bytes(), b'existing print')

    @unittest.skipUnless(sys.platform == 'win32', 'Windows Printing3D API')
    def test_native_local_repair_and_guard(self):
        repaired, report = prepare_print_mesh(self.mesh)
        self.assertTrue(report['closed_single_body'])
        self.assertLessEqual(report['max_vertex_movement_mm'], .005)
        np.testing.assert_allclose(repaired.bounds, self.mesh.bounds, atol=.005)
