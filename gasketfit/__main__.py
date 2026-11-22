import argparse
import logging
from pathlib import Path
import sys
from PySide6 import QtCore, QtGui, QtWidgets
from .window import MainWindow


def configure_graphics():
    # pyqtgraph caches line/scatter shader programs across viewers. All top-level
    # windows must share GL resources so those programs remain valid there.
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    fmt = QtGui.QSurfaceFormat()
    fmt.setVersion(2, 1)
    fmt.setProfile(QtGui.QSurfaceFormat.OpenGLContextProfile.NoProfile if sys.platform == "darwin" else QtGui.QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)

def main():
    parser = argparse.ArgumentParser(description="GasketFit — lokale PFDMR-Anpassung")
    parser.add_argument("--gasket")
    parser.add_argument("--head")
    parser.add_argument("--hmd")
    parser.add_argument("--project")
    parser.add_argument("--pad-project")
    parser.add_argument("--pad-design", action="store_true")
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--calculate", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Disable automatic online checks for this session")
    parser.add_argument("--screenshot", help=argparse.SUPPRESS)
    parser.add_argument("--exit-after-screenshot", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--check-online", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_online:
        import json
        import traceback
        from .online import language_inventory, check_update
        try:
            data = {"languages": language_inventory(), "release": check_update()}
        except Exception:
            data = {"error": traceback.format_exc()}
        Path(args.check_online).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return 0
    configure_graphics()
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('PFDhub.GasketFit.Beta')
    app = QtWidgets.QApplication(sys.argv[:1])
    app.setOrganizationName("GasketFit")
    app.setApplicationName("GasketFit")
    app.setWindowIcon(QtGui.QIcon(str(Path(__file__).parent/'assets/icon.png')))
    from .single_instance import SingleInstance
    instance = SingleInstance(app)
    try:
        if not instance.start():
            return 0
    except RuntimeError as exc:
        QtWidgets.QMessageBox.warning(None, 'GasketFit', str(exc))
        return 1
    app.aboutToQuit.connect(instance.close)
    from .platform_support import data_folder
    location = data_folder()
    location.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=location / "GasketFit.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.offline:
        from .localization import current
        current().settings.update(auto_updates=False, auto_languages=False)
    legacy = args.legacy or (not args.pad_design and bool(args.gasket or args.project or args.hmd))
    if legacy:
        window = MainWindow()
    else:
        from .padwindow import PadWindow
        window = PadWindow()
    window.show()
    instance.set_window(window)
    screenshot_pending = [bool(args.screenshot)]
    def screenshot():
        if not screenshot_pending[0] or window._worker:
            return
        screenshot_pending[0] = False
        window.viewer.grabFramebuffer().save(str(Path(args.screenshot).with_name(Path(args.screenshot).stem + "_viewport.png")))
        window.grab().save(args.screenshot)
        if args.exit_after_screenshot:
            window.close()
    if args.screenshot:
        window.ready.connect(lambda: QtCore.QTimer.singleShot(2000, screenshot))
    if not legacy and args.pad_project:
        QtCore.QTimer.singleShot(100, lambda: window.load_project_path(args.pad_project))
    elif not legacy and args.head:
        QtCore.QTimer.singleShot(100, lambda: window.load_head_path(args.head, calculate=args.calculate))
    elif args.project:
        QtCore.QTimer.singleShot(100, lambda: window.load_project_path(args.project))
    elif args.gasket:
        hmd_then = (lambda: window.load_hmd_path(args.hmd)) if args.hmd else None
        then = (lambda: window.load_path(args.head, True, then=hmd_then)) if args.head else hmd_then
        QtCore.QTimer.singleShot(100, lambda: window.load_path(args.gasket, False, then=then))
    elif args.head:
        QtCore.QTimer.singleShot(100, lambda: window.load_path(args.head, True))
    elif args.screenshot:
        QtCore.QTimer.singleShot(2000, screenshot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
