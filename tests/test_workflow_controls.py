import os,unittest,tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6 import QtWidgets as W,QtCore as C,QtTest
from gasketfit.window import STYLE,NumericInput
from gasketfit.simple_fit_dialog import SimpleFitDialog
from gasketfit import localization
class WorkflowControls(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=W.QApplication.instance() or W.QApplication([])
 def wait(self,w):
  loop=C.QEventLoop();timer=C.QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit);w.worker.finished.connect(loop.quit);timer.start(30000);loop.exec();timer.stop();self.assertIsNone(w.worker)
 def test_step_one_shows_full_selected_support(self):
  import numpy as np
  from gasketfit import simple_fit as fit
  w=SimpleFitDialog()
  try:
   for preset,height in [('vr_panda',48),('custom',60)]:
    w.preset.setCurrentIndex(w.preset.findData(preset));w.height.setValue(height)
    np.testing.assert_allclose(w.viewer.pad_vertices,fit.support(w.settings(),False).mesh.vertices)
    self.assertGreater(np.ptp(w.viewer.pad_vertices[:,2]),25)
   w.tabs.setCurrentIndex(1);self.assertLessEqual(np.ptp(w.viewer.pad_vertices[:,2]),10.001)
  finally:w.close()
 def test_back_edit_updates_mesh_and_grid_without_calculation(self):
  import numpy as np
  from gasketfit import simple_fit as fit
  w=SimpleFitDialog()
  try:
   w.tabs.setCurrentIndex(2);w.calculate('trial');self.wait(w)
   w.tabs.setCurrentIndex(1);w.tabs.setCurrentIndex(2)
   self.assertEqual(w._preview_stage,2)
   w.tabs.setCurrentIndex(0);w.preset.setCurrentIndex(1);w.height.setValue(60)
   w.tabs.setCurrentIndex(2);w.height_offset.setValue(-10)
   for step in (2,3,1,2,0,3):
    w.tabs.setCurrentIndex(step)
    self.assertEqual(w._preview_stage,step);self.assertFalse(w.calculated)
    expected=fit.support(w.settings(),aligned=step>=2).mesh.vertices if step!=1 else fit.arc(w.settings(),2).vertices
    np.testing.assert_allclose(w.viewer.pad_vertices,expected)
    lo,_=w.viewer.visible_bounds()
    self.assertAlmostEqual(w.viewer.grid.transform().column(3).z(),lo[2]-2,places=4)
  finally:w.close()
 def test_compact_sidebar_keeps_preview_space(self):
  w=SimpleFitDialog();w.setStyleSheet(STYLE);w.resize(1500,900);w.show();self.app.processEvents()
  try:
   for step in range(4):
    w.tabs.setCurrentIndex(step);self.app.processEvents()
    self.assertLessEqual(w.tabs.width(),450)
    self.assertGreater(w.viewer.width(),900);self.assertGreater(w.viewer.height(),550)
   self.assertLessEqual(w.distance.width(),170)
   w.tabs.setCurrentIndex(2);w.height_offset.setValue(20)
   self.assertIsNotNone(w.depth_measurement);self.assertEqual(w.depth_measurement.mode,'projected_lower_edge')
  finally:w.close()
 def test_right_increases_left_decreases(self):
  for cls in (W.QDoubleSpinBox,W.QSpinBox,NumericInput):
   w=cls();w.setStyleSheet(STYLE);w.resize(260,40);w.setValue(20);w.show();self.app.processEvents()
   opt=W.QStyleOptionSpinBox();w.initStyleOption(opt)
   up=w.style().subControlRect(W.QStyle.ComplexControl.CC_SpinBox,opt,W.QStyle.SubControl.SC_SpinBoxUp,w)
   down=w.style().subControlRect(W.QStyle.ComplexControl.CC_SpinBox,opt,W.QStyle.SubControl.SC_SpinBoxDown,w)
   self.assertGreater(up.center().x(),down.center().x());self.assertFalse(up.intersects(down))
   QtTest.QTest.mouseClick(w,C.Qt.MouseButton.LeftButton,pos=up.center());self.assertEqual(w.value(),21)
   QtTest.QTest.mouseClick(w,C.Qt.MouseButton.LeftButton,pos=down.center());self.assertEqual(w.value(),20);w.close()
 def test_preview_then_export_cached_and_invalidate(self):
  w=SimpleFitDialog();errors=[];w.failed=errors.append
  try:
   w.tabs.setCurrentIndex(2);self.assertFalse(w.export_buttons['trial'].isEnabled())
   with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'trial.3mf';w.export_one_to('trial',str(p));self.assertFalse(p.exists());self.assertIsNone(w.worker)
    w.calculate('trial');self.wait(w);self.assertFalse(errors,errors);self.assertFalse(p.exists());self.assertTrue(w.export_buttons['trial'].isEnabled())
    mesh=w.calculated['trial']['preview'];self.assertEqual(len(w.viewer.pad_vertices),len(mesh.vertices))
    w.tabs.setCurrentIndex(3);w.tabs.setCurrentIndex(2);self.assertEqual(len(w.viewer.pad_vertices),len(mesh.vertices))
    with patch('gasketfit.simple_fit.build',side_effect=AssertionError('Export recalculated geometry')):
     w.export_one_to('trial',str(p));self.wait(w)
    self.assertFalse(errors,errors);self.assertTrue(p.exists())
    w.tilt.stepUp();self.assertFalse(w.calculated);self.assertFalse(w.export_buttons['trial'].isEnabled())
    w.calculate('arc');self.wait(w);w.strap.setChecked(True);self.assertFalse(w.calculated)
  finally:w.close()
 def test_language_live_without_losing_settings(self):
  with tempfile.TemporaryDirectory() as d:
   loc=localization.Localizer(d);loc.set_language('de')
   with patch.object(localization,'_current',loc):
    w=SimpleFitDialog()
    try:
     w.radius_spin.setValue(112.5);w.tabs.setCurrentIndex(2);loc.set_language('en')
     self.assertEqual(w.tabs.tabText(2),'3  Fit on HMD');self.assertIn('Base',w.depth_info.text());self.assertIn('Calculate',w.final_btn.text());self.assertEqual(w.radius,112.5)
     loc.set_language('de');self.assertEqual(w.tabs.tabText(2),'3  Sitz am HMD');self.assertIn('Basis',w.depth_info.text());self.assertEqual(w.radius,112.5)
    finally:w.close();loc.poll.stop()

