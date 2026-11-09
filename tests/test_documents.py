"""Tests: Dokumente öffnen und falsch eingeordnete Dokumente korrigieren."""

from __future__ import annotations

from app.database.models import Document, DocumentCorrection
from tests.conftest import ADMIN_AUTH, EXE_BYTES, PDF_BYTES, PNG_BYTES, upload


def _upload_and_get(client, db, customer, doc_type, period, filename, content=PDF_BYTES) -> Document:
    assert upload(client, customer.upload_token, doc_type, period, filename, content).status_code == 200
    return db.query(Document).order_by(Document.id.desc()).first()


# --- Öffnen -------------------------------------------------------------------

def test_admin_can_open_uploaded_pdf(client, db, customer):
    doc = _upload_and_get(client, db, customer, "eingangsrechnung", "2026-03", "Rechnung123.pdf")
    response = client.get(f"/admin/documents/{doc.id}/file", auth=ADMIN_AUTH)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content == PDF_BYTES


def test_admin_can_download_image(client, db, customer):
    doc = _upload_and_get(client, db, customer, "z_bericht", "2026-02", "beleg.png", PNG_BYTES)
    response = client.get(f"/admin/documents/{doc.id}/file?download=1", auth=ADMIN_AUTH)

    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("attachment")


def test_documents_require_admin_login(client, db, customer):
    doc = _upload_and_get(client, db, customer, "eingangsrechnung", "2026-03", "Rechnung123.pdf")
    assert client.get(f"/admin/documents/{doc.id}/file").status_code == 401
    assert client.get(f"/admin/documents/{doc.id}").status_code == 401


def test_failed_or_unknown_document_cannot_be_opened(client, db, customer):
    upload(client, customer.upload_token, "eingangsrechnung", "2026-03", "virus.exe", EXE_BYTES)
    failed = db.query(Document).one()
    assert client.get(f"/admin/documents/{failed.id}/file", auth=ADMIN_AUTH).status_code == 404
    assert client.get("/admin/documents/9999/file", auth=ADMIN_AUTH).status_code == 404


def test_review_page_shows_preview(client, db, customer):
    doc = _upload_and_get(client, db, customer, "eingangsrechnung", "2026-03", "Rechnung123.pdf")
    page = client.get(f"/admin/documents/{doc.id}", auth=ADMIN_AUTH)
    assert page.status_code == 200
    assert f'src="/admin/documents/{doc.id}/file"' in page.text
    assert "Einordnung korrigieren" in page.text


# --- Korrigieren ----------------------------------------------------------------

def test_wrong_type_is_corrected_and_file_moved(client, db, customer, storage_root):
    # Mandant lädt einen Z-Bericht fälschlich als Kontoauszug hoch.
    doc = _upload_and_get(client, db, customer, "kontoauszug", "2026-04", "kasse-beleg.png", PNG_BYTES)
    old_file = storage_root / doc.destination_path
    assert old_file.is_file()

    response = client.post(
        f"/admin/documents/{doc.id}",
        data={"document_type": "z_bericht", "period": "2026-04"},
        auth=ADMIN_AUTH,
    )
    assert response.status_code == 200 and "Einordnung korrigiert" in response.text

    db.expire_all()
    doc = db.get(Document, doc.id)
    new_file = storage_root / doc.destination_path
    assert not old_file.exists()
    assert new_file.read_bytes() == PNG_BYTES
    assert doc.destination_path == "Muster_GmbH/FIBU/2026/04_April/Kasse_Z_Berichte/2026-04_Z-Bericht_kasse-beleg.png"
    assert doc.document_type == "z_bericht"

    correction = db.query(DocumentCorrection).one()
    assert correction.old_document_type == "kontoauszug"
    assert correction.new_document_type == "z_bericht"
    assert correction.corrected_by == ADMIN_AUTH[0]


def test_correction_from_fibu_to_stammdaten(client, db, customer, storage_root):
    doc = _upload_and_get(client, db, customer, "eingangsrechnung", "2026-03", "Gewerbeschein.pdf")
    client.post(f"/admin/documents/{doc.id}", data={"document_type": "gewerbeanmeldung", "period": ""}, auth=ADMIN_AUTH)

    db.expire_all()
    doc = db.get(Document, doc.id)
    assert doc.destination_path.startswith("Muster_GmbH/Stammdaten/Gewerbeanmeldung/")
    assert doc.year is None and doc.month is None
    assert (storage_root / doc.destination_path).is_file()


def test_correction_of_period_creates_year_structure(client, db, customer, storage_root):
    doc = _upload_and_get(client, db, customer, "kontoauszug", "2026-04", "Auszug.pdf")
    client.post(f"/admin/documents/{doc.id}", data={"document_type": "kontoauszug", "period": "2025-10"}, auth=ADMIN_AUTH)

    db.expire_all()
    doc = db.get(Document, doc.id)
    assert doc.destination_path.startswith("Muster_GmbH/FIBU/2025/10_Oktober/Bank/")
    assert (storage_root / "Muster_GmbH/FIBU/2025/01_Januar/Eingangsrechnungen").is_dir()


def test_correction_does_not_overwrite_existing_file(client, db, customer, storage_root):
    upload(client, customer.upload_token, "z_bericht", "2026-04", "beleg.pdf", PDF_BYTES + b"A")
    doc = _upload_and_get(client, db, customer, "kontoauszug", "2026-04", "beleg.pdf", PDF_BYTES + b"B")
    client.post(f"/admin/documents/{doc.id}", data={"document_type": "z_bericht", "period": "2026-04"}, auth=ADMIN_AUTH)

    folder = storage_root / "Muster_GmbH/FIBU/2026/04_April/Kasse_Z_Berichte"
    assert (folder / "2026-04_Z-Bericht_beleg.pdf").read_bytes().endswith(b"A")
    assert (folder / "2026-04_Z-Bericht_beleg_2.pdf").read_bytes().endswith(b"B")


def test_invalid_correction_is_rejected(client, db, customer, storage_root):
    doc = _upload_and_get(client, db, customer, "kontoauszug", "2026-04", "Auszug.pdf")
    path_before = doc.destination_path

    unchanged = client.post(f"/admin/documents/{doc.id}", data={"document_type": "kontoauszug", "period": "2026-04"}, auth=ADMIN_AUTH)
    missing_period = client.post(f"/admin/documents/{doc.id}", data={"document_type": "z_bericht", "period": ""}, auth=ADMIN_AUTH)
    unknown = client.post(f"/admin/documents/{doc.id}", data={"document_type": "../../x", "period": "2026-04"}, auth=ADMIN_AUTH)

    assert unchanged.status_code == missing_period.status_code == unknown.status_code == 400
    db.expire_all()
    assert db.get(Document, doc.id).destination_path == path_before
    assert (storage_root / path_before).is_file()
    assert db.query(DocumentCorrection).count() == 0


def test_dashboard_links_to_document_and_marks_correction(client, db, customer):
    doc = _upload_and_get(client, db, customer, "kontoauszug", "2026-04", "Auszug.pdf")
    client.post(f"/admin/documents/{doc.id}", data={"document_type": "z_bericht", "period": "2026-04"}, auth=ADMIN_AUTH)
    page = client.get("/admin", auth=ADMIN_AUTH).text
    assert f'href="/admin/documents/{doc.id}/file"' in page
    assert "Korrigiert" in page
