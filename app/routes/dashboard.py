"""Mitarbeiterbereich: Dashboard mit Kennzahlen und letzten Uploads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_admin
from app.services import dashboard_service
from app.templating import templates

router = APIRouter(tags=["Dashboard"])


@router.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/admin")


@router.get("/admin", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def dashboard(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stats": dashboard_service.get_stats(db),
            "uploads": dashboard_service.recent_uploads(db, limit=20),
            "active": "dashboard",
        },
    )
