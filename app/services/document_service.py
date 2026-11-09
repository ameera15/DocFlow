"""Mitarbeiterfunktionen für einzelne Dokumente: öffnen und Einordnung korrigieren.

Hintergrund: Der Mandant wählt die Dokumentart selbst. Ohne OCR/KI (bewusst
nicht Teil von Version 1) kann das System nicht prüfen, ob der Inhalt zur
gewählten Art passt. Deshalb gibt es eine Kontrolle durch Mitarbeiter
("Human in the Loop"): Dokument ansehen -> bei Bedarf korrigieren -> DocFlow
berechnet den neuen Zielordner mit derselben Routing Engine und verschiebt
die Datei. Jede Korrektur wird in ``document_corrections`` protokolliert.
"""

from __future__ import annotations

import logging
import mimetypes
from datetime import date
from pathlib import PurePosixPath
from typing import BinaryIO

from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.database.models import Document, DocumentCorrection
from app.domain.document_types import get_document_type
from app.domain.exceptions import DocFlowError, DocumentNotFoundError, StorageError
from app.domain.periods import parse_period
from app.services import filename_service, routing_service
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

_MEDIA_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg"}


def get_stored_document(db: Session, document_id: int) -> Document:
    """Liefert ein erfolgreich gespeichertes Dokument oder wirft einen Fehler."""
    document = db.get(Document, document_id)
    if document is None or not document.is_success or not document.destination_path:
        raise DocumentNotFoundError()
    return document


def media_type(document: Document) -> str:
    extension = (document.stored_filename or "").rsplit(".", 1)[-1].lower()
    return _MEDIA_TYPES.get(extension) or mimetypes.guess_type(document.stored_filename or "")[0] or "application/octet-stream"


def open_document(storage: StorageService, document: Document) -> BinaryIO:
    return storage.open_file(PurePosixPath(document.destination_path))


def reclassify_document(
    db: Session,
    storage: StorageService,
    document: Document,
    new_document_type: str | None,
    period: str | None,
    corrected_by: str,
    today: date | None = None,
) -> Document:
    """Ändert Dokumentart/Zeitraum und verschiebt die Datei in den neuen Zielordner."""
    today = today or date.today()
    doc_type = get_document_type(new_document_type)
    year = month = None
    if doc_type.requires_period:
        year, month = parse_period(period)

    if (doc_type.key, year, month) == (document.document_type, document.year, document.month):
        raise DocFlowError("Dokumentart und Zeitraum sind unverändert.")

    customer = document.customer
    new_dir = routing_service.resolve_destination(customer, doc_type.key, year, month, today)
    if doc_type.requires_period:
        storage.ensure_directories(routing_service.year_skeleton(customer.folder_name, year))

    extension = document.stored_filename.rsplit(".", 1)[-1]
    upload_date = document.uploaded_at.date() if document.uploaded_at else today
    new_name = filename_service.make_unique(
        storage,
        new_dir,
        filename_service.build_filename(doc_type, document.original_filename, extension, year, month, upload_date),
    )

    old_path = document.destination_path
    new_path = storage.move_file(PurePosixPath(old_path), new_dir / new_name).as_posix()

    correction = DocumentCorrection(
        document=document,
        old_document_type=document.document_type,
        old_year=document.year,
        old_month=document.month,
        old_path=old_path,
        new_document_type=doc_type.key,
        new_year=year,
        new_month=month,
        new_path=new_path,
        corrected_by=corrected_by,
    )
    db.add(correction)
    document.document_type = doc_type.key
    document.year, document.month = year, month
    _mark_reviewed(document, corrected_by)
    document.stored_filename = new_name
    document.destination_path = new_path

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        # Datei zurückschieben, damit Datenbank und Ablage konsistent bleiben.
        try:
            storage.move_file(PurePosixPath(new_path), PurePosixPath(old_path))
        except StorageError:
            logger.exception("Rückgängig machen der Verschiebung fehlgeschlagen: %s", new_path)
        logger.exception("Korrektur von Dokument %s konnte nicht gespeichert werden", document.id)
        raise StorageError("Die Korrektur konnte nicht gespeichert werden.") from exc

    logger.info("Dokument %s korrigiert von %s: %s -> %s", document.id, corrected_by, old_path, new_path)
    return document


def _mark_reviewed(document: Document, reviewer: str) -> None:
    if document.analysis is not None and document.analysis.reviewed_at is None:
        document.analysis.reviewed_by = reviewer
        document.analysis.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)


def confirm_document(db: Session, document: Document, reviewer: str) -> Document:
    """Mitarbeiter bestätigt die (automatische) Einordnung als korrekt."""
    if document.analysis is None or not document.needs_review:
        raise DocFlowError("Für dieses Dokument ist keine Prüfung offen.")
    if document.document_type == "ungeklaert":
        raise DocFlowError("Ungeklärte Dokumente bitte über „Korrigieren & verschieben“ zuordnen.")
    _mark_reviewed(document, reviewer)
    db.commit()
    logger.info("Einordnung von Dokument %s bestätigt durch %s", document.id, reviewer)
    return document
