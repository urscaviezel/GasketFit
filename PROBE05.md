# Probe 05 mit GasketFit 0.6.1

Diese lokale Testversion verwendet die mit VRcover und Klett bestätigte
**Probe 04** als Ausgangsfläche. Sie erzeugt eine an den Kopf angepasste
Polsterauflage mit **1,5 mm** Materialstärke. Adapterring und Verbindungshülle
sind weiterhin ein späterer Schritt.

## Ablauf

1. `GasketFit.exe` starten und einen Kopfscan laden. Der Kopf muss aufrecht
   stehen und nach vorne schauen. `free_head.3mf` benötigt **X +90°**.
2. Die orange Auflage an Stirn, Schläfen und Wangen positionieren. Ansichten
   vorne und seitlich prüfen. Alt + Ziehen verschiebt die Auflage; **Recenter**
   zentriert ausschließlich die Ansicht.
3. Als Startwert **6,5 mm wirksame Polsterdicke** verwenden. Das ist ein
   Versuchswert für das vorhandene 10-mm-VRcover, keine Komfortgarantie.
   Die gesamte zusätzliche Klettverbindung separat messen und eintragen;
   **0 mm** bedeutet noch nicht berücksichtigt. Die maximale Formanpassung
   beginnt bei **12 mm**. Ein Wert von 0 hält die Probe-04-Form unverändert.
4. **Auflage berechnen**. Deine manuelle Höhe, seitliche Zentrierung und Drehung
   bleiben unverändert. Der standardmäßig ausgeschaltete Feinabgleich darf nur
   den Abstand vor/zurück (Y) verändern. Auch bei älteren Projekten mit aktivem
   Feinabgleich bleiben Höhe und Drehung jetzt fest. Die Augen-Linsen-Ausrichtung
   wird weiterhin von dir gewählt, nicht automatisch erkannt.
5. Abstände prüfen: **Rot** liegt unter 3,5 mm, **Grün** zwischen 3,5 und 10 mm,
   **Blau** über 10 mm; die eingetragene Klettdicke wird jeweils dazugezählt.
   Diese Farben zeigen geometrischen Abstand, **keinen gemessenen Druck**.
   Die zweite Farbanzeige vergleicht Längen mit Probe 04.
6. Bei Warnungen die Abweichungen bewusst prüfen. Erst dann den Export als
   Probestück freigeben und **VRcover_Probe_05.3mf** oder STL speichern.
   Im Slicer Druckausrichtung und Vorschau prüfen. Der Export enthält nur
   die Auflage und liegt mit seinem tiefsten Punkt bei Z = 0.

Der Prüfbericht wird daneben als `.pruefung.json` gespeichert. Ein `.padfit`
Projekt enthält den privaten Kopfscan und Einstellungen und bleibt lokal.
Ältere Projekte mit der Flächenprojektion werden im neuen Workflow nicht
stillschweigend umgerechnet: dafür den Kopfscan neu laden.

## Was die Anpassung begrenzt

Die Höhenführung der bestätigten Form bleibt in ihrem eigenen Bezugssystem
unverändert. Die Berechnung darf die Auflage nur breit und weich in der
horizontalen Ebene biegen. Örtliche Kantenlängenänderungen gegenüber Probe 04
sind auf **4 %** begrenzt. Das ist eine experimentelle geometrische Grenze,
keine geprüfte Materialkennlinie des Kunstleders. Verbleibende Lücken werden
angezeigt, statt die Form ohne Begrenzung in den Scan zu drücken.

1,5-mm-Schalen können beim Aufsetzen noch nachgeben. Eine gleichmäßige
Druckverteilung, ein steifer Rahmen und eine korrekte Augen-Linsen-Ausrichtung
sind damit noch nicht bestätigt. Mit montiertem Polster und Klett testen.

DE und EN sind enthalten. Diese lokale Testausgabe startet mit automatischer
Sprach- und Updatesuche ausgeschaltet; beides lässt sich unter Settings ändern.
Es wurden keine Modelle oder Dateien veröffentlicht.

Die Referenzfläche wurde für diese lokale Erprobung aus Sir Dominiks
„Pfd 108Fov Face Gasket mod V2“ abgeleitet und anhand der Polstertests erweitert
und gekürzt. Die ursprünglichen Modelle und Probe 04 bleiben unverändert.
