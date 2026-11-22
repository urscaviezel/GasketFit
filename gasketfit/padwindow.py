"""Cushion-first local workflow; the HMD adapter is a separate future stage."""
from pathlib import Path
import json
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets as W
from . import __version__
from .window import STYLE, NumericInput, Job, label, button, preview
from .viewer import Viewer
from .meshio import Mesh, load_mesh, export_mesh
from .printmesh import export_print_mesh, print_frame
from .padtemplate import load_template
from .referencefit import initial_parameters, wrapped_preview, fit_pad, reference, reference_for_parameters
from .pad_alignment import pose_from_alignment, alignment_from_pose
from .assembly import base_reference, build_assembly
from .assembly_preview import AssemblyPreview
from .hmd_reference import hmd_reference
from .collision import FrontClearance
from .depth_measurement import UpperDepthGauge
from .section_view import section_plane
from .navigation import controls
from .padproject import save_pad_project, load_pad_project
from .profile import pose_matrix, transform
from .localization import tr, current
from .settings import SettingsDialog, OnlineController, build_info


class PadViewer(Viewer):
    def __init__(self):
        super().__init__()
        self.pad_vertices = None
        self.base_vertices = None
        self.hmd_vertices = None
        self._assembly_preview = None
        self._pad_colors = None

    def set_pad(self, vertices, faces, *, result=False, strain=None, gap=None, velcro=0, smooth=None):
        self.pad_vertices = vertices
        colors = None
        if strain is not None:
            t = np.clip(strain / 4, 0, 1)
            colors = np.c_[.25 + .7 * t, .80 - .5 * t, .65 - .4 * t, np.ones(len(t))]
        if gap is not None:
            colors = np.tile([.29, .82, .62, 1.], (len(gap), 1))
            colors[gap < 3.5+velcro] = [1., .3, .25, 1.]
            colors[gap > 10+velcro] = [.25, .55, 1., 1.]
        color = (.29, .82, .62, 1) if result else (.98, .64, .25, 1)
        self._pad_colors = colors
        item = self._put("pad", vertices, faces, colors=colors, color=color, smooth=smooth)
        item.setColor(color)
        item.setVisible(True)

    def set_assembly(self, assembly, support):
        cached = self._assembly_preview
        if (cached is None or cached.mesh is not assembly.mesh or
                cached.base is not assembly.base or cached.pad is not support.mesh):
            cached = self._assembly_preview = AssemblyPreview(assembly.mesh, assembly.base, support.mesh)
        # Draw the same single surface used by export. Separate solids overlap
        # at their joins and can z-fight; averaged normals also dent CAD edges.
        self._put('assembly', assembly.mesh.vertices, assembly.mesh.faces,
                  face_colors=cached.colors(self._pad_colors), smooth=False).setVisible(True)
        for name in ('pad', 'base', 'bridges'):
            if name in self.items_by_name:
                self.items_by_name[name].hide()

    def hide_assembly(self):
        if 'assembly' in self.items_by_name:
            self.items_by_name['assembly'].hide()

    def visible_bounds(self):
        chunks = []
        if self.preview_head is not None and self.head_visible:
            chunks.append(self.preview_head[0])
        if self.pad_vertices is not None and self.items_by_name['pad'].visible():
            chunks.append(self.pad_vertices)
        if self.base_vertices is not None:
            chunks.append(self.base_vertices)
        if self.hmd_vertices is not None:
            chunks.append(self.hmd_vertices)
        if not chunks:
            return
        lo = np.min([x.min(0) for x in chunks], axis=0)
        hi = np.max([x.max(0) for x in chunks], axis=0)
        return lo,hi

    def update_grid(self):
        bounds=self.visible_bounds()
        if bounds is None:return
        lo,hi=bounds
        self.grid.resetTransform()
        self.grid.translate(float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2), float(lo[2] - 2))
        self.update()

    def fit_view(self):
        bounds=self.visible_bounds()
        if bounds is None:return
        lo,hi=bounds
        self.opts["center"] = QtGui.QVector3D(*((lo + hi) / 2))
        half = np.deg2rad(self.opts["fov"] / 2)
        vertical = np.arctan(np.tan(half) * self.height() / max(1, self.width()))
        self.opts["distance"] = max(1., np.linalg.norm(hi - lo) / 2) / np.sin(min(half, vertical)) * 1.08
        self.update_grid()

    def set_depth_measurement(self, measurement, visible=True):
        import pyqtgraph.opengl as gl
        from OpenGL import GL
        if measurement is not None:
            for name, points, scatter in (
                    ('depth_line', measurement.line_segments, False),
                    ('depth_points', np.array([measurement.base_point, measurement.pad_point]), True)):
                item = self.items_by_name.get(name)
                if item is None:
                    item = (gl.GLScatterPlotItem(pos=points, color=(1., .76, .30, 1.), size=7, pxMode=True)
                            if scatter else gl.GLLinePlotItem(pos=points, color=(1., .76, .30, 1.),
                                                             width=2, mode='lines', antialias=True))
                    item.setGLOptions({GL.GL_DEPTH_TEST: False, GL.GL_BLEND: True,
                        'glBlendFunc': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)})
                    item.setDepthValue(30)
                    self.addItem(item)
                    self.items_by_name[name] = item
                else:
                    item.setData(pos=points)
        for name in ('depth_line', 'depth_points'):
            if name in self.items_by_name:
                self.items_by_name[name].setVisible(visible and measurement is not None)


class PadWindow(W.QMainWindow):
    ready = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.workflow = 'closed'
        self._workflow_states = {}
        self.project_path = None
        self._simple_settings = None
        self._simple_used = False
        self.setWindowTitle(f"GasketFit Beta {__version__}")
        self.resize(1420, 950)
        self.setMinimumSize(1050, 740)
        self.setStyleSheet(STYLE)
        self.outline, self.template = load_template(Path(__file__).with_name("vrcover_236x116.json"))
        self.reference = reference()['contact']
        self.reference_faces = reference()['faces']
        self._depth_gauge = UpperDepthGauge(self.reference_faces)
        self._depth_support = None
        self.depth_measurement = None
        self.head = self.result = None
        self.assembly = None
        self.base_positioned = False
        self._clearance_head = None
        self._clearance_query = None
        self._clearance_key = None
        self._clearance_result = None
        self._clearance_worker = None
        self._clearance_timer = QtCore.QTimer(self)
        self._clearance_timer.setSingleShot(True)
        self._clearance_timer.setInterval(180)
        self._clearance_timer.timeout.connect(self.update_clearance)
        self._worker = None
        self._closing = self._blocked = False
        self.last_directory = str(Path(__file__).resolve().parents[2])
        self.params = dict(pose=[0, -75, 50, 0, 0, 0], radius=90., padding=6.5, smoothing=1.5, thickness=1.5, solver='reference04', velcro=0., max_adjustment=12., refine_pose=False)
        self._legacy_windows = []
        root = W.QWidget()
        layout = W.QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(root)
        header = W.QFrame()
        header.setObjectName("header")
        hl = W.QHBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 15)
        text = W.QVBoxLayout()
        text.addWidget(label("GasketFit Beta", "title"))
        hl.addLayout(text)
        self.workflow_buttons = {}
        for mode, caption in (('closed', 'Geschlossenes Gasket'), ('open', 'Offenes Gasket')):
            btn = button(tr(caption), lambda checked=False, m=mode: self.switch_workflow(m))
            btn.setCheckable(True)
            btn.setChecked(mode == self.workflow)
            btn.setStyleSheet('QPushButton:checked { background: #26204b; border: 1px solid #22d3ff; }')
            hl.addWidget(btn)
            self.workflow_buttons[mode] = btn
        hl.addStretch()
        self.open_btn = button(tr("Projekt öffnen"), self.open_project)
        self.save_btn = button(tr("Projekt speichern"), self.save_project)
        hl.addWidget(self.open_btn)
        hl.addWidget(self.save_btn)
        layout.addWidget(header)
        self.tabs = W.QTabBar()
        self.tabs.setExpanding(True)
        for name in (tr("1  Kopfscan"), tr("2  HMD ausrichten"), tr("3  Auflage ausrichten"), tr("4  Auflage berechnen"), tr("5  Verbindung"), tr("6  Exportieren")):
            self.tabs.addTab(name)
        layout.addWidget(self.tabs)
        split = W.QSplitter()
        self.stack = W.QStackedWidget()
        self.stack.setMinimumWidth(350)
        self.stack.setMaximumWidth(470)
        self.pages = []
        for _ in range(6):
            page = W.QWidget()
            pl = W.QVBoxLayout(page)
            pl.setContentsMargins(22, 16, 18, 16)
            scroll = W.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
            self.pages.append(pl)
        self.tabs.currentChanged.connect(self.stack.setCurrentIndex)
        split.addWidget(self.stack)
        scene = W.QWidget()
        sl = W.QVBoxLayout(scene)
        tools = W.QHBoxLayout()
        for caption, name in (("3D", "3d"), (tr("Vorne"), "front"), (tr("Rechts"), "right"), (tr("Links"), "left"), (tr("Oben"), "top")):
            tools.addWidget(button(caption, lambda checked=False, n=name: self.viewer.view(n)))
        tools.addStretch()
        self.recenter_btn = button("Recenter", lambda: self.viewer.fit_view())
        tools.addWidget(self.recenter_btn)
        self.show_head = W.QCheckBox(tr("Kopf zeigen"))
        self.show_head.setChecked(True)
        sl.addLayout(tools)
        visibility=W.QHBoxLayout()
        visibility.addStretch()
        visibility.addWidget(self.show_head)
        self.show_base = W.QCheckBox(tr("Magnetbasis und Verbindungen anzeigen"))
        self.show_base.setChecked(True)
        self.show_base.toggled.connect(self.redraw)
        visibility.addWidget(self.show_base)
        self.show_hmd = W.QCheckBox(tr("HMD zeigen"))
        self.show_hmd.setChecked(True)
        self.show_hmd.toggled.connect(self.redraw)
        visibility.addWidget(self.show_hmd)
        sl.addLayout(visibility)
        section_tools = W.QHBoxLayout()
        section_tools.addWidget(label(tr('Schnittansicht:')))
        self.section_mode = W.QComboBox()
        for caption, mode in ((tr('Aus'), 'off'), (tr('Von rechts'), 'right'), (tr('Von links'), 'left')):
            self.section_mode.addItem(caption, mode)
        self.section_mode.setToolTip(tr('Blendet eine seitliche Hälfte bis zur Mitte aus (YZ-Schnitt). Nutze dazu die Seitenansicht Rechts oder Links. Nur Anzeige: Berechnung und Export bleiben vollständig.'))
        self.section_mode.currentIndexChanged.connect(self.update_section_view)
        section_tools.addWidget(self.section_mode)
        section_tools.addStretch()
        sl.addLayout(section_tools)
        self.depth_info = label('', 'hint')
        self.depth_info.setFixedHeight(28)
        self.depth_info.setWordWrap(False)
        self.depth_info.setStyleSheet('color: #ffcf70; font-size: 14px; font-weight: 600;')
        self.depth_info.setSizePolicy(W.QSizePolicy.Policy.Ignored, W.QSizePolicy.Policy.Fixed)
        self.depth_info.setToolTip(tr('Oben mittig: gerade nach hinten von der Magnetauflage bis zur Innenseite der Gesichtsauflage (Klebefläche zum Polster/Gesicht). Die Messlinie bleibt auf gleicher Höhe in Y-Richtung der Basis. Ohne Polster und Klett.'))
        sl.addWidget(self.depth_info)
        self.viewer = PadViewer()
        self.viewer.moved.connect(self.drag_pad)
        self.show_head.toggled.connect(self.redraw)
        sl.addWidget(self.viewer, 1)
        self.clearance_info = label(tr("Abstand vorne: Kopfscan laden."), "hint")
        self.clearance_info.setFixedHeight(112)
        self.clearance_info.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.clearance_info.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Fixed)
        sl.addWidget(self.clearance_info)
        self.strain_view = W.QCheckBox(tr("Längenänderung gegenüber Probe 04: Grün gering · Rot ab 4 %"))
        self.strain_view.toggled.connect(self.redraw)
        sl.addWidget(self.strain_view)
        self.gap_view = W.QCheckBox(tr("Polsterabstand: Rot unter 3,5 · Grün 3,5–10 · Blau über 10 mm (plus Klett)"))
        self.gap_view.setChecked(True)
        self.gap_view.toggled.connect(self.redraw)
        self.strain_view.toggled.connect(lambda checked: self.gap_view.setChecked(False) if checked else None)
        self.gap_view.toggled.connect(lambda checked: self.strain_view.setChecked(False) if checked else None)
        sl.addWidget(self.gap_view)
        self.navigation_hint = label("", "hint")
        sl.addWidget(self.navigation_hint)
        split.addWidget(scene)
        split.setSizes([390, 1030])
        layout.addWidget(split, 1)
        bottom = W.QHBoxLayout()
        bottom.setContentsMargins(22, 8, 22, 8)
        self.activity = label(tr("Kopfscan laden. Die freigegebene Polsterkontur ist bereits enthalten."), "hint")
        self.progress = W.QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        self.cancel = button(tr("Abbrechen"), self.cancel_job)
        self.cancel.hide()
        bottom.addWidget(self.activity, 1)
        bottom.addWidget(self.progress)
        bottom.addWidget(self.cancel)
        layout.addLayout(bottom)
        self.create_pages()
        self.forehead_controls = W.QWidget()
        forehead_form = W.QFormLayout(self.forehead_controls)
        from .cushion_presets import PRESETS
        self.cushion_preset = W.QComboBox()
        for key, entry in PRESETS.items(): self.cushion_preset.addItem(tr(entry['name']), key)
        forehead_form.addRow(tr('Polstervorlage'), self.cushion_preset)
        self.forehead_form = forehead_form
        self.forehead_spins = {}
        for key, caption, low, high, value in (
                ('forehead_width', 'Polsterlänge flach', 140, 240, 200),
                ('forehead_height', 'Polsterhöhe', 30, 65, 48),
                ('forehead_radius', 'Stirnkrümmung / Radius', 80, 180, 105)):
            spin = self.spin(low, high, value, ' mm')
            self.forehead_spins[key] = spin
            forehead_form.addRow(tr(caption), spin)
        self.cushion_preset.currentIndexChanged.connect(self.preset_changed)
        self.pages[2].insertWidget(2, self.forehead_controls)
        self.forehead_controls.hide()
        self._closed_texts = [(w, current().source_text(w.text())) for w in root.findChildren(W.QLabel)]
        self.tabs.currentChanged.connect(self.redraw)
        self.tabs.currentChanged.connect(self.update_navigation_hint)
        current().navigation_changed.connect(self.update_navigation_hint)
        self.online = OnlineController(self)
        self.settings_menu = self.menuBar().addMenu(tr("Einstellungen"))
        self.settings_action = self.settings_menu.menuAction()
        self.language_action = self.settings_menu.addAction(tr("Sprache"), lambda: self.show_settings("language"))
        self.settings_menu.addAction(tr("Aktualisierungen"), lambda: self.show_settings("updates"))
        self.controls_action = self.settings_menu.addAction(tr("Tastenbelegung"), lambda: self.show_settings("controls"))
        self.menuBar().addAction(tr("Build-Informationen"), lambda: build_info(self))
        self._settings_dialog = None
        current().changed.connect(self.language_changed)
        self.online.update_changed.connect(self.update_notice)
        self.redraw()
        self.update_navigation_hint()
        self.refresh()
        # The viewport size is known only after the window has been laid out.
        QtCore.QTimer.singleShot(100, self.viewer.fit_view)

    def workflow_base(self):
        if self.workflow == 'open':
            from .forehead import base_reference as open_base
            return open_base()
        return base_reference()

    def workflow_initial(self, head):
        if self.workflow == 'open':
            from .forehead import initial_parameters as initial
            return initial(head)
        return initial_parameters(head)

    def update_reference(self):
        if self.workflow == 'open':
            from .forehead import reference as forehead_reference
            data = forehead_reference(self.params)
        else:
            data = reference_for_parameters(self.params)
        self.reference, self.reference_faces = data['contact'], data['faces']
        self._depth_gauge = UpperDepthGauge(self.reference_faces)
        self._depth_support = None

    def switch_workflow(self, mode):
        if mode == self.workflow or self._worker:
            for key, btn in self.workflow_buttons.items(): btn.setChecked(key == self.workflow)
            return
        self._workflow_states[self.workflow] = dict(head=self.head, params=self.parameter_values(),
            result=self.result, assembly=self.assembly, step=self.tabs.currentIndex(), positioned=self.base_positioned)
        previous = self.parameter_values()
        self.workflow = mode
        saved = self._workflow_states.get(mode)
        restore_result = False
        if saved and saved['head'] is self.head:
            params = dict(saved['params'])
            restore_result = params.get('base_pose') == previous.get('base_pose')
            params['base_pose'] = list(previous.get('base_pose', previous['pose']))
            params['pose'] = pose_from_alignment(params['base_pose'], params['pad_alignment'], mode)
        else:
            saved = None
        if saved is None and mode == 'open':
            from .forehead import initial_parameters as initial
            params = initial(self.head, previous)
        elif saved is None:
            params = initial_parameters(self.head) if self.head is not None else {**previous, 'solver':'reference04'}
            params['base_pose'] = list(previous.get('base_pose', previous['pose']))
            params['pad_alignment'] = alignment_from_pose(params['base_pose'], params['pose'], mode)
        # Both variants share the scan and current HMD pose. Only support
        # settings and still-valid calculated geometry belong to each variant.

        self.update_workflow_ui()
        if self.head is not None:
            self.viewer.set_head(*preview(self.head))
            self.head_info.setText(self.head.name)
        else:
            if 'head' in self.viewer.items_by_name:self.viewer.items_by_name['head'].hide()
            self.viewer.preview_head = None
            self.head_info.setText(tr('Noch kein Kopfscan geladen.'))
        self.set_parameters(params)
        if saved and restore_result:
            self.result, self.assembly = saved['result'], saved['assembly']
            self.base_positioned = saved['positioned']
            self.update_result_text()
        self.tabs.setCurrentIndex(saved['step'] if saved else (1 if self.head is not None else 0))
        self.redraw(); self.refresh(); self.viewer.fit_view()
        self.activity.setText(tr('Offener Workflow: Stirnauflage ausrichten. Die aktuelle Headset-Position wurde übernommen.') if mode == 'open' else tr('Geschlossener Workflow wiederhergestellt.'))

    def update_workflow_ui(self):
        opened = self.workflow == 'open'
        self.simple_fit_btn.setVisible(opened)
        for key, btn in self.workflow_buttons.items(): btn.setChecked(key == self.workflow)
        self.forehead_controls.setVisible(opened)
        self.closed_radius_row.setVisible(not opened)
        self.strain_view.setText(tr('Längenänderung gegenüber Stirnvorlage: Grün gering · Rot ab 4 %') if opened else tr('Längenänderung gegenüber Probe 04: Grün gering · Rot ab 4 %'))
        for widget in (self.nose_enabled, self.nose_pockets):
            widget.setVisible(not opened)
        self.top_strap.setVisible(True)
        self.top_strap.setToolTip(tr('37 mm freie Breite, 4 mm Durchlass, runder 4-mm-Quersteg. Vorne an der oberen Stirnauflage abgestützt.') if opened else tr('37 mm freie Breite, 4 mm Durchlass, runder 4-mm-Quersteg. Beide Halter sind nach hinten an der Auflage abgestützt.'))
        captions = ('1  Kopfscan', '2  HMD ausrichten', '3  Stirnauflage ausrichten', '4  Stirnauflage berechnen', '5  Verbindung', '6  Exportieren') if opened else ('1  Kopfscan', '2  HMD ausrichten', '3  Auflage ausrichten', '4  Auflage berechnen', '5  Verbindung', '6  Exportieren')
        for i, caption in enumerate(captions): self.tabs.setTabText(i, tr(caption))
        for widget, text in self._closed_texts:
            if not opened:
                widget.setText(tr(text))
                continue
            replacement=text.replace('Probe 04', 'Stirnvorlage').replace('1.5 mm','2.5 mm').replace('1,5 mm','2,5 mm')
            if 'Stirn, Schläfen und Wangen' in text:
                replacement='Orange zeigt die Stirnauflage. Höhe, Abstand und Neigung am Kopfscan ausrichten; Polstermaße und Krümmung sind einstellbar.'
            elif 'mit Klett bestätigte Auflage' in text:
                replacement='Kopfscan laden oder ein bestehendes Projekt öffnen. Beim Import eines geschlossenen Projekts wird die Headset-Position übernommen.'
            elif 'Polsterenden' in text:
                replacement='Die Stirnauflage wird weich an den Kopfscan angepasst.'
            elif 'Magnetadapter, Nasenteil' in text:
                replacement='Dieser Schritt berechnet den Stirnträger. Anschließend die durchgehende Oberschale berechnen.'
            elif 'Blau ist die unveränderte Magnetbasis' in text:
                replacement='Blau ist die eigene Basiskopie mit vorläufigen Kippanschlägen. Die Headset-Position gilt für beide Workflows; die Stirnauflage folgt dem Headset.'
            elif text == 'Polster positionieren': replacement='Stirnauflage ausrichten'
            elif text == 'Glatte Polsterauflage': replacement='Stirnauflage an Kopfscan anpassen'
            elif text == 'Magnetische Basis positionieren': replacement='HMD ausrichten'
            elif 'Nasenbogen 06' in text: replacement='PFDMR · Offene Stirnauflage · Test'
            elif 'Geschlossene 1,5-mm-Hülle' in text:
                replacement='Durchgehende Oberschale mit fließendem Übergang zur Stirnauflage. Die Verbindung greift breit in Basis und Stirnträger ein; Magnetanschluss und Klebefläche bleiben frei.'
            widget.setText(tr(replacement))

    def create_pages(self):
        p = self.pages[0]
        p.addWidget(label(tr("Kopfscan laden"), "section"))
        p.addWidget(label(tr("Die mit Klett bestätigte Auflage von Probe 04 ist enthalten. Ihre Biegung wird begrenzt angepasst; die Polsterenden werden nicht erneut nach unten gezogen.")))
        self.load_btn = button(tr("Kopfscan wählen …"), self.open_head, True)
        p.addWidget(self.load_btn)
        self.simple_fit_btn=button(tr('Offenes Gasket ohne Scan …'),self.open_simple_fit)
        self.simple_fit_btn.setVisible(self.workflow=='open')
        p.addWidget(self.simple_fit_btn)
        self.head_info = label(tr("Noch kein Kopfscan geladen."), "hint")
        p.addWidget(self.head_info)
        p.addWidget(label(tr("Falls der Scan liegt oder falsch herum schaut:")))
        row = W.QHBoxLayout()
        for caption, axis in (("X +90°", 0), ("Y +90°", 1), ("Z +90°", 2)):
            row.addWidget(button(caption, lambda checked=False, a=axis: self.rotate_head(a)))
        p.addLayout(row)
        p.addWidget(label(tr("Vorne zeigt in Richtung Gesicht. Einheit: Millimeter. Bitte Orientierung und Lebensgröße prüfen."), "hint"))
        p.addWidget(button(tr("Weiter zur Positionierung"), lambda: self.tabs.setCurrentIndex(1)))
        p.addStretch()
        p = self.pages[2]
        p.addWidget(label(tr("Polster positionieren"), "section"))
        p.addWidget(label(tr('Mittig zum HMD · Y-Drehung vom HMD. Abstand, Höhe, X-Neigung und Z-Drehung sind relativ zum Headset.'), 'hint'))
        p.addWidget(label(tr("Orange zeigt Probe 04. Richte Stirn, Schläfen und Wangen am Scan aus. Die Berechnung passt diese Form weich und begrenzt an.")))
        self.pose_spins = []
        form = W.QFormLayout()
        for i, name in enumerate((tr("Seitlich X"), tr("Vor / zurück Y"), tr("Höhe Z"), tr("Neigen X"), tr("Drehen Y"), tr("Drehen Z"))):
            spin = NumericInput()
            spin.setRange(-1000 if i < 3 else -180, 1000 if i < 3 else 180)
            spin.setDecimals(2)
            spin.setSuffix(" mm" if i < 3 else "°")
            spin.setValue(0.)
            spin.valueChanged.connect(self.parameters_changed)
            self.pose_spins.append(spin)
            if i in (0,4): spin.hide()
            else: form.addRow(name, spin)
        self.radius = self.spin(55, 180, 90, " mm")
        self.closed_radius_row = W.QWidget()
        radius_form = W.QFormLayout(self.closed_radius_row)
        radius_form.addRow(tr("Radius"), self.radius)
        p.addWidget(self.closed_radius_row)
        p.addLayout(form)
        p.addWidget(label(tr("Die Startposition ist nur eine Hilfe. Augenhöhe und Linsenabstand sind noch nicht kalibriert. Bei einem falsch orientierten Scan zuerst dessen Ausrichtung korrigieren."), "hint"))
        p.addWidget(button(tr("Startposition wiederherstellen"), self.reset_position))
        p.addWidget(button(tr("Weiter zur Auflage"), lambda: self.tabs.setCurrentIndex(3)))
        p.addStretch()
        p = self.pages[3]
        p.addWidget(label(tr("Glatte Polsterauflage"), "section"))
        form = W.QFormLayout()
        self.padding = self.spin(3.5, 10, 6.5, " mm")
        self.smoothing = self.spin(.2, 3, 1.5, " mm")
        form.addRow(tr("Wirksame Polsterdicke"), self.padding)
        self.smoothing.hide()
        self.velcro = self.spin(0, 3, 0, " mm")
        self.max_adjustment = self.spin(0, 20, 12, " mm")
        form.addRow(tr("Zusätzliche Klettdicke"), self.velcro)
        form.addRow(tr("Maximale Formanpassung"), self.max_adjustment)
        self.refine_pose = W.QCheckBox(tr("Nur Abstand vor/zurück feinabgleichen (Y)"))
        self.refine_pose.setChecked(False)
        self.refine_pose.toggled.connect(self.parameters_changed)
        self.refine_pose.hide()
        form.addRow(tr("Materialstärke"), label("1.5 mm"))
        p.addLayout(form)
        p.addWidget(label(tr("Die Auflage bleibt mittig zum HMD. Abstand, Höhe, X-Neigung und Z-Drehung werden relativ zum Headset eingestellt. Polsterdicke meint den Abstand beim Tragen; Klett separat eintragen."), "hint"))
        self.calculate_btn = button(tr("Auflage berechnen"), self.calculate, True)
        p.addWidget(self.calculate_btn)
        p.addWidget(label(tr("Längenänderungen sind auf 4 % gegenüber Probe 04 begrenzt: eine Versuchsgrenze, keine Materialgarantie. Verbleibende Abstände werden angezeigt. Gleichmäßiger Druck wird nicht berechnet."), "hint"))
        p.addWidget(label(tr("Dieser Schritt erzeugt nur die Polsterauflage. Magnetadapter, Nasenteil und Verbindungshülle sind noch nicht enthalten."), "hint"))
        p.addStretch()
        p = self.pages[1]
        p.addWidget(label(tr("HMD ausrichten"), "section"))
        self.include_base = W.QCheckBox(tr("Magnetbasis hinzufügen"))
        self.include_base.setChecked(True)
        self.include_base.toggled.connect(self.base_changed)
        self.include_base.hide()
        self.closed_shell = W.QCheckBox(tr("Geschlossene Hülle · Probe 07 · 1,5 mm"))
        self.closed_shell.setChecked(True)
        self.closed_shell.toggled.connect(self.base_changed)
        self.closed_shell.hide()
        opacity_row = W.QHBoxLayout()
        opacity_row.addWidget(label(tr("HMD-Deckkraft")))
        self.hmd_alpha = W.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.hmd_alpha.setRange(5, 100)
        self.hmd_alpha.setValue(40)
        self.hmd_alpha.valueChanged.connect(self.redraw)
        opacity_row.addWidget(self.hmd_alpha)
        p.addLayout(opacity_row)
        warning_row = W.QHBoxLayout()
        warning_row.addWidget(label(tr("Warnabstand vorne")))
        self.clearance_margin = NumericInput()
        self.clearance_margin.setRange(0, 10)
        self.clearance_margin.setDecimals(1)
        self.clearance_margin.setSingleStep(.5)
        self.clearance_margin.setSuffix(" mm")
        self.clearance_margin.setValue(2)
        self.clearance_margin.valueChanged.connect(self.update_clearance_text)
        warning_row.addWidget(self.clearance_margin)
        p.addLayout(warning_row)
        p.addWidget(label(tr("Kollisionen: Rot im Linsen-/Randbereich, Orange in der Mitte. Die Mittelzone ist nur geometrisch geschätzt: Stoff und harte Teile am Scan prüfen. Bügel und Backplate bleiben ungeprüft."), "hint"))
        p.addWidget(label(tr("HMD und Magnetbasis zuerst ausrichten. Die Auflage folgt dem Headset und bleibt seitlich zentriert. Eine Änderung verwirft bereits berechnete Geometrie.")))
        form = W.QFormLayout()
        self.base_spins = []
        for i, name in enumerate((tr("Seitlich X"), tr("Vor / zurück Y"), tr("Höhe Z"), tr("Neigen X"), tr("Drehen Y"), tr("Drehen Z"))):
            spin = NumericInput()
            spin.setRange(-1000 if i < 3 else -180, 1000 if i < 3 else 180)
            spin.setDecimals(2)
            spin.setSuffix(" mm" if i < 3 else "°")
            spin.setValue(self.params['pose'][i])
            spin.valueChanged.connect(self.base_changed)
            self.base_spins.append(spin)
            form.addRow(name, spin)
        p.addLayout(form)
        p.addWidget(button(tr("Weiter zur Auflage"), lambda: self.tabs.setCurrentIndex(2)))
        p.addStretch()
        p = self.pages[4]
        p.addWidget(label(tr("Verbindung berechnen"), "section"))
        nose_title=label(tr("Nasenöffnung"),"section");nose_title.hide();p.addWidget(nose_title)
        self.nose_enabled=W.QCheckBox(tr('Nasenbogen'));self.nose_enabled.setChecked(True);self.nose_enabled.toggled.connect(self.nose_changed);p.addWidget(self.nose_enabled)
        self.nose_pockets=W.QCheckBox(tr("Seitliche Nasentaschen füllen"));self.nose_pockets.setChecked(True);self.nose_pockets.toggled.connect(self.nose_changed);p.addWidget(self.nose_pockets)
        self.top_strap = W.QCheckBox(tr('Kopfbandhalterung · 37 × 4 mm'))
        self.top_strap.setChecked(True)
        self.top_strap.toggled.connect(self.nose_changed)
        self.top_strap.setToolTip(tr('37 mm freie Breite, 4 mm Durchlass, runder 4-mm-Quersteg. Beide Halter sind nach hinten an der Auflage abgestützt.'))
        p.addWidget(self.top_strap)
        self.nose_spins={};self._nose_pending=False
        nose_form=W.QFormLayout()
        for key,title,low,high,default in [('width','Breite',16,65,36),('height','Höhe',8,45,24),('clearance','Abstand zur Nase',1,8,3)]:
            spin=NumericInput();spin.setRange(low,high);spin.setDecimals(1);spin.setSingleStep(.5);spin.setSuffix(' mm');spin.setValue(default)
            spin.valueChanged.connect(self.nose_changed);self.nose_spins[key]=spin;nose_form.addRow(tr(title),spin)
        nose_controls=W.QWidget();nose_controls.setLayout(nose_form);nose_controls.hide();p.addWidget(nose_controls)
        self.nose_scan_btn=button(tr("Nase aus Kopfscan übernehmen"),lambda:self.nose_from_head());p.addWidget(self.nose_scan_btn)
        self.nose_scan_btn.hide()
        p.addWidget(label(tr("HMD und Basis bewegen sich gemeinsam. Die Zuordnung stammt aus deiner manuellen Ausrichtung am physischen Headset. Die Linsenposition ist eine visuelle Referenz und nicht exakt vermessen. Das HMD wird nicht mit exportiert."), "hint"))
        self.build_btn = button(tr("Probe 06 verbinden"), self.calculate_assembly, True)
        p.addWidget(self.build_btn)
        self.assembly_info = label(tr("Noch kein Stabilitätsrahmen berechnet."), "hint")
        p.addWidget(self.assembly_info)
        p.addWidget(label(tr("Geschlossene 1,5-mm-Hülle mit drei oberen Innenstegen. Der Nasenbogen verbindet die rechteckigen Auflagenenden. Die Füllung folgt den seitlichen Taschen; Nasenöffnung, Polsterfläche und Magnetaufnahme bleiben erhalten."), "hint"))
        p.addWidget(button(tr("Weiter zum Export"), lambda: self.tabs.setCurrentIndex(5)))
        p.addStretch()
        p = self.pages[5]
        p.addWidget(label(tr("Auflage prüfen und exportieren"), "section"))
        self.frame_export_info = label("")
        p.addWidget(self.frame_export_info)
        self.result_info = label(tr("Noch keine Auflage berechnet."))
        p.addWidget(self.result_info)
        self.warning_info = label("")
        p.addWidget(self.warning_info)
        self.accept_warnings = W.QCheckBox(tr("Abweichungen geprüft – als Probestück exportieren"))
        self.accept_warnings.toggled.connect(self.refresh)
        p.addWidget(self.accept_warnings)
        self.export_btn = button(tr("Polsterauflage exportieren …"), self.export, True)
        p.addWidget(self.export_btn)
        p.addWidget(label(tr("STL oder 3MF · Millimeter. Der Export wird an der Magnetbasis ausgerichtet, in X/Y zentriert und auf Z = 0 gesetzt. Ohne Basis gilt die Referenzausrichtung der Auflage. Deine Positionierung im Projekt bleibt erhalten."), "hint"))
        p.addWidget(button(tr("Position oder Anpassung ändern"), lambda: self.tabs.setCurrentIndex(2)))
        p.addStretch()

    def spin(self, lo, hi, value, suffix):
        spin = NumericInput()
        spin.setRange(lo, hi)
        spin.setDecimals(2)
        spin.setSingleStep(.5)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.valueChanged.connect(self.parameters_changed)
        return spin

    def update_navigation_hint(self, *_):
        p = controls()
        names = {'left':tr('Linke Maustaste'),'middle':tr('Mittlere Maustaste'),'right':tr('Rechte Maustaste')}
        target = tr('Basis') if self.tabs.currentIndex() == 1 else tr('Auflage')
        self.navigation_hint.setText(tr('Drehen: {v0} · Verschieben: {v1} · Mausrad: Zoom · Alt + Links: {v2} positionieren',
                                        v0=names[p['rotate_button']],v1=names[p['pan_button']],v2=target))

    def preset_changed(self, *_):
        custom = self.cushion_preset.currentData() == 'custom'
        for key in ('forehead_width', 'forehead_height'):
            spin = self.forehead_spins[key]
            spin.setVisible(custom)
            self.forehead_form.labelForField(spin).setVisible(custom)
        if not self._blocked: self.parameters_changed()

    def parameter_values(self):
        base_pose=[s.value() for s in self.base_spins]
        relative=[self.pose_spins[i].value() for i in (1,2,3,5)]
        p = dict(pose=pose_from_alignment(base_pose, relative, self.workflow), radius=self.radius.value(),
                    pad_alignment=relative,
                    padding=self.padding.value(), smoothing=self.smoothing.value(), thickness=1.5,
                    solver='reference04', velcro=self.velcro.value(), max_adjustment=self.max_adjustment.value(),
                    refine_pose=False, include_base=self.include_base.isChecked(),
                    closed_shell=self.closed_shell.isChecked(),base_pose=[s.value() for s in self.base_spins],
                    nose_enabled=False, nose_bridge=self.nose_enabled.isChecked(), nose_pockets=self.nose_pockets.isChecked(),
                    top_strap=self.top_strap.isChecked(),
                    **{'nose_'+key:spin.value() for key,spin in self.nose_spins.items()})
        if self.workflow == 'open':
            from .forehead import validate
            p.update({key: spin.value() for key, spin in self.forehead_spins.items()})
            p['cushion_preset'] = self.cushion_preset.currentData()
            p = validate(p)
        return p

    def set_parameters(self, values):
        self._blocked = True
        try:
            for key, spin in self.forehead_spins.items():
                spin.setValue(values.get(key, {'forehead_width':200, 'forehead_height':48, 'forehead_radius':105}[key]))
            relative=values.get('pad_alignment')
            if relative is None:
                relative=alignment_from_pose(values.get('base_pose',values['pose']),values['pose'],self.workflow)
            for i,value in zip((1,2,3,5),relative):self.pose_spins[i].setValue(value)
            self.pose_spins[0].setValue(0.); self.pose_spins[4].setValue(0.)
            self.cushion_preset.setCurrentIndex(max(0,self.cushion_preset.findData(values.get('cushion_preset','custom'))))
            self.preset_changed()
            for key in ("radius", "padding", "smoothing"):
                getattr(self, key).setValue(values[key])
            self.velcro.setValue(values.get('velcro', 0.))
            self.max_adjustment.setValue(values.get('max_adjustment', 12.))
            self.refine_pose.setChecked(False)
            self.include_base.setChecked(True)
            self.closed_shell.setChecked(True)
            for spin, value in zip(self.base_spins, values.get('base_pose', values['pose'])):
                spin.setValue(value)
            self.base_positioned = 'base_pose' in values
            for key,spin in self.nose_spins.items():spin.setValue(values.get('nose_'+key,{'width':36.,'height':24.,'clearance':3.}[key]))
            self._nose_pending=False
            self.nose_enabled.setChecked(values.get('nose_bridge', True))
            self.nose_pockets.setChecked(values.get('nose_pockets', True))
            self.top_strap.setChecked(values.get('top_strap', self.workflow != 'open'))
        finally:
            self._blocked = False
        self.parameters_changed()

    def parameters_changed(self, *_):
        if self._blocked:
            return
        self.params = self.parameter_values()
        self.update_reference()
        self.result = None
        self.assembly = None
        self.assembly_info.setText(tr("Noch kein Stabilitätsrahmen berechnet."))
        self.accept_warnings.setChecked(False)
        self.result_info.setText(tr("Noch keine Auflage berechnet."))
        self.warning_info.clear()
        self.redraw()
        self.refresh()

    def hmd_is_visible(self):
        step = self.tabs.currentIndex()
        return step == 1 or (step >= 4 and self.include_base.isChecked() and self.show_hmd.isChecked())

    def redraw(self, *_):
        step = self.tabs.currentIndex()
        # Early steps have a fixed scene, independent of review toggles.
        for control in (self.show_head, self.show_base, self.show_hmd):
            control.setVisible(step >= 4)
        self.viewer.set_head_visible(step < 4 or self.show_head.isChecked())
        self.strain_view.setVisible(step >= 3)
        self.gap_view.setVisible(step >= 3)
        if self.result is None:
            vertices = (transform(self.reference, pose_matrix(self.params['pose'])) if self.workflow == 'open'
                        else wrapped_preview(self.reference, self.params))
            self.viewer.set_pad(vertices, self.reference_faces)
        else:
            strain = None
            if self.strain_view.isChecked():
                strain = np.tile(self.result.vertex_strain, 2)
            self.viewer.set_pad(self.result.mesh.vertices, self.result.mesh.faces, result=True, strain=strain,
                                gap=np.tile(self.result.vertex_gap, 2) if self.gap_view.isChecked() else None,
                                velcro=self.params.get('velcro', 0))
        self.viewer.items_by_name["pad"].setVisible(step >= 2)
        reference_visible = step >= 4
        visible = reference_visible and self.include_base.isChecked() and self.show_base.isChecked()
        self.show_base.setEnabled(reference_visible)
        self.show_hmd.setEnabled(reference_visible)
        self.clearance_info.setVisible(self.hmd_is_visible())
        self.viewer.base_vertices = None
        if visible:
            mesh = self.workflow_base()
            vertices = mesh.vertices @ pose_matrix([s.value() for s in self.base_spins])[:3, :3].T + np.array([s.value() for s in self.base_spins])[:3]
            self.viewer._put('base', vertices, mesh.faces, color=(.25, .57, .90, 1)).setVisible(True)
            self.viewer.base_vertices = vertices
        elif 'base' in self.viewer.items_by_name:
            self.viewer.items_by_name['base'].setVisible(False)
        hmd_visible = self.hmd_is_visible()
        self.viewer.hmd_vertices = None
        if hmd_visible:
            mesh = hmd_reference()
            matrix = pose_matrix([s.value() for s in self.base_spins])
            self.viewer.pose = matrix
            self.viewer.hmd_visible = True
            self.viewer.hmd_opacity = self.hmd_alpha.value() / 100
            self.viewer.set_hmd(mesh.vertices, mesh.faces, np.eye(4))
            self.viewer.hmd_vertices = mesh.vertices @ matrix[:3,:3].T + matrix[:3,3]
        else:
            self.viewer.set_hmd_visible(False)
        if self.assembly is not None and visible:
            self.viewer.set_assembly(self.assembly, self.result)
        else:
            self.viewer.hide_assembly()
            if 'bridges' in self.viewer.items_by_name:
                self.viewer.items_by_name['bridges'].hide()
        self.update_depth_measurement(visible)
        self.update_section_view()
        if hmd_visible and self.head is not None:
            key=(id(self.head),tuple(s.value() for s in self.base_spins))
            if key != self._clearance_key:
                self.clearance_info.setText(tr("Abstand vorne wird geprüft …"))
                if 'collision' in self.viewer.items_by_name:
                    self.viewer.items_by_name['collision'].setVisible(False)
                if 'collision_patch' in self.viewer.items_by_name:
                    self.viewer.items_by_name['collision_patch'].setVisible(False)
                self._clearance_timer.start()
            elif 'collision' in self.viewer.items_by_name:
                self.viewer.items_by_name['collision'].setVisible(hmd_visible and self._clearance_result is not None)
                if 'collision_patch' in self.viewer.items_by_name:
                    self.viewer.items_by_name['collision_patch'].setVisible(hmd_visible and self._clearance_result is not None and bool(len(self._clearance_result['patch_faces'])))
        elif 'collision' in self.viewer.items_by_name:
            self.viewer.items_by_name['collision'].setVisible(False)
            if 'collision_patch' in self.viewer.items_by_name:
                self.viewer.items_by_name['collision_patch'].setVisible(False)

    def update_section_view(self, *_):
        # During support placement follow its middle; in the base/export steps
        # follow the base so its central measurement remains in the cut plane.
        pose = ([s.value() for s in self.base_spins]
                if self.tabs.currentIndex() in (1, 4, 5)
                else self.params['pose'])
        self.viewer.set_section_plane(section_plane(pose_matrix(pose), self.section_mode.currentData()))

    def update_depth_measurement(self, line_visible):
        show = self.tabs.currentIndex() >= 4 and self.include_base.isChecked()
        self.depth_info.setVisible(show)
        if show:
            if self._depth_support is not self.result:
                if self.result is None:
                    self._depth_gauge = UpperDepthGauge(self.reference_faces)
                else:
                    self._depth_gauge = UpperDepthGauge(self.result.surface_faces)
                self._depth_support = self.result
            vertices = (transform(self.reference, pose_matrix(self.params['pose']))
                        if self.result is None else self.result.contact)
            self.depth_measurement = self._depth_gauge.measure(
                vertices, pose_matrix([s.value() for s in self.base_spins]))
            if self.depth_measurement is None:
                self.depth_info.setText(tr('Tiefe oben: nicht messbar – Messlinie trifft die Auflage nicht.'))
            else:
                source = tr('berechnete Auflage') if self.result is not None else tr('Vorschau')
                self.depth_info.setText(tr('Tiefe oben (Innenseite): {v0} mm · ohne Polster · {v1}',
                    v0=f'{self.depth_measurement.millimetres:.2f}', v1=source))
        self.viewer.set_depth_measurement(self.depth_measurement, visible=show and line_visible)

    def update_clearance(self):
        if self.head is None or not self.hmd_is_visible() or self._closing:
            return
        if self._clearance_worker is not None:
            return
        key=(id(self.head),tuple(s.value() for s in self.base_spins))
        head=self.head
        vertices,faces=self.viewer.preview_head
        cached=self._clearance_query if self._clearance_head is head else None
        def check(progress):
            query=cached if cached is not None else FrontClearance(Mesh(vertices,faces,'Head preview'))
            return query,query.check(pose_matrix(key[1]))
        worker=Job(check,self)
        self._clearance_worker=worker
        def succeeded(value):
            if self._closing or self.head is not head:
                return
            self._clearance_query,self._clearance_head=value[0],head
            if key != (id(self.head),tuple(s.value() for s in self.base_spins)):
                return
            self._clearance_result=value[1]
            self._clearance_key=key
            self.update_clearance_text()
            from OpenGL import GL
            overlay_options={GL.GL_DEPTH_TEST:False,GL.GL_BLEND:True,
                             'glBlendFunc':(GL.GL_SRC_ALPHA,GL.GL_ONE_MINUS_SRC_ALPHA),
                             GL.GL_CULL_FACE:False}
            marks=self._clearance_result['marks']
            item=self.viewer.set_section_points('collision',marks,self._clearance_result['mark_colors'])
            item.setGLOptions(overlay_options)
            item.setDepthValue(20)
            visible=self.hmd_is_visible()
            self.viewer.items_by_name['collision'].setVisible(visible)
            result=self._clearance_result
            if len(result['patch_faces']):
                patch=self.viewer._put('collision_patch',result['patch_vertices'],result['patch_faces'],colors=result['patch_colors'])
                patch.setGLOptions(overlay_options)
                patch.setDepthValue(19)
                patch.setVisible(visible)
            elif 'collision_patch' in self.viewer.items_by_name:
                self.viewer.items_by_name['collision_patch'].setVisible(False)
        def failed(message):
            if not self._closing and self.head is head and key==(id(self.head),tuple(s.value() for s in self.base_spins)):
                self._clearance_key=key
                self._clearance_result=None
                self.clearance_info.setText(tr("Abstand vorne konnte nicht geprüft werden. Ausrichtung und Scan prüfen."))
                self.clearance_info.setStyleSheet('color: #ffbf69;')
        def finished():
            self._clearance_worker=None
            worker.deleteLater()
            self.refresh()
            if self._closing:
                self.close()
            elif self.head is not None and self.hmd_is_visible():
                if self._clearance_key != (id(self.head),tuple(s.value() for s in self.base_spins)):
                    self._clearance_timer.start()
        worker.succeeded.connect(succeeded)
        worker.failed.connect(failed)
        worker.finished.connect(finished)
        worker.start()

    def update_clearance_text(self, *_):
        result=self._clearance_result
        if result is None:
            return
        distance=result['minimum']
        coverage=round(result['coverage']*100)
        if distance is None:
            text=tr("Vorne keine Kopfoberfläche erfasst. Keine Kollisionsaussage möglich.")
            color='#ffbf69'
        elif distance < 0:
            text=tr("Kollision vorne erkannt: bis {v0} mm Überschneidung entlang Y.",v0=f'{-distance:.1f}')
            color='#ff776b'
        elif distance < self.clearance_margin.value():
            text=tr("Vorne knapp: kleinster erfasster Y-Abstand {v0} mm.",v0=f'{distance:.1f}')
            color='#ffbf69'
        else:
            text=tr("Vorne keine Kollision erkannt. Kleinster erfasster Y-Abstand: {v0} mm.",v0=f'{distance:.1f}')
            color='#b9d4dd'
        if distance is not None:
            text+=' '+tr("Scan-Abdeckung im Prüfbereich: {v0} %; nicht erfasste Stellen bleiben ungeprüft.",v0=str(coverage))
        if 'outer_minimum' in result:
            def description(value):
                if value is None:
                    return tr("nicht erfasst")
                if value<0:
                    return tr("{v0} mm Überschneidung",v0=f'{-value:.1f}')
                if value<self.clearance_margin.value():
                    return tr("knapp: {v0} mm Abstand",v0=f'{value:.1f}')
                return tr("{v0} mm Abstand",v0=f'{value:.1f}')
            text=tr("Rot · Linsen-/Randbereich: {v0}",v0=description(result['outer_minimum']))
            text+='\n'+tr("Orange · Mitte (Stoff prüfen): {v0}",v0=description(result['middle_minimum']))
            text+='\n'+tr("Erfasste Prüfpunkte: {v0} %. Scanlücken bleiben ungeprüft.",v0=f"{result['coverage']*100:.1f}")
            outer=result['outer_minimum']
            if outer is not None and outer<0:
                color='#ff776b'
            elif any(v is not None and v<self.clearance_margin.value() for v in (outer,result['middle_minimum'])):
                color='#ffbf69'
            else:
                color='#b9d4dd'
        self.clearance_info.setText(text)
        self.clearance_info.setToolTip(text)
        self.clearance_info.setStyleSheet('color: '+color+';')

    def base_changed(self, *_):
        if self._blocked:
            return
        self.base_positioned = True
        if self.params.get('base_pose') != [s.value() for s in self.base_spins]:
            self.parameters_changed()
        else:
            self.assembly = None
            self.accept_warnings.setChecked(False)
            self.redraw(); self.refresh()

    def reset_base(self):
        self._blocked = True
        for spin, value in zip(self.base_spins, self.parameter_values()['pose']):
            spin.setValue(value)
        self._blocked = False
        self.base_changed()

    def nose_changed(self,*_):
        if self._blocked:return
        self._nose_pending=False
        positioned=self.base_positioned;self.base_changed();self.base_positioned=positioned

    def nose_from_head(self,silent=False):
        if self.result is None or self.head is None:return
        from .nose import settings_from_head
        try:
            p=settings_from_head(self.result,self.head,pose_matrix([s.value() for s in self.base_spins]),self.nose_spins['clearance'].value())
            blocked=self._blocked;self._blocked=True
            try:
                for key,spin in self.nose_spins.items():spin.setValue(p[key])
            finally:self._blocked=blocked
            self._nose_pending=False
            if not silent:
                positioned=self.base_positioned;self.base_changed();self.base_positioned=positioned
        except ValueError as exc:
            if not silent:W.QMessageBox.warning(self,tr('Vorgang nicht abgeschlossen'),str(exc))

    def calculate_assembly(self):
        if self.result is None or self._worker:
            return
        self.assembly = None
        self.accept_warnings.setChecked(False)
        self.redraw()
        pose = [s.value() for s in self.base_spins]
        closed=self.closed_shell.isChecked()
        nose={key:spin.value() for key,spin in self.nose_spins.items()}
        nose['enabled']=False
        nose['bridge_enabled']=self.nose_enabled.isChecked()
        nose['fill_pockets']=self.nose_pockets.isChecked()
        top_strap = self.top_strap.isChecked() and closed
        builder = build_assembly
        if self.workflow == 'open':
            from .forehead import build_assembly as builder
        self.run_job(lambda progress: builder(self.result, pose, progress,closed_shell=closed,head=self.head,nose_settings=nose,top_strap=top_strap), self.display_assembly)

    def display_assembly(self, result):
        self.assembly = result
        self.assembly_info.setText(tr("Probe 07: Hülle und Verstärkungen als ein Druckkörper. Magnetaufnahme, Klebefläche und Hüllenanschlüsse geprüft.") if self.closed_shell.isChecked() else tr("Probe 06: ein geschlossener, zusammenhängender Druckkörper. Magnetaufnahme und Klebefläche geprüft."))
        if self.workflow == 'open':
            self.assembly_info.setText(tr('Offenes Gasket: ein geschlossener Druckkörper mit Oberschale. Kippanschläge vorläufig; USB-Stecker und Belastbarkeit am Probedruck prüfen.'))
        self.redraw()
        self.tabs.setCurrentIndex(5)
        self.refresh()

    def drag_pad(self, delta):
        if self.head is None or self._worker:
            return
        if self.tabs.currentIndex() not in (1,2):return
        self._blocked = True
        moving_base = self.tabs.currentIndex() == 1 and self.include_base.isChecked()
        controls = self.base_spins if moving_base else self.pose_spins
        if moving_base:
            for spin, change in zip(controls, delta):spin.setValue(spin.value()+float(change))
        else:
            local=np.asarray(delta) @ pose_matrix([s.value() for s in self.base_spins])[:3,:3]
            for i in (1,2):controls[i].setValue(controls[i].value()+float(local[i]))
        self._blocked = False
        if moving_base:
            self.base_changed()
        else:
            self.parameters_changed()

    def refresh(self, *_):
        busy = self._worker is not None
        for btn in self.workflow_buttons.values(): btn.setEnabled(not busy and self._clearance_worker is None)
        self.stack.setEnabled(not busy)
        self.open_btn.setEnabled(not busy)
        self.save_btn.setEnabled((self.head is not None or self._simple_used) and not busy)
        self.calculate_btn.setEnabled(self.head is not None and not busy)
        warnings = bool(self.result and self.result.report["warnings"])
        self.accept_warnings.setVisible(warnings)
        complete = not self.include_base.isChecked() or self.assembly is not None
        self.export_btn.setEnabled(self.result is not None and complete and not busy and (not warnings or self.accept_warnings.isChecked()))
        self.build_btn.setEnabled(self.result is not None and self.include_base.isChecked() and not busy)
        self.closed_shell.setEnabled(self.include_base.isChecked() and not busy)
        self.nose_enabled.setEnabled(self.include_base.isChecked() and self.closed_shell.isChecked() and not busy)
        self.nose_pockets.setEnabled(self.nose_enabled.isChecked() and self.nose_enabled.isEnabled())
        self.top_strap.setEnabled(self.include_base.isChecked() and self.closed_shell.isChecked() and not busy)
        for spin in self.nose_spins.values():spin.setEnabled(self.nose_enabled.isChecked() and self.nose_enabled.isEnabled())
        self.nose_scan_btn.setEnabled(self.nose_enabled.isChecked() and self.nose_enabled.isEnabled() and self.head is not None and self.result is not None)
        self.build_btn.setText(tr("Geschlossenes Gasket berechnen") if self.closed_shell.isChecked() else tr("Probe 06 verbinden"))
        if self.include_base.isChecked():
            if self.closed_shell.isChecked():
                self.frame_export_info.setText(tr("Geschlossenes Gasket mit Magnetbasis") if self.assembly else tr("Zuerst im Schritt Verbindung das Gasket berechnen."))
                self.export_btn.setText(tr("Gasket exportieren …"))
            else:
                self.frame_export_info.setText(tr("Probe 06 · Stabilitätsrahmen mit Magnetbasis") if self.assembly else tr("Für Probe 06 zuerst im Schritt Magnetbasis die Verbindungen berechnen."))
                self.export_btn.setText(tr("Probe 06 exportieren …"))
        else:
            self.frame_export_info.setText(tr("Probe 05 · nur die Polsterauflage"))
            self.export_btn.setText(tr("Polsterauflage exportieren …"))
        self.strain_view.setEnabled(self.result is not None and not busy)
        self.gap_view.setEnabled(self.result is not None and not busy)
        self.viewer.allow_move = self.head is not None and not busy
        self.tabs.setEnabled(not busy)
        for i in range(1, 6):
            self.tabs.setTabEnabled(i, self.head is not None)
        self.progress.setVisible(busy)
        self.cancel.setVisible(busy)
        if self.workflow == 'open':
            self.build_btn.setText(tr('Offenes Gasket berechnen'))
            self.export_btn.setText(tr('Offenes Gasket exportieren …'))
            self.frame_export_info.setText(tr('Offenes Gasket mit Stirnauflage und Testanschlägen') if self.assembly else tr('Zuerst im Schritt Verbindung das Gasket berechnen.'))

    def run_job(self, function, success):
        if self._worker is not None:
            return
        worker = Job(function, self)
        self._worker = worker
        def succeeded(value):
            if not self._closing:
                success(value)
        def failed(message):
            self.activity.setText(message)
            if not self._closing and not worker.isInterruptionRequested():
                W.QMessageBox.warning(self, tr("Vorgang nicht abgeschlossen"), message)
        def finished():
            self._worker = None
            worker.deleteLater()
            self.refresh()
            if self._closing:
                self.close()
            else:
                self.ready.emit()
        worker.succeeded.connect(succeeded)
        worker.failed.connect(failed)
        worker.progress.connect(lambda n, message: (self.progress.setValue(n), self.activity.setText(message)))
        worker.finished.connect(finished)
        self.refresh()
        worker.start()

    def cancel_job(self):
        if self._worker:
            self._worker.requestInterruption()
            self.activity.setText(tr("Vorgang wird abgebrochen …"))

    def open_simple_fit(self):
        if self.workflow!='open':return
        self._simple_used = True
        from .simple_fit_dialog import SimpleFitDialog
        if not hasattr(self,'_simple_fit_dialog'):
            self._simple_fit_dialog=SimpleFitDialog(self)
            if self._simple_settings is not None:
                self._simple_fit_dialog.apply_settings(self._simple_settings)
        self.refresh()
        self._simple_fit_dialog.showNormal()
        self._simple_fit_dialog.raise_()
        self._simple_fit_dialog.activateWindow()

    def open_head(self):
        filename, _ = W.QFileDialog.getOpenFileName(self, tr("Kopfscan wählen …"), self.last_directory, "3D (*.stl *.3mf)")
        if filename:
            self.load_head_path(filename)

    def load_head_path(self, filename, calculate=False):
        self.last_directory = str(Path(filename).parent)
        self.run_job(lambda progress: self.prepare_head(load_mesh(filename, head=True)),
                     lambda value: self.apply_head(value, calculate=calculate))

    @staticmethod
    def prepare_head(head):
        return head, preview(head)

    def apply_head(self, value, params=None, calculate=False, advance=False):
        self.head, mesh_preview = value
        self.viewer.set_head(*mesh_preview)
        self.head_info.setText(self.head.name)
        self.set_parameters(params or self.workflow_initial(self.head))
        self.viewer.fit_view()
        if advance:
            self.tabs.setCurrentIndex(1)
        self.activity.setText(tr("Kopfscan geladen. Position und Ausrichtung prüfen."))
        if calculate:
            # Queue after the import worker's finished signal has cleared it.
            QtCore.QTimer.singleShot(100, self.calculate)

    def rotate_head(self, axis):
        if self.head is None:
            return
        rotation = [0., 0., 0., 0., 0., 0.]
        rotation[axis + 3] = 90
        vertices = self.head.vertices @ pose_matrix(rotation)[:3, :3].T
        head = Mesh(vertices, self.head.faces.copy(), self.head.name)
        self.run_job(lambda progress: self.prepare_head(head), self.apply_head)

    def reset_position(self):
        if self.head is not None:
            p = self.parameter_values()
            p['pad_alignment'] = [0.,0.,0.,0.]
            self.set_parameters(p)

    def calculate(self):
        if self.head is None or self._worker:
            return
        self.result = None
        self.assembly = None
        self.result_info.setText(tr("Noch keine Auflage berechnet."))
        self.warning_info.clear()
        self.redraw()
        self.accept_warnings.setChecked(False)
        params = self.parameter_values()
        fitter = fit_pad
        if self.workflow == 'open':
            from .forehead import fit_pad as fitter
        self.run_job(lambda progress: fitter(self.outline, self.head, params, progress), self.display_result)

    def display_result(self, result):
        # Update the displayed pose without invalidating the finished result.
        self._blocked = True
        relative=alignment_from_pose([s.value() for s in self.base_spins], result.report['parameters']['pose'], self.workflow)
        for i,value in zip((1,2,3,5),relative):self.pose_spins[i].setValue(value)
        self._blocked = False
        self.params = self.parameter_values()
        self.result = result
        self.assembly = None
        if self._nose_pending and self.include_base.isChecked() and self.nose_enabled.isChecked():self.nose_from_head(silent=True)
        self.params=self.parameter_values()
        self.redraw()
        self.update_result_text()
        self.tabs.setCurrentIndex(4 if self.include_base.isChecked() else 5)
        self.activity.setText(tr("Polsterauflage berechnet. Abstände und Polsterdehnung prüfen."))
        self.refresh()

    def update_result_text(self):
        if self.result is None:
            return
        r = self.result.report
        summary = "Polsterauflage · 1,5 mm\nAbstand zum Scan: {v0}–{v1} mm\nMittlere 90 % der Abstände: {v2}–{v3} mm\nLängenänderung gegenüber Probe 04: {v4} bis +{v5} %\nGrößte Formanpassung: {v6} mm"
        if self.workflow == 'open':
            summary = summary.replace('1,5 mm', '2,5 mm').replace('Probe 04', 'Stirnvorlage')
        self.result_info.setText(tr(summary,
            v0=f'{r["padding_min_mm"]:.2f}', v1=f'{r["padding_max_mm"]:.2f}',
            v2=f'{r["padding_p05_mm"]:.2f}', v3=f'{r["padding_p95_mm"]:.2f}',
            v4=f'{r["edge_strain_min_percent"]:.1f}', v5=f'{r["edge_strain_max_percent"]:.1f}',
            v6=f'{r["displacement_max_mm"]:.1f}'))
        warnings = []
        if "strain" in r["warnings"]:
            warnings.append(tr("Die Vorlage wird örtlich deutlich gedehnt oder gestaucht. Farbvorschau und tatsächliches Polster prüfen; eventuell Position ändern."))
        if "gap" in r["warnings"]:
            warnings.append(tr("Einige Abstände liegen außerhalb von 3,5–10 mm plus Klett. Position und Farbvorschau prüfen; die Auflage erreicht dort noch keinen passenden Polsterabstand."))
        if "limit" in r["warnings"]:
            warnings.append(tr("Die Anpassung erreicht eine Formgrenze. Verbleibende Lücken durch Positionierung verbessern; das Polster nicht gewaltsam verformen."))
        self.warning_info.setText("\n\n".join(warnings))

    def export(self):
        if self.result is None or not self.export_btn.isEnabled() or self._worker:
            return
        item = self.assembly if self.include_base.isChecked() else self.result
        default_name = ("PFDMR_Gasket.3mf" if self.closed_shell.isChecked() else "PFDMR_OEM_Stabilitaetsrahmen.3mf") if self.include_base.isChecked() else "VRcover_Probe_05.3mf"
        if self.workflow == 'open': default_name = 'PFDMR_Offenes_Gasket.3mf'
        filename, _ = W.QFileDialog.getSaveFileName(self, tr("Polsterauflage exportieren …"),
                                                  str(Path(self.last_directory) / default_name), "3MF (*.3mf);;STL (*.stl)")
        if not filename:
            return
        include_base = self.include_base.isChecked()
        # The report belongs to this exact calculated mesh. Reading spin boxes
        # here could apply a different pose to a cached result or a refined fit.
        export_pose = (item.report['base_pose'] if include_base
                       else item.report['parameters']['pose'])
        def write(progress):
            progress(5, tr('Druckdatei lokal aufbereiten und prüfen …'))
            mesh, placement = print_frame(item.mesh, export_pose)
            report = dict(item.report)
            report['export_placement'] = placement
            if include_base:
                report['print_preparation'] = export_print_mesh(filename, mesh)
            else:
                export_mesh(filename, mesh)
            progress(100, tr('Druckdatei lokal gespeichert.'))
            return report
        def complete(value):
            self.last_export_report = value
            self.activity.setText(tr("Druckdatei lokal gespeichert."))
        self.run_job(write, complete)

    def save_project(self):
        simple = getattr(self, '_simple_fit_dialog', None)
        if self._worker or (simple is not None and simple.worker):
            return
        if self.head is None and not self._simple_used:
            return
        filename, _ = W.QFileDialog.getSaveFileName(self, tr("Projekt speichern"),
            self.project_path or str(Path(self.last_directory) / "GasketFit.padfit"), "GasketFit (*.padfit)")
        if filename:
            try:
                self.save_project_path(filename)
                self.activity.setText(tr("Alle verwendeten Workflows im gemeinsamen Projekt gespeichert. Modelle bei Bedarf neu berechnen."))
            except Exception as exc:
                W.QMessageBox.warning(self, tr("Vorgang nicht abgeschlossen"), str(exc))

    def save_project_path(self, filename):
        from copy import deepcopy
        previous = self.parameter_values()
        states = dict(self._workflow_states)
        states[self.workflow] = dict(head=self.head, params=previous, result=self.result)
        variants = {}
        for mode, state in states.items():
            if state['head'] is not self.head:
                continue
            params = deepcopy(state['params'])
            result = state['result']
            if result is not None:
                params['pose'] = list(result.report['requested_pose'])
            if params.get('base_pose') != previous.get('base_pose'):
                params['base_pose'] = list(previous['base_pose'])
                params['pose'] = pose_from_alignment(params['base_pose'], params['pad_alignment'], mode)
            variants[mode] = params
        simple = getattr(self, '_simple_fit_dialog', None)
        settings = (simple.settings() if simple is not None else self._simple_settings) if self._simple_used else None
        save_pad_project(filename, self.head, self.outline, variants[self.workflow],
                         workflows=variants, active=self.workflow, simple=settings)
        self.project_path = str(filename)
        self.last_directory = str(Path(filename).parent)

    def open_project(self):
        filename, _ = W.QFileDialog.getOpenFileName(self, tr("Projekt öffnen"), self.last_directory, "GasketFit Polster (*.padfit)")
        if filename:
            self.load_project_path(filename)

    def load_project_path(self, filename, calculate=False):
        self.last_directory = str(Path(filename).parent)
        simple = getattr(self, '_simple_fit_dialog', None)
        if simple is not None and simple.worker:
            return
        def load(progress):
            head, params, project = load_pad_project(filename, self.outline, with_workflows=True)
            if params.get('solver') not in ('reference04', 'forehead'):
                raise ValueError(tr('Dieses Projekt verwendet die alte Flächenprojektion. Bitte den Kopfscan neu laden; Probe 04 verwendet eine andere Ausgangsform.'))
            return self.prepare_head(head) if head is not None else None, params, project
        def loaded(value):
            head, params, project = value
            self._workflow_states.clear()
            self.project_path = str(filename)
            self._simple_settings = project['simple']
            self._simple_used = self._simple_settings is not None
            if simple is not None:
                simple.apply_settings(self._simple_settings or {})
                simple.tabs.setCurrentIndex(0)
                simple.hide()
            source_mode = project['active']
            if project['version'] == 2 or source_mode == 'open':
                self.workflow = source_mode
            elif self.workflow == 'open':
                from .forehead import initial_parameters as convert
                params = convert(head[0], params)
            self.update_workflow_ui()
            if head is not None:
                self.apply_head(head, params, calculate=calculate, advance=True)
            else:
                self.head = None
                self.viewer.preview_head = None
                if 'head' in self.viewer.items_by_name:
                    self.viewer.items_by_name['head'].hide()
                self.head_info.setText(tr('Noch kein Kopfscan geladen.'))
                self.set_parameters(params)
                self.tabs.setCurrentIndex(0)
                self.redraw(); self.refresh(); self.viewer.fit_view()
            for mode, settings in project['workflows'].items():
                self._workflow_states[mode] = dict(head=self.head, params=settings,
                    result=None, assembly=None, step=1 if self.head is not None else 0, positioned=False)
            if self.head is None and self._simple_settings is not None:
                self.open_simple_fit()
        self.run_job(load, loaded)

    def show_settings(self, section="language"):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self, section)
        self._settings_dialog.set_section(section)
        self._settings_dialog.show()
        self._settings_dialog.raise_()

    def update_notice(self):
        new = self.online.release and self.online.release.get("state") == "new"
        self.settings_action.setText(tr("Einstellungen") + (" ●" if new else ""))

    def language_changed(self, *_):
        current().retranslate(self)
        self.language_action.setText(tr("Sprache"))
        self.controls_action.setText(tr("Tastenbelegung"))
        self.update_notice()
        self.refresh()
        self.update_result_text()
        self.update_navigation_hint()
        self.update_clearance_text()

    def show_legacy(self):
        from .window import MainWindow
        window = MainWindow()
        self._legacy_windows.append(window)
        window.show()

    def closeEvent(self, event):
        simple=getattr(self,'_simple_fit_dialog',None)
        if simple is not None and simple.worker is not None:
            simple.status.setText(tr('Bitte den laufenden Export abwarten, bevor GasketFit geschlossen wird.'))
            event.ignore()
            return
        if self._worker is not None or self._clearance_worker is not None:
            self._closing = True
            self.cancel_job()
            self._clearance_timer.stop()
            if self._clearance_worker is not None:
                self._clearance_worker.requestInterruption()
            event.ignore()
        elif self.online.busy():
            self.online.timer.stop()
            QtCore.QTimer.singleShot(200, self.close)
            event.ignore()
        else:
            event.accept()
