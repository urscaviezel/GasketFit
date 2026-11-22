"""Local Windows print-net repair, with a bounded geometry comparison.

The construction guards remain stricter. This final manufacturing conversion
allows at most five micrometres of numeric movement, including on the mating
and cushion surfaces. A failed/unavailable repair never silently exports.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from .meshio import Mesh, export_mesh, load_mesh
from .localization import tr, app_folder

MAX_MOVEMENT_MM = .005


def print_frame(mesh, pose):
    """Export in the reference axes, independent of scan/workflow placement.

    Use the pose stored WITH the calculated geometry, not current UI inputs.
    Assemblies use their magnetic-base pose; a support-only export uses the
    fitted support pose. This is a rigid copy: relative fit and source meshes
    are never changed. Centre the bounding box in XY and put its bottom at Z=0.
    """
    from .profile import pose_matrix, transform
    pose = np.asarray(pose, dtype=float)
    if pose.shape != (6,) or not np.isfinite(pose).all():
        raise ValueError(tr('Die Referenzausrichtung f\u00fcr den Export fehlt oder ist ung\u00fcltig.'))
    matrix = np.linalg.inv(pose_matrix(pose))
    vertices = transform(mesh.vertices, matrix)
    lo, hi = vertices.min(0), vertices.max(0)
    shift = -np.array([(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]])
    vertices += shift
    matrix[:3, 3] += shift
    return Mesh(vertices, mesh.faces.copy(), mesh.name), dict(
        reference_pose=pose.tolist(), world_to_print=matrix.tolist(),
        xy_centred=True, bottom_z_mm=0., workflow_pose_removed=True)


def validate_repair(original, repaired):
    original.validate()
    repaired.validate()
    before = trimesh.Trimesh(original.vertices, original.faces, process=False)
    after = trimesh.Trimesh(repaired.vertices, repaired.faces, process=False)
    if not before.is_volume or not after.is_volume or len(after.split()) != 1:
        raise ValueError(tr('Die Druckaufbereitung ergibt keinen geschlossenen Einzelkörper.'))
    if np.any(after.area_faces <= 0):
        raise ValueError(tr('Die Druckaufbereitung enthält ungültige Dreiecke.'))
    maximum = 0.
    # All vertices in both directions: a conservative bound that also rejects
    # merged details or disconnected additions, without registering/moving parts.
    for source, target in ((before, after), (after, before)):
        distances = cKDTree(target.vertices).query(source.vertices)[0]
        maximum = max(maximum, float(distances.max()))
    if maximum > MAX_MOVEMENT_MM:
        raise ValueError(tr('Die Druckaufbereitung würde die Passform verändern. Export abgebrochen.'))
    # Check every triangle centre too; changed triangulation must not bridge
    # openings or flatten the protected surfaces. Bound query memory in batches.
    surface_maximum = 0.
    for source, target in ((before, after), (after, before)):
        centres = source.triangles_center
        for start in range(0, len(centres), 10000):
            distances = trimesh.proximity.closest_point(target, centres[start:start+10000])[1]
            surface_maximum = max(surface_maximum, float(distances.max()))
    volume_change = abs(float(after.volume - before.volume))
    if surface_maximum > MAX_MOVEMENT_MM or volume_change > max(.1, abs(before.volume)*.0001):
        raise ValueError(tr('Die Druckaufbereitung würde die Passform verändern. Export abgebrochen.'))
    return dict(method='Windows Printing3D TryPartialRepairAsync (local)',
                max_vertex_movement_mm=maximum,
                max_triangle_centre_distance_mm=surface_maximum,
                movement_limit_mm=MAX_MOVEMENT_MM,
                volume_change_mm3=volume_change,
                vertices_checked=len(before.vertices)+len(after.vertices),
                triangle_centres_checked=len(before.faces)+len(after.faces),
                closed_single_body=True)


def prepare_print_mesh(mesh):
    # Already printable meshes must not be sent through Windows repair:
    # retriangulation can change the physically approved mating interface.
    vertices=mesh.vertices.astype(np.float32).astype(np.float64)
    encoded=trimesh.Trimesh(vertices,mesh.faces,process=False)
    distinct = len(np.unique(vertices, axis=0)) == len(vertices)
    if distinct and encoded.is_volume and encoded.is_winding_consistent and (encoded.area_faces>0).all() and len(encoded.split())==1:
        movement=float(np.linalg.norm(vertices-mesh.vertices,axis=1).max(initial=0.))
        if movement<=1e-4:
            return Mesh(vertices,mesh.faces.copy(),mesh.name), dict(
                method='Validated float32 export; no geometry repair',
                max_vertex_movement_mm=movement, movement_limit_mm=1e-4,
                closed_single_body=True, repair_applied=False)
    # A rigid rotation into print coordinates can collapse tiny Boolean seams
    # again, even if they were float-safe in the workflow frame. Preserve the
    # original topology at the FINAL coordinates instead of repairing/rebuilding
    # an otherwise valid body. This also protects STL, which welds equal points.
    original = trimesh.Trimesh(mesh.vertices, mesh.faces, process=False)
    if original.is_volume and (original.area_faces > 0).all() and len(original.split()) == 1:
        from .floatmesh import float_safe
        try:
            vertices, faces, precision = float_safe(mesh.vertices, mesh.faces, max_change=.00009)
        except AssertionError:
            pass  # Leave genuine failures to the existing checked repair path.
        else:
            return Mesh(vertices, faces, mesh.name), dict(
                method='Topology-preserving float32 encoding in print coordinates',
                max_vertex_movement_mm=precision['max_coordinate_change_mm'],
                movement_limit_mm=1e-4, closed_single_body=True,
                repair_applied=False, float_encoding=precision)
    if sys.platform != 'win32':
        raise RuntimeError(tr('Das Modell benötigt eine zusätzliche Netzreparatur. Es wurde nichts exportiert.'))
    helper = Path(__file__).with_name('GasketRepair.exe')
    if not helper.exists():
        raise RuntimeError(tr('Die lokale Windows-Druckaufbereitung fehlt. Bitte die vollständige App verwenden.'))
    from .platform_support import cache_folder
    cache = cache_folder()
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='print-', dir=cache) as folder:
        source, destination = Path(folder)/'input.3mf', Path(folder)/'output.3mf'
        export_mesh(source, mesh)
        result = subprocess.run([str(helper), str(source), str(destination)],
                                capture_output=True, text=True, timeout=90,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or not destination.exists():
            raise RuntimeError(tr('Die lokale Windows-Druckaufbereitung ist fehlgeschlagen. Es wurde nichts exportiert.'))
        repaired = load_mesh(str(destination))
        report = validate_repair(mesh, repaired)
        repaired.name = mesh.name
        return repaired, report


def export_print_mesh(filename, mesh):
    if Path(filename).suffix.lower() not in ('.stl', '.3mf'):
        raise ValueError(tr('Bitte .stl oder .3mf als Dateiendung verwenden.'))
    repaired, report = prepare_print_mesh(mesh)
    export_mesh(filename, repaired)
    return report
