"""Legt fiktive Demo-Mandanten und Beispieldokumente an.

Aufruf (im Projektordner):
    python -m scripts.seed_demo              # Demo-Mandanten + Beispieldokumente in samples/
    python -m scripts.seed_demo --testdaten  # zusätzlich: Testfirmen anlegen und testdaten/ hochladen

Alle Daten sind frei erfunden. Bereits vorhandene Mandantennummern werden
übersprungen, das Skript kann also gefahrlos mehrfach laufen.

Mit ``--testdaten`` werden die Firmen aus ``testdaten/manifest.csv`` als Mandanten
angelegt und jedes Dokument über denselben Ablauf hochgeladen wie über den
persönlichen Upload-Link ("Automatisch erkennen"). Danach stehen die Dokumente in
``storage/`` und im Dashboard. Ein Dokument, das ein Mandant schon hochgeladen hat,
wird beim erneuten Aufruf übersprungen.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from app.config import BASE_DIR, Settings
from app.database.database import create_session_factory
from app.database.models import Customer
from app.domain.exceptions import DocFlowError, DuplicateCustomerNumberError
from app.services import customer_service, upload_service
from app.services.storage_service import LocalStorageService
from app.services.text_extraction_service import TextExtractor
from scripts.sample_documents import write_samples

DEMO_CUSTOMERS = (
    ("Muster GmbH", "10001"),
    ("Alpha Consulting UG", "10002"),
    ("Demo Handel GmbH", "10003"),
)

TESTDATEN_MANIFEST = BASE_DIR / "testdaten" / "manifest.csv"
TESTDATEN_FIRST_NUMBER = 20001  # Mandantennummern der Testfirmen: 20001, 20002, …


def _get_or_create(session, storage, company_name: str, number: str) -> tuple[Customer, bool]:
    """Gibt (Mandant, neu_angelegt) zurück."""
    try:
        return customer_service.create_customer(session, storage, company_name, number), True
    except DuplicateCustomerNumberError:
        customer = next(c for c, _ in customer_service.list_customers_with_counts(session)
                        if c.customer_number == number)
        return customer, False


def _testdaten_rows() -> list[dict[str, str]]:
    with TESTDATEN_MANIFEST.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def upload_testdaten(session, storage, settings: Settings, customers: dict[str, tuple[Customer, bool]]) -> None:
    """Lädt jedes Dokument aus testdaten/ für den im Manifest genannten Mandanten hoch."""
    extractor = TextExtractor(
        tesseract_cmd=settings.tesseract_cmd, enable_ocr=settings.enable_ocr, ocr_engine=settings.ocr_engine
    )
    print("\nUpload der Testdaten (\"Automatisch erkennen\"):")
    for row in _testdaten_rows():
        customer, _ = customers[row["mandant"]]
        path = TESTDATEN_MANIFEST.parent / row["datei"]
        if any(doc.original_filename == path.name for doc in customer.documents):
            print(f"  übersprungen  {path.name}  (bereits hochgeladen)")
            continue
        with path.open("rb") as stream:
            try:
                document = upload_service.process_upload(
                    session, storage, customer, "auto", "auto", path.name, stream,
                    settings.max_upload_size_bytes, extractor=extractor,
                )
            except DocFlowError as exc:
                print(f"  abgelehnt     {path.name:<52} {exc}")
                continue
        target = upload_service.destination_folder(document)
        status = "Prüfung nötig" if document.needs_review else "abgelegt"
        print(f"  {status:<13} {path.name:<52} -> {target}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Demo-Mandanten und Beispieldokumente anlegen.")
    parser.add_argument("--testdaten", action="store_true",
                        help="Testfirmen aus testdaten/manifest.csv anlegen und deren Dokumente hochladen")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    session = create_session_factory(settings.database_url)()
    storage = LocalStorageService(settings.storage_dir)

    customers: dict[str, tuple[Customer, bool]] = {}
    try:
        print("Demo-Mandanten:")
        for company_name, number in DEMO_CUSTOMERS:
            customer, is_new = _get_or_create(session, storage, company_name, number)
            customers[company_name] = (customer, is_new)
            url = customer_service.build_upload_url(settings.base_url, customer.upload_token)
            status = "angelegt" if is_new else "bereits vorhanden"
            print(f"  {number}  {company_name:<32} {status:<18} {url}")

        if args.testdaten:
            print("\nTestfirmen aus testdaten/manifest.csv:")
            names = list(dict.fromkeys(row["mandant"] for row in _testdaten_rows()))
            number = TESTDATEN_FIRST_NUMBER
            for name in names:
                if name in customers:  # z. B. Muster GmbH ist bereits Demo-Mandant
                    continue
                customer, is_new = _get_or_create(session, storage, name, str(number))
                customers[name] = (customer, is_new)
                url = customer_service.build_upload_url(settings.base_url, customer.upload_token)
                status = "angelegt" if is_new else "bereits vorhanden"
                print(f"  {number}  {name:<32} {status:<18} {url}")
                number += 1
            upload_testdaten(session, storage, settings, customers)
    finally:
        session.close()

    samples_dir = BASE_DIR / "samples"
    files = write_samples(samples_dir, company="Muster GmbH")
    print(f"\nBeispieldokumente für 'Muster GmbH' (Upload mit 'Automatisch erkennen'): {samples_dir}")
    for path in files:
        print(f"  - {path.name}")


if __name__ == "__main__":
    main()
