"""Tests der regelbasierten Erkennung (Dokumentart, Rechnungsrichtung, Zeitraum)."""

from __future__ import annotations

import io
from datetime import date

import pytest

from app.services.classification_service import classify, core_company_name, detect_period, is_customer_issuer
from app.services.text_extraction_service import TextExtractor
from scripts.sample_documents import make_pdf, sample_lines

TODAY = date(2026, 10, 14)
SAMPLES = sample_lines("Muster GmbH")


def text_of(name: str) -> str:
    return "\n".join(SAMPLES[name])


@pytest.mark.parametrize("name, expected_type, expected_period", [
    ("Eingangsrechnung_Buerobedarf.pdf", "eingangsrechnung", (2026, 3)),
    ("Ausgangsrechnung_2026-005.pdf", "ausgangsrechnung", (2026, 5)),
    ("Kontoauszug_April.pdf", "kontoauszug", (2026, 4)),
    ("Z-Bericht_Februar.pdf", "z_bericht", (2026, 2)),
    ("Gewerbeanmeldung.pdf", "gewerbeanmeldung", (None, None)),
])
def test_sample_documents_are_recognized(name, expected_type, expected_period):
    # Neutraler Dateiname: Die Erkennung muss allein aus dem Inhalt funktionieren.
    result = classify(text_of(name), "scan001.pdf", "Muster GmbH", TODAY)
    assert result.document_type.key == expected_type
    assert (result.year, result.month) == expected_period
    assert result.confidence == "hoch"
    assert result.customer_name_found is True


def test_unrelated_text_is_not_classified():
    result = classify(text_of("Besprechungsnotiz.pdf"), "notiz.pdf", "Muster GmbH", TODAY)
    assert result.document_type is None
    assert not result.is_usable


def test_empty_text_is_not_classified():
    result = classify("", "IMG_2041.jpg", "Muster GmbH", TODAY)
    assert result.document_type is None
    assert result.customer_name_found is None


def test_filename_alone_is_not_enough():
    result = classify("", "Rechnung123.pdf", "Muster GmbH", TODAY)
    assert not result.is_usable


def test_customer_name_missing_is_reported():
    result = classify(text_of("Kontoauszug_April.pdf"), "a.pdf", "Alpha Consulting UG", TODAY)
    assert result.document_type.key == "kontoauszug"
    assert result.customer_name_found is False


# --- Eingangs- vs. Ausgangsrechnung -------------------------------------------------

def test_invoice_direction():
    assert is_customer_issuer(text_of("Ausgangsrechnung_2026-005.pdf"), "Muster GmbH") is True
    assert is_customer_issuer(text_of("Eingangsrechnung_Buerobedarf.pdf"), "Muster GmbH") is False
    assert is_customer_issuer(text_of("Eingangsrechnung_Buerobedarf.pdf"), "Andere GmbH") is None


def test_company_name_is_matched_as_whole_word():
    # 'Muster' darf nicht in 'Musterweg' oder 'Mustermann' gefunden werden.
    text = "Rechnung\nMusterweg 1\nMax Mustermann\nRechnungsnummer 1"
    assert is_customer_issuer(text, "Muster GmbH") is None


def test_core_company_name():
    assert core_company_name("Muster GmbH") == "muster"
    assert core_company_name("Alpha Consulting UG (haftungsbeschränkt)") == "alpha consulting"
    assert core_company_name("Müller & Söhne KG") == "mueller soehne"


# --- Zeitraum -----------------------------------------------------------------------

def test_period_ignores_due_date():
    text = "Rechnungsdatum: 30.03.2026\nZahlbar bis 29.04.2026"
    assert detect_period(text, "rechnung", TODAY)[0] == (2026, 3)


def test_period_prefers_service_period():
    text = "Rechnungsdatum: 02.04.2026\nLeistungszeitraum: März 2026"
    assert detect_period(text, "rechnung", TODAY)[0] == (2026, 3)


def test_bank_statement_uses_most_frequent_month():
    text = "Kontoauszug\n03.04.2026 Miete\n15.04.2026 Strom\n30.04.2026 Gehalt\n02.05.2026 Gebühr"
    assert detect_period(text, "kontoauszug", TODAY)[0] == (2026, 4)


@pytest.mark.parametrize("line, expected", [
    ("Datum: 5.6.26", (2026, 6)),
    ("Datum 2026-01-31", (2026, 1)),
    ("Datum: Dezember 2025", (2025, 12)),
    ("Datum: 07/2026", (2026, 7)),
])
def test_date_formats(line, expected):
    assert detect_period(line, "kassenbeleg", TODAY)[0] == expected


def test_implausible_dates_are_ignored():
    assert detect_period("Datum: 01.01.1985", "kassenbeleg", TODAY)[0] is None


# --- Textauslesen -------------------------------------------------------------------

def test_text_is_extracted_from_pdf():
    extractor = TextExtractor(enable_ocr=False)
    pdf = make_pdf(SAMPLES["Kontoauszug_April.pdf"])
    stream = io.BytesIO(pdf)
    result = extractor.extract(stream, "pdf")
    assert result.source == "pdf-text"
    assert "Kontoauszug Nr. 4/2026" in result.text
    assert "Bürobedarf" in result.text  # Umlaute bleiben erhalten
    assert stream.tell() == 0           # Stream ist für das Speichern zurückgespult


def test_image_without_ocr_returns_no_text():
    extractor = TextExtractor(enable_ocr=False)
    result = extractor.extract(io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20), "png")
    assert result.source == "keine" and not result.has_text


def test_broken_pdf_does_not_crash():
    extractor = TextExtractor(enable_ocr=False)
    result = extractor.extract(io.BytesIO(b"%PDF-1.4 kaputt"), "pdf")
    assert not result.has_text


# --- OCR-Toleranz -----------------------------------------------------------------

@pytest.mark.parametrize("ocr_text", ["Rückgeld", "Rueckgeld", "Rückgeld".replace("ü", "ø"), "Rckgeld"])
def test_keywords_tolerate_ocr_umlaut_errors(ocr_text):
    from app.services.classification_service import contains, normalize

    assert contains(normalize(ocr_text), "rueckgeld")


def test_receipt_with_broken_umlauts_is_recognized():
    text = "Bøckerei Mller\nQuittung\nDatum: 03.07.2026\nBrøtchen 3,20 EUR\nRøckgeld 1,80 EUR"
    result = classify(text, "IMG_1.jpg", "Muster GmbH", TODAY)
    assert result.document_type.key == "kassenbeleg"
    assert (result.year, result.month) == (2026, 7)


def test_ocr_boxes_are_grouped_into_lines():
    from app.services.text_extraction_service import group_into_lines

    def box(x, y, w=100, h=20):
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    boxes = [box(300, 102), box(10, 100), box(10, 140)]
    texts = ["72,32", "Summe EUR", "Gegeben bar"]
    assert group_into_lines(boxes, texts) == "Summe EUR 72,32\nGegeben bar"
