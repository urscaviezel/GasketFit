# GasketFit Beta

[English](#english) · [Deutsch](#deutsch)

## English

This is a public **beta**, not a stable production release. Windows and Linux
have been exercised locally; macOS still needs native validation. Existing
project files should be backed up before opening them in a new version.

## Packages

- **Windows portable:** extract the ZIP into a writable folder. Settings and
  additional languages stay alongside `GasketFit.exe`.
- **Windows installer:** choose the installation folder in Setup. Settings,
  languages and cache are stored in `%LOCALAPPDATA%\GasketFit`. Uninstall asks
  whether to retain these data. Silent uninstall always retains them.
- **Linux:** extract the `.tar.gz` into a new folder and run `GasketFit/GasketFit`. The published binary
  is built on Ubuntu 24.04 x64. Building from source also works on other suitable
  distributions; the current package was tested by the maintainer on CachyOS.
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

---

## Deutsch

Dies ist eine öffentliche **Beta**, noch keine stabile Produktivversion. Windows
und Linux wurden lokal geprüft; der native macOS-Test steht noch aus. Sichere
bestehende Projekte, bevor du sie mit einer neuen Version öffnest.

### Pakete

- **Windows portabel:** ZIP in einen beschreibbaren Ordner entpacken. Einstellungen
  und zusätzliche Sprachen bleiben neben `GasketFit.exe`.
- **Windows-Installer:** Installationsordner im Setup wählen. Einstellungen,
  Sprachen und Cache liegen unter `%LOCALAPPDATA%\GasketFit`. Bei der Deinstallation
  kannst du diese Daten behalten. Eine unbeaufsichtigte Deinstallation behält sie immer.
- **Linux:** `.tar.gz` in einen neuen Ordner entpacken und `GasketFit/GasketFit`
  starten. Das veröffentlichte Paket wird auf Ubuntu 24.04 x64 gebaut. Der Quellcode
  lässt sich auch auf anderen geeigneten Distributionen bauen; das aktuelle Paket
  wurde vom Maintainer auf CachyOS getestet.
- **macOS:** Bis zur Prüfung eines nativen Pakets auf dem Ziel-Mac aus dem Quellcode
  bauen; siehe `PORTIERUNG.md`.

Pro Benutzer läuft nur eine Instanz mit Oberfläche. Ein weiterer Start holt das
bestehende Fenster nach vorne. Das gilt gemeinsam für portable und installierte Kopien.

### Updates

Der Beta-Kanal berücksichtigt GitHub-Vorabversionen, ignoriert Entwürfe und
vergleicht Versionsnummern statt Veröffentlichungsdaten. Die automatische Suche
kann in den Einstellungen abgeschaltet werden. Die Installation benötigt eine Bestätigung.

Portable Windows-Updates erhalten Einstellungen und Sprachdateien sowie den
vorherigen Ordner zur Wiederherstellung. Installierte Windows-Versionen erhalten
den Installer; Installationspfad und Benutzerdaten bleiben erhalten. Downloads
werden anhand der SHA-256-Prüfsummen des Releases geprüft. Linux/macOS erkennen
Updates und bieten die Downloadseite an; der automatische Austausch ist dort noch
nicht umgesetzt.

Die Beta-Pakete sind derzeit nicht signiert. SHA-256 prüft die Dateien gegen die
Release-Prüfsummen, ist aber keine unabhängige Signatur des Herausgebers.

### Rückmeldungen

Bitte App-Version, Betriebssystem, Workflow und Schritte zum Nachstellen nennen.
Screenshots helfen. Kopfscans und `.padfit`-Projekte können persönliche Daten
enthalten: nur an öffentliche Issues anhängen, wenn du sie bewusst veröffentlichen möchtest.

SpaceMouse-Unterstützung und die zusätzliche Netzreparatur sind derzeit Windows
vorbehalten. Reguläre Modellberechnung, STL-/3MF-Export und 3MF-Miniaturansichten
funktionieren ohne diese optionalen Funktionen.
