"""Erkennung mit externen Testdokumenten (ZUGFeRD-Corpus, XRechnung-Testsuite).

Die Dokumente und die erwarteten Ergebnisse stehen in ``testdaten/manifest.csv``.
Bekannte Grenzen der regelbasierten Erkennung sind als ``xfail`` markiert: Sie sind
dokumentiert und fallen auf, sobald eine Regeländerung sie behebt (strict=True).
"""

from __future__ import annotations

import csv

import pytest

from app.services.text_extraction_service import TextExtractor
from scripts.evaluate_testdaten import MANIFEST, _expected, evaluate_file

KNOWN_LIMITATIONS = {
    "zugferd_2p0_BASIC_Taxifahrt.pdf":
        "Verkäufer-Block ohne USt-IdNr./IBAN in derselben Zeile – Mandant wird als Empfänger gewertet",
    "MustangGnuaccountingBeispielRE-20201121_508.pdf":
        "englische Rechnung: nur 'invoice' (3 Punkte) – Sicherheit niedrig, landet im Posteingang",
    "zugferd_2p0_MINIMUM.pdf":
        "'Buchungshilfe – KEINE Rechnung' wird wegen des Worts 'Rechnung' als Rechnung erkannt",
}


def _rows():
    with MANIFEST.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    params = []
    for row in rows:
        name = row["datei"].rsplit("/", 1)[-1]
        marks = []
        if name in KNOWN_LIMITATIONS:
            marks.append(pytest.mark.xfail(reason=KNOWN_LIMITATIONS[name], strict=True))
        params.append(pytest.param(row, id=name, marks=marks))
    return params


@pytest.fixture(scope="module")
def extractor():
    # Alle Testdokumente haben eine Textebene; OCR ist hier nicht nötig.
    return TextExtractor(enable_ocr=False)


@pytest.mark.parametrize("row", _rows())
def test_external_document_is_classified_as_expected(row, extractor):
    path = MANIFEST.parent / row["datei"]
    assert path.exists(), f"Testdokument fehlt: {path}"
    recognized, _, _, _, why = evaluate_file(path, row["mandant"], extractor)
    assert recognized == _expected(row), why
