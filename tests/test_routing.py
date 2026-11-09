"""Tests der Routing Engine (Pflichttests 3–6) und der Zeitraum-Regeln."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath

import pytest

from app.domain.exceptions import (
    CustomerValidationError,
    InvalidPeriodError,
    MissingDocumentTypeError,
    MissingPeriodError,
    UnknownDocumentTypeError,
)
from app.domain.periods import parse_period
from app.services.routing_service import customer_skeleton, resolve_destination, year_skeleton

TODAY = date(2026, 10, 11)


@dataclass
class FakeCustomer:
    folder_name: str = "Muster_GmbH"


CUSTOMER = FakeCustomer()


def route(document_type, year=None, month=None):
    return resolve_destination(CUSTOMER, document_type, year, month, today=TODAY)


# --- Pflichttests ----------------------------------------------------------------

def test_eingangsrechnung_maerz_2026():  # Test 3
    assert route("eingangsrechnung", 2026, 3) == PurePosixPath("Muster_GmbH/FIBU/2026/03_Maerz/Eingangsrechnungen")


def test_kontoauszug_april_2026():  # Test 4
    assert route("kontoauszug", 2026, 4) == PurePosixPath("Muster_GmbH/FIBU/2026/04_April/Bank")


def test_z_bericht_februar_2026():  # Test 5
    assert route("z_bericht", 2026, 2) == PurePosixPath("Muster_GmbH/FIBU/2026/02_Februar/Kasse_Z_Berichte")


def test_gewerbeanmeldung():  # Test 6
    assert route("gewerbeanmeldung") == PurePosixPath("Muster_GmbH/Stammdaten/Gewerbeanmeldung")


# --- Weitere Routing-Regeln --------------------------------------------------------

@pytest.mark.parametrize("doc_type, expected", [
    ("ausgangsrechnung", "Muster_GmbH/FIBU/2026/12_Dezember/Ausgangsrechnungen"),
    ("kassenbeleg", "Muster_GmbH/FIBU/2026/12_Dezember/Kasse_Z_Berichte"),
])
def test_other_fibu_types(doc_type, expected):
    assert route(doc_type, 2026, 12) == PurePosixPath(expected)


@pytest.mark.parametrize("doc_type, folder", [
    ("bankverbindung", "Bankverbindungsdaten"),
    ("vollmacht", "Vollmacht_Dienstleistungsvertrag"),
    ("ust_idnr", "USt_IdNr"),
    ("sonstige_stammdaten", "Sonstige"),
])
def test_stammdaten_types(doc_type, folder):
    assert route(doc_type) == PurePosixPath("Muster_GmbH/Stammdaten") / folder


def test_stammdaten_ignore_period():
    assert route("ausweis", 2026, 5) == PurePosixPath("Muster_GmbH/Stammdaten/Ausweis")


def test_fibu_without_period_is_rejected():
    with pytest.raises(MissingPeriodError):
        route("eingangsrechnung")


@pytest.mark.parametrize("year, month", [(2026, 0), (2026, 13), (1999, 5), (2028, 1)])
def test_invalid_period_is_rejected(year, month):
    with pytest.raises(InvalidPeriodError):
        route("eingangsrechnung", year, month)


def test_unknown_document_type_is_rejected():
    with pytest.raises(UnknownDocumentTypeError):
        route("../../geheim")


def test_missing_document_type_is_rejected():
    with pytest.raises(MissingDocumentTypeError):
        route("")


def test_unsafe_customer_folder_is_rejected():
    with pytest.raises(CustomerValidationError):
        resolve_destination(FakeCustomer("../Andere_GmbH"), "ausweis", today=TODAY)


def test_parse_period():
    assert parse_period("2026-03") == (2026, 3)
    with pytest.raises(MissingPeriodError):
        parse_period("")
    with pytest.raises(InvalidPeriodError):
        parse_period("März 2026")


def test_skeleton_sizes():
    assert len(year_skeleton("Muster_GmbH", 2026)) == 12 * 4
    assert len(customer_skeleton("Muster_GmbH", 2026)) == 1 + 10 + 12 * 4
