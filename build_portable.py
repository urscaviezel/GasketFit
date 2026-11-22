"""Native Linux/macOS packaging. Build on the target OS and architecture."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent


def require_case_sensitive_folder(folder):
    import tempfile
    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        probe = Path(temporary)/'CaseSensitive'
        probe.write_text('probe')
        if (probe.parent/'casesensitive').exists():
            raise RuntimeError('Linux builds require a case-sensitive filesystem for source, venv and output (use ext4, not /mnt/c).')


def check_case_sensitive_layout(application):
    """Validate the paths rtree actually resolves from its wheel RECORD."""
    import csv
    internal = application/'_internal'
    names = [p.name for p in internal.iterdir()]
    if len({name.casefold() for name in names}) != len(names):
        raise RuntimeError('Case-colliding bundled library paths')
    if 'Rtree.libs' in names or 'rtree.libs' not in names:
        raise RuntimeError('Expected bundled rtree.libs with lowercase r')
    records = list(internal.glob('*rtree*.dist-info/RECORD'))
    if not records:
        raise RuntimeError('Missing rtree package metadata')
    libraries = [row[0] for record in records for row in csv.reader(record.read_text().splitlines())
                 if row and row[0].startswith('rtree.libs/') and 'libspatialindex' in row[0]]
    if not libraries or any(not (internal/name).is_file() for name in libraries):
        raise RuntimeError('Bundled spatialindex library does not match rtree RECORD')


def build_plan(system=None, machine=None):
    from gasketfit import __version__
    from gasketfit.platform_support import package_name
    system = system or sys.platform
    machine = machine or platform.machine()
    filename = package_name(__version__, system, machine)
    if system not in ('linux', 'darwin') or filename is None:
        raise ValueError('Use build_windows.py on Windows; supported Unix targets are Linux and macOS x64/arm64.')
    output = ROOT/'dist'/('v'+__version__)/filename.removesuffix('.zip')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
               '--name', 'GasketFit', '--paths', str(ROOT), '--distpath', str(output),
               '--workpath', str(ROOT/'build'/system), '--specpath', str(ROOT/'build'/system)]
    for path in sorted((ROOT/'gasketfit').iterdir()):
        if path.suffix in ('.npz', '.json') or path.name in ('lang','assets'):
            command += ['--add-data', f'{path}:gasketfit'+('/'+path.name if path.is_dir() else '')]
    for module in ('manifold3d', 'shapely', 'fast_simplification'):
        command += ['--collect-all', module]
    command += ['--collect-submodules', 'pyqtgraph', '--collect-data', 'trimesh', '--collect-binaries', 'rtree']
    if system == 'linux':
        command += ['--hidden-import', 'OpenGL.platform.glx', '--hidden-import', 'OpenGL.platform.egl']
    for module in ('tkinter', 'IPython', 'matplotlib', 'pymeshfix', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'):
        command += ['--exclude-module', module]
    if system == 'darwin':
        command += ['--osx-bundle-identifier', 'com.pfdhub.gasketfit', '--icon', str(ROOT/'gasketfit/assets/icon.icns')]
    command += [str(ROOT/'run.py')]
    return dict(system=system, machine=machine, filename=filename, output=str(output), command=command)


def zip_tree(folder, destination):
    """Preserve executable bits and framework/library symlinks in Unix packages."""
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for base, dirs, files in os.walk(folder, followlinks=False):
            for name in dirs[:]+files:
                path = Path(base)/name
                relative = path.relative_to(folder.parent).as_posix()
                if path.is_symlink():
                    info = zipfile.ZipInfo(relative)
                    info.create_system = 3
                    info.external_attr = (0o120777 << 16)
                    archive.writestr(info, os.readlink(path))
                    if name in dirs:
                        dirs.remove(name)
                elif path.is_file():
                    archive.write(path, relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', choices=['linux', 'darwin'], help='Show a build command without running it')
    parser.add_argument('--arch', choices=['x86_64', 'arm64'], help='Architecture for --plan only')
    args = parser.parse_args()
    if args.arch and not args.plan:
        parser.error('--arch is only for --plan; actual builds use the host architecture')
    plan = build_plan(args.plan, args.arch)
    if args.plan:
        print(json.dumps(plan, indent=2))
        return
    if sys.platform == 'linux':
        require_case_sensitive_folder(ROOT)
        require_case_sensitive_folder(Path(sys.prefix))
    from gasketfit import __version__
    from datetime import datetime, timezone
    (ROOT/'gasketfit/build_info.json').write_text(json.dumps(dict(version=__version__,
        built_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'), repository='urscaviezel/GasketFit')))
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'QT_QPA_PLATFORM'):
        env.pop(key, None)
    subprocess.run(plan['command'], cwd=ROOT, env=env, check=True)
    output = Path(plan['output'])
    application = output/('GasketFit.app' if sys.platform == 'darwin' else 'GasketFit')
    if sys.platform == 'linux':
        check_case_sensitive_layout(application)
    executable = application/('Contents/MacOS/GasketFit' if sys.platform == 'darwin' else 'GasketFit')
    # Use isolated user data during the packaged smoke check.
    import tempfile
    with tempfile.TemporaryDirectory() as temporary:
        if sys.platform == 'linux':
            require_case_sensitive_folder(Path(temporary))
            # Exercise a copy, away from the build tree and its environment.
            clean_application = Path(temporary)/'GasketFit'
            shutil.copytree(application, clean_application, symlinks=True)
            executable = clean_application/'GasketFit'
        report = Path(temporary)/'startup.json'
        env['GASKETFIT_DATA_DIR'] = str(Path(temporary)/'data')
        process = subprocess.run([str(executable), '--startup-check', str(report)], env=env, timeout=180)
        result = json.loads(report.read_text()) if report.exists() else {'success': False, 'exit_code': process.returncode}
        (ROOT/'build'/('startup_'+plan['system']+'.json')).write_text(json.dumps(result, indent=2))
        if process.returncode or not result.get('success'):
            raise RuntimeError(result)
    package = output/'package'/'GasketFit'
    package.mkdir(parents=True, exist_ok=True)
    shutil.copytree(application, package/application.name if sys.platform == "darwin" else package, symlinks=True, dirs_exist_ok=True)
    source = package/'source'
    shutil.copytree(ROOT/'gasketfit', source/'gasketfit',
                    ignore=shutil.ignore_patterns('__pycache__', '*.exe'), dirs_exist_ok=True)
    for name in ('run.py', 'build_portable.py', 'requirements.txt', 'LICENSE', 'PORTIERUNG.md'):
        shutil.copy2(ROOT/name, source/name)
        shutil.copy2(ROOT/name, package/name)
    notices = package/'licenses'
    notices.mkdir(exist_ok=True)
    for distribution in importlib.metadata.distributions():
        for item in distribution.files or []:
            if 'license' not in str(item).lower() and not Path(str(item)).name.lower().startswith(('copying', 'notice')):
                continue
            path = Path(distribution.locate_file(item))
            if path.is_file() and path.stat().st_size < 2_000_000:
                relative = Path(*[p for p in Path(str(item)).parts if p not in ('.','..')])
                dest = notices/distribution.metadata['Name']/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
    archive = ROOT/'dist'/plan['filename']
    zip_tree(package, archive)
    with archive.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive.with_suffix('.zip.sha256').write_text(checksum+'  '+archive.name+'\n')
    sums_path = ROOT/'dist/checksums.json'
    sums = json.loads(sums_path.read_text()) if sums_path.exists() else {}
    sums[archive.name] = checksum
    sums_path.write_text(json.dumps(sums, indent=2))
    print(archive)


if __name__ == '__main__':
    main()
