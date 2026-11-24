<p align="center"><img src="gasketfit/assets/logo.svg" alt="GasketFit Beta" width="600"></p>

# GasketFit Beta — PFDMR

[English](#english) · [Deutsch](#deutsch)

## English

**Public beta — not a stable release.**

Create a custom closed or open facial interface for PFDMR. Use a head scan or the
guided open-gasket workflow without a scan. Align the HMD and support, calculate
the connection, and export a printable STL or 3MF with an embedded thumbnail.
Closed, open and scan-free settings can share one project.

[Download beta builds](https://github.com/urscaviezel/GasketFit/releases) ·
[Report a problem](https://github.com/urscaviezel/GasketFit/issues)

### Getting started

- **Windows:** choose the portable ZIP or Setup installer. Portable keeps settings
  beside the EXE; Setup stores them in your user profile. The uninstaller lets you
  keep or delete the application settings.
- **Linux:** extract the `.tar.gz` into a new folder and run `GasketFit/GasketFit`.
  The current package has been tested on CachyOS and Ubuntu 24.04/WSLg.
- **macOS:** the build route is prepared; native validation is still pending.

English, German and French are included and available offline. On first launch,
the app uses the preferred system UI language, with English as the fallback.
Head scans and projects are processed locally. No account is required for downloads
or updates. Only one instance runs per user; starting another brings it forward.

### Updates and beta testing

The app checks for newer beta versions. Windows can install updates after
confirmation; Linux/macOS open the download page for manual replacement.

- Review exported models in your slicer and verify fit with a test print.
- Back up projects before trying a new version.
- Windows packages are currently unsigned.
- SpaceMouse integration and the additional mesh-repair fallback are Windows-only.
- When reporting a problem, include the app version, OS, workflow and reproduction
  steps. Avoid publishing personal head scans or project files in public issues.

### Building from source

Use Python 3.12 in a virtual environment:

```sh
python -m pip install --only-binary=:all: -r requirements.txt
python run.py
```

For standalone packages, also install `pyinstaller`, then run `build_windows.py`
on Windows or `build_portable.py` on Linux/macOS. `build_installer.py` additionally
requires Inno Setup 6. Linux source and build environments must be on a
case-sensitive filesystem. The manual GitHub Actions workflow builds packages
without publishing them automatically.

On Ubuntu, install the Qt desktop dependencies before building:

```sh
sudo apt install python3.12-venv libxcb-cursor0 libegl1 libopengl0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xkb1
```

Linux builds require a case-sensitive filesystem for both source and virtual
environment (under WSL, use the Linux filesystem rather than `/mnt/c`). The build
checks the packaged application, including calculations and exports. The current
Linux build targets Ubuntu 24.04 and newer compatible systems; native Wayland and
older distributions are not yet validated.

### For maintainers

Use numeric `vX.Y.Z` tags and publish beta builds as GitHub pre-releases. Upload
packages and `checksums.json` (asset filename → SHA-256) to a draft, verify them,
then publish. Linux packages use `.tar.gz`; Windows portable and macOS use `.zip`.
Only publish macOS packages after native testing. Keep credentials and personal
scans out of the repository.

Language catalogues are UTF-8 JSON in `gasketfit/lang` (bundled) and `lang`
(downloadable). Use `en.json` as the template; retain message keys and formatting
placeholders. English, German and French are bundled. Additional catalogues can
be imported in Settings; missing translations fall back to English.

GasketFit uses the MIT license; bundled third-party components retain their own
licenses. The repository contains application assets, not personal head scans or
development projects.

---

## Deutsch

**Öffentliche Beta — noch keine stabile Version.**

Erstelle eine individuell angepasste geschlossene oder offene Gesichtsauflage für
PFDMR. Verwende einen Kopfscan oder den geführten Workflow für ein offenes Gasket
ohne Scan. Richte HMD und Auflage aus, berechne die Verbindung und exportiere das
Druckmodell als STL oder 3MF mit eingebetteter Miniaturansicht. Einstellungen für
geschlossene, offene und scanfreie Varianten lassen sich in einem Projekt speichern.

[Beta herunterladen](https://github.com/urscaviezel/GasketFit/releases) ·
[Problem melden](https://github.com/urscaviezel/GasketFit/issues)

### Erste Schritte

- **Windows:** Wähle das portable ZIP oder den Setup-Installer. Die portable Version
  speichert Einstellungen neben der EXE, die installierte Version im Benutzerprofil.
  Bei der Deinstallation kannst du die Anwendungseinstellungen behalten oder löschen.
- **Linux:** Entpacke die `.tar.gz` in einen neuen Ordner und starte
  `GasketFit/GasketFit`. Das aktuelle Paket wurde auf CachyOS und Ubuntu 24.04/WSLg getestet.
- **macOS:** Der Build ist vorbereitet; der native Praxistest steht noch aus.

Englisch, Deutsch und Französisch sind enthalten und offline verfügbar. Beim ersten
Start verwendet die App die bevorzugte Systemsprache, mit Englisch als Rückfall.
Kopfscans und Projekte werden lokal verarbeitet. Für Downloads und Updates ist kein
Konto nötig. Pro Benutzer läuft nur eine Instanz; ein weiterer Start holt sie nach vorne.

### Updates und Beta-Tests

Die App sucht nach neueren Beta-Versionen. Windows kann Updates nach Bestätigung
installieren; Linux/macOS öffnen die Downloadseite für den manuellen Austausch.

- Kontrolliere exportierte Modelle im Slicer und prüfe den Sitz mit einem Probedruck.
- Sichere Projekte, bevor du eine neue Version ausprobierst.
- Die Windows-Pakete sind derzeit nicht signiert.
- SpaceMouse-Unterstützung und die zusätzliche Netzreparatur sind Windows vorbehalten.
- Nenne bei Fehlermeldungen App-Version, Betriebssystem, Workflow und die Schritte
  zum Nachstellen. Veröffentliche persönliche Kopfscans oder Projektdateien nicht
  versehentlich in öffentlichen Issues.

### Aus dem Quellcode bauen

Verwende Python 3.12 in einer virtuellen Umgebung:

```sh
python -m pip install --only-binary=:all: -r requirements.txt
python run.py
```

Für eigenständige Pakete zusätzlich `pyinstaller` installieren und unter Windows
`build_windows.py`, unter Linux/macOS `build_portable.py` ausführen.
`build_installer.py` benötigt außerdem Inno Setup 6. Unter Linux müssen Quellcode
und Build-Umgebung auf einem Dateisystem liegen, das Groß-/Kleinschreibung unterscheidet.
Der manuelle GitHub-Actions-Workflow baut Pakete, veröffentlicht sie aber nicht automatisch.

Unter Ubuntu vor dem Bauen die Qt-Desktop-Abhängigkeiten installieren:

```sh
sudo apt install python3.12-venv libxcb-cursor0 libegl1 libopengl0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xkb1
```

Linux-Builds benötigen für Quellcode und virtuelle Umgebung ein Dateisystem mit
Unterscheidung der Groß-/Kleinschreibung (unter WSL das Linux-Dateisystem statt
`/mnt/c` verwenden). Der Build prüft das fertige Paket einschließlich Berechnung
und Export. Der aktuelle Linux-Build zielt auf Ubuntu 24.04 und neuere kompatible
Systeme; natives Wayland und ältere Distributionen sind noch nicht geprüft.

### Für Maintainer

Numerische Tags wie `vX.Y.Z` verwenden und Beta-Builds als GitHub-Vorabversionen
veröffentlichen. Pakete und `checksums.json` (Dateiname → SHA-256) zunächst in einen
Entwurf hochladen, prüfen und danach veröffentlichen. Linux-Pakete verwenden
`.tar.gz`, Windows Portable und macOS `.zip`. macOS-Pakete erst nach nativen Tests
veröffentlichen. Zugangsdaten und persönliche Scans gehören nicht ins Repository.

Sprachkataloge sind UTF-8-JSON in `gasketfit/lang` (mitgeliefert) und `lang`
(herunterladbar). `en.json` als Vorlage verwenden; Nachrichtenschlüssel und
Formatplatzhalter beibehalten. Englisch, Deutsch und Französisch werden mitgeliefert.
Weitere Kataloge lassen sich in den Einstellungen importieren; fehlende
Übersetzungen verwenden Englisch.

GasketFit steht unter der MIT-Lizenz; mitgelieferte Drittanbieter-Komponenten
behalten ihre jeweiligen Lizenzen. Das Repository enthält Anwendungsdaten,
keine persönlichen Kopfscans oder Entwicklungsprojekte.
