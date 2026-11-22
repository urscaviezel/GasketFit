"""Build a self-contained, dynamically linked Windows folder distribution."""
from pathlib import Path
import importlib.metadata
import shutil
import subprocess
import sys
import zipfile
import hashlib
import json
import os
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent


def main():
    from native.build import build as build_native
    build_native()
    sys.path.insert(0, str(ROOT))
    from gasketfit import __version__
    (ROOT / "gasketfit" / "build_info.json").write_text(json.dumps({"version": __version__, "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "repository": "urscaviezel/GasketFit"}), encoding="utf-8")
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
            "--name", "GasketFit", "--distpath", str(ROOT / "dist" / ("v" + __version__)), "--workpath", str(ROOT / "build"),
            "--specpath", str(ROOT / "build"), "--paths", str(ROOT),
            "--icon", str(ROOT/'gasketfit/assets/icon.ico'),
            "--add-data", str(ROOT/'gasketfit/assets')+';gasketfit/assets',
            "--add-data", str(ROOT / "gasketfit" / "lang") + ";gasketfit/lang",
            "--add-data", str(ROOT / "gasketfit" / "build_info.json") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_profile.json") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "vrcover_236x116.json") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "vrcover_probe04.npz") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_magnetic_base.npz") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_open_base.npz") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "vr_panda_198x48.json") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_magnetic_base.json") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_hmd_reference.npz") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_hmd_reference.json") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_hmd_connector_guard.npz") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_base_feature_voids.npz") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_oem16_front_guard.npz") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "pfd_rear_cap.npz") + ";gasketfit",
            "--add-data", str(ROOT / "gasketfit" / "GasketRepair.exe") + ";gasketfit",
            "--collect-all", "manifold3d", "--collect-all", "shapely",
            "--collect-submodules", "pyqtgraph", "--collect-data", "trimesh",
            "--collect-binaries", "rtree", "--collect-all", "fast_simplification",
            "--hidden-import", "scipy.spatial._ckdtree", "--hidden-import", "scipy.sparse.csgraph._validation",
            "--exclude-module", "tkinter", "--exclude-module", "IPython", "--exclude-module", "matplotlib",
            "--exclude-module", "pymeshfix",
            "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.QtWebEngineWidgets",
            str(ROOT / "run.py")]
    # This Python runtime has an additional CA policy file referenced by ssl.py.
    # Preserve that policy in frozen builds instead of bypassing TLS validation.
    ssl_policy = Path(sys.base_prefix) / "Lib" / "codex-rejected-cas.pem"
    if ssl_policy.exists():
        args[-1:-1] = ["--add-data", str(ssl_policy) + ";."]
    if "--repack-only" not in sys.argv:
        build_env=os.environ.copy()
        build_env.pop("PYTHONPATH",None)
        build_env.pop("QT_QPA_PLATFORM",None)
        subprocess.run(args, cwd=ROOT, check=True, env=build_env)
    output = ROOT / "dist" / ("v" + __version__) / "GasketFit"
    (output/'portable.flag').write_text('GasketFit portable\n')
    if ssl_policy.exists():
        shutil.copy2(ssl_policy, output / "_internal" / ssl_policy.name)
    shutil.copy2(ROOT / "gasketfit" / "build_info.json", output / "_internal" / "gasketfit" / "build_info.json")
    shutil.copytree(ROOT / "lang", output / "lang", dirs_exist_ok=True)
    if "--local-test" in sys.argv and not (output / "settings.json").exists():
        (output / "settings.json").write_text(json.dumps(dict(language="de", auto_updates=False, auto_languages=False)), encoding="utf-8")

    # Qt 6.12 links against the Windows inbox ICU ABI (unversioned symbols).
    # The build runtime also ships an unrelated ICU 78 with versioned symbols;
    # PyInstaller's DLL search may collect it, shadowing the Windows DLL.
    # Python/scipy do not need that unrelated copy. Let Windows resolve its ICU.
    for name in ("icuuc.dll", "icudt78.dll"):
        unwanted = output / "_internal" / name
        if unwanted.exists():
            unwanted.unlink()
    for name in ("README.md", "BETA.md", "PORTIERUNG.md", "PROBE05.md", "PROBE06.md", "PROBE07.md", "PROBE09.md", "PROBE10.md", "PROBE11.md", "OEM_BASIS.md", "LANGUAGES.md", "UPDATES.md", "GEOMETRY.md", "LICENSE", "requirements.txt"):
        shutil.copy2(ROOT / name, output / name)
    # Include all installed dependency notices without bundling private models.
    licenses = output / "licenses"
    licenses.mkdir(exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    notices = ["GasketFit 0.1 — Third-party software notices", "", "The application uses dynamically linked Qt/PySide6 under LGPL-3.0 / applicable component licenses.",
               "The _internal DLL files are kept separate and replaceable. No modified third-party libraries are used.",
               "Exact upstream license texts are copied below licenses/.", "", "Installed distributions:"]
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "unknown")
        if name.lower() == 'pymeshfix':
            continue  # Rejected offline experiment; never part of the app.
        notices.append(f"{name} {distribution.version}")
        for item in distribution.files or []:
            text = str(item)
            base = Path(text).name.lower()
            if "license" in text.lower() or base.startswith(("copying", "notice", "copyright")):
                source = Path(distribution.locate_file(item))
                if source.is_file() and source.stat().st_size < 2_000_000:
                    relative = Path(*[part for part in Path(text).parts if part not in ("..", ".")])
                    destination = licenses / name / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    (output / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(notices), encoding="utf-8")
    # LGPL recipients have access to application source and may modify/rebuild it.
    source_dir = output / "source"
    shutil.copytree(ROOT / "gasketfit", source_dir / "gasketfit", ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    shutil.copytree(ROOT / "native", source_dir / "native", ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    shutil.copytree(ROOT / "installer", source_dir / "installer", dirs_exist_ok=True)
    for name in ("run.py", "build_windows.py", "build_portable.py", "build_icons.py", "build_installer.py", "PORTIERUNG.md", "requirements.txt", "LICENSE"):
        shutil.copy2(ROOT / name, source_dir / name)
    # Check the executable we ship, not merely source imports. The dedicated
    # mode builds the main window offscreen and catches startup exceptions.
    startup_report = ROOT / 'build' / ('startup_' + __version__ + '.json')
    startup = subprocess.run([str(output / 'GasketFit.exe'), '--startup-check', str(startup_report)],
        capture_output=True, text=True, timeout=60,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if startup.returncode or not startup_report.exists() or not json.loads(startup_report.read_text(encoding='utf-8')).get('success'):
        raise RuntimeError('Packaged application failed its offscreen startup check: ' +
            (startup_report.read_text(encoding='utf-8') if startup_report.exists() else startup.stderr))
    archive = ROOT / "dist" / f"GasketFit-{__version__}-Windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for file in output.rglob("*"):
            if file.is_file():
                z.write(file, file.relative_to(output.parent))
    checksums = json.loads((ROOT/'dist/checksums.json').read_text()) if (ROOT/'dist/checksums.json').exists() else {}
    checksums[archive.name] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (ROOT / "dist" / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    print(f"Portable app: {output / 'GasketFit.exe'}")
    print(f"Archive: {archive} ({archive.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
