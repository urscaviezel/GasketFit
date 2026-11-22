"""GasketFit: local PFDMR fitting assistant."""
__version__ = "0.62.0"
RELEASE_CHANNEL = "beta"

# Select matching Qt/PyOpenGL backends before any viewer imports OpenGL.
# A Wayland session can expose DISPLAY as well; Qt's XCB context must not be
# paired with PyOpenGL's automatically selected EGL context lookup.
import os as _os
import sys as _sys
if _sys.platform == "linux":
    if _os.environ.get("DISPLAY"):
        _os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    _qpa = _os.environ.get("QT_QPA_PLATFORM", "").split(":", 1)[0]
    if _qpa == "xcb" or (_qpa == "offscreen" and _os.environ.get("DISPLAY")):
        _os.environ.setdefault("PYOPENGL_PLATFORM", "glx")
    elif _qpa.startswith("wayland") or _os.environ.get("WAYLAND_DISPLAY"):
        _os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
