"""Platform boundaries; portable Windows installations keep their old layout."""
from pathlib import Path
import os
import platform
import sys
from PySide6.QtCore import QStandardPaths


def installation_folder():
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


def installed_windows():
    return sys.platform == 'win32' and (installation_folder()/'installed.flag').is_file()


def data_folder():
    override = os.environ.get('GASKETFIT_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'win32':
        if installed_windows():
            base = os.environ.get('LOCALAPPDATA') or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
            return Path(base)/'GasketFit'
        return installation_folder()
    # Never write into a macOS .app bundle or a system-wide Linux installation.
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    return Path(base)/'GasketFit'


def cache_folder():
    if sys.platform == 'win32' or os.environ.get('GASKETFIT_DATA_DIR'):
        return data_folder()/'cache'
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation)
    return Path(base)/'GasketFit'


def package_name(version, system=None, machine=None):
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    architecture = {'amd64':'x64', 'x86_64':'x64', 'arm64':'arm64', 'aarch64':'arm64'}.get(machine)
    label = {'win32':'Windows', 'linux':'Linux', 'darwin':'macOS'}.get(system)
    if not architecture or not label:
        return None
    extension = '.tar.gz' if system == 'linux' else '.zip'
    return f'GasketFit-{version}-{label}-{architecture}{extension}'


def supports_in_app_update():
    return sys.platform == 'win32'
