"""Anlegen und Abfragen von Mandanten."""

from __future__ import annotations

import logging
import secrets
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import Customer, Document, UploadStatus
from app.domain.exceptions import (
    CustomerNotFoundError,
    CustomerValidationError,
    DocFlowError,
    DuplicateCustomerNumberError,
    InvalidTokenError,
    StorageError,
)
from app.services.filename_service import slugify
from app.services.routing_service import customer_skeleton
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

TOKEN_BYTES = 32  # ~256 Bit Zufall -> ca. 43 Zeichen URL-sicher
MAX_COMPANY_NAME_LENGTH = 200
MAX_CUSTOMER_NUMBER_LENGTH = 20


def generate_upload_token() -> str:
    """Kryptografisch sicherer, nicht erratbarer Token für den Upload-Link."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def build_upload_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/upload/{token}"


def _validate_input(company_name: str, customer_number: str) -> tuple[str, str]:
    company_name = " ".join((company_name or "").split())
    customer_number = (customer_number or "").strip()
    if len(company_name) < 2:
        raise CustomerValidationError("Bitte geben Sie einen Unternehmensnamen ein (mind. 2 Zeichen).")
    if len(company_name) > MAX_COMPANY_NAME_LENGTH:
        raise CustomerValidationError("Der Unternehmensname ist zu lang (max. 200 Zeichen).")
    if not customer_number.isdigit() or len(customer_number) > MAX_CUSTOMER_NUMBER_LENGTH:
        raise CustomerValidationError("Die Mandantennummer darf nur aus Ziffern bestehen (max. 20).")
    return company_name, customer_number


def _choose_folder_name(db: Session, storage: StorageService, company_name: str, customer_number: str) -> str:
    """'Muster GmbH' -> 'Muster_GmbH'; bei Kollision 'Muster_GmbH_10004'."""
    base = slugify(company_name, max_length=80) or "Mandant"
    for candidate in (base, f"{base}_{customer_number}"):
        taken_in_db = db.scalar(select(Customer.id).where(Customer.folder_name == candidate))
        if not taken_in_db and not storage.exists(candidate):
            return candidate
    raise CustomerValidationError("Für diesen Mandanten konnte kein eindeutiger Ordnername gebildet werden.")


def create_customer(
    db: Session,
    storage: StorageService,
    company_name: str,
    customer_number: str,
    today: date | None = None,
) -> Customer:
    """Legt einen Mandanten inkl. Upload-Token und Ordnerstruktur an.

    Datenbank und Dateisystem werden gemeinsam behandelt: Schlägt die
    Ordnererstellung fehl, wird der Datenbankeintrag zurückgerollt.
    """
    today = today or date.today()
    company_name, customer_number = _validate_input(company_name, customer_number)

    if db.scalar(select(Customer.id).where(Customer.customer_number == customer_number)):
        raise DuplicateCustomerNumberError()

    customer = Customer(
        company_name=company_name,
        customer_number=customer_number,
        folder_name=_choose_folder_name(db, storage, company_name, customer_number),
        upload_token=generate_upload_token(),
    )
    try:
        db.add(customer)
        db.flush()  # vergibt die interne ID, prüft UNIQUE-Constraints
        storage.ensure_directories(customer_skeleton(customer.folder_name, today.year))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCustomerNumberError() from exc
    except DocFlowError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Mandant %s konnte nicht angelegt werden", customer_number)
        raise StorageError("Der Mandant konnte nicht angelegt werden.") from exc

    logger.info("Mandant angelegt: id=%s nr=%s ordner=%s", customer.id, customer_number, customer.folder_name)
    return customer


def get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise CustomerNotFoundError()
    return customer


def get_customer_by_token(db: Session, token: str) -> Customer:
    """Sucht den Mandanten zu einem Upload-Token."""
    if not token or len(token) > 64:
        raise InvalidTokenError()
    customer = db.scalar(select(Customer).where(Customer.upload_token == token))
    if customer is None:
        raise InvalidTokenError()
    return customer


def list_customers_with_counts(db: Session) -> list[tuple[Customer, int]]:
    """Alle Mandanten mit Anzahl erfolgreich hochgeladener Dokumente."""
    success_count = (
        select(Document.customer_id, func.count(Document.id).label("cnt"))
        .where(Document.status == UploadStatus.SUCCESS.value)
        .group_by(Document.customer_id)
        .subquery()
    )
    rows = db.execute(
        select(Customer, func.coalesce(success_count.c.cnt, 0))
        .outerjoin(success_count, success_count.c.customer_id == Customer.id)
        .order_by(Customer.customer_number)
    ).all()
    return [(customer, count) for customer, count in rows]
