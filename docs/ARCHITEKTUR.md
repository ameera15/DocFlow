# DocFlow – Architekturkonzept

Dieses Dokument beschreibt Architektur, Datenmodell, Routing-Konzept und Workflows des Proof of Concept.

## 1. Schichten

```
┌──────────────────────────────────────────────────────────────┐
│  WEB-LAYER (FastAPI-Routen + Jinja2-Templates)               │
│  → nimmt Formulardaten an, ruft Services auf, rendert HTML   │
│  → enthält KEINE Geschäftslogik                              │
└───────────────┬──────────────────────────────────────────────┘
┌───────────────▼──────────────────────────────────────────────┐
│  SERVICE-LAYER (Geschäftslogik, framework-unabhängig)        │
│  customer_service · upload_service · routing_service ·       │
│  validation_service · filename_service · storage_service ·   │
│  dashboard_service                                           │
│  domain/: document_types (Katalog) · periods · exceptions    │
└───────────────┬────────────────────────────┬─────────────────┘
┌───────────────▼──────────────┐  ┌──────────▼─────────────────┐
│  DATABASE-LAYER              │  │  STORAGE-LAYER             │
│  SQLAlchemy 2.0 + SQLite     │  │  StorageService (ABC)      │
│                              │  │   └─ LocalStorageService   │
└──────────────────────────────┘  └────────────────────────────┘
```

### Storage-Interface

```python
class StorageService(ABC):
    def ensure_directories(self, relative_dirs) -> None: ...
    def exists(self, relative_path) -> bool: ...
    def save_file(self, source, destination) -> PurePosixPath: ...
```

Alle Pfade sind relativ und logisch (`PurePosixPath`). Erst die Implementierung entscheidet über den physischen Speicherort. Ein späterer `SharePointStorageService` implementiert dieselben drei Methoden.

## 2. Datenmodell

| Tabelle | Spalte | Bemerkung |
|---|---|---|
| customers | id | interne Customer-ID (Autoincrement) |
| | company_name | Anzeige |
| | customer_number | eindeutig, nur Ziffern |
| | folder_name | eindeutig; einmalig aus dem Namen gebildet, bleibt stabil |
| | upload_token | eindeutig, indiziert; `secrets.token_urlsafe(32)` |
| | created_at | UTC |
| documents | id | |
| | customer_id | FK → customers.id |
| | original_filename | nur Anzeige/Audit, nie für Pfade genutzt |
| | stored_filename | NULL, wenn vor dem Speichern abgelehnt |
| | document_type | Katalog-Schlüssel |
| | year, month | nur FIBU |
| | destination_path | relativer Pfad der gespeicherten Datei |
| | status | `SUCCESS` / `FAILED` |
| | error_message | verständliche Fehlermeldung |
| | uploaded_at | UTC |

Die Tabelle `documents` ist zugleich das Audit-Log. Technische Details (Stacktraces) stehen zusätzlich in `logs/docflow.log`.

## 3. Routing-Konzept

```
resolve_destination(customer, document_type, year, month)
  1. document_type im Katalog?        nein → UnknownDocumentTypeError
  2. Stammdaten → {folder_name}/Stammdaten/{zielordner}
  3. FIBU:
       Zeitraum fehlt                 → MissingPeriodError
       Monat ∉ 1..12 / Jahr ∉ 2000..(heute+1) → InvalidPeriodError
       → {folder_name}/FIBU/{YYYY}/{MM_Monat}/{zielordner}
```

Der Pfad entsteht ausschließlich aus Whitelist-Werten. Benutzereingaben gelangen nie als freier Text in den Pfad.

## 4. Upload-Workflow

```
POST /upload/{token}   (document_type / period: Katalogwert oder "auto")
  1. Mandant per Token laden              → 404 bei ungültigem Token
  2. manuelle Angaben prüfen (Katalog, Zeitraum)
  3. Datei validieren (Endung, Größe, Magic Bytes)
  4. Text auslesen (pypdf; Fotos/Scans per OCR, optional)
  5. Erkennen (classification_service) und entscheiden:
       auto + hoch          → erkannte Art/Zeitraum (Zielordner)
       auto + mittel        → erkannte Art/Zeitraum (Zielordner), needs_review
       auto + niedrig       → Posteingang_Ungeklaert, needs_review
       FIBU ohne Zeitraum   → Posteingang_Ungeklaert, needs_review
       manuell              → Wahl des Mandanten, needs_review bei Widerspruch
       Mandantenname fehlt  → needs_review
  6. Zielordner berechnen (Routing bzw. Posteingang)
  7. Jahresstruktur anlegen, falls neu
  8. Dateiname bilden + eindeutig machen (_2, _3, …)
  9. Datei exklusiv speichern
 10. Document(status=SUCCESS) + DocumentAnalysis speichern
  Fehler in 2–8 → Document(status=FAILED, error_message) + Log, Formular mit Meldung
```

## 5. URL-Übersicht

| Methode | Pfad | Zugang |
|---|---|---|
| GET | `/` | Redirect → `/admin` |
| GET | `/admin` | Mitarbeiter |
| GET | `/admin/customers` | Mitarbeiter |
| GET/POST | `/admin/customers/new` | Mitarbeiter |
| GET | `/admin/customers/{id}` | Mitarbeiter |
| GET | `/admin/documents/{id}/file` | Mitarbeiter (Datei anzeigen, `?download=1` zum Herunterladen) |
| GET/POST | `/admin/documents/{id}` | Mitarbeiter (Dokument prüfen und Einordnung korrigieren) |
| GET/POST | `/upload/{token}` | Mandant (nur mit gültigem Token) |

## 6. Prüfung durch Mitarbeiter (Human in the Loop)

```
Mitarbeiter öffnet /admin/documents/{id}   (Vorschau + aktuelle Einordnung)
  → wählt richtige Dokumentart / Zeitraum
  → document_service.reclassify_document()
       1. Dokumentart + Zeitraum prüfen (wie beim Upload)
       2. neuen Zielordner per routing_service berechnen
       3. ggf. Jahresstruktur anlegen
       4. neuen eindeutigen Dateinamen bilden
       5. storage.move_file(alt, neu)        – nie überschreiben
       6. Document aktualisieren + DocumentCorrection speichern
          (bei DB-Fehler: Datei zurückverschieben)
```

Die Routing Engine wird dabei unverändert wiederverwendet. Das zeigt, dass Routing und Speicherung sauber getrennt sind.

## 7. Automatische Erkennung (regelbasiert)

| Baustein | Aufgabe |
|---|---|
| `text_extraction_service.TextExtractor` | Text aus PDF (pypdf); Fotos/gescannte PDFs per OCR – austauschbare Engines `RapidOcrEngine` (Standard, nur pip, offline) und `TesseractEngine`; OCR-Textblöcke werden zu Zeilen zusammengesetzt |
| `classification_service.classify()` | gewichtete Schlüsselbegriffe je Dokumentart → beste Art + Sicherheit; Rechnungsrichtung über Position des Mandantennamens; Zeitraum über beschriftete Datumszeilen bzw. häufigsten Monat |
| `upload_service._decide()` | kombiniert Mandantenangaben und Erkennung; bestimmt Ziel und Prüfgründe |
| `document_analyses` | speichert Methode, Textquelle, Ergebnis, Begründung, Prüfstatus |

Die Erkennung liefert exakt die Eingaben, die sonst der Mandant wählt (Dokumentart, Jahr, Monat). Routing- und Storage-Schicht bleiben dadurch unverändert.
