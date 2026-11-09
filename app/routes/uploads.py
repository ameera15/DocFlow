"""Kundenseite: Upload über den persönlichen Link /upload/{token}.

Der Mandant sieht hier ausschließlich seinen Firmennamen. Interne IDs,
Ordnerstrukturen und Daten anderer Mandanten werden nie angezeigt.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import Customer
from app.dependencies import get_db, get_settings, get_storage, get_text_extractor
from app.domain.document_types import AUTO, DOCUMENT_TYPES, UNCLASSIFIED, DocumentGroup, document_type_label
from app.domain.exceptions import DocFlowError, InvalidTokenError
from app.domain.periods import format_period, period_choices
from app.services import customer_service, upload_service
from app.services.storage_service import StorageService
from app.services.text_extraction_service import TextExtractor
from app.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Mandanten-Upload"])


def _render_form(
    request: Request,
    customer: Customer,
    *,
    error: str | None = None,
    selected_type: str = AUTO,
    selected_period: str = AUTO,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "company_name": customer.company_name,
            "fibu_types": [t for t in DOCUMENT_TYPES if t.group is DocumentGroup.FIBU],
            "stammdaten_types": [t for t in DOCUMENT_TYPES if t.group is DocumentGroup.STAMMDATEN],
            "period_choices": period_choices(),
            "selected_type": selected_type,
            "selected_period": selected_period,
            "max_size_mb": request.app.state.settings.max_upload_size_mb,
            "auto": AUTO,
            "error": error,
        },
        status_code=status_code,
    )


def _invalid_link(request: Request, token: str) -> HTMLResponse:
    logger.warning("Zugriff mit ungültigem Upload-Token (Präfix %s...)", token[:6])
    return templates.TemplateResponse(
        request,
        "error.html",
        {"title": "Link ungültig", "message": InvalidTokenError.default_message, "public": True},
        status_code=status.HTTP_404_NOT_FOUND,
    )


@router.get("/upload/{token}", response_class=HTMLResponse)
def upload_form(request: Request, token: str, db: Session = Depends(get_db)):
    try:
        customer = customer_service.get_customer_by_token(db, token)
    except InvalidTokenError:
        return _invalid_link(request, token)
    return _render_form(request, customer)


@router.post("/upload/{token}", response_class=HTMLResponse)
def upload_document(
    request: Request,
    token: str,
    document_type: str = Form(""),
    period: str = Form(""),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    extractor: TextExtractor = Depends(get_text_extractor),
):
    try:
        customer = customer_service.get_customer_by_token(db, token)
    except InvalidTokenError:
        return _invalid_link(request, token)

    try:
        document = upload_service.process_upload(
            db,
            storage,
            customer,
            document_type=document_type,
            period=period,
            filename=file.filename if file else None,
            stream=file.file if file else None,
            max_size_bytes=settings.max_upload_size_bytes,
            extractor=extractor,
        )
    except DocFlowError as exc:
        return _render_form(
            request,
            customer,
            error=exc.user_message,
            selected_type=document_type,
            selected_period=period,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return templates.TemplateResponse(
        request,
        "upload_success.html",
        {
            "company_name": customer.company_name,
            "token": token,
            "document_label": document_type_label(document.document_type),
            "period": format_period(document.year, document.month),
            "original_filename": document.original_filename,
            "auto_classified": document.auto_classified,
            "unclassified": document.document_type == UNCLASSIFIED.key,
        },
    )
