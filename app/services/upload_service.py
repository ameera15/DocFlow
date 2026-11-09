"""Orchestrierung eines Uploads.

Ablauf:
    Datei validieren -> Text auslesen (PDF-Text / OCR) -> Dokumentart und
    Zeitraum bestimmen (automatisch erkannt ODER vom Mandanten gewählt und
    auf Plausibilität geprüft) -> Zielordner berechnen (Routing) -> ggf.
    Jahresstruktur anlegen -> eindeutigen Dateinamen bilden -> Datei
    speichern -> Audit-Einträge in der Datenbank.

Kann ein Dokument nicht sicher zugeordnet werden, landet es im
"Posteingang_Ungeklaert" des Mandanten und wird für die Prüfung durch
Mitarbeiter markiert. Der Mandant muss dafür nichts weiter tun.

Jeder Versuch – erfolgreich oder fehlgeschlagen – wird in der Tabelle
``documents`` protokolliert. Technische Details landen zusätzlich im Log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import PurePosixPath
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.database.models import Customer, Document, DocumentAnalysis, UploadStatus
from app.domain.document_types import AUTO, UNCLASSIFIED, DocumentType, get_document_type
from app.domain.exceptions import DocFlowError, StorageError
from app.domain.periods import format_period, parse_period
from app.services import classification_service, filename_service, routing_service, validation_service
from app.services.classification_service import ClassificationResult
from app.services.storage_service import StorageService
from app.services.text_extraction_service import ExtractedText, TextExtractor

logger = logging.getLogger(__name__)

# Dokumentarten, auf denen der Mandantenname normalerweise steht.
# Fehlt er, gehört das Dokument evtl. zu einem anderen Mandanten -> prüfen.
NAME_EXPECTED = {
    "eingangsrechnung", "ausgangsrechnung", "kontoauszug", "gewerbeanmeldung", "steuernummer",
    "betriebsnummer", "unternehmensnummer_bg", "bankverbindung", "vollmacht", "eroeffnungsbilanz", "ust_idnr",
}

_default_extractor: TextExtractor | None = None


def _get_default_extractor() -> TextExtractor:
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = TextExtractor()
    return _default_extractor


@dataclass
class _Decision:
    """Ergebnis der Einordnung, bevor gespeichert wird."""

    document_type: DocumentType
    year: int | None
    month: int | None
    method: str                      # automatisch | manuell
    review_reasons: list[str] = field(default_factory=list)


def _display_filename(filename: str | None) -> str:
    """Original-Dateiname ohne Pfadanteile – nur für Anzeige und Audit."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return name[:255] or "(keine Datei)"


def _is_auto(value: str | None) -> bool:
    return (value or "").strip().lower() == AUTO


def _decide(
    customer: Customer,
    document_type: str | None,
    period: str | None,
    extracted: ExtractedText,
    detection: ClassificationResult,
    today: date,
) -> _Decision:
    """Kombiniert Angaben des Mandanten mit der automatischen Erkennung."""
    reasons: list[str] = []

    # --- 1. Dokumentart --------------------------------------------------------
    if _is_auto(document_type):
        method = "automatisch"
        if not detection.is_usable:
            reasons.append("Dokumentart konnte nicht sicher erkannt werden.")
            return _Decision(UNCLASSIFIED, None, None, method, reasons)
        doc_type = detection.document_type
        if detection.confidence != "hoch":
            reasons.append(f"Erkennung nur mit Sicherheit „{detection.confidence}“.")
    else:
        method = "manuell"
        doc_type = get_document_type(document_type)  # wirft bei leer/unbekannt
        if detection.is_confident and detection.document_type.key != doc_type.key:
            reasons.append(
                f"Mandant wählte „{doc_type.label}“, der Inhalt deutet auf „{detection.document_type.label}“ hin."
            )

    # --- 2. Zeitraum -------------------------------------------------------------
    year = month = None
    if doc_type.requires_period:
        if _is_auto(period) or (method == "automatisch" and not (period or "").strip()):
            if method == "automatisch" or detection.document_type is doc_type:
                year, month = detection.year, detection.month
            else:
                found, _ = classification_service.detect_period_for_type(extracted.text, doc_type, today)
                year, month = found if found else (None, None)
            if year is None:
                reasons.append("Zeitraum konnte nicht aus dem Dokument gelesen werden.")
                return _Decision(UNCLASSIFIED, None, None, method, reasons)
        else:
            year, month = parse_period(period)  # wirft bei leer/ungültig
            if detection.year and (detection.year, detection.month) != (year, month) \
                    and detection.document_type is not None and detection.document_type.requires_period:
                reasons.append(
                    f"Gewählter Zeitraum {format_period(year, month)} weicht vom Dokument "
                    f"({format_period(detection.year, detection.month)}) ab."
                )

    # --- 3. Gehört das Dokument zu diesem Mandanten? -------------------------------
    if doc_type.key in NAME_EXPECTED and detection.customer_name_found is False:
        reasons.append(f"Mandantenname „{customer.company_name}“ wurde im Dokument nicht gefunden.")

    if method == "automatisch" and not extracted.has_text:
        reasons.append("Kein Text lesbar – Einordnung nur anhand des Dateinamens.")

    return _Decision(doc_type, year, month, method, reasons)


def process_upload(
    db: Session,
    storage: StorageService,
    customer: Customer,
    document_type: str | None,
    period: str | None,
    filename: str | None,
    stream: BinaryIO | None,
    max_size_bytes: int,
    today: date | None = None,
    extractor: TextExtractor | None = None,
) -> Document:
    """Verarbeitet einen Upload vollständig und gibt den Audit-Datensatz zurück.

    ``document_type`` / ``period`` können ``"auto"`` sein (automatische Erkennung).
    Bei fachlichen Fehlern wird ein FAILED-Datensatz gespeichert und der
    ``DocFlowError`` erneut ausgelöst, damit die Oberfläche die Meldung anzeigt.
    """
    today = today or date.today()
    extractor = extractor or _get_default_extractor()
    record = Document(
        customer=customer,
        original_filename=_display_filename(filename),
        document_type=(document_type or "").strip()[:50],
        status=UploadStatus.FAILED.value,
    )

    try:
        # Pflichtangaben zuerst prüfen (verständliche Meldung vor Dateifehlern).
        if not _is_auto(document_type):
            doc_type = get_document_type(document_type)
            if doc_type.requires_period and not _is_auto(period):
                record.year, record.month = parse_period(period)

        validated = validation_service.validate_upload(filename, stream, max_size_bytes)
        extracted = extractor.extract(stream, validated.extension)
        detection = classification_service.classify(
            extracted.text, validated.original_filename, customer.company_name, today
        )
        decision = _decide(customer, document_type, period, extracted, detection, today)

        if decision.document_type is UNCLASSIFIED:
            destination_dir = routing_service.inbox_destination(customer)
        else:
            destination_dir = routing_service.resolve_destination(
                customer, decision.document_type.key, decision.year, decision.month, today
            )
            if decision.document_type.requires_period:
                storage.ensure_directories(routing_service.year_skeleton(customer.folder_name, decision.year))
        storage.ensure_directories([destination_dir])

        stored_filename = filename_service.make_unique(
            storage,
            destination_dir,
            filename_service.build_filename(
                decision.document_type, validated.original_filename, validated.extension,
                decision.year, decision.month, today,
            ),
        )
        stored_path = storage.save_file(stream, destination_dir / stored_filename)

        record.document_type = decision.document_type.key
        record.year, record.month = decision.year, decision.month
        record.stored_filename = stored_filename
        record.destination_path = stored_path.as_posix()
        record.status = UploadStatus.SUCCESS.value
        record.analysis = DocumentAnalysis(
            method=decision.method,
            text_source=extracted.source,
            detected_type=detection.document_type.key if detection.document_type else None,
            detected_year=detection.year,
            detected_month=detection.month,
            confidence=detection.confidence,
            score=detection.score,
            evidence="\n".join(detection.evidence),
            needs_review=bool(decision.review_reasons),
            review_reason="\n".join(decision.review_reasons) or None,
        )

    except DocFlowError as exc:
        record.error_message = exc.user_message
        _save(db, record)
        logger.warning("Upload abgelehnt: mandant=%s typ=%s grund=%s", customer.customer_number, document_type, exc.user_message)
        raise
    except Exception as exc:
        record.error_message = "Interner Fehler bei der Verarbeitung."
        _save(db, record)
        logger.exception("Unerwarteter Fehler beim Upload für Mandant %s", customer.customer_number)
        raise StorageError() from exc

    _save(db, record)
    logger.info(
        "Upload gespeichert: mandant=%s typ=%s methode=%s pruefung=%s ziel=%s",
        customer.customer_number, record.document_type, record.analysis.method,
        record.analysis.needs_review, record.destination_path,
    )
    return record


def _save(db: Session, record: Document) -> None:
    try:
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Audit-Eintrag konnte nicht gespeichert werden")
        raise


def destination_folder(document: Document) -> PurePosixPath | None:
    """Ordner (ohne Dateiname) eines gespeicherten Dokuments."""
    return PurePosixPath(document.destination_path).parent if document.destination_path else None
