"""Editable JSON catalogues. Language files are data, never executable code."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import string
import sys
from PySide6 import QtCore, QtGui, QtWidgets as W

REPOSITORY = "urscaviezel/GasketFit"


def app_folder():
    from .platform_support import data_folder
    return data_folder()


def validate_catalog(data):
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Invalid language file schema")
    code = data.get("code", "")
    if not isinstance(code, str) or not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?", code):
        raise ValueError("Invalid language code")
    if not isinstance(data.get("name"), str) or not 1 <= len(data["name"]) <= 80:
        raise ValueError("Invalid language name")
    messages = data.get("messages")
    if not isinstance(messages, dict) or len(messages) > 3000:
        raise ValueError("Invalid language messages")
    for key, value in messages.items():
        if not isinstance(key, str) or not isinstance(value, str) or len(key) > 8000 or len(value) > 16000:
            raise ValueError("Invalid translation")
        # No attribute/index lookups or arbitrary format fields in downloaded files.
        source = {field for _, field, _, _ in string.Formatter().parse(key) if field is not None}
        target = {field for _, field, _, _ in string.Formatter().parse(value) if field is not None}
        if source != target or any(not re.fullmatch(r"v[0-9]+", field) for field in source):
            raise ValueError("Translation placeholders do not match")
        if any(c in value.lower() for c in ("<script", "<img", "<iframe", "href=", "src=")):
            raise ValueError("External content is not allowed in language files")
    return data


def read_catalog(path):
    if path.stat().st_size > 1_000_000:
        raise ValueError("Language file exceeds 1 MB")
    return validate_catalog(json.loads(path.read_text(encoding="utf-8-sig")))


def atomic_json(path, data):
    temp = path.with_suffix(path.suffix + ".new")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


class Localizer(QtCore.QObject):
    changed = QtCore.Signal(str, str)
    navigation_changed = QtCore.Signal()
    inventory_changed = QtCore.Signal()

    def __init__(self, root=None):
        super().__init__()
        self.root = Path(root) if root else app_folder()
        self.directory = self.root / "lang"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.root / "settings.json"
        self.settings = {"language": QtCore.QLocale.system().name().split("_")[0] if QtCore.QLocale.system().name().split("_")[0] in ("de", "en", "fr") else "en",
                         "auto_updates": True, "auto_languages": True, "navigation": {}}
        if self.settings_path.exists():
            try:
                saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
                self.settings.update({k: v for k, v in saved.items() if k in self.settings and isinstance(v, type(self.settings[k]))})
            except (ValueError, OSError):
                pass
        self.catalogs = {}
        self.paths = {}
        self.invalid = []
        self.language = self.settings["language"]
        self.scan()
        self.watcher = QtCore.QFileSystemWatcher([str(self.directory)], self)
        self.watcher.directoryChanged.connect(self.scan)
        self.watcher.fileChanged.connect(self.scan)
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(3000)
        self.poll.timeout.connect(self.scan)
        if QtCore.QCoreApplication.instance():
            self.poll.start()

    def save_settings(self):
        self.settings["language"] = self.language
        atomic_json(self.settings_path, self.settings)

    def scan(self, *_):
        old_catalog = self.effective_messages(self.language)
        old_signature = getattr(self, "_signature", None)
        signature = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(self.directory.glob("*.json")) if p.exists())
        if signature == old_signature:
            return
        self._signature = signature
        self.catalogs, self.paths, self.invalid = {}, {}, []
        # Built-ins remain available even if their editable copies are deleted.
        for path in (Path(__file__).parent / "lang").glob("*.json"):
            data = read_catalog(path)
            self.catalogs[data["code"]] = data
        for path in sorted(self.directory.glob("*.json")):
            try:
                data = read_catalog(path)
                if data["code"] in self.paths:
                    raise ValueError("Duplicate language code")
                builtin = self.catalogs.get(data["code"], {})
                data = {**data, "messages": {**builtin.get("messages", {}), **data["messages"]}}
                self.catalogs[data["code"]] = data
                self.paths[data["code"]] = path
            except (ValueError, OSError, TypeError) as exc:
                self.invalid.append(f"{path.name}: {exc}")
        if self.language not in self.catalogs:
            self.language = "en"
        # Keep old dictionary for translating already displayed text on live reload.
        self.previous_messages = old_catalog
        self.inventory_changed.emit()
        self.changed.emit(self.language, self.language)
        if hasattr(self, "watcher"):
            files = self.watcher.files()
            if files:
                self.watcher.removePaths(files)
            self.watcher.addPaths([str(p) for p in self.paths.values()])

    def set_language(self, code):
        if code not in self.catalogs:
            return
        old = self.language
        self.previous_messages = self.effective_messages(old)
        self.language = code
        self.save_settings()
        self.changed.emit(old, code)

    def effective_messages(self, code):
        english = self.catalogs.get("en", {}).get("messages", {})
        result = {key: key for key in english} if code == "de" else dict(english)
        result.update(self.catalogs.get(code, {}).get("messages", {}))
        return result

    def translate(self, source, **values):
        fallback = self.catalogs.get("en", {}).get("messages", {})
        catalogue = self.catalogs.get(self.language, {}).get("messages", {})
        text = catalogue.get(source, source if self.language == "de" else fallback.get(source, source))
        return text.format(**values) if values else text

    def source_text(self, text):
        # Used when retaining static labels across workflow changes. Keep the
        # source key, never a translation captured at window construction.
        if text in self.catalogs.get('en', {}).get('messages', {}):
            return text
        for catalog in self.catalogs.values():
            for key, value in catalog.get('messages', {}).items():
                if value == text:
                    return key
        return text

    def translate_existing(self, text):
        """Recover source templates from current UI text; do not rebuild UI state."""
        if text in self.catalogs.get("en", {}).get("messages", {}):
            return self.translate(text)
        previous = getattr(self, "previous_messages", {})
        keys = set(self.catalogs.get("en", {}).get("messages", {})) | set(previous)
        for key in keys:
            rendered = previous.get(key, key)
            if text == rendered:
                return self.translate(key)
        # Formatted labels and rich result reports keep their already formatted values.
        for key in keys:
            rendered = previous.get(key, key)
            if "{v" not in rendered:
                continue
            pattern, names = "", []
            for literal, name, spec, conversion in string.Formatter().parse(rendered):
                pattern += re.escape(literal)
                if name:
                    pattern += "(.*?)"
                    names.append(name)
            match = re.fullmatch(pattern, text, re.DOTALL)
            if match:
                values = dict(zip(names, match.groups()))
                translated = self.translate(key)
                return "".join(literal + (values[name] if name else "") for literal, name, _, _ in string.Formatter().parse(translated))
        # Small translated suffixes, e.g. filename followed by profile status.
        for key in sorted(keys, key=len, reverse=True):
            rendered = previous.get(key, key)
            if len(rendered) > 12 and "{v" not in rendered and rendered in text:
                text = text.replace(rendered, self.translate(key))
        return text

    def retranslate(self, root):
        for action in root.findChildren(QtGui.QAction):
            action.setText(self.translate_existing(action.text()))
        for widget in [root, *root.findChildren(W.QWidget)]:
            if widget.toolTip():
                widget.setToolTip(self.translate_existing(widget.toolTip()))
            if isinstance(widget, W.QTextBrowser):
                continue
            if isinstance(widget, (W.QLabel, W.QAbstractButton, W.QGroupBox)):
                getter, setter = (widget.title, widget.setTitle) if isinstance(widget, W.QGroupBox) else (widget.text, widget.setText)
                setter(self.translate_existing(getter()))
            if isinstance(widget, W.QComboBox):
                for i in range(widget.count()):
                    widget.setItemText(i, self.translate_existing(widget.itemText(i)))
            if isinstance(widget, W.QTabBar):
                for i in range(widget.count()):
                    widget.setTabText(i, self.translate_existing(widget.tabText(i)))
        root.statusBar().showMessage(self.translate_existing(root.statusBar().currentMessage())) if isinstance(root, W.QMainWindow) else None


_current = None


def current():
    global _current
    if _current is None:
        _current = Localizer()
    return _current


def tr(source, **values):
    return current().translate(source, **values)
