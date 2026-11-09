"""Kennzahlen und Upload-Historie für das Mitarbeiter-Dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import DISPLAY_TIMEZONE
from app.database.models import Customer, Document, DocumentAnalysis, UploadStatus


@dataclass(frozen=True)
class DashboardStats:
    customer_count: int
    document_count: int
    uploads_today: int
    successful_uploads: int
    failed_uploads: int
    review_needed: int


def _start_of_local_day_utc(now_utc: datetime) -> datetime:
    """Beginn des heutigen Tages (deutsche Zeit) als naive UTC-Zeit wie in der DB."""
    tz = ZoneInfo(DISPLAY_TIMEZONE)
    local_today = now_utc.replace(tzinfo=timezone.utc).astimezone(tz).date()
    start_local = datetime.combine(local_today, time.min, tzinfo=tz)
    return start_local.astimezone(timezone.utc).replace(tzinfo=None)


def get_stats(db: Session, now_utc: datetime | None = None) -> DashboardStats:
    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)

    def count(*conditions) -> int:
        return db.scalar(select(func.count(Document.id)).where(*conditions)) or 0

    return DashboardStats(
        customer_count=db.scalar(select(func.count(Customer.id))) or 0,
        document_count=count(),  # alle Upload-Vorgänge = erfolgreich + fehlgeschlagen
        uploads_today=count(Document.uploaded_at >= _start_of_local_day_utc(now_utc)),
        successful_uploads=count(Document.status == UploadStatus.SUCCESS.value),
        failed_uploads=count(Document.status == UploadStatus.FAILED.value),
        review_needed=db.scalar(
            select(func.count(DocumentAnalysis.id)).where(
                DocumentAnalysis.needs_review.is_(True), DocumentAnalysis.reviewed_at.is_(None)
            )
        ) or 0,
    )


def recent_uploads(db: Session, limit: int = 20, customer_id: int | None = None) -> list[Document]:
    query = (
        select(Document)
        .options(joinedload(Document.customer), joinedload(Document.analysis))
        .order_by(Document.uploaded_at.desc(), Document.id.desc())
        .limit(limit)
    )
    if customer_id is not None:
        query = query.where(Document.customer_id == customer_id)
    return list(db.scalars(query))
