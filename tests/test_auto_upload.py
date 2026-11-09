"""End-to-End: Upload mit automatischer Erkennung, Posteingang und Prüfung."""

from __future__ import annotations

import pytest

from app.application import create_app
from app.database.models import Document
from app.services import customer_service
from app.services.text_extraction_service import TextExtractor
from scripts.sample_documents import make_pdf, make_png, receipt_lines, sample_lines
from tests.conftest import ADMIN_AUTH, upload

SAMPLES = sample_lines("Muster GmbH")


def pdf(name: str) -> bytes:
    return make_pdf(SAMPLES[name])


def last_document(db) -> Document:
    db.expire_all()
    return db.query(Document).order_by(Document.id.desc()).first()


@pytest.mark.parametrize("name, expected_dir", [
    ("Eingangsrechnung_Buerobedarf.pdf", "Muster_GmbH/FIBU/2026/03_Maerz/Eingangsrechnungen/"),
    ("Ausgangsrechnung_2026-005.pdf", "Muster_GmbH/FIBU/2026/05_Mai/Ausgangsrechnungen/"),
    ("Kontoauszug_April.pdf", "Muster_GmbH/FIBU/2026/04_April/Bank/"),
    ("Z-Bericht_Februar.pdf", "Muster_GmbH/FIBU/2026/02_Februar/Kasse_Z_Berichte/"),
    ("Gewerbeanmeldung.pdf", "Muster_GmbH/Stammdaten/Gewerbeanmeldung/"),
])
def test_auto_upload_routes_by_content(client, db, customer, storage_root, name, expected_dir):
    response = upload(client, customer.upload_token, "auto", "auto", "scan.pdf", pdf(name))

    assert response.status_code == 200
    assert "automatisch erkannt" in response.text
    doc = last_document(db)
    assert doc.destination_path.startswith(expected_dir)
    assert (storage_root / doc.destination_path).is_file()
    assert doc.analysis.method == "automatisch"
    assert doc.analysis.text_source == "pdf-text"
    assert doc.needs_review is False


def test_unrecognizable_document_goes_to_inbox(client, db, customer, storage_root):
    response = upload(client, customer.upload_token, "auto", "auto", "notiz.pdf", pdf("Besprechungsnotiz.pdf"))

    assert response.status_code == 200
    assert "nicht automatisch eindeutig zugeordnet" in response.text
    doc = last_document(db)
    assert doc.document_type == "ungeklaert"
    assert doc.destination_path.startswith("Muster_GmbH/Posteingang_Ungeklaert/")
    assert doc.needs_review is True

    dashboard = client.get("/admin", auth=ADMIN_AUTH).text
    assert "Prüfung nötig" in dashboard


def test_image_without_ocr_goes_to_inbox(client, db, customer):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    upload(client, customer.upload_token, "auto", "auto", "IMG_2041.png", png)
    doc = last_document(db)
    assert doc.document_type == "ungeklaert"
    assert doc.analysis.text_source == "keine"


def test_document_of_other_customer_is_flagged(client, db, storage):
    alpha = customer_service.create_customer(db, storage, "Alpha Consulting UG", "10002")
    upload(client, alpha.upload_token, "auto", "auto", "auszug.pdf", pdf("Kontoauszug_April.pdf"))
    doc = last_document(db)
    assert doc.document_type == "kontoauszug"
    assert doc.needs_review is True
    assert "Mandantenname" in doc.analysis.review_reason


def test_wrong_manual_choice_is_flagged(client, db, customer):
    """Mandant wählt 'Kontoauszug', hochgeladen wird aber ein Z-Bericht."""
    upload(client, customer.upload_token, "kontoauszug", "2026-02", "beleg.pdf", pdf("Z-Bericht_Februar.pdf"))
    doc = last_document(db)
    assert doc.document_type == "kontoauszug"  # Wahl des Mandanten wird respektiert ...
    assert doc.needs_review is True             # ... aber zur Prüfung markiert
    assert "Z-Bericht" in doc.analysis.review_reason


def test_wrong_manual_period_is_flagged(client, db, customer):
    upload(client, customer.upload_token, "eingangsrechnung", "2026-07", "re.pdf", pdf("Eingangsrechnung_Buerobedarf.pdf"))
    doc = last_document(db)
    assert (doc.year, doc.month) == (2026, 7)
    assert doc.needs_review and "03/2026" in doc.analysis.review_reason


def test_manual_type_with_auto_period(client, db, customer):
    upload(client, customer.upload_token, "kontoauszug", "auto", "auszug.pdf", pdf("Kontoauszug_April.pdf"))
    doc = last_document(db)
    assert doc.destination_path.startswith("Muster_GmbH/FIBU/2026/04_April/Bank/")
    assert doc.needs_review is False


def test_matching_manual_choice_is_not_flagged(client, db, customer):
    upload(client, customer.upload_token, "z_bericht", "2026-02", "z.pdf", pdf("Z-Bericht_Februar.pdf"))
    assert last_document(db).needs_review is False


# --- Prüfung durch Mitarbeiter ---------------------------------------------------------

def test_inbox_document_is_assigned_by_staff(client, db, customer, storage_root):
    upload(client, customer.upload_token, "auto", "auto", "notiz.pdf", pdf("Besprechungsnotiz.pdf"))
    doc = last_document(db)
    old = storage_root / doc.destination_path

    client.post(f"/admin/documents/{doc.id}", data={"document_type": "sonstige_stammdaten", "period": ""}, auth=ADMIN_AUTH)

    doc = last_document(db)
    assert doc.destination_path.startswith("Muster_GmbH/Stammdaten/Sonstige/")
    assert not old.exists() and (storage_root / doc.destination_path).is_file()
    assert doc.needs_review is False and doc.analysis.reviewed_by == ADMIN_AUTH[0]


def test_staff_can_confirm_flagged_document(client, db, customer):
    upload(client, customer.upload_token, "kontoauszug", "2026-02", "beleg.pdf", pdf("Z-Bericht_Februar.pdf"))
    doc = last_document(db)
    review_page = client.get(f"/admin/documents/{doc.id}", auth=ADMIN_AUTH).text
    assert "Grund für die Prüfung" in review_page

    response = client.post(f"/admin/documents/{doc.id}/confirm", auth=ADMIN_AUTH)
    assert response.status_code == 200 and "Einordnung bestätigt" in response.text
    assert last_document(db).needs_review is False


def test_inbox_document_cannot_just_be_confirmed(client, db, customer):
    upload(client, customer.upload_token, "auto", "auto", "notiz.pdf", pdf("Besprechungsnotiz.pdf"))
    doc = last_document(db)
    assert client.post(f"/admin/documents/{doc.id}/confirm", auth=ADMIN_AUTH).status_code == 400
    assert last_document(db).needs_review is True


def test_review_page_prefills_detected_type(client, db, customer):
    upload(client, customer.upload_token, "kontoauszug", "2026-02", "beleg.pdf", pdf("Z-Bericht_Februar.pdf"))
    doc = last_document(db)
    page = client.get(f"/admin/documents/{doc.id}", auth=ADMIN_AUTH).text
    assert "Erkannt als" in page and "Z-Bericht" in page


# --- OCR (nur wenn eine OCR-Engine installiert ist: pip install -r requirements-ocr.txt) ---

ocr_available = TextExtractor().ocr_available
needs_ocr = pytest.mark.skipif(not ocr_available, reason="keine OCR-Engine installiert")


@pytest.fixture
def ocr_client(settings):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    app = create_app(replace(settings, enable_ocr=True))
    db = app.state.session_factory()
    customer = customer_service.create_customer(db, app.state.storage, "Muster GmbH", "10001")
    yield TestClient(app), db, customer
    db.close()


def scanned_pdf(lines: list[str]) -> bytes:
    """PDF, das nur ein Bild enthält (wie aus einem Scanner) – ohne Textebene."""
    import io

    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(make_pdf(lines))
    image = document[0].render(scale=2).to_pil().convert("L")
    document.close()
    buffer = io.BytesIO()
    image.save(buffer, format="PDF")
    return buffer.getvalue()


@needs_ocr
def test_photo_of_receipt_is_recognized_with_ocr(ocr_client):
    client, db, customer = ocr_client
    response = upload(client, customer.upload_token, "auto", "auto", "IMG_2041.png", make_png(receipt_lines()))

    assert response.status_code == 200
    doc = last_document(db)
    assert doc.analysis.text_source == "ocr"
    assert doc.document_type == "kassenbeleg"
    assert doc.destination_path.startswith("Muster_GmbH/FIBU/2026/06_Juni/Kasse_Z_Berichte/")


@needs_ocr
def test_scanned_pdf_without_text_layer_is_recognized(ocr_client):
    client, db, customer = ocr_client
    content = scanned_pdf(SAMPLES["Eingangsrechnung_Buerobedarf.pdf"])
    upload(client, customer.upload_token, "auto", "auto", "Scan_0001.pdf", content)

    doc = last_document(db)
    assert doc.analysis.text_source == "ocr"
    assert doc.destination_path.startswith("Muster_GmbH/FIBU/2026/03_Maerz/Eingangsrechnungen/")
