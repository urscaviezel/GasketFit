import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6 import QtWidgets
from gasketfit import localization


class FirstRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_ui_language_and_english_fallback_offline(self):
        for preferred, expected in [(['de-CH'], 'de'), (['en-GB'], 'en'),
                                    (['fr-CA'], 'fr'), (['it-CH', 'de'], 'en'), ([], 'en')]:
            with self.subTest(preferred=preferred), tempfile.TemporaryDirectory() as folder:
                with patch.object(localization.QtCore.QLocale, 'system') as locale:
                    locale.return_value.uiLanguages.return_value = preferred
                    loc = localization.Localizer(folder)
                self.assertEqual(loc.language, expected)
                self.assertEqual(set(loc.catalogs), {'de', 'en', 'fr'})
                self.assertEqual(list(loc.directory.iterdir()), [])
                for code, text in [('en', 'Settings'), ('de', 'Einstellungen'), ('fr', 'Paramètres')]:
                    loc.set_language(code)
                    self.assertEqual(loc.translate('Einstellungen'), text)
                loc.poll.stop()

    def test_explicit_choice_survives_update(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'settings.json').write_text(json.dumps({'language': 'fr'}))
            with patch.object(localization, 'system_language', return_value='en'):
                loc = localization.Localizer(folder)
            self.assertEqual(loc.language, 'fr')
            loc.poll.stop()

    def test_hmd_step_has_no_legacy_options_or_empty_design_menu(self):
        from gasketfit.padwindow import PadWindow
        with tempfile.TemporaryDirectory() as folder:
            loc = localization.Localizer(folder)
            loc.settings.update(auto_updates=False, auto_languages=False)
            with patch.object(localization, '_current', loc):
                window = PadWindow()
                for workflow in ('closed', 'open', 'closed'):
                    window.switch_workflow(workflow)
                    window.tabs.setCurrentIndex(1)
                    self.assertTrue(window.include_base.isHidden())
                    self.assertTrue(window.closed_shell.isHidden())
                    self.assertTrue(window.include_base.isChecked())
                    self.assertTrue(window.closed_shell.isChecked())
                self.assertNotIn(loc.translate('Entwurf'), [a.text() for a in window.menuBar().actions()])
                window.close()
                window.deleteLater()
            loc.poll.stop()

    def test_linux_layout_detects_case_and_missing_library(self):
        from build_portable import check_case_sensitive_layout
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder)
            internal = app/'_internal'
            (internal/'Rtree.libs').mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                check_case_sensitive_layout(app)
            (internal/'Rtree.libs').rename(internal/'temporary')
            (internal/'temporary').rename(internal/'rtree.libs')
            metadata = internal/'rtree-1.4.1.dist-info'
            metadata.mkdir()
            (metadata/'RECORD').write_text('rtree.libs/libspatialindex-test.so,,\n')
            with self.assertRaises(RuntimeError):
                check_case_sensitive_layout(app)
            (internal/'rtree.libs/libspatialindex-test.so').write_bytes(b'test')
            check_case_sensitive_layout(app)
