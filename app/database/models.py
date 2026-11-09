"""ORM-Modelle: Mandanten und hochgeladene Dokumente.

Zeitstempel werden als UTC (ohne Zeitzoneninfo) gespeichert und erst in der
Oberfläche in deutsche Zeit umgerechnet.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UploadStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # interne Customer-ID
    company_name: Mapped[str] = mapped_column(String(200))
    customer_number: Mapped[str] = mapped_column(String(20), unique=True)
    # Einmalig aus dem Firmennamen erzeugt; bleibt stabil, auch wenn der Name sich ändert.
    folder_name: Mapped[str] = mapped_column(String(200), unique=True)
    upload_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="customer",
        order_by="Document.uploaded_at.desc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Customer {self.customer_number} {self.company_name!r}>"


class Document(Base):
    """Ein Upload-Vorgang – erfolgreich oder fehlgeschlagen (= Audit-Log)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_type: Mapped[str] = mapped_column(String(50))
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    destination_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=UploadStatus.FAILED.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    customer: Mapped[Customer] = relationship(back_populates="documents")
    analysis: Mapped["DocumentAnalysis | None"] = relationship(
        back_populates="document", uselist=False, cascade="all, delete-orphan"
    )
    corrections: Mapped[list["DocumentCorrection"]] = relationship(
        back_populates="document",
        order_by="DocumentCorrection.corrected_at.desc()",
        cascade="all, delete-orphan",
    )

    @property
    def is_success(self) -> bool:
        return self.status == UploadStatus.SUCCESS.value

    @property
    def is_corrected(self) -> bool:
        return bool(self.corrections)

    @property
    def needs_review(self) -> bool:
        return bool(self.analysis and self.analysis.needs_review and self.analysis.reviewed_at is None)

    @property
    def auto_classified(self) -> bool:
        return bool(self.analysis and self.analysis.method == "automatisch")

    def __repr__(self) -> str:
        return f"<Document {self.id} {self.document_type} {self.status}>"


class DocumentCorrection(Base):
    """Audit-Eintrag: Ein Mitarbeiter hat Dokumentart/Zeitraum eines Uploads korrigiert.

    Der Mandant kann eine falsche Dokumentart wählen (ohne OCR/KI erkennt das
    System den Inhalt nicht). Mitarbeiter prüfen das Dokument und korrigieren
    die Einordnung; die Datei wird dabei automatisch verschoben. Alter und
    neuer Zustand bleiben hier nachvollziehbar.
    """

    __tablename__ = "document_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    old_document_type: Mapped[str] = mapped_column(String(50))
    old_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_path: Mapped[str] = mapped_column(String(500))
    new_document_type: Mapped[str] = mapped_column(String(50))
    new_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_path: Mapped[str] = mapped_column(String(500))
    corrected_by: Mapped[str] = mapped_column(String(100))
    corrected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    document: Mapped[Document] = relationship(back_populates="corrections")


class DocumentAnalysis(Base):
    """Ergebnis der automatischen Erkennung eines Uploads (1:1 zu Document).

    Hält fest, WIE die Einordnung zustande kam (automatisch oder vom Mandanten
    gewählt), was die Erkennung gefunden hat und ob ein Mitarbeiter prüfen muss.
    """

    __tablename__ = "document_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), unique=True)
    method: Mapped[str] = mapped_column(String(20))              # automatisch | manuell
    text_source: Mapped[str] = mapped_column(String(20))         # pdf-text | ocr | keine
    detected_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detected_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str] = mapped_column(String(10))          # hoch | mittel | niedrig
    score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    document: Mapped[Document] = relationship(back_populates="analysis")

    @property
    def evidence_list(self) -> list[str]:
        return [e for e in (self.evidence or "").split("\n") if e]
