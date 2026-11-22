from __future__ import annotations
import json
import logging
from pathlib import Path
import platform
import sys
from PySide6 import QtCore, QtGui, QtWidgets as W
from . import __version__
from .localization import current, tr, read_catalog, atomic_json, REPOSITORY
from . import online


class NetworkJob(QtCore.QThread):
    success = QtCore.Signal(object)
    failure = QtCore.Signal(str)

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.success.emit(self.function())
        except Exception as exc:
            logging.exception("GitHub request failed")
            self.failure.emit(str(exc))


class OnlineController(QtCore.QObject):
    languages_changed = QtCore.Signal()
    update_changed = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.languages = []
        self.release = None
        self.language_status = "Noch nicht geprüft."
        self.update_status = "Noch nicht geprüft."
        self.jobs = {}
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(6 * 60 * 60 * 1000)
        self.timer.timeout.connect(self.automatic)
        self.timer.start()
        QtCore.QTimer.singleShot(1500, self.automatic)

    def automatic(self):
        settings = current().settings
        if settings["auto_languages"]:
            self.check_languages()
        if settings["auto_updates"]:
            self.check_updates()

    def run(self, key, function, success, failure):
        if key in self.jobs:
            return False
        job = NetworkJob(function, self)
        self.jobs[key] = job
        job.success.connect(success)
        job.failure.connect(failure)
        def finished():
            self.jobs.pop(key, None)
            job.deleteLater()
        job.finished.connect(finished)
        job.start()
        return True

    def check_languages(self):
        if "languages" in self.jobs:
            return
        self.language_status = "Suche läuft …"
        self.languages_changed.emit()
        def done(data):
            self.languages = data
            self.language_status = "" if data else "Keine Sprachdateien veröffentlicht. Lokale Dateien funktionieren bereits."
            self.languages_changed.emit()
        def failed(_):
            self.language_status = "Keine Verbindung zu GitHub. Lokale Funktionen bleiben verfügbar."
            self.languages_changed.emit()
        self.run("languages", online.language_inventory, done, failed)

    def check_updates(self):
        if "updates" in self.jobs:
            return
        self.update_status = "Suche läuft …"
        self.update_changed.emit()
        def done(data):
            self.release = data
            self.update_status = {"unpublished": "Noch keine Releases veröffentlicht.", "current": "Diese Version ist aktuell.", "new": ""}[data["state"]]
            self.update_changed.emit()
        def failed(_):
            self.update_status = "Keine Verbindung zu GitHub. Lokale Funktionen bleiben verfügbar."
            self.update_changed.emit()
        self.run("updates", online.check_update, done, failed)

    def busy(self):
        return any(job.isRunning() for job in self.jobs.values())


class SettingsDialog(W.QDialog):
    def __init__(self, parent, section="language"):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(660, 590)
        self.localizer = current()
        self.controller = parent.online
        self.root_layout = W.QVBoxLayout(self)
        self.pages = W.QStackedWidget()
        self.root_layout.addWidget(self.pages)
        language_page = W.QWidget()
        self.pages.addWidget(language_page)
        self.layout = W.QVBoxLayout(language_page)
        self.layout.setSpacing(12)
        self.language = W.QComboBox()
        self.layout.addWidget(W.QLabel(tr("Sprache")))
        self.layout.addWidget(self.language)
        apply = W.QPushButton(tr("Sprache anwenden"))
        apply.clicked.connect(lambda: self.localizer.set_language(self.language.currentData()))
        self.layout.addWidget(apply)
        row = W.QHBoxLayout()
        for text, callback in (("Sprachdatei importieren …", self.import_file), ("Sprache löschen", self.delete_language), ("Sprachordner öffnen", self.open_folder)):
            b = W.QPushButton(tr(text))
            b.clicked.connect(callback)
            row.addWidget(b)
        self.layout.addLayout(row)
        self.hint = W.QLabel(tr("Dateien im lang-Ordner werden automatisch erkannt. Fehlende Übersetzungen verwenden Englisch."))
        self.hint.setWordWrap(True)
        self.layout.addWidget(self.hint)
        self.local_status = W.QLabel()
        self.local_status.setWordWrap(True)
        self.layout.addWidget(self.local_status)
        self.auto_languages = W.QCheckBox(tr("Automatisch nach neuen Sprachen suchen"))
        self.auto_languages.setChecked(self.localizer.settings["auto_languages"])
        self.auto_languages.toggled.connect(lambda value: self.setting("auto_languages", value))
        self.layout.addWidget(self.auto_languages)
        row = W.QHBoxLayout()
        self.remote = W.QComboBox()
        row.addWidget(self.remote, 1)
        self.download = W.QPushButton(tr("Herunterladen / aktualisieren"))
        self.download.clicked.connect(self.download_language)
        row.addWidget(self.download)
        self.layout.addLayout(row)
        check = W.QPushButton(tr("Sprachen auf GitHub suchen"))
        check.clicked.connect(self.controller.check_languages)
        self.layout.addWidget(check)
        self.language_status = W.QLabel()
        self.language_status.setWordWrap(True)
        self.layout.addWidget(self.language_status)
        self.layout.addStretch()
        updates_page = W.QWidget()
        self.pages.addWidget(updates_page)
        self.layout = W.QVBoxLayout(updates_page)
        self.layout.setSpacing(12)
        channel = W.QLabel(tr("Beta-Kanal: Es werden auch neue Beta-Versionen angeboten."))
        channel.setWordWrap(True)
        self.layout.addWidget(channel)
        self.auto_updates = W.QCheckBox(tr("Automatisch nach App-Updates suchen"))
        self.auto_updates.setChecked(self.localizer.settings["auto_updates"])
        self.auto_updates.toggled.connect(lambda value: self.setting("auto_updates", value))
        self.layout.addWidget(self.auto_updates)
        check = W.QPushButton(tr("Jetzt nach Updates suchen"))
        check.clicked.connect(self.controller.check_updates)
        self.layout.addWidget(check)
        self.update_status = W.QLabel()
        self.update_status.setWordWrap(True)
        self.layout.addWidget(self.update_status)
        self.install = W.QPushButton(tr("Update herunterladen & installieren"))
        self.install.clicked.connect(self.install_update)
        self.layout.addWidget(self.install)
        hint = W.QLabel(tr("Updates werden erst nach Bestätigung heruntergeladen und installiert."))
        hint.setWordWrap(True)
        self.layout.addWidget(hint)
        self.layout.addStretch()
        close = W.QPushButton(tr("Schließen"))
        from .navigation_ui import NavigationPage
        self.navigation_page = NavigationPage(self)
        navigation_scroll = W.QScrollArea()
        navigation_scroll.setWidgetResizable(True)
        navigation_scroll.setWidget(self.navigation_page)
        self.pages.addWidget(navigation_scroll)
        close.clicked.connect(self.accept)
        self.root_layout.addWidget(close)
        self.set_section(section)
        self.localizer.inventory_changed.connect(self.populate)
        self.localizer.changed.connect(self.language_changed)
        self.controller.languages_changed.connect(self.remote_changed)
        self.controller.update_changed.connect(self.update_changed)
        self.populate()
        self.remote_changed()
        self.update_changed()

    def set_section(self, section):
        self.section = section
        self.pages.setCurrentIndex({'language':0,'updates':1,'controls':2}.get(section,0))
        self.setWindowTitle(tr("Einstellungen") + " - " + ({'updates':tr('Aktualisierungen'),'controls':tr('Tastenbelegung')}.get(section,tr('Sprache'))))

    def setting(self, key, value):
        self.localizer.settings[key] = value
        self.localizer.save_settings()

    def populate(self):
        selected = self.language.currentData() or self.localizer.language
        if selected not in self.localizer.catalogs:
            selected = self.localizer.language
        self.language.clear()
        for code, data in sorted(self.localizer.catalogs.items()):
            self.language.addItem(f"{data['name']} ({code})", code)
        self.language.setCurrentIndex(max(0, self.language.findData(selected)))
        self.local_status.setText(tr("Ungültige lokale Sprachdateien: {v0}", v0="; ".join(self.localizer.invalid)) if self.localizer.invalid else tr("Deutsch, Englisch und Französisch sind fest integriert."))

    def language_changed(self, *_):
        self.localizer.retranslate(self)
        self.set_section(self.section)
        self.populate()
        self.remote_changed()
        self.update_changed()

    def import_file(self):
        filename, _ = W.QFileDialog.getOpenFileName(self, tr("Sprachdatei auswählen"), str(self.localizer.directory), "JSON (*.json)")
        if not filename:
            return
        try:
            data = read_catalog(Path(filename))
            atomic_json(self.localizer.directory / (data["code"] + ".json"), data)
            self.localizer.scan()
            self.local_status.setText(tr("Sprachdatei wurde gespeichert."))
        except (ValueError, OSError, TypeError) as exc:
            W.QMessageBox.warning(self, tr("Einstellungen"), tr("Ungültige Sprachdatei: {v0}", v0=str(exc)))

    def delete_language(self):
        code = self.language.currentData()
        if code in ("en", "de", "fr"):
            self.local_status.setText(tr("Grundsprachen können nicht gelöscht werden."))
            return
        path = self.localizer.paths.get(code)
        if path:
            path.unlink()
            self.localizer.scan()
            self.localizer.save_settings()
            self.local_status.setText(tr("Sprache wurde gelöscht."))

    def open_folder(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.localizer.directory)))

    def remote_changed(self):
        self.remote.clear()
        for item in self.controller.languages:
            self.remote.addItem(item["name"], item)
        self.download.setEnabled(self.remote.count() > 0 and "download_language" not in self.controller.jobs)
        self.language_status.setText(tr(self.controller.language_status) if self.controller.language_status else tr("Sprachdateien auf GitHub: {v0}", v0=len(self.controller.languages)))

    def download_language(self):
        item = self.remote.currentData()
        if not item:
            return
        self.download.setEnabled(False)
        def done(_):
            self.localizer.scan()
            self.language_status.setText(tr("Sprachdatei wurde gespeichert."))
            self.download.setEnabled(True)
        def failed(_):
            self.language_status.setText(tr("Keine Verbindung zu GitHub. Lokale Funktionen bleiben verfügbar."))
            self.download.setEnabled(True)
        self.controller.run("download_language", lambda: online.download_language(item, self.localizer.directory), done, failed)

    def update_changed(self):
        release = self.controller.release or {}
        text = tr(self.controller.update_status) if self.controller.update_status else tr("Neue Version: {v0}", v0=release.get("version", ""))
        from .platform_support import supports_in_app_update
        self.install.setText(tr("Update herunterladen & installieren") if supports_in_app_update() else tr("Download öffnen"))
        installable = supports_in_app_update() and release.get("state") == "new" and release.get("package") and release.get("checksums")
        if release.get("state") == "new" and not installable:
            text += "\n" + (tr("Neue Version bitte als Paket herunterladen und installieren.") if not supports_in_app_update() else tr("Update ohne Prüfsumme oder Windows-Paket. Noch nicht installierbar."))
        self.update_status.setText(text)
        self.install.setEnabled((bool(installable) and getattr(sys, "frozen", False) or (not supports_in_app_update() and release.get('state') == 'new' and bool(release.get('package')))) and "install" not in self.controller.jobs)

    def install_update(self):
        from .platform_support import supports_in_app_update, installation_folder
        if not supports_in_app_update():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl('https://github.com/'+REPOSITORY+'/releases'))
            return
        if self.parent()._worker:
            W.QMessageBox.information(self, tr("Einstellungen"), tr("Bitte zuerst den laufenden Vorgang beenden."))
            return
        if W.QMessageBox.question(self, tr("Update installieren"), tr("Update herunterladen & installieren") + "?") != W.QMessageBox.StandardButton.Yes:
            return
        self.install.setEnabled(False)
        self.update_status.setText(tr("Update wird vorbereitet …"))
        def done(stage):
            if self.parent()._worker:
                self.update_status.setText(tr("Bitte zuerst den laufenden Vorgang beenden."))
                self.install.setEnabled(True)
                return
            if W.QMessageBox.question(self, tr("Update installieren"), tr("Update bereit. App jetzt schließen und aktualisieren?") + "\n\n" + tr("Ungespeicherte Änderungen gehen verloren. Bitte das Projekt vorher speichern.")) == W.QMessageBox.StandardButton.Yes:
                online.install_update(stage, installation_folder())
                self.accept()
                self.parent().close()
            else:
                self.update_changed()
        def failed(error):
            self.update_status.setText(tr("Update konnte nicht vorbereitet werden: {v0}", v0=error))
            self.install.setEnabled(True)
        self.controller.run("install", lambda: online.prepare_update(self.controller.release, installation_folder()), done, failed)

    def closeEvent(self, event):
        # Controller outlives the popup, so active requests finish safely.
        event.accept()


def build_info(parent):
    dialog = W.QDialog(parent)
    dialog.setWindowTitle(tr("Build-Informationen"))
    dialog.resize(560, 350)
    layout = W.QVBoxLayout(dialog)
    build = json.loads((Path(__file__).parent / "build_info.json").read_text(encoding="utf-8"))
    for text in (tr("Version: {v0}", v0=__version__), tr("Build: {v0}", v0=build["built_utc"]),
                 tr("Plattform: {v0}", v0=platform.platform()), tr("GasketFit Beta · Individuelle Gaskets für PFDMR"),
                 tr("Geschlossene und offene Gaskets mit eigener Magnetbasis."),
                 tr("Kopfmodelle und Projekte werden ausschließlich lokal verarbeitet."),
                 tr("Quelle: {v0}", v0="https://github.com/" + REPOSITORY)):
        label = W.QLabel(text)
        label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
    close = W.QPushButton(tr("Schließen"))
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    dialog.exec()
