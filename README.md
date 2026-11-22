<p align="center"><img src="gasketfit/assets/logo.svg" alt="GasketFit Beta" width="600"></p>

# GasketFit Beta — PFDMR

**Public beta. Not a stable release.**

Create a custom closed or open facial interface for PFDMR. Work locally with a
head scan, or use the guided open-gasket workflow without a scan. Align the HMD
and support, calculate the connection, and export a printable STL or 3MF with
an embedded thumbnail. Closed, open and scan-free settings can share one project.

[Download beta builds](https://github.com/urscaviezel/GasketFit/releases) ·
[Beta notes](BETA.md) · [Report a problem](https://github.com/urscaviezel/GasketFit/issues)

## Getting started

- **Windows:** choose the portable ZIP or the Setup installer. Portable keeps
  settings beside the EXE; Setup stores them in your user profile.
- **Linux:** extract the Linux ZIP and run `GasketFit/GasketFit`. See
  [PORTIERUNG.md](PORTIERUNG.md) for Qt dependencies and source builds.
- **macOS:** the build route is prepared, but a native Mac test is still pending.

The interface includes German, English and French. Head scans and projects are
processed locally. No account is required for public beta downloads or updates.
Beta builds automatically check for newer beta versions; installation is confirmed
by the user. Linux/macOS currently open the download page for manual replacement.

## From source

Use Python 3.12 and a virtual environment:

```sh
python -m pip install --only-binary=:all: -r requirements.txt
python run.py
```

For standalone packages, install `pyinstaller`, then run `build_windows.py` on
Windows or `build_portable.py` on Linux/macOS. `build_installer.py` additionally
requires Inno Setup 6. The manual GitHub Actions workflow builds native packages;
it does not publish releases automatically.

## Beta limitations

- Review the exported model in your slicer and verify fit with a test print.
- SpaceMouse integration and the extra Windows mesh-repair fallback are Windows-only.
- Windows packages are currently unsigned.
- Keep a backup of your projects when testing a new version.

See [BETA.md](BETA.md) for storage, uninstall and update details, and
[UPDATES.md](UPDATES.md) for the release contract. The public repository contains
application assets, not personal head scans or development project files.

MIT license for GasketFit; bundled third-party components retain their own licenses.
