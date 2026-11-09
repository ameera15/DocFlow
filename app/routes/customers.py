"""Mitarbeiterbereich: Mandantenverwaltung."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import get_db, get_settings, get_storage, require_admin
from app.domain.exceptions import CustomerNotFoundError, DocFlowError
from app.services import customer_service, dashboard_service
from app.services.storage_service import StorageService
from app.templating import templates

router = APIRouter(prefix="/admin/customers", tags=["Mandanten"], dependencies=[Depends(require_admin)])


@router.get("", response_class=HTMLResponse)
def list_customers(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    rows = [
        {
            "customer": customer,
            "document_count": count,
            "upload_url": customer_service.build_upload_url(settings.base_url, customer.upload_token),
        }
        for customer, count in customer_service.list_customers_with_counts(db)
    ]
    return templates.TemplateResponse(request, "customers.html", {"rows": rows, "active": "customers"})


@router.get("/new", response_class=HTMLResponse)
def new_customer_form(request: Request):
    return templates.TemplateResponse(
        request, "create_customer.html", {"form": {}, "error": None, "active": "customers"}
    )


@router.post("/new", response_class=HTMLResponse)
def create_customer(
    request: Request,
    company_name: str = Form(""),
    customer_number: str = Form(""),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage),
):
    try:
        customer = customer_service.create_customer(db, storage, company_name, customer_number)
    except DocFlowError as exc:
        return templates.TemplateResponse(
            request,
            "create_customer.html",
            {
                "form": {"company_name": company_name, "customer_number": customer_number},
                "error": exc.user_message,
                "active": "customers",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    # Post/Redirect/Get: verhindert doppeltes Anlegen beim Neuladen der Seite.
    return RedirectResponse(
        url=f"/admin/customers/{customer.id}?created=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{customer_id}", response_class=HTMLResponse)
def customer_detail(
    request: Request,
    customer_id: int,
    created: bool = False,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        customer = customer_service.get_customer(db, customer_id)
    except CustomerNotFoundError as exc:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"title": "Nicht gefunden", "message": exc.user_message, "public": False},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    uploads = dashboard_service.recent_uploads(db, limit=200, customer_id=customer.id)
    return templates.TemplateResponse(
        request,
        "customer_detail.html",
        {
            "customer": customer,
            "uploads": uploads,
            "success_count": sum(1 for d in uploads if d.is_success),
            "upload_url": customer_service.build_upload_url(settings.base_url, customer.upload_token),
            "created": created,
            "active": "customers",
        },
    )
