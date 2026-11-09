# DocFlow - Automated Client Document Intake & Routing

**Proof of Concept · Project: Digitalization and Automation Hackathon (DLBCCOEDAH01)**

**Studentin:** Amira Sahraoui

**Hochschule:** IU International University of Applied Sciences


DocFlow ist eine Webanwendung, über die Mandanten ihre Unterlagen über einen persönlichen Upload-Link einreichen. Das System legt jedes Dokument anhand fest definierter Geschäftsregeln automatisch in der richtigen digitalen Mandantenakte und im richtigen Unterordner ab.

> **Hinweis:** Der aktuelle Prototyp simuliert die betriebliche Dokumentenablage mit lokalem Storage. Eine produktive Integration in SharePoint ist bewusst nicht Teil des Proof of Concept. Es werden ausschließlich fiktive Testdaten verwendet.

---

## Inhalt

1. [Problemstellung](#problemstellung)
2. [Ziel](#ziel)
3. [Architektur](#architektur)
4. [Technologie-Stack](#technologie-stack)
5. [Installation](#installation)
6. [Startanleitung](#startanleitung)
7. [Beispiel-Workflow](#beispiel-workflow)
8. [Ordnerstruktur](#ordnerstruktur)
9. [Tests starten](#tests-starten)
10. [Screenshots](#screenshots)
11. [Getroffene Annahmen](#getroffene-annahmen)
12. [Limitationen](#limitationen)
13. [Future Work](#future-work)

---

## Problemstellung

In Steuerberatungs- und Buchhaltungskanzleien erreichen Mandantenunterlagen das Büro meist per E-Mail, auf Papier oder über unstrukturierte Datei-Freigaben. Mitarbeitende müssen jedes Dokument öffnen, einordnen, umbenennen und manuell in die richtige Mandantenakte verschieben. Das kostet Zeit, ist fehleranfällig und führt zu uneinheitlichen Ablagen.

## Ziel

DocFlow automatisiert den Eingang und die Ablage:

- Jeder Mandant erhält einen **persönlichen, nicht erratbaren Upload-Link**.
- Der Mandant lädt nur die Datei hoch. DocFlow **erkennt Dokumentart und Zeitraum automatisch** aus dem Inhalt (regelbasiert, bei Fotos/Scans per OCR). Alternativ kann der Mandant die Art selbst wählen; sie wird dann auf Plausibilität geprüft.
- Eine **Routing Engine** bestimmt den Zielordner nach festen Regeln. Der Mandant wählt nie einen internen Ordner.
- Bei **hoher Erkennungssicherheit** wird das Dokument automatisch im Zielordner abgelegt. Bei **mittlerer Sicherheit oder widersprüchlichen Angaben** wird es abgelegt und als **„Prüfung nötig“** markiert. **Nicht eindeutig klassifizierbare** Dokumente gelangen in den **Posteingang** (ebenfalls „Prüfung nötig“).
- Dateien werden **validiert**, **einheitlich benannt** und **nie überschrieben**.
- Jeder Upload wird **protokolliert** und erscheint im **Mitarbeiter-Dashboard**.
- Mitarbeiter können jedes Dokument **im Browser öffnen** und eine falsche Einordnung **korrigieren**. Die Datei wird dabei automatisch verschoben (Human in the Loop).

---

## Architektur

Schlanker Monolith mit klarer Schichtentrennung. Jede Schicht kennt nur die darunterliegende.

```
┌──────────────────────────────────────────────────────────────┐
│  WEB-LAYER  (FastAPI-Routen + Jinja2-Templates)              │
│  routes/dashboard.py · routes/customers.py · routes/uploads.py│
│  → nimmt Formulare an, ruft Services auf, rendert HTML       │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  SERVICE-LAYER  (Geschäftslogik, unabhängig vom Web)         │
│  customer_service   Mandant + Token + Ordnerstruktur         │
│  upload_service     orchestriert den Upload:                 │
│    ├─ validation_service  Endung, Größe, Dateisignatur       │
│    ├─ text_extraction_service  PDF-Text / OCR (optional)     │
│    ├─ classification_service   Dokumentart + Zeitraum (Regeln)│
│    ├─ routing_service     Dokumentart+Zeitraum → Zielordner  │
│    ├─ filename_service    sicherer, eindeutiger Dateiname    │
│    └─ storage_service     Datei speichern                    │
│  dashboard_service  Kennzahlen + Upload-Historie             │
│  document_service   Dokument öffnen + Einordnung korrigieren │
│  domain/document_types.py  zentraler Dokumentarten-Katalog   │
└───────────────┬────────────────────────────┬─────────────────┘
┌───────────────▼──────────────┐  ┌──────────▼─────────────────┐
│  DATENBANK                   │  │  STORAGE                   │
│  SQLAlchemy 2.0 + SQLite     │  │  StorageService (abstrakt) │
│  customers, documents        │  │   └─ LocalStorageService   │
└──────────────────────────────┘  └────────────────────────────┘
```

**Zentrale Designentscheidungen**

| Entscheidung | Begründung |
|---|---|
| Routing liefert nur relative, logische Pfade | Die Routing-Logik kennt kein Dateisystem. `LocalStorageService` lässt sich später durch `SharePointStorageService` ersetzen, ohne das Routing zu ändern. |
| Dokumentarten-Katalog als einzige Wahrheitsquelle | Dropdown, Validierung, Routing, Ordnerstruktur und Dateiname werden aus derselben Tabelle abgeleitet. Eine neue Dokumentart ist eine einzige Zeile. |
| `upload_service` als Orchestrator | Die Upload-Route bleibt dünn; jeder Schritt ist einzeln testbar. |
| Dependency Injection über `app.state` | Tests erzeugen eigene App-Instanzen mit temporärer Datenbank und temporärem Storage. |
| Erkennung liefert dieselben Eingaben wie der Mandant | Die Klassifikation bestimmt nur Dokumentart, Jahr und Monat. Die Routing Engine bleibt unverändert, egal ob die Angaben vom Mandanten oder von der Erkennung kommen. |
| Regeln statt KI | Jede Entscheidung ist nachvollziehbar (gefundene Begriffe werden gespeichert und angezeigt), läuft offline und sendet keine Mandantendaten an Dritte. |
| `documents`-Tabelle als Audit-Log | Jeder Versuch (erfolgreich oder fehlgeschlagen) wird mit Zeitpunkt, Mandant, Datei, Kategorie und Ziel gespeichert. |

**Sicherheitsmaßnahmen**

- Upload-Token mit `secrets.token_urlsafe(32)` (ca. 256 Bit Zufall). Der Firmenname ist **kein** Bestandteil des Links.
- Zielpfade werden ausschließlich aus Whitelist-Werten gebildet: gespeicherter Ordnername, Katalogwerte, ganzzahliges Jahr und Monat.
- `LocalStorageService` prüft zusätzlich jeden Pfad (`..`, absolute Pfade, `resolve()` + `is_relative_to`).
- Dateien werden exklusiv angelegt (`open("xb")`). Ein Überschreiben ist technisch ausgeschlossen.
- Validierung von Endung **und Dateiinhalt** (Magic Bytes). Eine in `rechnung.pdf` umbenannte `.exe` wird abgelehnt.
- Der Mitarbeiterbereich `/admin/*` ist per HTTP Basic Auth geschützt. Der Mandant sieht weder andere Mandanten noch interne Pfade.

Ausführlicher in [`docs/ARCHITEKTUR.md`](docs/ARCHITEKTUR.md).

### Datenmodell

```
customers                          documents
───────────────────────            ──────────────────────────────
id              PK                 id                 PK
company_name                       customer_id        FK → customers.id
customer_number UNIQUE             original_filename
folder_name     UNIQUE             stored_filename    (nullable)
upload_token    UNIQUE, INDEX      document_type
created_at                         year, month        (nur FIBU)
                                   destination_path   (nullable)
        1 ─────────────── n        status             SUCCESS | FAILED
                                   error_message      (nullable)
                                   uploaded_at

document_analyses   (Ergebnis der Erkennung, 1:1 zu documents)
──────────────────────────────────────────────
id, document_id → documents.id (UNIQUE), method (automatisch | manuell),
text_source (pdf-text | ocr | keine), detected_type, detected_year,
detected_month, confidence (hoch | mittel | niedrig), score, evidence,
needs_review, review_reason, reviewed_by, reviewed_at

document_corrections   (Audit der Mitarbeiter-Korrekturen)
──────────────────────────────────────────────
id, document_id → documents.id, old_document_type, old_year, old_month,
old_path, new_document_type, new_year, new_month, new_path,
corrected_by, corrected_at
```

### Automatische Erkennung

```
Upload ─► Text auslesen ─────────► Regeln anwenden ─────────► Entscheidung (Erkennungssicherheit)
          PDF-Text (pypdf)         Schlüsselbegriffe          hoch    → Zielordner (Routing)
          Foto/Scan → OCR          Rechnungsrichtung          mittel  → Zielordner + „Prüfung nötig“
          (RapidOCR, optional)     Datum → Zeitraum           niedrig → Posteingang_Ungeklaert + „Prüfung nötig“
```

1. **Text auslesen:** PDFs aus Buchhaltungs- oder Bankprogrammen enthalten eine Textebene, die direkt gelesen wird. Fotos und gescannte PDFs werden per OCR gelesen, sofern `requirements-ocr.txt` installiert ist (siehe [OCR einrichten](#ocr-einrichten-optional)).
2. **Dokumentart:** Für jede Dokumentart gibt es gewichtete Schlüsselbegriffe, z. B. „Rechnungsnummer“, „Alter Saldo“, „Z-Bericht“, „§ 14 GewO“. Die Art mit den meisten Punkten gewinnt. Der Dateiname zählt nur mit halbem Gewicht.
3. **Eingangs- oder Ausgangsrechnung:** Steht der Mandantenname im Briefkopf bzw. in der Fußzeile (neben USt-IdNr., IBAN, Geschäftsführer …), ist der Mandant Rechnungssteller, also **Ausgangsrechnung**. Steht er nur im Adressfeld, ist es eine **Eingangsrechnung**.
4. **Zeitraum:** Bevorzugt aus beschrifteten Zeilen (Leistungszeitraum, Rechnungsdatum, Auszugszeitraum, Tagesabschluss). Fälligkeits- oder Gültigkeitsdaten werden ignoriert. Sonst gilt der häufigste Monat im Dokument (typisch für Kontoauszüge).
5. **Sicherheit:** „hoch“ bei klarer Punktzahl und deutlichem Abstand zur zweitbesten Art, sonst „mittel“ oder „niedrig“.

**Wann muss ein Mitarbeiter prüfen?**

| Situation | Ergebnis |
|---|---|
| Art und Zeitraum sicher erkannt | direkt im Zielordner abgelegt |
| Art nicht erkannt (z. B. Notiz, unlesbares Foto) | `Posteingang_Ungeklaert`, Prüfung nötig |
| FIBU-Dokument ohne erkennbaren Zeitraum | `Posteingang_Ungeklaert`, Prüfung nötig |
| Erkennung nur mit Sicherheit „mittel“ | im Zielordner abgelegt, Prüfung nötig |
| Mandant wählt selbst eine Art, der Inhalt deutet auf eine andere hin | Wahl des Mandanten wird übernommen, Prüfung nötig |
| Gewählter Zeitraum weicht vom Dokument ab | Wahl des Mandanten wird übernommen, Prüfung nötig |
| Mandantenname steht nicht im Dokument (z. B. Kontoauszug eines anderen Mandanten) | Prüfung nötig |

Der Mandant muss in keinem Fall etwas nachreichen. Er erhält eine Bestätigung, und die Kanzlei bzw. Beratung übernimmt die Zuordnung.

### Prüfung durch Mitarbeiter (Human in the Loop)

1. Das Dashboard zeigt die Kennzahl **„Prüfung nötig“**. Betroffene Zeilen haben einen gelben **Prüfen**-Button.
2. Die Prüfseite zeigt das Dokument neben dem Erkennungsergebnis: gefundene Begriffe, Zeitraumquelle, Sicherheit und **Grund für die Prüfung**.
3. Ist die Einordnung richtig, genügt **Einordnung ist korrekt – bestätigen**.
4. Ist sie falsch, ist der erkannte Vorschlag bereits vorausgewählt. Ein Klick auf **Korrigieren & verschieben** genügt. DocFlow berechnet den neuen Zielordner mit derselben Routing Engine und verschiebt die Datei, ohne etwas zu überschreiben.
5. Jede Korrektur wird in `document_corrections` protokolliert, jede Prüfung in `document_analyses` (wer, wann). Die Zahl der Korrekturen ist damit eine direkte Kennzahl für **Fehlablagen**.

### Routing-Regeln

| Eingabe | Zielordner |
|---|---|
| Eingangsrechnung + März 2026 | `Muster_GmbH/FIBU/2026/03_Maerz/Eingangsrechnungen/` |
| Ausgangsrechnung + Mai 2026 | `Muster_GmbH/FIBU/2026/05_Mai/Ausgangsrechnungen/` |
| Kontoauszug + April 2026 | `Muster_GmbH/FIBU/2026/04_April/Bank/` |
| Kassenbeleg / Z-Bericht + Februar 2026 | `Muster_GmbH/FIBU/2026/02_Februar/Kasse_Z_Berichte/` |
| Gewerbeanmeldung | `Muster_GmbH/Stammdaten/Gewerbeanmeldung/` |
| Bankverbindungsdaten | `Muster_GmbH/Stammdaten/Bankverbindungsdaten/` |

**Dateinamen:** `2026-03_Eingangsrechnung_Rechnung123.pdf` (FIBU) bzw. `2026-10-11_Gewerbeanmeldung_Scan.pdf` (Stammdaten, Präfix = Upload-Datum). Bei gleichem Namen folgen `_2`, `_3`, …

---

## Technologie-Stack

| Bereich | Technologie |
|---|---|
| Backend | Python 3.11+, FastAPI |
| Frontend | Jinja2, HTML, Bootstrap 5 (CDN), wenig JavaScript |
| Datenbank | SQLite, SQLAlchemy 2.0 |
| Ablage | lokales Dateisystem (`storage/`) |
| Erkennung | `pypdf` (PDF-Text); optional OCR mit `rapidocr` + `onnxruntime` (nur pip, offline), `pypdfium2` für gescannte PDFs |
| Tests | pytest, FastAPI TestClient |

---

## Installation

Voraussetzung: **Python 3.11 oder neuer**.

```bash
cd docflow
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### OCR einrichten (optional, nur pip)

Ohne OCR funktioniert DocFlow vollständig. **PDFs mit Textebene** werden immer erkannt. **Fotos und Scans** landen dann im Posteingang zur Prüfung. Damit auch sie automatisch erkannt werden, installierst du in der aktivierten `.venv`:

```bash
pip install -r requirements-ocr.txt
```

Das installiert **RapidOCR** und **onnxruntime**. Ein Zusatzprogramm ist nicht nötig, die Erkennungsmodelle stecken bereits im Paket, und die Erkennung läuft komplett offline. Nach dem Neustart erscheint in der Konsole `OCR aktiv: RapidOCR`. Das erste Foto dauert wegen des Modellladens etwa 2 bis 3 Sekunden, danach geht es schneller.

Alternativ wird auch **Tesseract** unterstützt, falls es bereits installiert ist (`DOCFLOW_OCR_ENGINE=tesseract`).

## Startanleitung

```bash
# optional: fiktive Demo-Mandanten und Beispieldokumente (samples/) anlegen
python -m scripts.seed_demo

# optional: zusätzlich die Testfirmen aus testdaten/ anlegen und deren
# 16 Testdokumente automatisch hochladen (siehe testdaten/README.md)
python -m scripts.seed_demo --testdaten

# Anwendung starten
python run.py
```

Danach im Browser öffnen: **http://localhost:8000**

| Bereich | URL | Zugang |
|---|---|---|
| Mitarbeiter-Dashboard | http://localhost:8000/admin | Benutzer `admin`, Passwort `docflow` |
| Mandantenverwaltung | http://localhost:8000/admin/customers | wie oben |
| Kunden-Uploadseite | http://localhost:8000/upload/&lt;TOKEN&gt; | nur über den persönlichen Link |

**Konfiguration** über Umgebungsvariablen (alle optional):

| Variable | Standard | Bedeutung |
|---|---|---|
| `DOCFLOW_MAX_UPLOAD_SIZE_MB` | `10` | maximale Dateigröße |
| `DOCFLOW_STORAGE_DIR` | `./storage` | Ablageverzeichnis |
| `DOCFLOW_DATABASE_URL` | `sqlite:///./docflow.db` | Datenbank |
| `DOCFLOW_LOG_DIR` | `./logs` | Logdateien |
| `DOCFLOW_BASE_URL` | `http://localhost:8000` | Basis für Upload-Links |
| `DOCFLOW_ADMIN_USER` / `DOCFLOW_ADMIN_PASSWORD` | `admin` / `docflow` | Zugang Mitarbeiterbereich |
| `DOCFLOW_OCR` | `1` | `0` schaltet OCR ab |
| `DOCFLOW_OCR_ENGINE` | `auto` | `rapidocr` oder `tesseract` (auto = RapidOCR, sonst Tesseract) |
| `DOCFLOW_TESSERACT_CMD` | automatisch | nur für Tesseract: Pfad zu `tesseract.exe` |

---

## Beispiel-Workflow

1. `python -m scripts.seed_demo` ausführen. Das legt drei Demo-Mandanten und im Ordner `samples/` fiktive Dokumente für die Muster GmbH an.
2. `python run.py` starten und **http://localhost:8000/admin** öffnen (Login `admin` / `docflow`).
3. **Mandanten → Muster GmbH → Öffnen** beim Upload-Link (Kundenansicht).
4. Eine Datei aus `samples/` wählen, die Dokumentart auf **Automatisch erkennen** lassen und hochladen:

| Datei | Ergebnis |
|---|---|
| `Eingangsrechnung_Buerobedarf.pdf` | `FIBU/2026/03_Maerz/Eingangsrechnungen/` |
| `Ausgangsrechnung_2026-005.pdf` | `FIBU/2026/05_Mai/Ausgangsrechnungen/` |
| `Kontoauszug_April.pdf` | `FIBU/2026/04_April/Bank/` |
| `Z-Bericht_Februar.pdf` | `FIBU/2026/02_Februar/Kasse_Z_Berichte/` |
| `Gewerbeanmeldung.pdf` | `Stammdaten/Gewerbeanmeldung/` |
| `Kassenbon_Foto.png` | mit OCR: `FIBU/2026/06_Juni/Kasse_Z_Berichte/`, ohne OCR: Posteingang |
| `Besprechungsnotiz.pdf` | `Posteingang_Ungeklaert/` und „Prüfung nötig“ |

5. Im **Dashboard** erscheinen die Uploads mit dem Hinweis „automatisch erkannt“. Die Kennzahl „Prüfung nötig“ zählt offene Fälle.
6. **Fehleinordnung testen:** `Z-Bericht_Februar.pdf` hochladen und dabei selbst *Kontoauszug / Bank* wählen. Das Dokument wird gelb markiert. Auf der Prüfseite ist „Z-Bericht“ vorausgewählt, und **Korrigieren & verschieben** legt es richtig ab.

---

## Ordnerstruktur

### Projekt

```
docflow/
├── app/
│   ├── main.py                 # Einstiegspunkt (uvicorn app.main:app)
│   ├── application.py          # App-Factory + Logging-Setup
│   ├── config.py               # zentrale Konfiguration
│   ├── dependencies.py         # DB-Session, Storage, Admin-Login
│   ├── templating.py           # Jinja2 + Anzeige-Filter
│   ├── domain/
│   │   ├── document_types.py   # Katalog der Dokumentarten
│   │   ├── periods.py          # Monate, Zeiträume
│   │   └── exceptions.py       # fachliche Fehler mit Nutzertext
│   ├── routes/                 # dashboard, customers, documents, uploads
│   ├── services/               # customer, upload, routing, storage,
│   │                           # validation, filename, dashboard, document,
│   │                           # text_extraction, classification
│   ├── database/               # database.py, models.py
│   ├── templates/              # Jinja2-Templates
│   └── static/css/docflow.css
├── scripts/
│   ├── seed_demo.py            # Demo-Mandanten + Beispieldokumente
│   ├── sample_documents.py     # fiktive Rechnungen, Kontoauszug, Z-Bericht …
│   └── evaluate_testdaten.py   # Erkennungstest mit den externen Testdaten
├── testdaten/                  # öffentliche Beispielrechnungen (ZUGFeRD, XRechnung),
│                               # manifest.csv mit erwarteten Ergebnissen, Lizenzen
├── tests/                      # pytest-Tests
├── docs/ARCHITEKTUR.md
├── storage/                    # simulierte Mandantenablage (nicht im Git)
├── logs/                       # Logdateien (nicht im Git)
├── requirements.txt
├── requirements-ocr.txt        # optional: OCR für Fotos/Scans
└── run.py
```

### Mandantenakte (wird automatisch erzeugt)

```
storage/Muster_GmbH/
├── Posteingang_Ungeklaert/     # nicht sicher erkannte Dokumente
├── Stammdaten/
│   ├── Gewerbeanmeldung/  Steuernummer/  Betriebsnummer/
│   ├── Unternehmensnummer_BG/  Bankverbindungsdaten/
│   ├── Vollmacht_Dienstleistungsvertrag/  Ausweis/
│   ├── Eroeffnungsbilanz/  USt_IdNr/  Sonstige/
└── FIBU/
    └── 2026/
        ├── 01_Januar/   Eingangsrechnungen/ Ausgangsrechnungen/ Bank/ Kasse_Z_Berichte/
        ├── 02_Februar/  …
        └── 12_Dezember/ …
```

Wird ein Dokument für ein noch nicht vorhandenes Jahr hochgeladen, legt DocFlow die komplette Jahresstruktur automatisch an.

---

## Tests starten

```bash
pytest
```

Die Tests laufen mit eigener temporärer Datenbank und eigenem temporärem Storage. Das echte `storage/` bleibt unberührt.

| Pflichttest | Testfunktion |
|---|---|
| 1. Mandant erstellt → Ordnerstruktur existiert | `test_customers.py::test_create_customer_creates_folder_structure` |
| 2. eindeutiger Upload-Token | `test_customers.py::test_customer_gets_unique_upload_token` |
| 3. Eingangsrechnung März 2026 | `test_routing.py::test_eingangsrechnung_maerz_2026`, `test_uploads.py::test_eingangsrechnung_upload_lands_in_correct_folder` |
| 4. Kontoauszug April 2026 | `test_routing.py::test_kontoauszug_april_2026` |
| 5. Z-Bericht Februar 2026 | `test_routing.py::test_z_bericht_februar_2026` |
| 6. Gewerbeanmeldung | `test_routing.py::test_gewerbeanmeldung` |
| 7. .exe wird abgelehnt | `test_uploads.py::test_exe_file_is_rejected` |
| 8. ungültiger Token → Zugriff verweigert | `test_uploads.py::test_invalid_token_is_denied` |
| 9. neues Jahr → Struktur wird erzeugt | `test_uploads.py::test_missing_year_structure_is_created` |
| 10. doppelter Dateiname → kein Überschreiben | `test_storage.py::test_duplicate_filename_does_not_overwrite` |

Zusätzlich werden Path Traversal, umbenannte `.exe`, Dateigröße, fehlende Angaben, Admin-Login, Kundenansicht sowie Öffnen und Korrigieren von Dokumenten geprüft.

**Automatische Erkennung** (`test_classification.py`, `test_auto_upload.py`): Erkennung aller Beispieldokumente allein aus dem Inhalt, Eingangs- vs. Ausgangsrechnung, Datumsformate, ignorierte Fälligkeitsdaten, Posteingang bei unklaren Dokumenten, Markierung falscher Mandantenangaben und fremder Dokumente, Bestätigen und Korrigieren durch Mitarbeiter. Die OCR-Tests (Kassenbon-Foto, eingescanntes PDF ohne Textebene) laufen nur, wenn `requirements-ocr.txt` installiert ist. Sonst werden sie übersprungen. Zusätzlich wird geprüft, dass falsch gelesene Umlaute („Røckgeld“) die Erkennung nicht stören.

**Externe Testdaten** (`test_testdaten.py`): 16 öffentliche Beispieldokumente aus dem ZUGFeRD-Corpus und der XRechnung-Testsuite der KoSIT (Ordner `testdaten/`). 13 werden wie erwartet erkannt bzw. abgelehnt. Drei bekannte Grenzen (Verkäufer-Block ohne Steuermerkmal, englische Rechnung, „KEINE Rechnung“) sind als erwartete Fehlschläge (`xfail`) dokumentiert, nicht als bestanden. Details und Quellen: [`testdaten/README.md`](testdaten/README.md). Eine Tabelle mit Laufzeiten erzeugt:

```bash
python -m scripts.evaluate_testdaten
```

Insgesamt 135 Tests: 132 bestanden, 3 erwartete Fehlschläge (`xfail`). Die `xfail`-Tests dokumentieren bekannte Grenzen und zählen nicht als bestanden.

---

## Screenshots

Die Screenshots des Prototyps liegen in der Abgabe unter `Phase2_Development/Supporting_Evidence/Screenshots/`:

| Ansicht | Datei |
|---|---|
| Kunden-Uploadseite | `01_Upload_Mandant.png` |
| Upload automatisch erkannt | `02_Bestaetigung_automatisch_erkannt.png` |
| Dashboard | `03_Dashboard.png` |
| Mandantenliste | `04_Mandantenliste.png` |
| Mandant anlegen | `05_Mandant_anlegen.png` |
| Mandant angelegt mit Upload-Link | `06_Mandant_angelegt_Upload-Link.png` |
| Mandantendetail mit Upload-Historie | `07_Mandantendetail_Upload-Historie.png` |
| Dokument prüfen (Fehleinordnung) | `08_Pruefung_Fehleinordnung.png` |
| Nach der Korrektur | `09_Nach_Korrektur.png` |
| Dashboard mit öffentlichen Testdaten | `10_Dashboard_Testdaten.png` |
| Mandanten mit Testfirmen | `11_Mandanten_Testdaten.png` |

---

## Getroffene Annahmen

- **Mitarbeiterbereich:** Geschützt per HTTP Basic Auth mit einem festen Zugang aus der Konfiguration. Bewusst keine Benutzerverwaltung.
- **Interne Customer-ID:** Autoincrement-ID der Datenbank. Sie erscheint nie in Kunden-URLs.
- **Ordnername:** Wird beim Anlegen einmalig aus dem Firmennamen gebildet (Umlaute transliteriert) und gespeichert. Bei Namensgleichheit wird die Mandantennummer angehängt (`Muster_GmbH_10004`).
- **Mandantennummer:** Nur Ziffern, eindeutig.
- **Zeitraum-Auswahl:** Die letzten 36 Monate. Serverseitig sind die Jahre 2000 bis aktuelles Jahr + 1 erlaubt.
- **Stammdaten-Dateinamen:** Erhalten das Upload-Datum als Präfix.
- **Zeitstempel:** Gespeichert in UTC, angezeigt in deutscher Zeit (Europe/Berlin).
- **Kennzahl „Dokumente gesamt“:** Zählt alle Upload-Vorgänge (erfolgreich + fehlgeschlagen). Die Mandantenliste zählt nur erfolgreich gespeicherte Dokumente.
- **Datenbank-Schema:** Wird beim Start per `create_all` angelegt. Keine Migrationen (Alembic) im PoC. Neue Tabellen kommen bei bestehenden Datenbanken automatisch hinzu.
- **Erkennung regelbasiert:** bewusst keine KI bzw. kein Sprachmodell. Die Entscheidungen sind erklärbar, laufen offline und geben keine Mandantendaten weiter.
- **Wahl des Mandanten hat Vorrang:** Wählt der Mandant die Art selbst, wird sie übernommen. Widerspricht der Inhalt, wird das Dokument nur zur Prüfung markiert.
- **Eingangs- vs. Ausgangsrechnung:** wird über die Position des Mandantennamens bestimmt (Briefkopf/Fußzeile = Absender).

## Limitationen

- Lokale Ablage statt SharePoint; kein Mehrbenutzerbetrieb, keine Rollen.
- **Erkennung ist heuristisch:** Die Regeln decken typische deutsche Belege ab. Ungewöhnliche Layouts, Handschrift oder schlechte Fotos werden nicht immer erkannt. Diese Fälle landen dann im Posteingang. Die Trefferquote sollte mit echten (anonymisierten) Belegen evaluiert und die Regeln ggf. nachgeschärft werden.
- **Test mit öffentlichen Beispielrechnungen** (`testdaten/`): Die Rechnungsrichtung wird über Steuermerkmale (USt-IdNr., IBAN …) neben dem Mandantennamen bestimmt, Beschriftungen wie „Verkäufer:“/„Käufer:“ werden noch nicht ausgewertet. Englische Rechnungen und Verneinungen („KEINE Rechnung“) werden nicht erkannt. Firmennamen mit Rechtsform in der Mitte („Kunden AG Mitte“) oder mit „& Co. KG“ werden im Dokument nicht gefunden – die Dokumente landen dann zusätzlich als „Prüfung nötig“ im Dashboard.
- OCR ist optional (`requirements-ocr.txt`). Umlaute liest die OCR teils fehlerhaft. Die Begriffssuche ist deshalb tolerant („Rückgeld“ = „Ruckgeld“ = „Rckgeld“). Handschrift wird kaum erkannt.
- Upload-Links laufen nicht ab und können nicht widerrufen werden.
- Kein Virenscan. Die Inhaltsprüfung beschränkt sich auf die Dateisignatur.
- Bootstrap wird per CDN geladen. Für eine vollständige Darstellung ist eine Internetverbindung nötig.
- Kein HTTPS. Für den produktiven Einsatz wäre ein Reverse Proxy mit TLS Pflicht.
- SQLite ist für Demo- und Einzelplatzbetrieb ausgelegt.

## Future Work

Die regelbasierte Erkennung samt OCR wurde gegenüber der ursprünglichen Planung vorgezogen und ist bereits Teil des Prototyps.


| Version | Erweiterung |
|---|---|
| **2** | **Lernende Klassifikation:** Die protokollierten Korrekturen (`document_corrections`) dienen als Trainingsdaten für ein ML-Modell, das die Regeln ergänzt. Zusätzlich können Betrag, Rechnungsnummer und Lieferant ausgelesen werden (z. B. für eine DATEV-Übergabe). |
| **3** | **SharePoint Storage Adapter:** `SharePointStorageService` implementiert das bestehende `StorageService`-Interface (z. B. über Microsoft Graph) und ersetzt `LocalStorageService` in `create_app()`. |
| **4** | **Benachrichtigungen:** automatische Erinnerung an fehlende Monatsunterlagen. Die Upload-Historie liefert bereits die nötigen Daten. |

Weitere Ideen: ablaufende bzw. widerrufbare Upload-Links, Mehrfach-Upload, Rollen und Rechte, Virenscan.
