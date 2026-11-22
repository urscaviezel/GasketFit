import unittest
from pathlib import Path
import tempfile
import numpy as np
import trimesh
from gasketfit.meshio import Mesh, load_mesh
from gasketfit.profile import pose_matrix, transform
from gasketfit.printmesh import print_frame, export_print_mesh


class ExportReferenceFrame(unittest.TestCase):
    def test_all_workflow_rotations_and_translations_export_in_the_same_frame(self):
        local = trimesh.creation.box(extents=[41., 23., 17.])
        local.apply_translation([3., -12., 40.])
        poses = [[0]*6, [18, -32, 47, 23, 0, 0], [-15, 6, 22, 0, -12, 0],
                 [8, -9, -12, 0, 0, 37], [500, -200, 330, 12, -8, 17]]
        expected = local.vertices - [3., -12., 31.5]
        for pose in poses:
            with self.subTest(pose=pose):
                source = Mesh(transform(local.vertices, pose_matrix(pose)), local.faces.copy(), 'Test')
                unchanged = source.vertices.copy()
                output, report = print_frame(source, pose)
                np.testing.assert_allclose(output.vertices, expected, atol=1e-12)
                np.testing.assert_allclose(output.bounds.mean(0)[:2], 0, atol=1e-12)
                self.assertEqual(output.bounds[0, 2], 0.)
                np.testing.assert_array_equal(source.vertices, unchanged)
                np.testing.assert_array_equal(output.faces, source.faces)
                np.testing.assert_allclose(transform(source.vertices, np.array(report['world_to_print'])), output.vertices, atol=1e-12)

    def test_stl_and_3mf_store_the_normalized_geometry_without_a_hidden_pose(self):
        solid = trimesh.creation.box(extents=[41., 23., 17.])
        pose = [13., -21., 97., 19., -7., 13.]
        source = Mesh(transform(solid.vertices, pose_matrix(pose)), solid.faces.copy(), 'Test')
        normalized, _ = print_frame(source, pose)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'tmp') as folder:
            for ext in ['stl', '3mf']:
                path = Path(folder)/('normalized.'+ext)
                export_print_mesh(path, normalized)
                actual = load_mesh(str(path))
                np.testing.assert_allclose(actual.bounds, [[-20.5,-11.5,0],[20.5,11.5,17]], atol=1e-6)
                self.assertTrue(trimesh.Trimesh(actual.vertices,actual.faces,process=False).is_volume)

    def test_invalid_pose_is_rejected(self):
        solid = trimesh.creation.box()
        mesh = Mesh(solid.vertices, solid.faces, 'Test')
        for pose in [None, [], [0]*5, [0]*5+[float('nan')]]:
            with self.subTest(pose=pose), self.assertRaises(ValueError):
                print_frame(mesh, pose)
