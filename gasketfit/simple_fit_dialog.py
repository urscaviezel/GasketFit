"""Guided physical fitting without importing or inventing a head scan."""
from pathlib import Path
import numpy as np
from PySide6 import QtCore,QtWidgets as W
from .window import button,label,Job
from . import simple_fit as fit
from .printmesh import prepare_print_mesh,print_frame
from .meshio import Mesh,export_mesh
from .localization import tr,current

class WorkflowPages(W.QStackedWidget):
    """Step bar above the workspace; scrollable controls in a narrow sidebar."""
    def __init__(self):
        super().__init__();self.bar=W.QTabBar();self.bar.setExpanding(False)
        self.bar.currentChanged.connect(self.setCurrentIndex)
        self.currentChanged.connect(self.bar.setCurrentIndex)

    def addTab(self,page,title):
        area=W.QScrollArea();area.setWidgetResizable(True);area.setWidget(page)
        self.addWidget(area);self.bar.addTab(title)

    def tabText(self,index):return self.bar.tabText(index)

    def setEnabled(self,enabled):
        super().setEnabled(enabled);self.bar.setEnabled(enabled)

class WrappedCheckBox(W.QWidget):
    toggled=QtCore.Signal(bool)
    def __init__(self,text):
        super().__init__();row=W.QHBoxLayout(self);row.setContentsMargins(0,0,0,0)
        self.check=W.QCheckBox();self.caption=label(text)
        row.addWidget(self.check,0,QtCore.Qt.AlignmentFlag.AlignTop);row.addWidget(self.caption,1)
        self.caption.installEventFilter(self);self.check.toggled.connect(self.toggled)
    def isChecked(self):return self.check.isChecked()
    def setChecked(self,value):self.check.setChecked(value)
    def eventFilter(self,obj,event):
        if obj is self.caption and event.type()==QtCore.QEvent.Type.MouseButtonRelease:
            self.check.toggle();return True
        return super().eventFilter(obj,event)

class SimpleFitDialog(W.QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('Offenes Gasket · Ohne Scan'));self.resize(1200,800);self.worker=None;self.radius=110.;self.calculated={};self.export_buttons={}
        self.setWindowFlags(QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.WindowMinMaxButtonsHint | QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.setModal(False)
        self.last_directory=QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.DesktopLocation)
        layout=W.QVBoxLayout(self)
        layout.addWidget(label(tr('Offenes Gasket ohne Scan'),'section'))
        layout.addWidget(label(tr('Polster wählen → Stirnform testen → Sitz testen → Gasket erstellen. Die Passproben ersetzen die Ausrichtung am Kopfscan.')))
        tools=W.QHBoxLayout();tools.addWidget(button(tr('Entwurf öffnen …'),self.open));tools.addWidget(button(tr('Entwurf speichern …'),self.save));tools.addStretch();layout.addLayout(tools)
        self.tabs=WorkflowPages();layout.addWidget(self.tabs.bar)
        workspace=W.QHBoxLayout();layout.addLayout(workspace,1)
        self.tabs.setFixedWidth(440);workspace.addWidget(self.tabs)
        preview=W.QVBoxLayout();workspace.addLayout(preview,1)
        self.tabs.setStyleSheet('QPushButton { padding:6px 8px; } QPushButton#primary { padding:8px 10px; } QLabel#section { font-size:15pt; }')
        pages=[]
        for title in [tr('1  Polster'),tr('2  Stirnform'),tr('3  Sitz am HMD'),tr('4  Fertiges Gasket')]:
            page=W.QWidget();p=W.QVBoxLayout(page);p.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop);pages.append(p);self.tabs.addTab(page,title)
        p=pages[0];p.addWidget(label(tr('Welches Polster verwendest du?'),'section'))
        self.preset=W.QComboBox();self.preset.addItem('VR Panda','vr_panda');self.preset.addItem(tr('Benutzerdefiniert'),'custom');p.addWidget(self.preset)
        self.custom=W.QWidget();form=W.QFormLayout(self.custom);self.width=self.spin(140,240,198,' mm');self.height=self.spin(30,65,48,' mm');form.addRow(tr('Länge flach'),self.width);form.addRow(tr('Höhe'),self.height);p.addWidget(self.custom);self.custom.hide()
        p.addWidget(label(tr('Verwende bei allen Passproben dasselbe Polster und dieselbe Klettschicht wie später am Gasket.')));p.addWidget(button(tr('Weiter zur Stirnform'),lambda:self.tabs.setCurrentIndex(1)))
        p=pages[1];p.addWidget(label(tr('Welche Rundung liegt gleichmäßig an?'),'section'))
        p.addWidget(label(tr('Drei kleine Bögen drucken und mit dem Polster an der späteren Stirnposition anhalten. Nicht fest gegen die Stirn drücken. Punkte auf der Vorderseite kennzeichnen die Bögen.')))
        self.actions(p,'arcs',tr('Drei Stirn-Passbögen berechnen'),self.export_arcs)
        self.shape=W.QComboBox()
        for text,r in [(tr('•  Flach · R140 mm'),140.),(tr('••  Mittel · R110 mm'),110.),(tr('•••  Stärker gewölbt · R85 mm'),85.)]:self.shape.addItem(text,r)
        self.shape.addItem(tr('Angepasste Stirnform'),None)
        self.shape.setCurrentIndex(1);p.addWidget(self.shape)
        radius_form=W.QFormLayout();self.radius_spin=self.spin(80,180,110,' mm');self.radius_spin.setSingleStep(1);radius_form.addRow(tr('Radius der Stirnauflage'),self.radius_spin);p.addLayout(radius_form)
        p.addWidget(label(tr('Kleinerer Radius: stärker gewölbt. Größerer Radius: flacher. Der Radius steht auf dem Passbogen und im Dateinamen.'),'hint'))
        self.shape_info=label(tr('Ausgewählt: mittel.'),'hint');p.addWidget(self.shape_info)
        self.actions(p,'arc',tr('Angepassten Passbogen berechnen'),lambda:self.export_one('arc'))
        self.fit_ok=WrappedCheckBox(tr('Mit Polster geprüft: liegt gleichmäßig und angenehm an.'));p.addWidget(self.fit_ok)
        p.addWidget(button(tr('Weiter zum Sitz am HMD'),lambda:self.tabs.setCurrentIndex(2)))
        p=pages[2];p.addWidget(label(tr('Abstand und Neigung ausprobieren'),'section'))
        p.addWidget(label(tr('Die Montageprobe enthält die Magnetbasis und eine schmale mittlere Stirnauflage. Mit Polster und befestigter Basis vorsichtig anprobieren. Bei Kontakt der Linsenfassungen mehr Abstand wählen. Ohne Scan wird kein Augenabstand berechnet.')))
        form=W.QFormLayout()
        self.distance=self.spin(-15,30,5,' mm');self.distance.setSingleStep(.5)
        self.tilt=self.spin(-25,0,-15,'°');self.tilt.setSingleStep(1)
        self.height_offset=self.spin(-20,20,0,' mm');self.height_offset.setSingleStep(.5)
        form.addRow(tr('Auflage vor/zurück'),self.distance);form.addRow(tr('Neigung'),self.tilt);form.addRow(tr('Höhenversatz'),self.height_offset);p.addLayout(form)
        p.addWidget(label(tr('Positiv: Auflage höher am HMD. Negativ: tiefer. 0 mm entspricht der bisherigen Ausgangshöhe.'),'hint'))
        self.depth_info=label('');self.depth_info.setStyleSheet('font-size:14.4px; font-weight:700; color:#ffd16a; background:#151d3c; border:1px solid #34406a; border-radius:8px; padding:8px;');p.addWidget(self.depth_info)
        p.addWidget(label(tr('Waagerechter Abstand ohne Polster. Liegt die Auflage höher, dient das Lot ihrer äußeren Unterkante als Referenz.'),'hint'))
        self.actions(p,'trial',tr('Montageprobe berechnen'),lambda:self.export_one('trial'))
        self.mount_ok=WrappedCheckBox(tr('Diese Einstellung am HMD geprüft: Sitz und Abstand passen.'));p.addWidget(self.mount_ok)
        p.addWidget(button(tr('Weiter zum fertigen Gasket'),lambda:self.tabs.setCurrentIndex(3)))
        p=pages[3];self.strap=WrappedCheckBox(tr('Kopfbandhalterung hinzufügen · 37 × 4 mm'));p.addWidget(self.strap)
        p.addWidget(label(tr('Die gewählte Rundung, der Abstand und die Neigung werden in das fertige Modell übernommen. Eine individuelle Anpassung an Stirnasymmetrien findet ohne Scan nicht statt.')))
        self.review_info=label('','hint');p.addWidget(self.review_info)
        self.final_btn=self.actions(p,'final',tr('Fertiges offenes Gasket berechnen'),lambda:self.export_one('final'))
        from .padwindow import PadViewer
        self.viewer=PadViewer();self.viewer.setMinimumHeight(260)
        views=W.QHBoxLayout()
        for caption,direction in [('3D','3d'),(tr('Vorne'),'front'),(tr('Rechts'),'right'),(tr('Links'),'left'),(tr('Oben'),'top')]:
            views.addWidget(button(caption,lambda checked=False,d=direction:self.viewer.view(d)))
        views.addWidget(button(tr('Zentrieren'),self.viewer.fit_view));views.addStretch();preview.addLayout(views);preview.addWidget(self.viewer,1)
        preview.addWidget(label(tr('Erst berechnen und die Vorschau prüfen. Export speichert das berechnete Modell.'),'hint'))
        self.status=label(tr('Zuerst Polster auswählen.'),'hint');preview.addWidget(self.status)
        self.preset.currentIndexChanged.connect(self.changed);self.width.valueChanged.connect(self.changed);self.height.valueChanged.connect(self.changed);self.shape.currentIndexChanged.connect(self.choose_shape);self.radius_spin.valueChanged.connect(self.radius_changed)
        self.distance.valueChanged.connect(self.position_changed);self.tilt.valueChanged.connect(self.position_changed);self.height_offset.valueChanged.connect(self.position_changed)
        self.strap.toggled.connect(self.position_changed)
        self.fit_ok.toggled.connect(self.refresh);self.mount_ok.toggled.connect(self.refresh);self.refresh()
        self.tabs.currentChanged.connect(self.preview_arc)
        self.preview_arc()
        current().changed.connect(self.language_changed)

    def actions(self,layout,kind,caption,export):
        layout.addWidget(label(caption))
        row=W.QHBoxLayout();calc=button(tr('Berechnen'),lambda:self.calculate(kind),True)
        out=button(tr('Export …'),export);self.export_buttons[kind]=out
        row.addWidget(calc);row.addWidget(out);layout.addLayout(row);return calc
    def language_changed(self,*_):
        current().retranslate(self);self.setWindowTitle(tr('Offenes Gasket · Ohne Scan'));self.refresh()
    def spin(self,lo,hi,value,suffix):
        w=W.QDoubleSpinBox();w.setFixedWidth(160);w.setRange(lo,hi);w.setValue(value);w.setSuffix(suffix);return w
    def settings(self):
        return fit.validate(dict(preset=self.preset.currentData(),width=self.width.value(),height=self.height.value(),radius=self.radius,distance=self.distance.value(),tilt=self.tilt.value(),height_offset=self.height_offset.value(),strap=self.strap.isChecked()))
    def refresh(self,*_):
        self.final_btn.setEnabled(self.worker is None)
        for kind,b in self.export_buttons.items():b.setEnabled(self.worker is None and kind in self.calculated)
        missing=[]
        if not self.fit_ok.isChecked():missing.append(tr('Stirnform'))
        if not self.mount_ok.isChecked():missing.append(tr('Sitz am HMD'))
        self.review_info.setText(tr('Noch nicht praktisch bestätigt: {v0}. Berechnung und Export sind trotzdem möglich.',v0=', '.join(missing)) if missing else tr('Stirnform und Sitz am HMD als geprüft markiert.'))
    def changed(self,*_):
        self.custom.setVisible(self.preset.currentData()=='custom');self.fit_ok.setChecked(False);self.position_changed()
    def position_changed(self,*_):
        self.calculated.clear()
        self.mount_ok.setChecked(False);self.status.setText(tr('Einstellung geändert: passende Probe neu prüfen.'));self.preview_arc();self.refresh()
    def choose_shape(self,*_):
        if self.shape.currentData() is not None:self.radius_spin.setValue(self.shape.currentData())
    def radius_changed(self,value):
        self.radius=float(value)
        self.shape.blockSignals(True);self.shape.setCurrentIndex(self.shape.findData(self.radius) if self.shape.findData(self.radius)>=0 else 3);self.shape.blockSignals(False)
        self.shape_info.setText(tr('Aktueller Radius: {v0:g} mm',v0=self.radius))
        self.fit_ok.setChecked(False);self.position_changed()
    def preview_arc(self,*_):
        if self.worker:return
        if self.tabs.currentIndex()>=2:
            support=fit.support(self.settings());mesh=support.mesh
            base=fit.forehead.base_reference()
            self.viewer.base_vertices=base.vertices
            self.viewer._put('base',base.vertices,base.faces,color=(.25,.57,.9,1)).show()
            from .hmd_reference import hmd_reference
            if 'hmd' not in self.viewer.items_by_name:
                hmd=hmd_reference();self.viewer.set_hmd(hmd.vertices,hmd.faces,np.eye(4))
            self.viewer.set_hmd_visible(self.tabs.currentIndex()==2)
            self.viewer.hmd_vertices=self.viewer.hmd_preview[0] if self.tabs.currentIndex()==2 else None
            from .depth_measurement import UpperDepthGauge
            self.depth_measurement=UpperDepthGauge(support.surface_faces).measure_with_lower_edge_projection(support.contact,np.eye(4),support.mesh.vertices[len(support.contact):])
            self.viewer.set_depth_measurement(self.depth_measurement,self.tabs.currentIndex()==2)
            self.depth_info.setText(tr('Basis → Auflage: {v0:.2f} mm · ohne Polster',v0=self.depth_measurement.millimetres) if self.depth_measurement else tr('Basis → Auflage: keine mittige Messung möglich.'))
            if self.depth_measurement and self.depth_measurement.mode=='projected_lower_edge':
                self.depth_info.setText(self.depth_info.text()+'\n'+tr('Waagerecht bis zum Lot der äußeren Unterkante.'))
        else:
            mark=fit.RADII.index(self.radius)+1 if self.radius in fit.RADII else 4
            mesh=fit.support(self.settings(),aligned=False).mesh if self.tabs.currentIndex()==0 else fit.arc(self.settings(),mark)
            if 'base' in self.viewer.items_by_name:self.viewer.items_by_name['base'].hide()
            self.viewer.base_vertices=None
            self.viewer.hmd_vertices=None
            self.viewer.set_hmd_visible(False);self.viewer.set_depth_measurement(None,False)
        kind={1:'arc',2:'trial',3:'final'}.get(self.tabs.currentIndex())
        if kind in self.calculated:self.display_calculated(kind)
        else:self.viewer.set_pad(mesh.vertices,mesh.faces,result=False,smooth=False)
        # Geometry changes must move the grid even when the camera is preserved.
        self.viewer.update_grid()
        if getattr(self,'_preview_stage',None)!=self.tabs.currentIndex():
            self.viewer.fit_view()
            # The current page changes the viewport height after this signal.
            QtCore.QTimer.singleShot(0,self.viewer.fit_view)
        self._preview_stage=self.tabs.currentIndex()
    def adjust(self,answer):
        self.radius_spin.setValue(fit.feedback(self.radius,answer))
    def run(self,fn):
        if self.worker:return
        self.tabs.setEnabled(False);self.status.setText(tr('Modell wird berechnet …'));self.worker=Job(fn,self)
        self.worker.progress.connect(lambda n,t:self.status.setText(t));self.worker.succeeded.connect(self.show_result);self.worker.failed.connect(self.failed);self.worker.finished.connect(self.job_finished);self.worker.start();self.refresh()
    def display_calculated(self,kind):
        mesh=self.calculated[kind]['preview']
        if 'base' in self.viewer.items_by_name:self.viewer.items_by_name['base'].hide()
        self.viewer.base_vertices=None
        # Do not average normals across the thin carrier rim and Boolean joins.
        # Display the original surface with hard CAD edges, just like set_assembly.
        self.viewer.set_pad(mesh.vertices,mesh.faces,result=True,smooth=False)
    def show_result(self,result):
        if result['action']=='calculate':
            kind=result['kind'];self.calculated[kind]=result;self.display_calculated(kind)
            self.viewer.fit_view();self.status.setText(tr('Berechnet. Vorschau prüfen; anschließend bei Bedarf exportieren.'))
        else:self.status.setText(tr('Gespeichert: {v0}',v0=str(result['path'])))
    def calculate(self,kind):
        if self.worker:return
        s=self.settings();self.calculated.pop(kind,None)
        def work(progress):
            radii=fit.RADII if kind=='arcs' else [s['radius']]
            outputs=[];previews=[]
            for i,r in enumerate(radii,1):
                mesh=fit.arc(dict(s,radius=r),i if kind=='arcs' else 4) if kind in ('arc','arcs') else fit.build(s,kind=='trial',progress)
                printable,_=print_frame(mesh,[0]*6);printable,_=prepare_print_mesh(printable)
                outputs.append((fit.arc_filename(r,i if kind=='arcs' else 4),printable))
                previews.append(mesh)
            if kind=='arcs':
                vertices=[];faces=[];offset=0
                for i,m in enumerate(previews):
                    vertices.append(m.vertices+[(i-1)*220,0,0]);faces.append(m.faces+offset);offset+=len(m.vertices)
                preview=Mesh(np.vstack(vertices),np.vstack(faces),'Passbögen')
            else:preview=previews[0]
            return dict(action='calculate',kind=kind,preview=preview,outputs=outputs)
        self.run(work)
    def failed(self,message):self.status.setText(message);W.QMessageBox.warning(self,tr('Berechnung nicht möglich'),message)
    def job_finished(self):
        self.worker.deleteLater();self.worker=None;self.tabs.setEnabled(True);self.refresh()
    def export_arcs(self):
        if self.worker or 'arcs' not in self.calculated:return
        folder=W.QFileDialog.getExistingDirectory(self,tr('Ordner für die drei Passbögen'),self.last_directory)
        if not folder:return
        self.last_directory=folder
        self.export_arcs_to(folder)
    def export_arcs_to(self,folder):
        self.export_cached('arcs',folder)
    def export_one(self,kind):
        if self.worker or kind not in self.calculated:return
        name={'arc':fit.arc_filename(self.radius,4),'trial':'Montageprobe.3mf','final':tr('Offenes_Gasket_ohne_Scan.3mf')}[kind]
        path,_=W.QFileDialog.getSaveFileName(self,tr('Druckdatei speichern'),str(Path(self.last_directory)/name),'3MF (*.3mf)')
        if not path:return
        self.last_directory=str(Path(path).parent)
        self.export_one_to(kind,path)
    def export_one_to(self,kind,path):
        self.export_cached(kind,path)
    def export_cached(self,kind,path):
        if self.worker:return
        if kind not in self.calculated:
            self.status.setText(tr('Bitte zuerst berechnen und die Vorschau prüfen.'));return
        outputs=self.calculated[kind]['outputs']
        def work(progress):
            for name,mesh in outputs:export_mesh(Path(path)/name if kind=='arcs' else path,mesh)
            return dict(action='export',path=path)
        self.run(work)
    def save(self):
        if self.worker:return
        if hasattr(self.parent(), 'save_project'):
            self.parent().save_project();return
        path,_=W.QFileDialog.getSaveFileName(self,tr('Entwurf speichern'),tr('Offenes_Gasket.gasket-simple.json'),tr('Entwurf (*.gasket-simple.json)'))
        if path:fit.save(path,self.settings())
    def open(self):
        if self.worker:return
        path,_=W.QFileDialog.getOpenFileName(self,tr('Entwurf öffnen'),'',tr('GasketFit (*.padfit *.gasket-simple.json)'))
        if not path:return
        if Path(path).suffix.lower()=='.padfit' and hasattr(self.parent(), 'load_project_path'):
            self.parent().load_project_path(path);return
        try:s=fit.load(path)
        except Exception as e:self.failed(str(e));return
        self.apply_settings(s)
    def apply_settings(self, settings):
        s=fit.validate(settings)
        self.preset.setCurrentIndex(self.preset.findData(s['preset']));self.width.setValue(s['width']);self.height.setValue(s['height']);self.radius_spin.setValue(s['radius']);self.distance.setValue(s['distance']);self.tilt.setValue(s['tilt']);self.height_offset.setValue(s['height_offset']);self.strap.setChecked(s['strap']);self.shape_info.setText(tr('Gespeicherte Stirnform geladen.'));self.fit_ok.setChecked(False);self.position_changed();self.preview_arc()
    def reject(self):
        if self.worker:self.status.setText(tr('Bitte die laufende Berechnung abwarten.'));return
        super().reject()
    def closeEvent(self,event):
        if self.worker:event.ignore()
        else:super().closeEvent(event)
