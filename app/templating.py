"""Jinja2-Templates und Anzeige-Filter."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, DISPLAY_TIMEZONE
from app.domain.document_types import document_type_label
from app.domain.periods import format_period

templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")

_TZ = ZoneInfo(DISPLAY_TIMEZONE)


def _local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:  # in der DB als UTC gespeichert
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_TZ)


def format_date(value: datetime | None) -> str:
    local = _local(value)
    return local.strftime("%d.%m.%Y") if local else "–"


def format_datetime(value: datetime | None) -> str:
    local = _local(value)
    return local.strftime("%d.%m.%Y %H:%M") if local else "–"


def status_label(status: str) -> str:
    return {"SUCCESS": "Erfolgreich", "FAILED": "Fehlgeschlagen"}.get(status, status)


templates.env.filters.update(
    date_de=format_date,
    datetime_de=format_datetime,
    doc_type_label=document_type_label,
    status_label=status_label,
)
templates.env.globals["format_period"] = format_period
