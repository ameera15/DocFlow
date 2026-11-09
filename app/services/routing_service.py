"""Routing Engine: bestimmt den Zielordner eines Dokuments.

Der Mandant wählt nur Dokumentart und ggf. Zeitraum. Dieser Service leitet
daraus nach festen Geschäftsregeln den Zielpfad ab:

    Stammdaten: <Mandant>/Stammdaten/<Ordner>
    FIBU:       <Mandant>/FIBU/<Jahr>/<MM_Monat>/<Ordner>
    Unklar:     <Mandant>/Posteingang_Ungeklaert   (Prüfung durch Mitarbeiter)

Sicherheit: Der Pfad wird ausschließlich aus Whitelist-Werten gebildet
(gespeicherter Ordnername des Mandanten, Katalogwerte, ganzzahliges Jahr und
Monat). Freie Benutzereingaben gelangen nie in den Pfad.

Zusätzlich kennt dieser Service das Ablagelayout und liefert die Standard-
Ordnerstruktur für neue Mandanten bzw. neue Jahre.
"""

from __future__ import annotations

from datetime import date
from pathlib import PurePosixPath
from typing import Protocol

from app.domain.document_types import FIBU_FOLDERS, STAMMDATEN_FOLDERS, UNCLASSIFIED, get_document_type
from app.domain.exceptions import CustomerValidationError, MissingPeriodError
from app.domain.periods import month_folder, validate_period
from app.services.filename_service import slugify

STAMMDATEN_DIR = "Stammdaten"
FIBU_DIR = "FIBU"


class HasFolderName(Protocol):
    folder_name: str


def _customer_root(folder_name: str) -> PurePosixPath:
    # Defensive Prüfung: Der gespeicherte Ordnername muss bereits "sauber" sein.
    if not folder_name or slugify(folder_name, max_length=200) != folder_name:
        raise CustomerValidationError("Ungültiger Ordnername des Mandanten.")
    return PurePosixPath(folder_name)


def resolve_destination(
    customer: HasFolderName,
    document_type: str,
    year: int | None = None,
    month: int | None = None,
    today: date | None = None,
) -> PurePosixPath:
    """Berechnet den relativen Zielordner für ein Dokument."""
    doc_type = get_document_type(document_type)
    root = _customer_root(customer.folder_name)

    if not doc_type.requires_period:
        return root / STAMMDATEN_DIR / doc_type.folder

    if year is None or month is None:
        raise MissingPeriodError()
    validate_period(year, month, today)
    return root / FIBU_DIR / f"{year:04d}" / month_folder(month) / doc_type.folder


def inbox_destination(customer: HasFolderName) -> PurePosixPath:
    """Posteingang für Dokumente, die nicht sicher erkannt wurden (Prüfung durch Mitarbeiter)."""
    return _customer_root(customer.folder_name) / UNCLASSIFIED.folder


def year_skeleton(folder_name: str, year: int) -> list[PurePosixPath]:
    """Alle Ordner eines FIBU-Jahres: 12 Monate x 4 Unterordner."""
    year_root = _customer_root(folder_name) / FIBU_DIR / f"{year:04d}"
    return [
        year_root / month_folder(month) / folder
        for month in range(1, 13)
        for folder in FIBU_FOLDERS
    ]


def customer_skeleton(folder_name: str, year: int) -> list[PurePosixPath]:
    """Komplette Standardstruktur eines neuen Mandanten (Stammdaten + FIBU-Jahr)."""
    root = _customer_root(folder_name)
    stammdaten = [root / STAMMDATEN_DIR / folder for folder in STAMMDATEN_FOLDERS]
    return [root / UNCLASSIFIED.folder] + stammdaten + year_skeleton(folder_name, year)
