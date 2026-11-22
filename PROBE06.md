# Probe 06 mit GasketFit 0.7.1

Die neue Probe ergänzt die angepasste Polsterauflage um die magnetische Basis
und sieben Verbindungen. Das ist ein **offener Stabilitätsrahmen** zum Prüfen
des Sitzes am Headset. Die geschlossene Lichtschutzhülle folgt später.

## Workflow

1. **Kopfscan:** Importieren und ausrichten. Drehen bleibt jetzt in diesem
   Schritt, auch nach mehreren Drehungen. Erst mit **Weiter** fortfahren.
2. **Polster positionieren:** Augen wie gewünscht zentrieren. Höhe, seitliche
   Position und Drehung bleiben bei der Berechnung erhalten.
3. **Auflage berechnen:** Polsterdicke und zusätzliche Klettdicke einstellen.
   Abstandswarnungen und die Polsterfläche weiterhin prüfen.
4. **Magnetbasis:** Die blaue Basis unabhängig von der Auflage positionieren.
   **Basis an Auflagenposition setzen** übernimmt zunächst deren Bezugssystem.
   Danach Höhe, Tiefe und Neigung der Basis bei Bedarf separat einstellen.
   **Alt + Ziehen** bewegt in diesem Schritt die Basis, in Schritt 2 die Auflage.
   Die Basis wird dabei weder skaliert noch verformt.
5. **Probe 06 verbinden:** Die App baut sieben rückseitige Verbindungen und
   vereinigt Basis, Verbindungen und Auflage zu einem Druckkörper. Änderungen
   an der Basis machen nur diese Verbindungen ungültig; die Polsteranpassung
   bleibt erhalten. Änderungen an Kopf oder Auflage erfordern deren Neuberechnung.
6. **Export:** Warnungen prüfen und als Probestück exportieren. Vorgeschlagener
   Name: **PFDMR_Probe_06.3mf**. Der Export enthält einen verbundenen Körper,
   keinen Kopfscan. Der tiefste Punkt liegt bei Z = 0; die geeignete Orientierung
   und nötige Stützen bitte im Slicer kontrollieren.

Die Option **Basis und Verbindungen hinzufügen** kann ausgeschaltet werden,
um weiterhin nur eine Probe-05-Auflage zu exportieren. Projekte speichern
auch die unabhängige Basisposition. Vorhandene `.padfit`-Projekte bleiben lesbar;
die Auflage wird nach den aktuellen Regeln neu berechnet.

## Was geprüft wird und was noch offen ist

Die vordere Magnetaufnahme stammt aus Sir Dominiks unverändertem V2-Modell.
Nur das rückseitige Material wurde für die separate Basis abgetrennt und an
der Schnittfläche geschlossen. Die originalen Flächen im vorderen geschützten
8-mm-Bereich wurden beim Extrahieren vollständig gegen die Quelle geprüft.
Neue Verbindungen dürfen in diesen Bereich kein Material einbringen. Auch die
Klebefläche der Auflage wird nach dem Verbinden geprüft.

Die hinteren Nasen-/Lüftungsverlängerungen und die obere Kopfbandhalterung des
alten vollständigen V2-Gasket sind in dieser separaten Basis nicht enthalten.
Das fertige Probestück hat bewusst offene Seiten. Es prüft Geometrie und
Stabilität, nicht endgültige Blickdichtigkeit oder nachgewiesene Dauerfestigkeit.

Die Basisposition ist **keine automatische Augen-Linsen-Kalibrierung**.
Für den vorhandenen HMD-Scan gibt es weiterhin keine bestätigte Registrierung
zur Magnetaufnahme. Die frühere falsche automatische HMD-Kopplung bleibt aus.
Basisposition und Abstand müssen deshalb zunächst am echten Headset geprüft
werden. Die Kopfzentrierung der Auflage wird dafür nicht automatisch verschoben.

Alles bleibt lokal. Automatische Update- und Sprachsuchen sind in dieser
Testausgabe zunächst ausgeschaltet. DE und EN sind enthalten.

## Navigation (0.7.1)

Settings > Controls / Tastenbelegung: choose the mouse mapping and SpaceMouse
sensitivity. The default is left-button rotation and right-button panning.
The base is hidden automatically in steps 1-3.
# HMD-Referenz ab 0.8.0

Ab 0.8.2 stehen alle Sichtbarkeitsschalter zusammen oberhalb der 3D-Ansicht.
Der Kollisionsstatus hat darunter einen festen Platz. Statusänderungen bewegen
die Positionsfelder nicht mehr. Überschneidungen werden zusätzlich zu Punkten
als Flächen angezeigt, ohne fehlende Rasterpunkte zu überbrücken.

Rot kennzeichnet den Linsen-/Randbereich. Orange kennzeichnet geometrisch
geschätzt die Mitte: X = −12 bis +12 mm und Z = 45 bis 105 mm in
Basiskoordinaten. Die Abstände werden getrennt angezeigt. Diese Schätzung
erkennt weder Stoff noch Kunststoff; auch im mittleren Bereich können harte
Teile liegen. Eine Berührung dort wird weiterhin angezeigt und nicht automatisch
als unbedenklich behandelt. Die Magnetaufnahme und Exportgeometrie bleiben gleich.

Ab 0.8.1 beginnt die Deckkraft bei 40 % (einstellbar bis 100 %).
„Magnetbasis und Verbindungen anzeigen“ blendet Basis und Stege unabhängig
vom HMD aus. Die gemeinsame Position bleibt erhalten.

Die neue Warnung misst den kleinsten erfassten Abstand entlang der lokalen
HMD-Tiefe Y zwischen dem vorderen HMD und der Gesichtsoberfläche. Der
Prüfbereich ist in Basiskoordinaten auf X = −68 bis +68 mm,
Z = 38 bis 118 mm und HMD-Oberflächen mit Y = −100 bis +20 mm begrenzt.
Pro 2-mm-Rasterstrahl wird die hinterste HMD-Oberfläche in diesem Bereich
mit dem ersten frontseitigen Kopf-Treffer verglichen. Bügel und Backplate
sind ausgeschlossen. Rückseitige oder stark streifende Kopf-Treffer zählen
nicht als gesicherte Scan-Abdeckung.

Rote Punkte zeigen erkannte Überschneidungen auf dem Kopf. Ein Warnabstand
von zunächst 2 mm ist einstellbar. Der Wert ist keine Garantie für Komfort:
Scanfehler, fehlende Oberflächen, das Raster und die vereinfachte Vorschau
begrenzen die Genauigkeit. Die erfasste Abdeckung wird angezeigt; ungescannte
Stellen bleiben ungeprüft. Korrekturlinsen-Adapter sind noch nicht modelliert.
Die Prüfung verändert weder Pose noch Druckgeometrie und sperrt den Export
nicht automatisch.

In Schritt 4 und 5 kann der HMD-Scan transparent eingeblendet werden. Die
Deckkraft ist einstellbar; HMD und Magnetbasis lassen sich unabhängig voneinander
ausblenden. Beide folgen derselben Basisposition. In Schritt 1–3 bleiben sie
ausgeblendet. Zentrieren berücksichtigt das HMD nur, wenn es sichtbar ist.

Die relative Ausrichtung stammt aus `HMD_combo_magbasis.3mf`, vom Nutzer am
physischen HMD visuell geprüft. Die zwei ursprünglichen Scan-Hälften wurden
mit ihren gespeicherten Transformationen übernommen. Für flüssige Anzeige
wird ausschließlich die Vorschau auf 80.000 Dreiecke vereinfacht; die
magnetische Basis wird nicht verändert. Dies ist keine exakte Kalibrierung
der optischen Linsenflächen oder Augenabstände.

Das HMD dient nur zur Orientierung. Es wird weder zur Auflagenanpassung
verwendet noch mit dem Druckmodell exportiert. Bestehende Basispositionen
in gespeicherten Projekten bleiben erhalten.

