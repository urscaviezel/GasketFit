# GasketFit: Linux und macOS vorbereiten

Die freigegebene Windows-Referenz bleibt **0.60.0**. Die Portierung wird getrennt
ab **0.61.0** entwickelt; die öffentliche Beta ist **0.62.0**.
Qt/PySide bleibt das UI-Framework. Windows bietet portable ZIP und Setup;
der Installer speichert Benutzerdaten unter `%LOCALAPPDATA%\GasketFit`.
Die Version 0.61.0 wurde inzwischen auch auf CachyOS kompiliert und mit
vollständigen Workflows und Exporten vom Anwender geprüft.

## Aus dem Quellcode starten

Python 3.12 verwenden. Im Ordner `GasketFit`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt pyinstaller
.venv/bin/python run.py --offline
```

Auf Ubuntu 24.04 benötigt die grafische Qt-Oberfläche unter anderem
`python3.12-venv`, `libxcb-cursor0`, `libegl1`, `libopengl0`,
`libxkbcommon-x11-0`, `libxcb-icccm4`, `libxcb-keysyms1`, `libxcb-shape0`
und `libxcb-xkb1`. Installation auf Ubuntu:

```sh
sudo apt install python3.12-venv libxcb-cursor0 libegl1 libopengl0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xkb1
```

Die Anwendung benötigt eine funktionierende OpenGL-Umgebung. Ein erfolgreicher
Offscreen-Test allein bestätigt noch nicht die Darstellung mit jedem Grafiktreiber.
Wenn `DISPLAY` vorhanden ist, verwendet GasketFit standardmäßig X11/XWayland
und stimmt den PyOpenGL-Zugang darauf ab. Ein ausdrücklich gesetztes
`QT_QPA_PLATFORM` oder `PYOPENGL_PLATFORM` wird respektiert. Der native
Wayland-Weg ist noch nicht praktisch geprüft.

## Native Pakete bauen

```sh
.venv/bin/python build_portable.py
```

Linux-Pakete auf Linux bauen, macOS-Pakete auf dem Mac. Die Architektur wird vom
Build-Rechner übernommen: x64 oder arm64. Ein Windows-Build ist kein Mac-/Linux-Port.
Der Build führt anschließend den Paket-Starttest einschließlich Berechnung und
3MF-Export aus. Bei einem Fehler wird kein fertiges ZIP veröffentlicht.

Nur die Befehle anzeigen, ohne zu bauen:

```sh
python build_portable.py --plan linux --arch x86_64
python build_portable.py --plan darwin --arch arm64
```

Die ZIP-Dateien unter `dist` enthalten Anwendung, Quellcode und Lizenzhinweise.
macOS enthält `GasketFit.app`; Linux startet `GasketFit/GasketFit`.
Mac-Pakete sind zunächst lokale Testpakete, noch nicht für die öffentliche
Verteilung signiert und notarisiert. Für die erste Prüfung kann der Quellstart
verwendet werden; keine systemweiten Sicherheitseinstellungen abschalten.

## Unterschiede zur Windows-Version

- Einstellungen, zusätzliche Sprachdateien und Cache liegen auf Linux/macOS in
  den Benutzerverzeichnissen von Qt, nicht in der Installation oder im App-Bundle.
  `GASKETFIT_DATA_DIR` überschreibt den Datenordner für isolierte Tests.
- Windows behält seinen bisherigen portablen Speicherort.
- Die Update-Suche wählt Pakete für Betriebssystem und Architektur. Der bisherige
  PowerShell-Installer bleibt Windows vorbehalten; Unix-Pakete werden manuell ersetzt.
- Maussteuerung funktioniert unabhängig von Windows Raw Input. Die vorhandene
  SpaceMouse-Anbindung und die 3DxWare-Profilverwaltung sind vorerst nur für Windows.
- Reguläre STL-/3MF-Exporte und PNG-Miniaturansichten benötigen keine Windows-API.
  Falls eine zusätzliche Netzreparatur erforderlich ist, wird unter Linux/macOS
  verständlich abgebrochen. Es wird weder eine EXE gestartet noch ein ungültiger
  Körper stillschweigend exportiert.

## Prüfung auf einem neuen Testrechner

1. Alle drei Sprachen und beide Gasket-Workflows öffnen.
2. Ein vorhandenes `.padfit` laden, Kopf und HMD kontrollieren und die Ansicht drehen.
3. Im Assistenten ohne Scan Passbögen, Montageprobe und fertiges Gasket berechnen.
4. STL und 3MF exportieren und im Slicer öffnen; Vorschaubild im 3MF prüfen.
5. Projekt speichern, Anwendung beenden, neu starten und erneut laden.
6. Einstellungen ändern und nach Neustart kontrollieren.

Die lokalen Testprotokolle im Projektordner `Wartung` dokumentieren den tatsächlich
geprüften Stand. macOS muss auf dem realen Mac zusätzlich ausgeführt werden.

Am 22.11.2026 unter Ubuntu 24.04 (WSL2/WSLg, x64) geprüft: 74 erfolgreiche
automatische Prüfungen, eine ausgelassene Windows-API-Prüfung, zusätzlich
16 erfolgreiche Fenstertests mit der normalen Grafikinitialisierung.
Das gespeicherte Projekt GasketFit_test.padfit wurde ohne Kopfscan berechnet
und als echtes OpenGL-Modell im Linux-Fenster dargestellt.
Das ersetzt noch keinen Test auf dem separaten Linux-Rechner oder auf macOS.
