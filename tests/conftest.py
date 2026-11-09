"""Gemeinsame Test-Fixtures.

Jeder Test erhält eine eigene App mit eigener SQLite-Datei und eigenem
Storage-Verzeichnis in ``tmp_path`` – das echte ``storage/`` wird nie berührt.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.application import create_app
from app.config import Settings
from app.services import customer_service

ADMIN_AUTH = ("admin", "test-passwort")

# Minimale, gültige Dateiinhalte (Magic Bytes stimmen).
PDF_BYTES = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
EXE_BYTES = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 32


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        storage_dir=tmp_path / "storage",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        log_dir=tmp_path / "logs",
        max_upload_size_mb=1,
        base_url="http://localhost:8000",
        admin_username=ADMIN_AUTH[0],
        admin_password=ADMIN_AUTH[1],
        enable_ocr=False,  # Tests unabhängig davon, ob Tesseract installiert ist
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def storage(app):
    return app.state.storage


@pytest.fixture
def storage_root(settings):
    return settings.storage_dir


@pytest.fixture
def db(app):
    session = app.state.session_factory()
    yield session
    session.close()


@pytest.fixture
def customer(db, storage):
    """Fiktiver Testmandant 'Muster GmbH'."""
    return customer_service.create_customer(db, storage, "Muster GmbH", "10001")


def upload(client: TestClient, token: str, document_type: str, period: str = "",
           filename: str = "Rechnung123.pdf", content: bytes = PDF_BYTES):
    """Hilfsfunktion: Upload über das Kundenformular absenden."""
    return client.post(
        f"/upload/{token}",
        data={"document_type": document_type, "period": period},
        files={"file": (filename, content, "application/octet-stream")},
    )
