"""Hilfsfunktionen rund um Buchhaltungszeiträume (Monat/Jahr)."""

from __future__ import annotations

from datetime import date

from app.domain.exceptions import InvalidPeriodError, MissingPeriodError

# Anzeigenamen (mit Umlaut) und Ordnernamen (ohne Umlaut) der Monate.
MONTH_DISPLAY_NAMES = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)
MONTH_FOLDER_NAMES = (
    "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)

MIN_YEAR = 2000
PERIOD_CHOICES_MONTHS = 36  # so viele Monate rückwirkend bietet das Formular an


def month_folder(month: int) -> str:
    """3 -> '03_Maerz'"""
    return f"{month:02d}_{MONTH_FOLDER_NAMES[month - 1]}"


def format_period(year: int | None, month: int | None) -> str:
    """Kurzform für Tabellen: (2026, 3) -> '03/2026'; ohne Zeitraum -> '–'."""
    if year is None or month is None:
        return "–"
    return f"{month:02d}/{year}"


def period_label(year: int, month: int) -> str:
    """Langform für Dropdowns: (2026, 3) -> 'März 2026'."""
    return f"{MONTH_DISPLAY_NAMES[month - 1]} {year}"


def parse_period(value: str | None) -> tuple[int, int]:
    """Wandelt den Formularwert 'YYYY-MM' in (Jahr, Monat) um.

    Wirft ``MissingPeriodError`` bei leerem Wert und ``InvalidPeriodError`` bei
    falschem Format. Die fachliche Bereichsprüfung erfolgt im Routing-Service.
    """
    if not value or not value.strip():
        raise MissingPeriodError()
    parts = value.strip().split("-")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise InvalidPeriodError()
    return int(parts[0]), int(parts[1])


def validate_period(year: int, month: int, today: date | None = None) -> None:
    """Prüft, ob Jahr und Monat fachlich zulässig sind."""
    today = today or date.today()
    if not 1 <= month <= 12:
        raise InvalidPeriodError("Der Monat muss zwischen 1 und 12 liegen.")
    if not MIN_YEAR <= year <= today.year + 1:
        raise InvalidPeriodError(
            f"Das Jahr muss zwischen {MIN_YEAR} und {today.year + 1} liegen."
        )


def period_choices(today: date | None = None, months: int = PERIOD_CHOICES_MONTHS) -> list[tuple[str, str]]:
    """Liste von (Formularwert, Anzeige) – aktueller Monat zuerst, dann rückwärts."""
    today = today or date.today()
    year, month = today.year, today.month
    choices = []
    for _ in range(months + 1):
        choices.append((f"{year:04d}-{month:02d}", period_label(year, month)))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return choices
