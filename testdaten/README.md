# Externe Testdaten

Dieser Ordner enthält öffentliche Beispieldokumente aus zwei GitHub-Projekten. Sie
ergänzen die selbst erzeugten, fiktiven Dokumente aus `scripts/sample_documents.py`.
Alle Firmen und Personen in diesen Dokumenten sind Musterdaten
(„Lieferant GmbH“, „Kunden AG Mitte“, „Max Mustermann“). Es sind keine echten
Mandantenunterlagen enthalten.

## Inhalt

| Ordner | Dateien | Herkunft | Zweck |
|---|---|---|---|
| `rechnungen_zugferd/` | 10 PDF | ZUGFeRD-Corpus, Musterrechnungen von intarsys (ZUGFeRD 2.0) | Eingangs- und Ausgangsrechnungen mit echten deutschen Rechnungslayouts |
| `grenzfaelle/` | 4 PDF | ZUGFeRD-Corpus (intarsys, Mustangproject, FNFE) | Gutschrift, „Buchungshilfe – KEINE Rechnung“, englische und französische Rechnung |
| `xrechnung_xml/` | 2 XML | XRechnung-Testsuite der KoSIT | reine XML-E-Rechnung (UBL und CII) – Negativtest für die Dateiprüfung |
| `manifest.csv` | – | eigene Festlegung | Mandant, erwartete Dokumentart und erwarteter Zeitraum je Datei |
| `ergebnisse.csv` | – | wird erzeugt | Ergebnis des letzten Laufs von `scripts/evaluate_testdaten.py` |
| `LICENSES/` | 2 TXT | – | Lizenztexte der beiden Quellen (Apache 2.0) |

Die Spalte `mandant` in `manifest.csv` legt fest, aus wessen Sicht das Dokument
hochgeladen wird. Ist der Mandant der Käufer, wird eine Eingangsrechnung erwartet.
Ist er der Verkäufer, wird eine Ausgangsrechnung erwartet.

## In die Web-App hochladen

```bash
python -m scripts.seed_demo --testdaten
```

Das Skript legt die Firmen aus `manifest.csv` als Mandanten an (Nummern ab 20001)
und lädt jedes Dokument über denselben Ablauf hoch wie der persönliche Upload-Link
(„Automatisch erkennen“). Danach liegen die Dateien in `storage/<Mandant>/…` und
erscheinen im Dashboard und in der Upload-Historie des Mandanten. Ein erneuter
Aufruf lädt nichts doppelt hoch.

## Nur die Erkennung prüfen

```bash
# Erkennungstest mit Tabelle in der Konsole, schreibt testdaten/ergebnisse.csv
python -m scripts.evaluate_testdaten

# als Teil der Testsuite
pytest tests/test_testdaten.py
```

Es wird nichts in der Datenbank oder in `storage/` angelegt. Zum manuellen Testen
können die Dateien auch über den Upload-Link eines Mandanten hochgeladen werden:
Dazu einen Mandanten mit dem Namen aus `manifest.csv` anlegen (z. B. „Kunden AG Mitte“).

## Ergebnis (Stand 31.10.2026)

13 von 16 Dokumenten werden wie erwartet erkannt:

* alle 10 deutschen ZUGFeRD-Rechnungen bis auf eine: Art, Richtung und Monat stimmen;
* die Gutschrift wird richtig als Eingangsrechnung erkannt;
* die französische Rechnung landet im Posteingang („Prüfung nötig“);
* beide XML-Dateien werden mit „Dateityp nicht erlaubt“ abgelehnt.

Drei Fälle zeigen Grenzen der regelbasierten Erkennung. Sie sind in
`tests/test_testdaten.py` als `xfail` markiert:

| Datei | Erwartet | Erkannt | Ursache |
|---|---|---|---|
| `zugferd_2p0_BASIC_Taxifahrt.pdf` | Ausgangsrechnung 10/2018 | Eingangsrechnung 10/2018 | Im Block „Verkäufer:“ steht keine USt-IdNr./IBAN direkt neben dem Namen. Die Beschriftungen „Verkäufer“/„Käufer“ werden noch nicht ausgewertet. |
| `MustangGnuaccountingBeispielRE-20201121_508.pdf` | Ausgangsrechnung 11/2020 | Posteingang | Englische Rechnung: nur „invoice“ (3 Punkte) ist bekannt, das reicht nicht für „mittel“. |
| `zugferd_2p0_MINIMUM.pdf` | Posteingang | Eingangsrechnung 03/2018 | „Buchungshilfe – KEINE Rechnung“: Verneinungen werden nicht erkannt. |

Zusätzlich zeigt der Upload in die Web-App einen Fehler beim Abgleich des
Mandantennamens. Die Spalte `mandant_gefunden` in `ergebnisse.csv` macht ihn sichtbar:

| Mandant | Was passiert | Folge |
|---|---|---|
| Kunden AG Mitte | `core_company_name()` entfernt die Rechtsform auch in der Mitte des Namens: „kunden mitte“ wird im Text „Kunden AG Mitte“ nicht gefunden. | 4 Dokumente landen im richtigen Ordner, sind aber als „Prüfung nötig“ markiert. Die Rechnungsrichtung stimmt nur, weil „nicht gefunden“ als Eingangsrechnung gewertet wird. |
| Metallbau Leipzig GmbH & Co. KG | Der Punkt aus „Co.“ bleibt stehen: „metallbau leipzig .“ | 1 Dokument als „Prüfung nötig“ markiert |

Das Verhalten ist sicher (kein Dokument wird falsch abgelegt), erzeugt aber unnötige
Prüfaufträge.

Behebt eine Regeländerung einen dieser Fälle, schlägt der `xfail`-Test bewusst fehl
(`strict=True`). Dann den Eintrag aus `KNOWN_LIMITATIONS` entfernen.

## Weitere Quellen (nicht enthalten)

Diese Quellen konnten nicht automatisch heruntergeladen werden oder dürfen nicht
weiterverteilt werden. Sie können bei Bedarf manuell ergänzt werden. Anschließend
eine Zeile in `manifest.csv` hinzufügen.

| Dokumentart | Quelle | Hinweis |
|---|---|---|
| Kassenbeleg (Foto) | SROIE, https://huggingface.co/datasets/Voxel51/scanned_receipts | englisch/asiatisch, nur für OCR-Robustheit |
| Kassenbeleg (Foto) | CORD, https://huggingface.co/datasets/naver-clova-ix/cord-v2 | indonesisch, Lizenz CC BY 4.0 |
| Negativtests | RVL-CDIP, https://huggingface.co/datasets/aharley/rvl_cdip | Briefe, Memos, Formulare; TIFF vorher in PNG umwandeln |
| Ausweis | Musterausweis „Erika Mustermann“, https://www.personalausweisportal.de | Abbildung des BMI, nur lokal verwenden |
| Gewerbeanmeldung | Vordruck GewA 1, z. B. https://www.heilbronn.de | mit Fantasiedaten ausfüllen |
| Vollmacht | Amtliches Muster des BMF, https://www.formulare-bfinv.de | mit Fantasiedaten ausfüllen |
| Kontoauszug, Z-Bericht | keine öffentliche Quelle | selbst erzeugen mit `scripts/sample_documents.py` |

## Quellen und Lizenzen

* **ZUGFeRD-Corpus** – https://github.com/ZUGFeRD/corpus, Apache License 2.0
  (`LICENSES/ZUGFeRD-corpus_Apache-2.0.txt`). Stand: Commit `82e886f` vom 13.10.2026.
  Verwendet: `ZUGFeRDv2/correct/intarsys/…`, `ZUGFeRDv2/correct/Mustangproject/…`,
  `ZUGFeRDv2/correct/FNFE-factur-x-examples/Facture_FR_BASICWL.pdf`.
* **XRechnung Test Suite** der Koordinierungsstelle für IT-Standards (KoSIT) –
  https://github.com/itplr-kosit/xrechnung-testsuite, Apache License 2.0
  (`LICENSES/XRechnung-Testsuite_Apache-2.0.txt`). Stand: Commit `1ce1daf` vom 04.09.2026.
  Verwendet: `src/test/business-cases/standard/01.01a-INVOICE_ubl.xml` und `…_uncefact.xml`.

Die Dateien wurden unverändert übernommen.
