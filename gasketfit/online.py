"""Read-only GitHub discovery and verified portable updates. No model uploads."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from . import __version__, RELEASE_CHANNEL
from .localization import REPOSITORY, validate_catalog, atomic_json

API = f"https://api.github.com/repos/{REPOSITORY}"


def request(url, limit=2_000_000):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("api.github.com", "raw.githubusercontent.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"):
        raise ValueError("Untrusted download URL")
    req = urllib.request.Request(url, headers={"User-Agent": f"GasketFit/{__version__}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in ("api.github.com", "raw.githubusercontent.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"):
            raise ValueError("Untrusted download redirect")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Download size limit exceeded")
    return data


def github_json(path):
    try:
        return json.loads(request(API + path))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def language_inventory():
    items = github_json("/contents/lang")
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("Invalid GitHub language listing")
    return [{"name": item["name"], "sha": item["sha"]}
            for item in items if item.get("type") == "file" and re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?\.json", item.get("name", ""))]


def download_language(item, folder):
    filename = item["name"]
    if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?\.json", filename):
        raise ValueError("Invalid language filename")
    # Pin the content to the blob SHA from discovery instead of a mutable URL.
    data = github_json("/git/blobs/" + item["sha"])
    import base64
    content = base64.b64decode(data["content"], validate=False)
    if len(content) > 1_000_000 or hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest() != item["sha"]:
        raise ValueError("Language content checksum mismatch")
    catalogue = validate_catalog(json.loads(content.decode("utf-8-sig")))
    if catalogue["code"] != filename[:-5]:
        raise ValueError("Language code and filename differ")
    atomic_json(Path(folder) / filename, catalogue)
    return catalogue["code"]


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError("Unsupported version tag")
    return tuple(map(int, match.groups()))


def check_update():
    releases = github_json("/releases?per_page=100")
    candidates = []
    for item in releases or []:
        if not isinstance(item, dict) or item.get('draft') or (RELEASE_CHANNEL != 'beta' and item.get('prerelease')):
            continue
        try:
            candidates.append((version_tuple(item.get('tag_name', '')), item))
        except ValueError:
            continue
    if not candidates:
        return {"state": "unpublished"}
    release = max(candidates, key=lambda pair: pair[0])[1]
    tag = release.get("tag_name", "")
    newer = version_tuple(tag) > version_tuple(__version__)
    assets = release.get("assets", [])
    version = tag.lstrip("v")
    from .platform_support import package_name, installed_windows
    filename = package_name(version)
    if installed_windows() and filename:
        filename = filename.removesuffix('.zip')+'-Setup.exe'
    package = next((a for a in assets if a.get("name") == filename), None)
    sums = next((a for a in assets if a.get("name") == "checksums.json"), None)
    return {"state": "new" if newer else "current", "version": version,
            "package": package, "checksums": sums, "filename": filename,
            "page": release.get('html_url', 'https://github.com/'+REPOSITORY+'/releases'),
            "prerelease": bool(release.get('prerelease'))}


def extract_update(archive, destination):
    """No absolute paths, traversal, duplicate Windows paths or symlinks."""
    destination = Path(destination)
    with zipfile.ZipFile(archive) as z:
        total, names = 0, set()
        for item in z.infolist():
            path = PurePosixPath(item.filename)
            if (not path.parts or path.parts[0] != "GasketFit" or path.is_absolute()
                    or any(p in ("..", ".") or ":" in p or "\\" in p or p.endswith((" ", ".")) for p in path.parts)
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsafe update archive path")
            normalized = str(path).casefold()
            if normalized in names:
                raise ValueError("Duplicate update archive path")
            names.add(normalized)
            total += item.file_size
            if total > 1_500_000_000 or len(names) > 20000:
                raise ValueError("Update archive exceeds limit")
        if "gasketfit/gasketfit.exe" not in names or not any(n.startswith("gasketfit/_internal/") for n in names):
            raise ValueError("Incomplete Windows update package")
        z.extractall(destination)
    return destination / "GasketFit"


def prepare_update(release, root, progress=None):
    from .platform_support import supports_in_app_update, installed_windows, data_folder
    if not supports_in_app_update():
        raise RuntimeError("Install the native package manually on this platform")
    if not release.get("package") or not release.get("checksums"):
        raise ValueError("Release has no package or checksums.json")
    if version_tuple(release["version"]) <= version_tuple(__version__):
        raise ValueError("Update is not newer")
    progress = progress or (lambda *_: None)
    progress(10, "Downloading checksums")
    checks = json.loads(request(release["checksums"]["browser_download_url"]))
    expected = checks.get(release["filename"], "")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
        raise ValueError("Missing SHA-256 checksum")
    progress(20, "Downloading Windows package")
    content = request(release["package"]["browser_download_url"], 400_000_000)
    if hashlib.sha256(content).hexdigest().lower() != expected.lower():
        raise ValueError("Update checksum mismatch")
    if installed_windows():
        expected_name = f"GasketFit-{release['version']}-Windows-x64-Setup.exe"
        if release['filename'] != expected_name or not content.startswith(b'MZ'):
            raise ValueError('Invalid installer package')
        stage = data_folder()/'updates'/uuid.uuid4().hex
        stage.mkdir(parents=True)
        installer = stage/expected_name
        installer.write_bytes(content)
        return installer
    # Stage next to app directory; folder replacement requires the same volume.
    stage = Path(root).parent / ("GasketFit-update-" + uuid.uuid4().hex)
    stage.mkdir()
    archive = stage / release["filename"]
    archive.write_bytes(content)
    progress(75, "Validating Windows package")
    extracted = extract_update(archive, stage)
    # Preserve local settings and community translations; projects stay in backup.
    root = Path(root)
    if (root / "settings.json").exists():
        shutil.copy2(root / "settings.json", extracted / "settings.json")
    if (root / "lang").exists():
        shutil.copytree(root / "lang", extracted / "lang", dirs_exist_ok=True)
    progress(100, "Update ready")
    return extracted


def install_update(stage, root):
    from .platform_support import supports_in_app_update, installed_windows, data_folder, installation_folder
    if not supports_in_app_update():
        raise RuntimeError("Install the native package manually on this platform")
    if not getattr(sys, "frozen", False):
        raise ValueError("Updates can only replace a packaged Windows app")
    stage, root = Path(stage).resolve(), Path(root).resolve()
    if root != installation_folder().resolve():
        raise ValueError('Invalid application folder')
    if installed_windows():
        if not stage.is_relative_to((data_folder()/'updates').resolve()) or not re.fullmatch(r'GasketFit-\d+\.\d+\.\d+-Windows-x64-Setup\.exe', stage.name) or not stage.is_file():
            raise ValueError('Invalid staged installer')
        subprocess.Popen([str(stage), '/SP-', '/DIR='+str(root)], close_fds=True)
        return
    if (stage.name != "GasketFit"
            or stage.parent.parent != root.parent or not stage.parent.name.startswith("GasketFit-update-")
            or not (stage / "GasketFit.exe").is_file() or stage == root):
        raise ValueError("Invalid update destination")
    # LiteralPath end-to-end; no recursive deletes. The old app remains recoverable.
    helper = stage.parent / "apply-update.ps1"
    helper.write_text('''param([string]$AppFolder,[string]$StageFolder,[int]$AppProcessId)
$ErrorActionPreference = 'Stop'
Wait-Process -Id $AppProcessId -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$BackupFolder = $AppFolder + '.previous-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
try {
    Move-Item -LiteralPath $AppFolder -Destination $BackupFolder
    try { Move-Item -LiteralPath $StageFolder -Destination $AppFolder }
    catch { Move-Item -LiteralPath $BackupFolder -Destination $AppFolder; throw }
    Start-Process -FilePath (Join-Path $AppFolder 'GasketFit.exe') -WindowStyle Normal
} catch {
    $_ | Out-String | Set-Content -LiteralPath (Join-Path (Split-Path $StageFolder) 'update-error.txt')
    if (Test-Path -LiteralPath (Join-Path $AppFolder 'GasketFit.exe')) {
        Start-Process -FilePath (Join-Path $AppFolder 'GasketFit.exe') -WindowStyle Normal
    }
}
''', encoding="utf-8-sig")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper),
                      "-AppFolder", str(root), "-StageFolder", str(stage), "-AppProcessId", str(os.getpid())],
                     creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
