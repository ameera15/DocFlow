"""Tests rund um das Anlegen von Mandanten (Pflichttests 1 und 2)."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.document_types import FIBU_FOLDERS, STAMMDATEN_FOLDERS
from app.domain.exceptions import CustomerValidationError, DuplicateCustomerNumberError
from app.domain.periods import month_folder
from app.services import customer_service
from tests.conftest import ADMIN_AUTH


# --- Test 1: Mandant wird erstellt -> Ordnerstruktur existiert -----------------

def test_create_customer_creates_folder_structure(customer, storage_root):
    root = storage_root / "Muster_GmbH"
    year = date.today().year

    assert customer.folder_name == "Muster_GmbH"
    for folder in STAMMDATEN_FOLDERS:
        assert (root / "Stammdaten" / folder).is_dir(), folder
    for month in range(1, 13):
        for folder in FIBU_FOLDERS:
            assert (root / "FIBU" / str(year) / month_folder(month) / folder).is_dir()


def test_customer_structure_contains_expected_folders(customer, storage_root):
    year_dir = storage_root / "Muster_GmbH" / "FIBU" / str(date.today().year)
    assert (year_dir / "03_Maerz" / "Eingangsrechnungen").is_dir()
    assert (year_dir / "12_Dezember" / "Kasse_Z_Berichte").is_dir()
    assert (storage_root / "Muster_GmbH" / "Stammdaten" / "Vollmacht_Dienstleistungsvertrag").is_dir()


# --- Test 2: Mandant erhält eindeutigen Upload-Token ---------------------------

def test_customer_gets_unique_upload_token(db, storage):
    first = customer_service.create_customer(db, storage, "Muster GmbH", "10001")
    second = customer_service.create_customer(db, storage, "Alpha Consulting UG", "10002")

    assert first.upload_token != second.upload_token
    assert len(first.upload_token) >= 40
    # Der Firmenname ist kein Bestandteil des Links.
    assert "Muster" not in first.upload_token
    assert customer_service.get_customer_by_token(db, first.upload_token).id == first.id


def test_customer_gets_internal_id(customer):
    assert isinstance(customer.id, int) and customer.id > 0


# --- Weitere Regeln --------------------------------------------------------------

def test_duplicate_customer_number_is_rejected(db, storage, customer):
    with pytest.raises(DuplicateCustomerNumberError):
        customer_service.create_customer(db, storage, "Andere GmbH", "10001")


@pytest.mark.parametrize("name, number", [("", "10009"), ("Firma", "ABC"), ("Firma", "")])
def test_invalid_customer_input_is_rejected(db, storage, name, number):
    with pytest.raises(CustomerValidationError):
        customer_service.create_customer(db, storage, name, number)


def test_folder_name_is_sanitized(db, storage):
    customer = customer_service.create_customer(db, storage, "Müller & Söhne KG", "10005")
    assert customer.folder_name == "Mueller_Soehne_KG"


def test_same_company_name_gets_distinct_folder(db, storage, customer):
    twin = customer_service.create_customer(db, storage, "Muster GmbH", "10004")
    assert twin.folder_name == "Muster_GmbH_10004"


# --- Weboberfläche ---------------------------------------------------------------

def test_admin_area_requires_login(client):
    assert client.get("/admin").status_code == 401
    assert client.get("/admin/customers").status_code == 401
    assert client.get("/admin", auth=("admin", "falsch")).status_code == 401


def test_create_customer_via_web_form(client, storage_root):
    response = client.post(
        "/admin/customers/new",
        data={"company_name": "Demo Handel GmbH", "customer_number": "10003"},
        auth=ADMIN_AUTH,
    )
    assert response.status_code == 200
    assert "Demo Handel GmbH" in response.text
    assert "http://localhost:8000/upload/" in response.text
    assert (storage_root / "Demo_Handel_GmbH" / "Stammdaten" / "Ausweis").is_dir()

    listing = client.get("/admin/customers", auth=ADMIN_AUTH)
    assert "Demo Handel GmbH" in listing.text and "10003" in listing.text
