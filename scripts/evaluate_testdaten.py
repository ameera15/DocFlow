"""Erkennungstest mit externen Testdokumenten aus ``testdaten/``.

Aufruf (im Projektordner):
    python -m scripts.evaluate_testdaten

Für jede Zeile in ``testdaten/manifest.csv`` wird die Datei genau wie beim Upload
validiert, der Text ausgelesen (PDF-Text bzw. OCR) und klassifiziert. Das Ergebnis
wird mit der erwarteten Dokumentart und dem erwarteten Zeitraum verglichen und
nach ``testdaten/ergebnisse.csv`` geschrieben.

Es wird nichts in der Datenbank oder in ``storage/`` angelegt.
"""

from __future__ import annotations

import csv
import io
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import BASE_DIR
from app.domain.exceptions import InvalidFileError
from app.services.classification_service import classify
from app.services.text_extraction_service import TextExtractor
from app.services.validation_service import validate_upload

TESTDATEN_DIR = BASE_DIR / "testdaten"
MANIFEST = TESTDATEN_DIR / "manifest.csv"
RESULTS = TESTDATEN_DIR / "ergebnisse.csv"
MAX_SIZE_BYTES = 10 * 1024 * 1024


@dataclass
class Evaluation:
    datei: str
    mandant: str
    kategorie: str
    erwartet: str
    erkannt: str
    sicherheit: str
    textquelle: str
    dauer_ms: int
    korrekt: bool
    mandant_gefunden: str
    begruendung: str


def _expected(row: dict[str, str]) -> str:
    period = row["erwarteter_zeitraum"].strip()
    return f"{row['erwartete_art']} {period}".strip()


def evaluate_file(path: Path, company: str, extractor: TextExtractor) -> tuple[str, str, str, str, str]:
    """Liefert (erkannt, sicherheit, textquelle, mandant_gefunden, begründung) wie im Upload-Ablauf.

    ``mandant_gefunden`` = "nein" bedeutet: Im Dashboard erscheint das Dokument als
    "Prüfung nötig", weil der Mandantenname im Dokument nicht gefunden wurde.
    """
    data = path.read_bytes()
    stream = io.BytesIO(data)
    try:
        validated = validate_upload(path.name, stream, MAX_SIZE_BYTES)
    except InvalidFileError as exc:
        return "abgelehnt", "–", "–", "–", str(exc)

    extracted = extractor.extract(stream, validated.extension)
    result = classify(extracted.text, path.name, company)
    # Wie im Upload-Service: nur "hoch" mit Zeitraum (bzw. ohne Zeitraumpflicht) wird direkt abgelegt.
    if result.document_type is None or result.confidence == "niedrig":
        recognized = "ungeklaert"
    else:
        recognized = result.document_type.key
        if result.document_type.requires_period and result.year and result.month:
            recognized += f" {result.year:04d}-{result.month:02d}"
    found = {True: "ja", False: "nein", None: "–"}[result.customer_name_found]
    return recognized, result.confidence, extracted.source, found, " | ".join(result.evidence)


def run(manifest: Path = MANIFEST, extractor: TextExtractor | None = None) -> list[Evaluation]:
    extractor = extractor or TextExtractor()
    results: list[Evaluation] = []
    with manifest.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            path = manifest.parent / row["datei"]
            start = time.perf_counter()
            recognized, confidence, source, found, why = evaluate_file(path, row["mandant"], extractor)
            duration = int((time.perf_counter() - start) * 1000)
            expected = _expected(row)
            results.append(Evaluation(
                datei=row["datei"], mandant=row["mandant"], kategorie=row["kategorie"],
                erwartet=expected, erkannt=recognized, sicherheit=confidence, textquelle=source,
                dauer_ms=duration, korrekt=(recognized == expected), mandant_gefunden=found, begruendung=why,
            ))
    return results


def write_results(results: list[Evaluation], target: Path = RESULTS) -> None:
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["datei", "mandant", "kategorie", "erwartet", "erkannt", "sicherheit",
                         "textquelle", "dauer_ms", "korrekt", "mandant_gefunden", "begruendung"])
        for r in results:
            writer.writerow([r.datei, r.mandant, r.kategorie, r.erwartet, r.erkannt, r.sicherheit,
                             r.textquelle, r.dauer_ms, "ja" if r.korrekt else "nein", r.mandant_gefunden,
                             r.begruendung])


def main() -> None:
    results = run()
    write_results(results)
    width = max(len(Path(r.datei).name) for r in results)
    for r in results:
        mark = "OK  " if r.korrekt else "FEHL"
        print(f"{mark} {Path(r.datei).name:<{width}}  erwartet: {r.erwartet:<28} erkannt: {r.erkannt:<28} "
              f"({r.sicherheit}, {r.dauer_ms} ms, Mandant im Dokument: {r.mandant_gefunden})")
    correct = sum(r.korrekt for r in results)
    print(f"\n{correct} von {len(results)} korrekt – Details: {RESULTS.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
