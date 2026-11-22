import sys
from PySide6 import QtCore,QtWidgets as W
from .navigation import controls,save_controls,DEFAULTS,manager
from .localization import tr


class NavigationPage(W.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        layout=W.QVBoxLayout(self)
        layout.addWidget(W.QLabel(tr('Maus und SpaceMouse')))
        self.presets=W.QComboBox()
        for text,value in ((tr('Eigene Belegung'),'custom'),('Windows 3D Builder','builder'),('GasketFit 0.7','original')):
            self.presets.addItem(text,value)
        form=W.QFormLayout()
        form.addRow(tr('Vorlage'),self.presets)
        self.rotate=W.QComboBox();self.pan=W.QComboBox()
        for combo in (self.rotate,self.pan):
            for text,key in ((tr('Linke Maustaste'),'left'),(tr('Mittlere Maustaste'),'middle'),(tr('Rechte Maustaste'),'right')):
                combo.addItem(text,key)
        form.addRow(tr('Ansicht drehen'),self.rotate)
        form.addRow(tr('Ansicht verschieben'),self.pan)
        layout.addLayout(form)
        self.wheel=W.QCheckBox(tr('Zoomrichtung des Mausrads umkehren'))
        layout.addWidget(self.wheel)
        hint=W.QLabel(tr('Alt + linke Maustaste positioniert weiterhin das Modell. Die Belegung gilt nur für die Ansicht und wird lokal gespeichert.'))
        hint.setWordWrap(True);layout.addWidget(hint)
        self.enabled=W.QCheckBox(tr('SpaceMouse aktivieren'))
        self.translation=W.QCheckBox(tr('SpaceMouse: Verschieben und Zoomen'))
        self.rotation=W.QCheckBox(tr('SpaceMouse: Drehen inklusive Rollen'))
        for widget in (self.enabled,self.translation,self.rotation):layout.addWidget(widget)
        form=W.QFormLayout()
        self.translation_gain=W.QDoubleSpinBox();self.rotation_gain=W.QDoubleSpinBox()
        for spin in (self.translation_gain,self.rotation_gain):spin.setRange(.1,5);spin.setSingleStep(.1);spin.setDecimals(1)
        form.addRow(tr('Empfindlichkeit Bewegung'),self.translation_gain)
        form.addRow(tr('Empfindlichkeit Drehung'),self.rotation_gain)
        layout.addLayout(form)
        layout.addWidget(W.QLabel(tr('SpaceMouse-Achsen einzeln umkehren:')))
        row=W.QHBoxLayout();self.invert=[]
        for name in ('X','Y / Zoom','Z','RX','RY','RZ'):
            box=W.QCheckBox(name);row.addWidget(box);self.invert.append(box)
        layout.addLayout(row)
        self.status=W.QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        driver=W.QPushButton(tr('3DxWare-Profil für GasketFit einrichten'))
        driver.setVisible(sys.platform == "win32")
        driver.clicked.connect(self.setup_driver)
        layout.addWidget(driver)
        reset=W.QPushButton(tr('Standardbelegung wiederherstellen'))
        reset.clicked.connect(lambda:self.apply(DEFAULTS.copy()))
        layout.addWidget(reset);layout.addStretch()
        self.load()
        self.presets.currentIndexChanged.connect(self.preset)
        for widget in (self.rotate,self.pan):widget.currentIndexChanged.connect(self.save)
        for widget in (self.wheel,self.enabled,self.translation,self.rotation,*self.invert):widget.toggled.connect(self.save)
        self.translation_gain.valueChanged.connect(self.save);self.rotation_gain.valueChanged.connect(self.save)
        self.timer=QtCore.QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.update_status);self.timer.start()
        self.update_status()

    def load(self):
        p=controls()
        widgets=(self.presets,self.rotate,self.pan,self.wheel,self.enabled,self.translation,self.rotation,
                 self.translation_gain,self.rotation_gain,*self.invert)
        blockers=[QtCore.QSignalBlocker(w) for w in widgets]
        self.rotate.setCurrentIndex(self.rotate.findData(p['rotate_button']))
        self.pan.setCurrentIndex(self.pan.findData(p['pan_button']))
        for widget,key in ((self.wheel,'invert_wheel'),(self.enabled,'space_enabled'),(self.translation,'space_pan'),(self.rotation,'space_rotate')):
            widget.setChecked(p[key])
        self.translation_gain.setValue(p['space_translation_gain']);self.rotation_gain.setValue(p['space_rotation_gain'])
        for box,value in zip(self.invert,p['space_invert']):box.setChecked(value)
        profile='builder' if (p['rotate_button'],p['pan_button'])==('left','right') else 'original' if (p['rotate_button'],p['pan_button'])==('left','middle') else 'custom'
        self.presets.setCurrentIndex(self.presets.findData(profile))
        self.update_status()

    def apply(self,p):
        save_controls(p);self.load()

    def preset(self,*_):
        name=self.presets.currentData()
        if name in ('builder','original'):
            p=controls();p.update(rotate_button='left',pan_button='right' if name=='builder' else 'middle');self.apply(p)

    def save(self,*_):
        p=controls()
        r,b=self.rotate.currentData(),self.pan.currentData()
        if r==b:
            if self.sender() is self.rotate:b=p['rotate_button']
            else:r=p['pan_button']
        p.update(rotate_button=r,pan_button=b,invert_wheel=self.wheel.isChecked(),space_enabled=self.enabled.isChecked(),
                 space_pan=self.translation.isChecked(),space_rotate=self.rotation.isChecked(),
                 space_translation_gain=self.translation_gain.value(),space_rotation_gain=self.rotation_gain.value(),
                 space_invert=[box.isChecked() for box in self.invert])
        self.apply(p)

    def update_status(self):
        if sys.platform != "win32":
            widgets = (self.enabled, self.translation, self.rotation,
                       self.translation_gain, self.rotation_gain, *self.invert)
            for widget in widgets:
                widget.setEnabled(False)
            for widget in (self.enabled, self.translation, self.rotation, *self.invert):
                blocker = QtCore.QSignalBlocker(widget)
                widget.setChecked(False)
                del blocker
            self.status.setText(tr("SpaceMouse-Unterstützung ist auf diesem System noch nicht verfügbar. Maussteuerung ist verfügbar."))
            return
        m=manager()
        if m.error:self.status.setText(tr('SpaceMouse-Anbindung nicht verfügbar: {v0}',v0=m.error))
        elif not m.devices:self.status.setText(tr('Keine SpaceMouse erkannt. Anschließen und dieses Fenster erneut prüfen.'))
        else:self.status.setText(tr('SpaceMouse erkannt · Eingabepakete: {v0}\nAchsen: {v1}',v0=m.packets,v1=' / '.join(str(int(v)) for v in m.axes)))

    def setup_driver(self):
        from .driver_profile import configure_profile
        try:
            path,backup=configure_profile()
            W.QMessageBox.information(self,tr('Tastenbelegung'),tr('GasketFit-Treiberprofil ist eingerichtet. Eigene Achseneinstellungen bleiben erhalten. Bitte GasketFit erneut aktivieren.'))
        except (OSError,ValueError) as exc:
            W.QMessageBox.warning(self,tr('Tastenbelegung'),str(exc))
