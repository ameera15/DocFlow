"""Mitarbeiterbereich: Dokument öffnen, prüfen und Einordnung korrigieren."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_storage, require_admin
from app.domain.document_types import DOCUMENT_TYPES, DocumentGroup
from app.domain.exceptions import DocFlowError, DocumentNotFoundError, StorageError
from app.domain.periods import period_choices
from app.services import document_service
from app.services.storage_service import StorageService
from app.templating import templates

router = APIRouter(prefix="/admin/documents", tags=["Dokumente"], dependencies=[Depends(require_admin)])


def _not_found(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "error.html", {"title": "Nicht gefunden", "message": message, "public": False},
        status_code=status.HTTP_404_NOT_FOUND,
    )


@router.get("/{document_id}/file")
def show_file(
    request: Request,
    document_id: int,
    download: bool = False,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage),
):
    """Liefert die gespeicherte Datei aus – im Browser anzeigen oder herunterladen."""
    try:
        document = document_service.get_stored_document(db, document_id)
        stream = document_service.open_document(storage, document)
    except (DocumentNotFoundError, StorageError) as exc:
        return _not_found(request, exc.user_message)

    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        stream,
        media_type=document_service.media_type(document),
        headers={
            "Content-Disposition": f'{disposition}; filename="{document.stored_filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _render_review(request: Request, document, *, error: str | None = None,
                   selected_type: str | None = None, selected_period: str | None = None,
                   saved: bool = False, confirmed: bool = False, status_code: int = 200) -> HTMLResponse:
    analysis = document.analysis
    current_type = document.document_type
    current_period = f"{document.year:04d}-{document.month:02d}" if document.year else ""
    # Offene Prüfung: den erkannten Vorschlag vorauswählen -> Korrektur mit einem Klick.
    if document.needs_review and analysis is not None and analysis.detected_type:
        current_type = analysis.detected_type
        if analysis.detected_year:
            current_period = f"{analysis.detected_year:04d}-{analysis.detected_month:02d}"
    choices = period_choices()
    if current_period and current_period not in {value for value, _ in choices}:
        from app.domain.periods import period_label
        choices.append((current_period, period_label(document.year, document.month)))
    return templates.TemplateResponse(
        request,
        "document_review.html",
        {
            "doc": document,
            "media_type": document_service.media_type(document),
            "fibu_types": [t for t in DOCUMENT_TYPES if t.group is DocumentGroup.FIBU],
            "stammdaten_types": [t for t in DOCUMENT_TYPES if t.group is DocumentGroup.STAMMDATEN],
            "period_choices": choices,
            "selected_type": selected_type if selected_type is not None else current_type,
            "selected_period": selected_period if selected_period is not None else current_period,
            "error": error,
            "saved": saved,
            "confirmed": confirmed,
            "active": "customers",
        },
        status_code=status_code,
    )


@router.get("/{document_id}", response_class=HTMLResponse)
def review_document(request: Request, document_id: int, saved: bool = False, confirmed: bool = False,
                    db: Session = Depends(get_db)):
    try:
        document = document_service.get_stored_document(db, document_id)
    except DocumentNotFoundError as exc:
        return _not_found(request, exc.user_message)
    return _render_review(request, document, saved=saved, confirmed=confirmed)


@router.post("/{document_id}/confirm", response_class=HTMLResponse)
def confirm_document(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(require_admin),
):
    try:
        document = document_service.get_stored_document(db, document_id)
    except DocumentNotFoundError as exc:
        return _not_found(request, exc.user_message)
    try:
        document_service.confirm_document(db, document, admin)
    except DocFlowError as exc:
        return _render_review(request, document, error=exc.user_message, status_code=status.HTTP_400_BAD_REQUEST)
    return RedirectResponse(url=f"/admin/documents/{document.id}?confirmed=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{document_id}", response_class=HTMLResponse)
def correct_document(
    request: Request,
    document_id: int,
    document_type: str = Form(""),
    period: str = Form(""),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage),
    admin: str = Depends(require_admin),
):
    try:
        document = document_service.get_stored_document(db, document_id)
    except DocumentNotFoundError as exc:
        return _not_found(request, exc.user_message)

    try:
        document_service.reclassify_document(db, storage, document, document_type, period, corrected_by=admin)
    except DocFlowError as exc:
        return _render_review(request, document, error=exc.user_message, selected_type=document_type,
                              selected_period=period, status_code=status.HTTP_400_BAD_REQUEST)

    return RedirectResponse(url=f"/admin/documents/{document.id}?saved=1", status_code=status.HTTP_303_SEE_OTHER)
