"""Tests für Storage, Dateinamen und Path-Traversal-Schutz (Pflichttest 10)."""

from __future__ import annotations

import io
from datetime import date
from pathlib import PurePosixPath

import pytest

from app.domain.document_types import get_document_type
from app.domain.exceptions import StorageError
from app.services.filename_service import build_filename, make_unique, slugify
from app.services.storage_service import LocalStorageService

DIRECTORY = PurePosixPath("Muster_GmbH/FIBU/2026/04_April/Bank")


@pytest.fixture
def local_storage(tmp_path):
    return LocalStorageService(tmp_path / "storage")


# --- Test 10: doppelter Dateiname -> nichts wird überschrieben ---------------------

def test_duplicate_filename_does_not_overwrite(local_storage, tmp_path):
    name = "2026-04_Kontoauszug.pdf"
    local_storage.save_file(io.BytesIO(b"%PDF erste Datei"), DIRECTORY / name)

    second_name = make_unique(local_storage, DIRECTORY, name)
    local_storage.save_file(io.BytesIO(b"%PDF zweite Datei"), DIRECTORY / second_name)

    third_name = make_unique(local_storage, DIRECTORY, name)

    folder = tmp_path / "storage" / DIRECTORY
    assert second_name == "2026-04_Kontoauszug_2.pdf"
    assert third_name == "2026-04_Kontoauszug_3.pdf"
    assert (folder / name).read_bytes() == b"%PDF erste Datei"
    assert (folder / second_name).read_bytes() == b"%PDF zweite Datei"


def test_storage_refuses_to_overwrite_existing_file(local_storage):
    target = DIRECTORY / "beleg.pdf"
    local_storage.save_file(io.BytesIO(b"%PDF original"), target)
    with pytest.raises(StorageError):
        local_storage.save_file(io.BytesIO(b"%PDF neu"), target)


# --- Path Traversal ---------------------------------------------------------------

@pytest.mark.parametrize("bad_path", ["../ausserhalb.pdf", "Muster_GmbH/../../x.pdf", "/etc/passwd"])
def test_path_traversal_is_blocked(local_storage, bad_path):
    with pytest.raises(StorageError):
        local_storage.save_file(io.BytesIO(b"%PDF"), PurePosixPath(bad_path))


# --- Dateinamen -------------------------------------------------------------------

def test_fibu_filename():
    name = build_filename(get_document_type("eingangsrechnung"), "Rechnung123.pdf", "pdf", 2026, 3)
    assert name == "2026-03_Eingangsrechnung_Rechnung123.pdf"


def test_stammdaten_filename_uses_upload_date():
    name = build_filename(get_document_type("gewerbeanmeldung"), "Scan.PDF", "pdf", None, None, date(2026, 10, 11))
    assert name == "2026-10-11_Gewerbeanmeldung_Scan.pdf"


def test_filename_is_sanitized():
    name = build_filename(get_document_type("kontoauszug"), "..\\..\\Auszug März (final).pdf", "pdf", 2026, 4)
    assert name == "2026-04_Kontoauszug_Auszug_Maerz_final.pdf"
    assert "/" not in name and "\\" not in name and ".." not in name


def test_slugify():
    assert slugify("Müller & Söhne GmbH") == "Mueller_Soehne_GmbH"
    assert slugify("../../etc/passwd") == "etc_passwd"
    assert slugify("   ") == ""
