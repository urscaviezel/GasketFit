# Probe 11 – GasketFit 0.13.1

Nachprüfung in 3D Builder: Der Export aus 0.13.0 löste dort trotz positiver
Prusa-Prüfung eine Reparaturmeldung aus. 0.13.1 bereitet vollständige Rahmen
deshalb vor dem Export mit der lokalen Windows-Printing3D-Funktion auf.
3D Builder muss dafür nicht installiert oder geöffnet sein. Es werden keine
Modelle hochgeladen. Die Windows-Funktion läuft in einem separaten Prozess
mit Zeitbegrenzung; bei Fehlern wird kein Ersatzexport ungeprüft gespeichert.

Diese abschließende Druckaufbereitung hat eine eigene numerische Grenze
von 0,005 mm. Alle Netzpunkte und alle Dreiecksmittelpunkte werden in beiden
Richtungen verglichen, dazu Geschlossenheit, Einzelkörper und Volumenänderung.
Damit umfasst die Prüfung auch Magnetaufnahme und Polsterfläche. Beim lokalen
Probe-11-Vergleich betrug die größte Punktverschiebung 0,003455 mm.
Die strengeren nachfolgenden Angaben beziehen sich auf die Konstruktion vor
dieser Druckaufbereitung. Die Sollmaße und Positionen werden nicht angepasst.

Der hintere Anschluss der Magnetbasis ist neu aufgebaut. Die HMD-seitige
Passkontur und sieben Taschen für 10 × 3 × 2 mm Magnete bleiben erhalten.
Der frühere Mod-Anschluss mit seinen angeschnittenen Resten entfällt.

Sieben äußere Verstärkungen: drei oben, zwei seitlich auf Höhe der Öffnung,
je eine links und rechts neben der Nase. Die seitlichen Stege verlaufen auf
konstanter Höhe nach hinten. Breitere, abgerundete Füße verbinden sie mit
Basis und Auflage; überstehende Abschnitte werden auf die Anschlussflächen
begrenzt. Die geschützte Klebefläche wird weiterhin vollständig geprüft.

Die Kopfbandhalterung folgt dem Prinzip des Community-Mods: runde Querstrebe
mit breiten diagonalen Stützen statt eines dünnen aufgesetzten Rahmens.
Die Querstrebe ist 6 mm stark; das 25-mm-Band hat seitliches Spiel.
Die tatsächliche Belastbarkeit ist noch am Druck zu prüfen.

Der Nasenübergang greift in den Ring ein. Nicht nur die globale Verbindung,
sondern auch ein Streifen entlang der gesamten Nasen-Anschlusskurve wird
geprüft. Vor dem Export wird die Geometrie bei der von Druckprogrammen
verwendeten Zahlengenauigkeit geschlossen aufgebaut und erneut geprüft.

Die Prüfungen unterscheiden die Konstruktionsgeometrie von Rundungsresten:
Erhaltene Passflächen dürfen beim Vergleich höchstens 0,0001 mm abweichen;
neu erscheinende boolesche Restflächen im Schutzbereich höchstens 0,001 mm
von der Basisoberfläche entfernt sein. Magnetmaße und Einsetzwege werden
zusätzlich mit geometrischen Prüfkörpern kontrolliert.

Bestehendes Projekt öffnen, in Schritt 4 die Nasenöffnung aus dem Scan
übernehmen und neu berechnen. Ausrichtung und bestätigte VRcover-Kontur
werden nicht automatisch verändert. Die HMD-Referenz bleibt vorläufig.
Alles bleibt lokal. Probe 10 und die bisherige App bleiben erhalten.
