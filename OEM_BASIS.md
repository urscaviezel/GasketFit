# GasketFit 0.11.0 – OEM-HMD und Magnetbasis

Das lokale HMD-Modell stammt nun aus der vorlaeufig aufbereiteten Originalgeometrie.
Front und Kopfband bewegen sich als eine Referenz mit der Magnetbasis.
Der HMD-Schalter blendet beides gemeinsam ein und aus. In Schritt 1–3 bleibt
die Referenz ausgeblendet. HMD und Kopfband werden nicht mitgedruckt.

Der Adapterring stammt aus derselben OEM-Datei und behaelt seine dortige
Zuordnung zum HMD. Fuer die App werden beide gemeinsam starr umgerechnet.
Die Umrechnung zum bisherigen Mod-Rahmen war nur eine geometrische
Annaeherung; bestehende Projektpositionen bleiben Zahlenwerte, muessen aber
mit der neuen Referenz vor einem weiteren Druck kontrolliert werden.

## Magnete

- Sieben Magnete, jeweils **10 × 3 × 2 mm** (korrigierte Nutzervorgabe).
- Sieben Klebetaschen an den OEM-Positionen, nominal **10,2 × 3,2 mm**:
  0,1 mm Spiel pro Seite.
- Einsetzen von der **HMD-Seite**, wie beim Community-Mod. Die duenne
  urspruengliche Abdeckung ueber den Magneten wird gezielt geoeffnet.
- Boden 0,1 mm hinter der nominalen Magnetrueckseite fuer Klebstoff.
  Die Magnete sind wie im OEM-Ring etwas gegenueber der Anlagekontur
  zurueckgesetzt; sie sind nicht automatisch buendig mit deren Aussenflaeche.
- Einbauspiel und Klebeverbindung sind noch am gedruckten Teil zu pruefen.

Die HMD-seitige Ringkontur bleibt ausserhalb der sieben Magnetoeffnungen
erhalten. Hinten ergaenzt ein Anschlussbereich den kuerzeren OEM-Ring.
Die Huelle und Verstaerkungen werden dort gegen die innere HMD-Abdeckung
freigeschnitten und duerfen die geschuetzte Magnetaufnahme nicht auffuellen.

## Bisherige Passform

Die bestaetigte VRcover-Kontur, Polsterberechnung und die Klebeflaeche bleiben
erhalten. Der Prototyp benutzt weiterhin eine nominell 1,5 mm starke Huelle.
Der neue Exportname lautet `PFDMR_Probe_09.3mf`, damit der bisherige
Probe-07-Druck unterscheidbar bleibt. Alte Programmversionen und Druckdateien
werden nicht ueberschrieben.

Die Kollisionswarnung bleibt eine geometrische Hilfe. Ihr Raster stammt nun
aus den vollstaendigen OEM-Referenzflaechen statt aus dem vereinfachten
Anzeigenetz. Das Innenleben, die bewegliche IPD-Verstellung, die eigentlichen
optischen Glasflaechen und zusaetzliche Korrekturlinsenadapter sind damit nicht
vollstaendig kalibriert. Seitliche Buegel und Hinterkopfteil bleiben aus der
vorderen Kollisionspruefung ausgeschlossen.

Alles bleibt lokal; diese Version veroeffentlicht keine Modelle oder Dateien.

Beim Bereinigen der druckbaren Basis wurden die HMD-seitigen Anlageflaechen
an 70427 Punkten mit dem Original verglichen (Magnetoeffnungen ausgenommen).
Die groesste gemessene Abweichung betrug 0,00164 mm. Hinten wurden winzige
Ueberschneidungen und interne Restflaechen repariert. Das ist keine mechanische
Pruefung des gedruckten Teils. Die Polster-Klebeflaeche wird weiterhin gegen
die vollstaendige berechnete Auflage geprueft.

Fuer STL waehlt die App automatisch das standardisierte ASCII-Format, falls
die geringere Zahlengenauigkeit von binaerer STL verschiedene Kantenpunkte
zusammenfallen lassen wuerde. Diese Dateien koennen groesser sein. 3MF bleibt
die Voreinstellung. Der reale Workflow-Export wurde in beiden Formaten erneut
eingelesen; auch PrusaSlicer erkennt einen zusammenhaengenden geschlossenen
Koerper. PrusaSlicer verwirft bei seiner internen Rundung einige verschwindend
kleine Dreiecke automatisch.

Aktueller Anschluss, Nasenblende und Top-Strap: siehe PROBE09.md.
Die HMD-Referenz enthaelt noch unvollstaendige Innengeometrie.
