import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6 import QtWidgets as W
from gasketfit.navigation_ui import NavigationPage
from gasketfit.padwindow import PadWindow
from gasketfit.window import STYLE

class BetaUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=W.QApplication.instance() or W.QApplication([])

    def test_unavailable_spacemouse_is_unchecked_and_disabled_after_reset(self):
        with patch('gasketfit.navigation_ui.sys.platform','linux'):
            w=NavigationPage()
            try:
                for _ in range(2):
                    for box in (w.enabled,w.translation,w.rotation):
                        self.assertFalse(box.isChecked());self.assertFalse(box.isEnabled())
                    self.assertFalse(w.translation_gain.isEnabled())
                    w.load()
            finally:w.timer.stop();w.close()

    def test_header_and_menu_have_no_old_workflow_badge(self):
        w=PadWindow()
        try:
            labels=[x.text() for x in w.findChildren(W.QLabel)]
            self.assertIn('GasketFit Beta',labels)
            self.assertFalse(any('Polster zuerst' in x or 'cushion first' in x or 'Nose arch 06' in x or 'Nasenbogen 06' in x for x in labels))
            self.assertFalse(any('V2' in a.text() for a in w.design_menu.actions()))
        finally:w.close()

    def test_unchecked_indicator_has_its_own_visible_border(self):
        rule=STYLE.split('QCheckBox::indicator {',1)[1].split('}',1)[0]
        self.assertIn('border:2px solid #9aa8cc',rule)
