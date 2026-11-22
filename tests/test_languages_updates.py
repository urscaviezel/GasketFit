import io
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid
import zipfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets
import numpy as np
from gasketfit.localization import Localizer, validate_catalog, atomic_json
from gasketfit import online
from gasketfit.fitting import Surface, first_surface_crossing
from gasketfit.meshio import Mesh


class Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.root = Path(__file__).parent / "tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_sparse_triangles_are_not_rejected_as_missing_surface(self):
        head = Mesh(np.array([[0., -100, -100], [0, 100, -100], [0, 0, 100]]), np.array([[0, 1, 2]]), "sparse")
        surface = Surface(head)
        points = np.array([[10., 0, 0]])
        directions = np.array([[-1., 0, 0]])
        steps = np.arange(-4., 16.01, .5)
        self.assertGreater(surface.tree.query(points)[0][0], 50)
        hit = first_surface_crossing(surface, points, directions, 5.25, steps)
        self.assertEqual(steps[hit[0]], 5.)

    def test_first_exact_hit_precedes_coarse_vertex_hit(self):
        head = Mesh(np.array([[0., -6, -6], [0, 6, -6], [0, 0, 6.]]), np.array([[0, 1, 2]]), "sparse")
        hit = first_surface_crossing(Surface(head), np.array([[10., 0, 0]]), np.array([[-1., 0, 0]]), 7., np.arange(-4., 16.01, .5))
        self.assertEqual(hit[0], 14)  # 3 mm inward: exact clearance 7 mm.

    def test_language_hot_discovery_fallback_and_removal(self):
        loc = Localizer(self.root)
        self.assertEqual(set(loc.catalogs), {"en", "de", "fr"})
        data = {"schema": 1, "code": "es", "name": "Español", "messages": {"Dicke": "Épaisseur"}}
        atomic_json(loc.directory / "es.json", data)
        loc.scan()
        loc.set_language("es")
        self.assertEqual(loc.translate("Dicke"), "Épaisseur")
        self.assertEqual(loc.translate("Projekt öffnen"), "Open project")
        (loc.directory / "es.json").unlink()
        loc.scan()
        self.assertEqual(loc.language, "en")
        loc.poll.stop()
        loc.deleteLater()

    def test_malformed_translation_is_isolated(self):
        loc = Localizer(self.root)
        (loc.directory / "bad.json").write_text('{broken', encoding="utf8")
        loc.scan()
        self.assertEqual(len(loc.invalid), 1)
        self.assertIn("en", loc.catalogs)
        loc.poll.stop()
        loc.deleteLater()

    def test_placeholder_code_and_remote_content_validation(self):
        for code, messages in [("../en", {}), ("es", {"Version: {v0}": "Version"}), ("es", {"a": "{v0.__class__}"}), ("es", {"a": '<img src="https://example.com">'})]:
            with self.assertRaises(ValueError):
                validate_catalog({"schema": 1, "code": code, "name": "Test", "messages": messages})

    def test_disable_checks_and_language_persist(self):
        loc = Localizer(self.root)
        loc.settings["auto_updates"] = False
        loc.settings["auto_languages"] = False
        loc.set_language("de")
        second = Localizer(self.root)
        self.assertFalse(second.settings["auto_updates"])
        self.assertFalse(second.settings["auto_languages"])
        self.assertEqual(second.language, "de")
        for item in (loc, second):
            item.poll.stop()
            item.deleteLater()

    def test_partial_language_switch_restores_english_fallback_labels(self):
        loc = Localizer(self.root)
        atomic_json(loc.directory / "es.json", {"schema": 1, "code": "es", "name": "Español", "messages": {"Dicke": "Épaisseur"}})
        loc.scan()
        loc.set_language("es")
        label = QtWidgets.QLabel(loc.translate("Projekt öffnen"))
        self.assertEqual(label.text(), "Open project")
        loc.set_language("de")
        loc.retranslate(label)
        self.assertEqual(label.text(), "Projekt öffnen")
        loc.poll.stop()
        loc.deleteLater()

    def test_live_translation_keeps_formatted_values(self):
        loc = Localizer(self.root)
        loc.set_language("de")
        label = QtWidgets.QLabel(loc.translate("Neue Version: {v0}", v0="9.8.7"))
        loc.set_language("en")
        loc.retranslate(label)
        self.assertEqual(label.text(), "New version: 9.8.7")
        loc.set_language("de")
        loc.retranslate(label)
        self.assertEqual(label.text(), "Neue Version: 9.8.7")
        loc.poll.stop()
        loc.deleteLater()

    def test_empty_repository_and_unpublished_releases(self):
        with patch.object(online, "github_json", return_value=None):
            self.assertEqual(online.language_inventory(), [])
            self.assertEqual(online.check_update(), {"state": "unpublished"})

    def test_automatic_checks_can_be_disabled_while_manual_checks_remain(self):
        from PySide6 import QtCore
        from gasketfit.settings import OnlineController
        loc = Localizer(self.root)
        loc.settings.update(auto_languages=False, auto_updates=False)
        parent = QtCore.QObject()
        with patch("gasketfit.settings.current", return_value=loc):
            controller = OnlineController(parent)
            with patch.object(controller, "run") as run:
                controller.automatic()
                run.assert_not_called()
                controller.check_updates()
                self.assertEqual(run.call_args.args[0], "updates")
                controller.check_languages()
                self.assertEqual(run.call_args.args[0], "languages")
        controller.timer.stop()
        loc.poll.stop()
        loc.deleteLater()
        parent.deleteLater()

    def test_language_download_is_hash_pinned_and_validated(self):
        import base64
        import hashlib
        content = json.dumps({"schema": 1, "code": "es", "name": "Español", "messages": {"Dicke": "Épaisseur"}}).encode()
        sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        with patch.object(online, "github_json", return_value={"content": base64.b64encode(content).decode()}):
            self.assertEqual(online.download_language({"name": "es.json", "sha": sha}, self.root), "es")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                online.download_language({"name": "es.json", "sha": "0" * 40}, self.root)
        self.assertTrue((self.root / "es.json").is_file())

    def test_semantic_version_comparison_and_asset_selection(self):
        from gasketfit.platform_support import package_name
        release = {"tag_name": "v99.0.0", "assets": [{"name": package_name("99.0.0")}, {"name": "checksums.json"}]}
        with patch.object(online, "github_json", return_value=[release]):
            result = online.check_update()
        self.assertEqual(result["state"], "new")
        self.assertTrue(result["package"])
        self.assertGreater(online.version_tuple("0.10.0"), online.version_tuple("0.9.9"))

    def test_unsafe_or_incomplete_update_archive_rejected(self):
        for name in ["GasketFit/../escape", "GasketFit/C:/evil", "GasketFit/evil\\escape", "Other/GasketFit.exe"]:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as z:
                z.writestr(name, "bad")
            stream.seek(0)
            with self.assertRaises(ValueError):
                online.extract_update(stream, self.root / "extracted")
        self.assertFalse((self.root / "escape").exists())

    def test_valid_update_archive_extracts(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("GasketFit/GasketFit.exe", b"fake test exe")
            z.writestr("GasketFit/_internal/test.dll", b"fake test dll")
        stream.seek(0)
        target = online.extract_update(stream, self.root)
        self.assertTrue((target / "GasketFit.exe").is_file())

    @patch("gasketfit.platform_support.supports_in_app_update", return_value=True)
    def test_mismatched_update_checksum_prevents_staging(self, _windows_installer):
        release = {"version": "9.0.0", "filename": "GasketFit-9.0.0-Windows-x64.zip", "package": {"browser_download_url": "https://github.com/package"}, "checksums": {"browser_download_url": "https://github.com/sums"}}
        with patch.object(online, "request", side_effect=[json.dumps({release['filename']: 'a' * 64}).encode(), b'wrong']):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                online.prepare_update(release, self.root)

    @patch("gasketfit.platform_support.supports_in_app_update", return_value=True)
    def test_update_staging_preserves_settings_and_local_languages(self, _windows_installer):
        import hashlib
        root = self.root / "GasketFit"
        (root / "lang").mkdir(parents=True)
        (root / "settings.json").write_text('{"auto_updates":false}', encoding="utf8")
        (root / "lang" / "es.json").write_text('private translation', encoding="utf8")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("GasketFit/GasketFit.exe", b"test executable")
            z.writestr("GasketFit/_internal/test.dll", b"test dll")
        content = stream.getvalue()
        release = {"version": "9.0.0", "filename": "GasketFit-9.0.0-Windows-x64.zip", "package": {"browser_download_url": "https://github.com/package"}, "checksums": {"browser_download_url": "https://github.com/sums"}}
        with patch.object(online, "request", side_effect=[json.dumps({release['filename']: hashlib.sha256(content).hexdigest()}).encode(), content]):
            staged = online.prepare_update(release, root)
        self.assertEqual((staged / "settings.json").read_text(), '{"auto_updates":false}')
        self.assertEqual((staged / "lang" / "es.json").read_text(), 'private translation')
        self.assertTrue((root / "settings.json").exists())


if __name__ == "__main__":
    unittest.main()
