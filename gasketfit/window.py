from __future__ import annotations
from .localization import tr
from pathlib import Path
import json
import logging
import html
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets as W
from . import __version__
from .meshio import Mesh, load_mesh, export_mesh
from .profile import NAME, supported, initial_pose, pose_matrix, frame_vertices, weights, hmd_matrix, validate_regions, FULL_PROFILE
from .fitting import fit_gasket
from .fullfit import fit_full_face
from .project import save_project, load_project
from .viewer import Viewer
from .localization import current
from .settings import OnlineController, SettingsDialog, build_info


STYLE = """QMainWindow, QWidget { background:#070b1a; color:#dce1f0; font-family:'Segoe UI'; font-size:10pt; }
QLabel { background:transparent; }
QFrame#header { background:#0e1530; border-bottom:1px solid #253056; }
QLabel#title { font-size:22pt; font-weight:650; color:#ffffff; }
QLabel#subtitle, QLabel#hint { color:#8e98b8; }
QLabel#section { font-size:17pt; font-weight:600; margin-top:8px; }
QLabel#badge { color:#22d3ff; background:#151d3c; padding:5px 10px; border-radius:10px; }
QPushButton { background:#151d3c; border:1px solid #253056; border-radius:7px; padding:9px 12px; }
QPushButton:hover { background:#202c52; border-color:#22d3ff; }
QPushButton:disabled { color:#74809f; border-color:#253056; background:#10172d; }
QPushButton#primary { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #8a2bf2,stop:1 #007b9b); border-color:#9b5cff; color:white; font-weight:600; padding:12px; }
QPushButton#primary:hover { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #9845f5,stop:1 #087b9b); }
QPushButton#primary:disabled { background:#202440; color:#8e98b8; border-color:#34406a; }
QPushButton:focus { border-color:#22d3ff; }
QPushButton#view { padding:6px 10px; }
QSpinBox, QDoubleSpinBox, QComboBox { background:#0e1530; border:1px solid #253056; border-radius:5px; padding:6px; min-height:22px; }
QAbstractSpinBox { padding-right:54px; }
QAbstractSpinBox::up-button { subcontrol-origin:border; subcontrol-position:center right; width:24px; height:22px; right:2px; }
QAbstractSpinBox::down-button { subcontrol-origin:border; subcontrol-position:center right; width:24px; height:22px; right:27px; }
QAbstractSpinBox:focus, QComboBox:focus { border-color:#9b5cff; }
QComboBox QAbstractItemView { background:#0e1530; color:#dce1f0; selection-background-color:#392565; selection-color:white; }
QMenu { background:#0e1530; color:#dce1f0; border:1px solid #253056; }
QMenu::item:selected { background:#392565; }
QDoubleSpinBox:disabled { color:#74809f; }
QTabBar::tab { background:#0e1530; padding:12px 17px; color:#8e98b8; border-bottom:3px solid transparent; }
QTabBar::tab:selected { color:#ffffff; border-bottom:3px solid #22d3ff; background:#151d3c; }
QTabBar::tab:disabled { color:#74809f; }
QGroupBox { border:1px solid #253056; border-radius:8px; margin-top:12px; padding:14px 10px 8px; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; color:#dce1f0; }
QCheckBox { spacing:8px; padding:4px 0; }
QCheckBox::indicator { width:17px; height:17px; background:#111b35; border:2px solid #9aa8cc; border-radius:3px; }
QCheckBox::indicator:unchecked:hover { border-color:#22d3ff; background:#202c52; }
QCheckBox::indicator:disabled { background:#182035; border-color:#63708e; }
QCheckBox::indicator:checked { background:#8a2bf2; border:2px solid #b68aff; border-radius:3px; }
QProgressBar { background:#151d3c; border:none; border-radius:4px; height:10px; text-align:center; }
QProgressBar::chunk { background:#9b5cff; border-radius:4px; }
QScrollArea { border:none; }
QScrollBar:vertical { background:#070b1a; width:10px; } QScrollBar::handle:vertical { background:#34406a; border-radius:4px; min-height:30px; }
QTextBrowser { background:#0e1530; border:1px solid #253056; border-radius:6px; padding:8px; }
QStatusBar { color:#8e98b8; background:#050814; }
QToolTip { background:#151d3c; color:white; border:1px solid #9b5cff; }
"""


def label(text, kind=None):
    item = W.QLabel(text)
    item.setTextFormat(QtCore.Qt.TextFormat.PlainText)
    item.setWordWrap(True)
    if kind:
        item.setObjectName(kind)
    return item


def button(text, handler, primary=False):
    item = W.QPushButton(text)
    item.clicked.connect(handler)
    if primary:
        item.setObjectName("primary")
    return item


class NumericInput(W.QDoubleSpinBox):
    def wheelEvent(self, event):
        # Scrolling a long workflow page must not silently change padding,
        # strip width or alignment. Use typing or the arrow buttons to edit.
        event.ignore()


def preview(mesh):
    if len(mesh.faces) < 160_000:
        return mesh.vertices, mesh.faces
    import trimesh
    try:
        simple = trimesh.Trimesh(mesh.vertices, mesh.faces, process=False).simplify_quadric_decimation(face_count=160_000)
        return np.asarray(simple.vertices), np.asarray(simple.faces, dtype=np.int32)
    except Exception:
        logging.exception("Preview simplification failed; using full mesh")
        return mesh.vertices, mesh.faces


class Job(QtCore.QThread):
    succeeded = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    progress = QtCore.Signal(int, str)

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            def update(n, text):
                if self.isInterruptionRequested():
                    raise InterruptedError(tr('Vorgang abgebrochen.'))
                self.progress.emit(n, text)
            result = self.function(update)
            if self.isInterruptionRequested():
                raise InterruptedError(tr('Vorgang abgebrochen.'))
            self.succeeded.emit(result)
        except Exception as exc:
            logging.exception("Job failed")
            self.failed.emit(str(exc) or type(exc).__name__)


class MainWindow(W.QMainWindow):
    ready = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"GasketFit {__version__} · PFDMR")
        self.resize(1420, 950)
        self.setMinimumSize(1050, 740)
        self.gasket = self.head = self.head_base = self.result = None
        self.head_preview = None
        self.hmd = None
        self.hmd_preview = None
        self.hmd_docking = None
        self.region_config = validate_regions()
        self.head_rotation = np.eye(3)
        self._worker = None
        self._success = None
        self._blocked = False
        self._exact_pose = None
        self._closing = False
        self.revision = 0
        self.last_directory = str(Path.home())
        self.setStyleSheet(STYLE)
        central = W.QWidget()
        layout = W.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central)
        header = W.QFrame()
        header.setObjectName("header")
        hl = W.QHBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 15)
        text = W.QVBoxLayout()
        title = label("GasketFit", "title")
        title.setMinimumWidth(280)
        text.addWidget(title)
        tagline = label(tr('Dein Gasket. Deine Gesichtsform.'), "subtitle")
        tagline.setWordWrap(False)
        text.addWidget(tagline)
        hl.addLayout(text)
        hl.addStretch()
        badge = label(tr('Lokal · ohne Fusion'), "badge")
        badge.setMaximumHeight(34)
        hl.addWidget(badge)
        self.open_project_btn = button(tr('Projekt öffnen'), self.open_project)
        self.save_project_btn = button(tr('Projekt speichern'), self.save_project)
        hl.addWidget(self.open_project_btn)
        hl.addWidget(self.save_project_btn)
        layout.addWidget(header)
        self.tabs = W.QTabBar()
        self.tabs.setExpanding(True)
        for name in (tr('1  Modelle'), tr('2  Ausrichten'), tr('3  Anpassen'), tr('4  Exportieren')):
            self.tabs.addTab(name)
        self.tabs.currentChanged.connect(self.navigate)
        layout.addWidget(self.tabs)
        split = W.QSplitter()
        split.setChildrenCollapsible(False)
        self.stack = W.QStackedWidget()
        self.stack.setMinimumWidth(350)
        self.stack.setMaximumWidth(450)
        self.pages = []
        for _ in range(4):
            page = W.QWidget()
            pl = W.QVBoxLayout(page)
            pl.setContentsMargins(22, 15, 22, 20)
            pl.setSpacing(12)
            scroll = W.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
            self.pages.append(pl)
        split.addWidget(self.stack)
        scene = W.QWidget()
        sl = W.QVBoxLayout(scene)
        sl.setContentsMargins(12, 12, 12, 8)
        tools = W.QHBoxLayout()
        for text, view in (("3D", "3d"), (tr('Vorne'), "front"), (tr('Hinten'), "back"), (tr('Rechts'), "right"), (tr('Links'), "left"), (tr('Oben'), "top")):
            b = button(text, lambda checked=False, v=view: self.viewer.view(v))
            b.setObjectName("view")
            tools.addWidget(b)
        tools.addStretch()
        self.recenter_btn = button("Recenter", lambda: self.viewer.fit_view())
        self.recenter_btn.setToolTip(tr("Ansicht zentrieren und alle sichtbaren Modelle vollständig anzeigen. Die Ausrichtung bleibt unverändert."))
        tools.addWidget(self.recenter_btn)
        self.show_head = W.QCheckBox(tr('Kopf zeigen'))
        self.show_head.setChecked(True)
        tools.addWidget(self.show_head)
        sl.addLayout(tools)
        self.viewer = Viewer()
        self.viewer.moved.connect(self.drag_gasket)
        self.viewer.protection_marked.connect(self.add_protection)
        self.show_head.toggled.connect(self.viewer.set_head_visible)
        hmd_tools = W.QHBoxLayout()
        self.show_hmd = W.QCheckBox(tr("HMD zeigen"))
        self.show_hmd.setChecked(True)
        self.show_hmd.toggled.connect(self.viewer.set_hmd_visible)
        hmd_tools.addWidget(self.show_hmd)
        hmd_tools.addWidget(label(tr("HMD-Deckkraft")))
        self.hmd_opacity = W.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.hmd_opacity.setRange(5, 85)
        self.hmd_opacity.setValue(18)
        self.hmd_opacity.setMaximumWidth(150)
        self.hmd_opacity.valueChanged.connect(lambda value: self.viewer.set_hmd_opacity(value / 100.))
        hmd_tools.addWidget(self.hmd_opacity)
        self.hmd_percent = label("18%")
        self.hmd_opacity.valueChanged.connect(lambda value: self.hmd_percent.setText(f"{value}%"))
        hmd_tools.addWidget(self.hmd_percent)
        hmd_tools.addStretch()
        sl.addLayout(hmd_tools)
        sl.addWidget(self.viewer, 1)
        sl.addWidget(label(tr('Blau: feste Aufnahme · Orange: anpassbare Auflage · Grün: angepasste Bereiche'), "hint"))
        sl.addWidget(label(tr('Ziehen: Ansicht drehen  ·  Mittlere Maustaste + Ziehen: Ansicht verschieben  ·  Mausrad: zoomen  ·  Alt + Ziehen: Gasket verschieben'), "hint"))
        split.addWidget(scene)
        split.setSizes([380, 1040])
        layout.addWidget(split, 1)
        bottom = W.QWidget()
        bl = W.QHBoxLayout(bottom)
        bl.setContentsMargins(22, 8, 22, 8)
        self.activity = label(tr('Lade zuerst die beiden Modelle.'), "hint")
        self.progress = W.QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.cancel = button(tr('Abbrechen'), self.cancel_job)
        self.cancel.setVisible(False)
        bl.addWidget(self.activity, 1)
        bl.addWidget(self.progress)
        bl.addWidget(self.cancel)
        layout.addWidget(bottom)
        self.create_pages()
        self.statusBar().showMessage(tr('Version 0.4 · Begrenzte Polsterkante · Kopfband und Nase geschützt'))
        self.refresh()
        self.online = OnlineController(self)
        self.settings_menu = self.menuBar().addMenu(tr("Einstellungen"))
        self.settings_action = self.settings_menu.menuAction()
        self.language_action = self.settings_menu.addAction(tr("Sprache"), lambda: self.show_settings("language"))
        self.updates_action = self.settings_menu.addAction(tr("Aktualisierungen"), lambda: self.show_settings("updates"))
        self.menuBar().addAction(tr("Build-Informationen"), lambda: build_info(self))
        self._settings_dialog = None
        current().changed.connect(self.language_changed)
        self.online.update_changed.connect(self.update_notice)

    def show_settings(self, section="language"):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self, section)
        self._settings_dialog.set_section(section)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def update_notice(self):
        new = self.online.release and self.online.release.get("state") == "new"
        self.settings_action.setText(tr("Einstellungen") + (" ●" if new else ""))

    def language_changed(self, *_):
        current().retranslate(self)
        self.language_action.setText(tr("Sprache"))
        if self.result:
            self.display_result(reset_compare=False)

    def create_pages(self):
        p = self.pages[0]
        p.addWidget(label(tr('Modelle laden'), "section"))
        p.addWidget(label(tr('Diese erste Version unterstützt die unveränderte PFDMR Face Gasket Mod V2. Andere Modelle können betrachtet, aber noch nicht automatisch angepasst werden.'), "hint"))
        p.addWidget(button(tr('Face-Gasket öffnen …'), lambda: self.load_file(False), True))
        self.gasket_info = label(tr('Noch kein Gasket geladen.'))
        p.addWidget(self.gasket_info)
        p.addSpacing(8)
        p.addWidget(button(tr('Kopf-Scan öffnen …'), lambda: self.load_file(True), True))
        self.head_info = label(tr('Noch kein Kopf-Scan geladen.'))
        p.addWidget(self.head_info)
        self.hmd_load_btn = button(tr("HMD laden und koppeln …"), self.load_hmd_file)
        p.addWidget(self.hmd_load_btn)
        self.hmd_info = label(tr("Optional: PFDM HMD_base.stl als transparente Referenz laden. HMD und Gasket bewegen sich gemeinsam."), "hint")
        p.addWidget(self.hmd_info)
        p.addWidget(label(tr("Basis: Pfd 108Fov Face Gasket mod V2 von Sir Dominik. Die Aufnahme wird nicht aus dem Original-Gasket ersetzt."), "hint"))
        self.head_tools = W.QGroupBox(tr('Kopfmaßstab & Orientierung'))
        tools = W.QVBoxLayout(self.head_tools)
        tools.addWidget(label(tr('Prüfe die Kopfmaße. Bei STL/OBJ wird zunächst Millimeter angenommen.'), "hint"))
        tools.addWidget(label(tr("Kopf aufrecht, Gesicht nach vorne. Bei liegenden Modellen zuerst X +90° ausprobieren. Danach wird das Gasket neu grob positioniert."), "hint"))
        self.scale = W.QComboBox()
        for text, value in ((tr('Originalgröße · 1:1'), 1.), (tr('Zentimeter → Millimeter · ×10'), 10.), (tr('Meter → Millimeter · ×1000'), 1000.), (tr('Zoll → Millimeter · ×25,4'), 25.4), (tr('Verkleinern · ×0,1'), .1), (tr('Verkleinern · ×0,01'), .01)):
            self.scale.addItem(text, value)
        self.scale.currentIndexChanged.connect(self.change_head)
        tools.addWidget(self.scale)
        row = W.QHBoxLayout()
        for axis in range(3):
            row.addWidget(button(f"{'XYZ'[axis]} +90°", lambda checked=False, a=axis: self.rotate_head(a)))
        tools.addLayout(row)
        tools.addWidget(button(tr('Kopfausrichtung zurücksetzen'), self.reset_head))
        p.addWidget(self.head_tools)
        p.addStretch()
        self.next1 = button(tr('Weiter: ausrichten →'), lambda: self.tabs.setCurrentIndex(1), True)
        p.addWidget(self.next1)

        p = self.pages[1]
        p.addWidget(label(tr('Am Kopf ausrichten'), "section"))
        p.addWidget(label(tr('Die Öffnung liegt vor den Augen. Richte die Auflage an Stirn und Wangen mit Platz für das Polster aus. Die Schläfen dürfen noch weiter abstehen.'), "hint"))
        p.addWidget(button(tr('Grobe Startposition'), self.rough_pose))
        p.addWidget(label(tr('Fein verschieben: Alt gedrückt halten und das Gasket in der Ansicht ziehen.'), "hint"))
        self.pose_spins = []
        for title, names, unit, start in ((tr('Verschieben'), (tr('Links / rechts'), tr('Vor / zurück'), tr('Hoch / runter')), " mm", 0),
                                           (tr('Drehen'), (tr('Neigung'), tr('Seitlich kippen'), tr('Seitlich drehen')), "°", 3)):
            box = W.QGroupBox(title)
            form = W.QFormLayout(box)
            for i, name in enumerate(names):
                spin = NumericInput()
                spin.setDecimals(2 if start == 0 else 1)
                spin.setRange(-100000 if start == 0 else -180, 100000 if start == 0 else 180)
                spin.setSingleStep(1.)
                spin.setSuffix(unit)
                spin.setKeyboardTracking(False)
                spin.valueChanged.connect(self.pose_changed)
                self.pose_spins.append(spin)
                form.addRow(name, spin)
            p.addWidget(box)
        p.addStretch()
        p.addWidget(button(tr('Weiter: Polster & Anpassung →'), lambda: self.tabs.setCurrentIndex(2), True))

        p = self.pages[2]
        p.addWidget(label(tr('An dein Gesicht anpassen'), "section"))
        self.fit_mode = W.QComboBox()
        self.fit_mode.addItem(tr("Nur freigegebene Polsterkante (Beta)"), "full_face")
        self.fit_mode.currentIndexChanged.connect(self.mode_changed)
        p.addWidget(self.fit_mode)
        self.strip_width = NumericInput()
        self.strip_width.setRange(2., 12.)
        self.strip_width.setValue(self.region_config["strip_mm"])
        self.strip_width.setSuffix(" mm")
        self.strip_width.setDecimals(1)
        self.strip_width.valueChanged.connect(self.region_changed)
        p.addWidget(label(tr("Breite des veränderbaren Streifens an der Polsterkante"), "hint"))
        p.addWidget(self.strip_width)
        self.inspect_regions = W.QCheckBox(tr("Schutzbereiche am Original anzeigen"))
        self.inspect_regions.toggled.connect(self.inspect_changed)
        p.addWidget(self.inspect_regions)
        p.addWidget(label(tr("Violett: Kopfband-Befestigung und Nase/Belüftung bleiben fest. Blau: ebenfalls fest. Nur Orange darf verändert werden."), "hint"))
        self.brush = W.QCheckBox(tr("Zusätzlich schützen: Shift + Klick auf das Gasket"))
        self.brush.toggled.connect(self.brush_changed)
        p.addWidget(self.brush)
        self.brush_radius = NumericInput()
        self.brush_radius.setRange(1., 20.)
        self.brush_radius.setValue(5.)
        self.brush_radius.setSuffix(" mm")
        p.addWidget(self.brush_radius)
        p.addWidget(button(tr("Letzten Schutzpunkt zurücknehmen"), self.undo_protection))
        self.region_reviewed = W.QCheckBox(tr("Orangefarbenen Bereich geprüft und freigegeben"))
        self.region_reviewed.toggled.connect(self.refresh)
        p.addWidget(self.region_reviewed)
        p.addWidget(label(tr("Gesamte Auflage: Stirn, Wangen, Nase und Schläfen. Der feste vordere Aufnahmebereich bleibt exakt erhalten. Bestehende Öffnungen und Aussparungen bleiben bestehen."), "hint"))
        box = W.QGroupBox(tr('Platz für das Polster'))
        form = W.QFormLayout(box)
        self.pad = NumericInput()
        self.pad.setRange(1., 15.)
        self.pad.setDecimals(1)
        self.pad.setValue(5.)
        self.pad.setSingleStep(.5)
        self.pad.setSuffix(" mm")
        self.pad.valueChanged.connect(self.settings_changed)
        form.addRow(tr('Dicke'), self.pad)
        p.addWidget(box)
        p.addWidget(label(tr('Gemeint ist der gewünschte Abstand im getragenen Zustand. Ein weiches 5-mm-Polster kann unter Druck dünner sein.'), "hint"))
        self.aligned = W.QCheckBox(tr('Maßstab und Ausrichtung geprüft'))
        self.aligned.toggled.connect(self.refresh)
        p.addWidget(self.aligned)
        self.fit_btn = button(tr('Gesamte Gesichtsauflage anpassen'), self.start_fit, True)
        p.addWidget(self.fit_btn)
        p.addWidget(label(tr('Die Berechnung erfolgt auf dem vollständigen Scan. Die vereinfachte Ansicht dient nur der flüssigen Bedienung.'), "hint"))
        p.addStretch()

        p = self.pages[3]
        p.addWidget(label(tr('Ergebnis & Export'), "section"))
        self.result_info = label(tr('Noch kein Ergebnis berechnet.'))
        p.addWidget(self.result_info)
        self.compare = W.QComboBox()
        self.compare.addItems([tr('Angepasstes Gasket'), tr('Original zum Vergleich')])
        self.compare.currentIndexChanged.connect(self.redraw)
        p.addWidget(self.compare)
        self.export_btn = button(tr('Angepasstes Modell exportieren …'), self.export_result, True)
        p.addWidget(self.export_btn)
        p.addWidget(label(tr('STL oder 3MF · Millimeter · ursprüngliche Lage des Gaskets. Der Kopf-Scan wird nicht mit exportiert.'), "hint"))
        self.with_report = W.QCheckBox(tr('Prüfbericht daneben speichern'))
        self.with_report.setChecked(True)
        p.addWidget(self.with_report)
        self.details = W.QTextBrowser()
        self.details.setMinimumHeight(190)
        self.details.setOpenExternalLinks(False)
        p.addWidget(self.details)
        p.addWidget(label(tr('Die Passform ist eine geometrische Näherung. Erst mit dem vorhandenen Polster anprobieren, dann bei Bedarf nachjustieren.'), "hint"))
        p.addWidget(button(tr('← Ausrichtung nachjustieren'), lambda: self.tabs.setCurrentIndex(1)))
        p.addStretch()

    def pose_values(self):
        return self._exact_pose.copy() if self._exact_pose is not None else [s.value() for s in self.pose_spins]

    def set_pose(self, values):
        self._blocked = True
        for spin, value in zip(self.pose_spins, values):
            spin.setValue(float(value))
        self._blocked = False
        self.invalidate(True)
        self._exact_pose = [float(value) for value in values]
        self.redraw()

    def navigate(self, index):
        self.stack.setCurrentIndex(index)
        self.viewer.allow_move = index == 1 and self.gasket is not None and self._worker is None
        if hasattr(self, "brush"):
            self.viewer.protection_brush = index == 2 and self.brush.isChecked() and self._worker is None

    def refresh(self):
        loaded = self.gasket is not None and self.head is not None
        valid = loaded and supported(self.gasket)
        busy = self._worker is not None
        for i in (1, 2):
            self.tabs.setTabEnabled(i, loaded)
        self.tabs.setTabEnabled(3, self.result is not None)
        self.next1.setEnabled(loaded and not busy)
        self.fit_btn.setEnabled(valid and self.aligned.isChecked() and self.region_reviewed.isChecked() and not busy)
        self.head_tools.setEnabled(self.head_base is not None and not busy)
        self.save_project_btn.setEnabled(loaded and not busy)
        self.open_project_btn.setEnabled(not busy)
        self.export_btn.setEnabled(self.result is not None and not busy)
        self.hmd_load_btn.setEnabled(False)
        self.hmd_load_btn.setToolTip(tr("Die bisherige HMD-Kopplung ist deaktiviert. Eine verlässliche Referenz fehlt noch."))
        self.show_hmd.setEnabled(False)
        self.hmd_opacity.setEnabled(False)
        self.viewer.protection_brush = self.brush.isChecked() and not busy and self.tabs.currentIndex() == 2
        self.viewer.allow_move = self.tabs.currentIndex() == 1 and loaded and not busy

    def invalidate(self, clear_alignment=False):
        self.revision += 1
        self.result = None
        if clear_alignment:
            self.aligned.setChecked(False)
        if self.tabs.currentIndex() == 3:
            self.tabs.setCurrentIndex(2)
        self.result_info.setText(tr('Die Einstellungen wurden geändert. Bitte neu anpassen.'))
        self.refresh()

    def pose_changed(self):
        if self._blocked:
            return
        self._exact_pose = None
        self.invalidate(True)
        self.redraw()

    def settings_changed(self):
        if not self._blocked:
            self.invalidate()

    def mode_changed(self):
        if self._blocked:
            return
        self.viewer.fit_mode = self.fit_mode.currentData()
        self.fit_btn.setText(tr("Gesamte Gesichtsauflage anpassen") if self.viewer.fit_mode == "full_face" else tr("Beide Schläfen automatisch anpassen"))
        self.invalidate()
        self.redraw()

    def region_changed(self):
        if self._blocked:
            return
        self.region_config["strip_mm"] = self.strip_width.value()
        self.region_reviewed.setChecked(False)
        self.viewer.region_config = validate_regions(self.region_config)
        self.invalidate()
        self.redraw()

    def inspect_changed(self, checked):
        self.viewer.inspect_regions = checked
        self.redraw()

    def brush_changed(self, checked):
        self.viewer.protection_brush = checked and self._worker is None
        if checked:
            self.inspect_regions.setChecked(True)

    def add_protection(self, point):
        if self._worker or not self.brush.isChecked():
            return
        if len(self.region_config["protected_spheres"]) >= 1000:
            return
        self.region_config["protected_spheres"].append([*map(float, point), self.brush_radius.value()])
        self.region_changed()

    def undo_protection(self):
        if self.region_config["protected_spheres"]:
            self.region_config["protected_spheres"].pop()
            self.region_changed()

    def drag_gasket(self, delta):
        if self._worker:
            return
        values = self.pose_values()
        values[:3] = (np.array(values[:3]) + delta).tolist()
        self.set_pose(values)

    def redraw(self):
        self.viewer.pose = pose_matrix(self.pose_values())
        self.viewer.region_config = validate_regions(self.region_config)
        if self.gasket:
            self.viewer.set_gasket(self.gasket, pose_matrix(self.pose_values()), self.result, self.compare.currentIndex() == 0)
        else:
            self.viewer.redraw_hmd()

    def rough_pose(self):
        if self.head:
            self.set_pose(initial_pose(self.head))
            self.viewer.fit_view()

    def job(self, function, success, title):
        if self._worker:
            return
        self._success = success
        self._worker = Job(function, self)
        self._worker.succeeded.connect(self.job_success)
        self._worker.failed.connect(self.job_error)
        self._worker.progress.connect(self.job_progress)
        self._worker.finished.connect(self.job_finished)
        self.stack.setEnabled(False)
        self.tabs.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.cancel.setVisible(True)
        self.cancel.setEnabled(True)
        self.activity.setText(title)
        self.refresh()
        self._worker.start()

    @QtCore.Slot(object)
    def job_success(self, result):
        if self._success:
            self._success(result)

    @QtCore.Slot(str)
    def job_error(self, text):
        self.activity.setText(text)
        if not self._closing and text != tr('Vorgang abgebrochen.'):
            W.QMessageBox.warning(self, tr('Vorgang nicht abgeschlossen'), text)

    @QtCore.Slot(int, str)
    def job_progress(self, n, text):
        self.progress.setValue(n)
        self.activity.setText(text)

    def job_finished(self):
        old = self._worker
        self._worker = None
        if old:
            old.deleteLater()
        self.stack.setEnabled(True)
        self.tabs.setEnabled(True)
        self.progress.setVisible(False)
        self.cancel.setVisible(False)
        self.refresh()
        if self._closing:
            self.close()
        self.ready.emit()

    def cancel_job(self):
        if self._worker:
            self._worker.requestInterruption()
            self.cancel.setEnabled(False)
            self.activity.setText(tr('Abbruch angefordert – laufender Geometrieschritt wird beendet …'))

    def load_file(self, head):
        filename, _ = W.QFileDialog.getOpenFileName(self, tr('Kopf-Scan öffnen') if head else tr('Face-Gasket öffnen'), self.last_directory, tr('3D-Modelle (*.stl *.3mf *.obj *.ply)'))
        if filename:
            self.last_directory = str(Path(filename).parent)
            self.load_path(filename, head)

    def load_hmd_file(self):
        filename, _ = W.QFileDialog.getOpenFileName(self, tr("HMD laden und koppeln …"), self.last_directory, "STL (*.stl)")
        if filename:
            self.last_directory = str(Path(filename).parent)
            self.load_hmd_path(filename)

    def load_hmd_path(self, filename):
        self.activity.setText(tr("Die bisherige HMD-Kopplung ist deaktiviert. Eine verlässliche Referenz fehlt noch."))
        return
    def apply_hmd_view(self):
        self.viewer.hmd_preview = None
        self.viewer.set_hmd_visible(False)
        self.show_hmd.setChecked(False)
        self.hmd_info.setText(tr("HMD-Kopplung deaktiviert: Die bisherige Zuordnung war falsch. Alte HMD-Daten bleiben im Projekt, werden aber nicht angezeigt."))
        self.redraw()
        return
    def load_path(self, filename, head, then=None):
        def work(update):
            update(10, tr('Modell lesen …'))
            mesh = load_mesh(filename, head=head)
            update(60, tr('3D-Vorschau vorbereiten …'))
            pre = preview(mesh) if head else None
            return mesh, pre
        def done(data):
            mesh, pre = data
            self.invalidate(True)
            if head:
                self.head_base = self.head = mesh
                self.head_preview = pre
                self.head_rotation = np.eye(3)
                self.scale.blockSignals(True)
                self.scale.setCurrentIndex(0)
                self.scale.blockSignals(False)
                self.update_head_view()
                if self.gasket:
                    self.rough_pose()
            else:
                self.gasket = mesh
                self.region_config = validate_regions()
                self._blocked = True
                self.strip_width.setValue(self.region_config["strip_mm"])
                self._blocked = False
                self.region_reviewed.setChecked(False)
                valid = supported(mesh)
                self.gasket_info.setText(tr("{v0}\n{v1:,} Dreiecke\n", v0=mesh.name, v1=len(mesh.faces)) + (tr('✓ PFDMR-V2-Profil erkannt. Aufnahme geschützt.') if valid else tr('Dieses Gasket wird vom PFDMR-V2-Profil nicht unterstützt. Automatische Anpassung gesperrt.')))
                if self.head:
                    self.rough_pose()
                else:
                    self.set_pose([0, 0, 0, 0, 0, 0])
            self.redraw()
            self.viewer.fit_view()
            self.activity.setText(tr('Modell geladen.') + (" " + mesh.note if mesh.note else ""))
            if then:
                QtCore.QTimer.singleShot(100, lambda: self._defer_until_idle(then))
        self.job(work, done, tr('Modell wird geladen …'))

    def _defer_until_idle(self, callback):
        if self._worker:
            QtCore.QTimer.singleShot(100, lambda: self._defer_until_idle(callback))
        else:
            callback()

    def update_head_view(self):
        if not self.head_base:
            return
        scale = self.scale.currentData()
        center = self.head_base.bounds.mean(0)
        def mapping(v):
            return ((v - center) @ self.head_rotation.T + center) * scale
        self.head = Mesh(mapping(self.head_base.vertices), self.head_base.faces, self.head_base.name, self.head_base.source, self.head_base.note)
        v, f = self.head_preview
        self.viewer.set_head(mapping(v), f)
        sizes = np.ptp(self.head.vertices, axis=0)
        self.head_info.setText(tr('{v0}\nMaße X / Y / Z: {v1:.1f} / {v2:.1f} / {v3:.1f} mm\n{v4:,} Dreiecke', v0=self.head.name, v1=sizes[0], v2=sizes[1], v3=sizes[2], v4=len(self.head.faces)))

    def change_head(self):
        if self.head_base:
            self.invalidate(True)
            self.update_head_view()
            if self.gasket:
                self.rough_pose()
            self.viewer.fit_view()

    def rotate_head(self, axis):
        values = [0, 0, 0, 0, 0, 0]
        values[3 + axis] = 90
        self.head_rotation = pose_matrix(values)[:3, :3] @ self.head_rotation
        self.change_head()

    def reset_head(self):
        self.head_rotation = np.eye(3)
        self.scale.setCurrentIndex(0)
        self.change_head()

    def start_fit(self):
        if not self.gasket or not self.head or not self.aligned.isChecked() or not self.region_reviewed.isChecked():
            return
        self.brush.setChecked(False)
        self.inspect_regions.setChecked(False)
        revision = self.revision
        gasket, head, pose, pad = self.gasket, self.head, pose_matrix(self.pose_values()), self.pad.value()
        def done(result):
            if revision != self.revision:
                self.activity.setText(tr('Die Einstellungen haben sich geändert. Bitte neu berechnen.'))
                return
            self.result = result
            self.display_result()
            self.tabs.setTabEnabled(3, True)
            self.tabs.setCurrentIndex(3)
            self.activity.setText(tr('Anpassung fertig. Die geschützte Aufnahme ist unverändert.'))
        config = validate_regions(self.region_config)
        self.job(lambda update: fit_full_face(gasket, head, pose, pad, update, region_config=config), done, tr('Gesichtsauflage wird angepasst …'))

    def display_result(self, reset_compare=True):
        if not self.result:
            return
        r = self.result.report
        if r.get("mode") == "full_face":
            lo, hi = r["minimum_gap_mm"], r["maximum_gap_mm"]
            self.result_info.setText(tr("✓ Stirn, Wangen, Nase und Schläfen angepasst\n✓ Aufnahme unverändert\n✓ Netz geschlossen\n\nPolster: {v0:.1f} mm\nGeprüfte Auflage: {v1:.2f}–{v2:.2f} mm Abstand", v0=r["pad_mm"], v1=lo, v2=hi))
            text = "<b>" + html.escape(tr("Prüfung der gesamten Gesichtsauflage")) + "</b>"
            for key, title in (("forehead", "Stirn"), ("cheeks", "Wangen"), ("nose", "Nase"), ("temples", "Schläfen")):
                region = r["regions"][key]
                if not region["sample_count"]:
                    line = tr("{v0}: geschützt, unverändert", v0=tr(title))
                else:
                    line = tr("{v0}: {v1} Prüfpunkte · {v2:.2f}–{v3:.2f} mm Abstand", v0=tr(title), v1=region["sample_count"], v2=region["minimum_gap_mm"], v3=region["maximum_gap_mm"])
                text += "<p>" + html.escape(line) + "</p>"
            for line in (tr("Der feste Aufnahmebereich entspricht exakt der unveränderten V2. Der Export enthält nur das Gasket."),
                         tr("Vorhandene V2-Geometrie von Sir Dominik: Öffnungen und Aussparungen werden nicht aufgefüllt. Lange bewegliche Dreiecke werden vor der Anpassung unterteilt."),
                         tr("Die Prüfung erfasst die abgetastete Auflagekante rund um das Gesicht. Keine vollständige Prüfung aller Selbstüberschneidungen oder Wandstärken. Probedruck erforderlich.")):
                text += "<p>" + html.escape(line) + "</p>"
            self.details.setHtml(text)
            if reset_compare:
                self.compare.setCurrentIndex(0)
            self.redraw()
            return
        a, b = r["sides"]["links"], r["sides"]["rechts"]
        lo, hi = min(a["minimum_gap_mm"], b["minimum_gap_mm"]), max(a["maximum_gap_mm"], b["maximum_gap_mm"])
        self.result_info.setText(tr('✓ Beide Schläfen angepasst\n✓ Aufnahme unverändert\n✓ Netz geschlossen\n\nPolster: {v0:.1f} mm\nGeprüfte Auflagepunkte: {v1:.2f}–{v2:.2f} mm Abstand', v0=r['pad_mm'], v1=lo, v2=hi))
        scope = tr('Polsterabstand an der abgetasteten zentralen Schläfen-Auflagekante. Die übrigen Bereiche laufen weich zum Original aus.')
        text = (tr('<b>Prüfung der Schläfenauflage</b><p>Seite −X: maximal {v0:.2f} mm Änderung; Abstand {v1:.2f}–{v2:.2f} mm.</p><p>Seite +X: maximal {v3:.2f} mm Änderung; Abstand {v4:.2f}–{v5:.2f} mm.</p><p>{v6}</p><p>Die geschützten Koordinaten entsprechen exakt dem geladenen Original.</p><p><b>Grenzen dieser ersten Version</b><br>Keine vollständige Prüfung sämtlicher Selbstüberschneidungen oder Wandstärken. Trageposition und Polsterkompression durch Anprobe prüfen.</p>', v0=a['maximum_change_mm'], v1=a['minimum_gap_mm'], v2=a['maximum_gap_mm'], v3=b['maximum_change_mm'], v4=b['minimum_gap_mm'], v5=b['maximum_gap_mm'], v6=html.escape(scope)))
        self.details.setHtml(text)
        if reset_compare:
            self.compare.setCurrentIndex(0)
        self.redraw()

    def export_result(self):
        if not self.result:
            return
        filename, selected = W.QFileDialog.getSaveFileName(self, tr('Angepasstes Gasket exportieren'), str(Path(self.last_directory) / "PFDMR_Scanfit.stl"), "STL (*.stl);;3MF (*.3mf)")
        if not filename:
            return
        if not Path(filename).suffix:
            filename += ".3mf" if selected.startswith("3MF") else ".stl"
        result, with_report = self.result, self.with_report.isChecked()
        # Never overwrite imported source assets through export.
        for mesh in (self.gasket, self.head_base, self.hmd):
            if mesh is not None and mesh.source and Path(filename).resolve() == Path(mesh.source).resolve():
                W.QMessageBox.warning(self, tr('Originaldatei erhalten'), tr('Bitte einen neuen Dateinamen wählen. Das geladene Original bleibt erhalten.'))
                return
        def work(update):
            update(20, tr('Angepasstes Gasket exportieren …'))
            export_mesh(filename, result.mesh)
            if with_report:
                Path(filename).with_suffix(".pruefung.json").write_text(json.dumps(result.report, indent=2, ensure_ascii=False), encoding="utf-8")
            return filename
        self.job(work, lambda path: self.activity.setText(tr('Export gespeichert: {v0}', v0=path)), tr('Export vorbereiten …'))

    def save_project(self):
        if not self.gasket or not self.head:
            return
        filename, _ = W.QFileDialog.getSaveFileName(self, tr('Lokales Projekt speichern'), str(Path(self.last_directory) / "Meine_Anpassung.gasketfit"), tr('GasketFit-Projekt (*.gasketfit)'))
        if filename:
            if not filename.lower().endswith(".gasketfit"):
                filename += ".gasketfit"
            gasket, head, pose, pad, result = self.gasket, self.head, self.pose_values(), self.pad.value(), self.result
            extras = dict(hmd=self.hmd, hmd_to_frame=self.hmd_docking, fit_mode=self.fit_mode.currentData(),
                          hmd_opacity=self.hmd_opacity.value() / 100., hmd_visible=False,
                          region_config=validate_regions(self.region_config))
            self.job(lambda update: save_project(filename, gasket, head, pose, pad, result, **extras),
                     lambda _: self.activity.setText(tr('Lokales Projekt mit beiden Modellen gespeichert.')), tr('Projekt speichern …'))

    def open_project(self):
        filename, _ = W.QFileDialog.getOpenFileName(self, tr('Projekt öffnen'), self.last_directory, tr('GasketFit-Projekt (*.gasketfit)'))
        if filename:
            self.load_project_path(filename)

    def load_project_path(self, filename):
        self.last_directory = str(Path(filename).resolve().parent)
        def work(update):
            data = load_project(filename, with_extras=True)
            update(50, tr('Vorschau vorbereiten …'))
            return data, preview(data[1]), None
        def done(payload):
            (g, h, values, pad, result, extras), pre, hmd_pre = payload
            if result is not None and result.report.get("profile") != FULL_PROFILE["profile"]:
                result = None
                extras["cached_result_discarded"] = True
            self.gasket = g
            self.head_base = self.head = h
            self.head_preview = pre
            self.head_rotation = np.eye(3)
            self.scale.blockSignals(True)
            self.scale.setCurrentIndex(0)
            self.scale.blockSignals(False)
            self.set_pose(values)
            self._blocked = True
            self.pad.setValue(pad)
            mode = "full_face"
            self.fit_mode.setCurrentIndex(max(0, self.fit_mode.findData(mode)))
            self.viewer.fit_mode = mode
            self.region_config = validate_regions(extras["region_config"])
            self.strip_width.setValue(self.region_config["strip_mm"])
            self.region_reviewed.setChecked(False)
            self.fit_btn.setText(tr("Gesamte Gesichtsauflage anpassen") if mode == "full_face" else tr("Beide Schläfen automatisch anpassen"))
            self.hmd = extras["hmd"]
            self.hmd_preview = hmd_pre
            self.hmd_docking = extras["hmd_to_frame"]
            self.show_hmd.setChecked(False)
            self.hmd_opacity.setValue(round(extras["hmd_opacity"] * 100))
            self._blocked = False
            self.result = result
            if result and not supported(g):
                self.result = None
            self.gasket_info.setText(g.name + (tr('\n✓ PFDMR-V2-Profil erkannt.') if supported(g) else tr('\nProfil nicht unterstützt.')))
            self.update_head_view()
            self.apply_hmd_view()
            self.aligned.setChecked(result is not None)
            self.display_result()
            self.redraw()
            self.viewer.fit_view()
            self.tabs.setTabEnabled(1, True)
            self.tabs.setTabEnabled(3, self.result is not None)
            self.tabs.setCurrentIndex(3 if self.result else 1)
            self.activity.setText(tr("Altes Ergebnis verworfen. Modelle und Ausrichtung sind erhalten. Bitte Schutzbereiche prüfen und neu berechnen.") if extras.get("cached_result_discarded") else tr('Lokales Projekt geladen.'))
        self.job(work, done, tr('Projekt öffnen …'))

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._closing = True
            self.cancel_job()
            event.ignore()
        elif self.online.busy():
            self.online.timer.stop()
            QtCore.QTimer.singleShot(200, self.close)
            event.ignore()
        else:
            event.accept()
