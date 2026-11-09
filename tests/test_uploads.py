"""End-to-End-Tests des Kunden-Uploads (Pflichttests 3–9 über HTTP)."""

from __future__ import annotations

from datetime import date

import pytest

from app.database.models import Document, UploadStatus
from tests.conftest import ADMIN_AUTH, EXE_BYTES, PDF_BYTES, PNG_BYTES, upload


def stored_files(storage_root):
    return sorted(p.relative_to(storage_root).as_posix() for p in storage_root.rglob("*") if p.is_file())


# --- Abnahme-Szenario: Eingangsrechnung März 2026 -------------------------------------

def test_eingangsrechnung_upload_lands_in_correct_folder(client, customer, storage_root, db):
    response = upload(client, customer.upload_token, "eingangsrechnung", "2026-03", "Rechnung123.pdf")

    assert response.status_code == 200
    assert "Vielen Dank" in response.text
    target = storage_root / "Muster_GmbH/FIBU/2026/03_Maerz/Eingangsrechnungen/2026-03_Eingangsrechnung_Rechnung123.pdf"
    assert target.read_bytes() == PDF_BYTES

    record = db.query(Document).one()
    assert record.status == UploadStatus.SUCCESS.value
    assert record.destination_path == "Muster_GmbH/FIBU/2026/03_Maerz/Eingangsrechnungen/2026-03_Eingangsrechnung_Rechnung123.pdf"

    dashboard = client.get("/admin", auth=ADMIN_AUTH)
    assert "Rechnung123.pdf" in dashboard.text and "03/2026" in dashboard.text


@pytest.mark.parametrize("doc_type, period, filename, expected_dir", [
    ("kontoauszug", "2026-04", "Kontoauszug.pdf", "Muster_GmbH/FIBU/2026/04_April/Bank/"),
    ("z_bericht", "2026-02", "Z-Bericht.png", "Muster_GmbH/FIBU/2026/02_Februar/Kasse_Z_Berichte/"),
    ("gewerbeanmeldung", "", "Gewerbeanmeldung.pdf", "Muster_GmbH/Stammdaten/Gewerbeanmeldung/"),
    ("bankverbindung", "", "IBAN.jpeg", "Muster_GmbH/Stammdaten/Bankverbindungsdaten/"),
])
def test_other_document_types_are_routed(client, customer, storage_root, doc_type, period, filename, expected_dir):
    content = PNG_BYTES if filename.endswith(".png") else (b"\xff\xd8\xff\xe0" + b"\x00" * 16 if filename.endswith(".jpeg") else PDF_BYTES)
    response = upload(client, customer.upload_token, doc_type, period, filename, content)

    assert response.status_code == 200
    files = stored_files(storage_root)
    assert len(files) == 1 and files[0].startswith(expected_dir)


def test_customer_page_does_not_reveal_internal_paths(client, customer):
    form = client.get(f"/upload/{customer.upload_token}")
    success = upload(client, customer.upload_token, "eingangsrechnung", "2026-03")
    for page in (form.text, success.text):
        assert "Muster_GmbH" not in page
        assert "FIBU/" not in page
        assert "/admin" not in page


# --- Test 7: .exe-Datei wird abgelehnt -----------------------------------------------

def test_exe_file_is_rejected(client, customer, storage_root, db):
    response = upload(client, customer.upload_token, "eingangsrechnung", "2026-03", "virus.exe", EXE_BYTES)

    assert response.status_code == 400
    assert "nicht erlaubt" in response.text
    assert stored_files(storage_root) == []
    record = db.query(Document).one()
    assert record.status == UploadStatus.FAILED.value and record.error_message


def test_renamed_exe_is_rejected_by_content_check(client, customer, storage_root):
    response = upload(client, customer.upload_token, "eingangsrechnung", "2026-03", "rechnung.pdf", EXE_BYTES)
    assert response.status_code == 400
    assert stored_files(storage_root) == []


@pytest.mark.parametrize("filename", ["archiv.zip", "script.js", "ohne_endung"])
def test_other_file_types_are_rejected(client, customer, filename):
    assert upload(client, customer.upload_token, "ausweis", "", filename, PDF_BYTES).status_code == 400


def test_too_large_file_is_rejected(client, customer, storage_root):
    big = PDF_BYTES + b"0" * (1024 * 1024)  # > 1 MB (Testlimit)
    response = upload(client, customer.upload_token, "ausweis", "", "gross.pdf", big)
    assert response.status_code == 400 and "zu groß" in response.text
    assert stored_files(storage_root) == []


# --- Test 8: ungültiger Upload-Token -> Zugriff verweigert ------------------------------

def test_invalid_token_is_denied(client, customer, storage_root):
    assert client.get("/upload/ungueltiger-token").status_code == 404
    response = upload(client, "ungueltiger-token", "eingangsrechnung", "2026-03")
    assert response.status_code == 404
    assert "Muster" not in response.text
    assert stored_files(storage_root) == []


# --- Test 9: noch nicht vorhandenes Jahr -> Struktur wird erzeugt -----------------------

def test_missing_year_structure_is_created(client, customer, storage_root):
    previous_year = date.today().year - 1
    year_dir = storage_root / "Muster_GmbH" / "FIBU" / str(previous_year)
    assert not year_dir.exists()

    response = upload(client, customer.upload_token, "kontoauszug", f"{previous_year}-11", "Auszug.pdf")

    assert response.status_code == 200
    assert (year_dir / "11_November" / "Bank").is_dir()
    assert len([p for p in year_dir.iterdir() if p.is_dir()]) == 12
    assert (year_dir / "01_Januar" / "Kasse_Z_Berichte").is_dir()
    assert any((year_dir / "11_November" / "Bank").iterdir())


# --- Test 10 (über HTTP): gleicher Dateiname zweimal -------------------------------------

def test_duplicate_upload_is_not_overwritten(client, customer, storage_root):
    upload(client, customer.upload_token, "kontoauszug", "2026-04", "Kontoauszug.pdf", PDF_BYTES + b"1")
    upload(client, customer.upload_token, "kontoauszug", "2026-04", "Kontoauszug.pdf", PDF_BYTES + b"2")

    folder = storage_root / "Muster_GmbH/FIBU/2026/04_April/Bank"
    assert (folder / "2026-04_Kontoauszug_Kontoauszug.pdf").read_bytes().endswith(b"1")
    assert (folder / "2026-04_Kontoauszug_Kontoauszug_2.pdf").read_bytes().endswith(b"2")


# --- Fehlende Angaben ------------------------------------------------------------

def test_missing_period_for_fibu_is_rejected(client, customer):
    response = upload(client, customer.upload_token, "eingangsrechnung", "")
    assert response.status_code == 400 and "Zeitraum" in response.text


def test_missing_document_type_is_rejected(client, customer):
    response = upload(client, customer.upload_token, "", "2026-03")
    assert response.status_code == 400 and "Dokumentart" in response.text


def test_unknown_document_type_is_rejected(client, customer):
    response = upload(client, customer.upload_token, "steuerbescheid", "2026-03")
    assert response.status_code == 400 and "unbekannt" in response.text


def test_failed_uploads_appear_in_dashboard(client, customer):
    upload(client, customer.upload_token, "eingangsrechnung", "2026-03", "virus.exe", EXE_BYTES)
    upload(client, customer.upload_token, "eingangsrechnung", "2026-03")
    page = client.get("/admin", auth=ADMIN_AUTH).text
    assert "Fehlgeschlagen" in page and "Erfolgreich" in page
