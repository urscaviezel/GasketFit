# GasketFit Beta

This is a public **beta**, not a stable production release. Windows and Linux
have been exercised locally; macOS still needs native validation. Existing
project files should be backed up before opening them in a new version.

## Packages

- **Windows portable:** extract the ZIP into a writable folder. Settings and
  additional languages stay alongside `GasketFit.exe`.
- **Windows installer:** choose the installation folder in Setup. Settings,
  languages and cache are stored in `%LOCALAPPDATA%\GasketFit`. Uninstall asks
  whether to retain these data. Silent uninstall always retains them.
- **Linux:** extract the ZIP and run `GasketFit/GasketFit`. The published binary
  is built on Ubuntu 24.04 x64. Building from source also works on other suitable
  distributions; the previous version was tested by the maintainer on CachyOS.
- **macOS:** build from source on the target Mac using `PORTIERUNG.md` until a
  native package has been validated.

Only one GUI instance runs per OS user. Starting another copy brings the
existing window forward. Portable and installed copies share this rule.

## Updates

The beta channel includes GitHub **pre-releases**, excludes drafts, and checks
the numeric version rather than publication order. Checks run automatically
and can be disabled in Settings. Installation requires confirmation.

Windows portable updates preserve settings and language files, and keep the
previous folder for recovery. Installed Windows copies receive the installer
instead, preserving the chosen installation path and user data. Downloads are
verified against the release's SHA-256 manifest. Linux/macOS detect updates
and offer the download page; automatic replacement is not implemented there.

The beta builds are currently unsigned. SHA-256 verifies the files against the
release manifest; it is not an independent publisher signature.

## Feedback

Include the app version, OS, workflow and steps to reproduce. Screenshots help.
Head scans and `.padfit` projects can contain personal data: do not attach them
to public issues unless you intentionally want to publish them.

SpaceMouse integration and the additional Windows mesh-repair fallback are
currently Windows-only. Normal modelling, STL/3MF export and 3MF thumbnails
work without these optional facilities.
