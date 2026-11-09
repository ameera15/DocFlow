"""App-Factory und Logging-Setup.

Bewusst ohne Seiteneffekte beim Import: Tests erzeugen hier eigene
App-Instanzen mit Temp-Verzeichnissen. Die produktive Instanz entsteht in
``app/main.py``.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, Settings
from app.database.database import create_session_factory
from app.routes import customers, dashboard, documents, uploads
from app.services.storage_service import LocalStorageService
from app.services.text_extraction_service import TextExtractor


def setup_logging(log_dir: Path) -> None:
    """Protokolliert auf die Konsole und in logs/docflow.log."""
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(log_dir / "docflow.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False


def create_app(settings: Settings | None = None) -> FastAPI:
    """App-Factory. Tests übergeben eigene Settings mit Temp-Verzeichnissen."""
    settings = settings or Settings.from_env()

    app = FastAPI(
        title="DocFlow – Automated Client Document Intake & Routing",
        version="1.0.0",
        docs_url=None,  # keine öffentliche API-Dokumentation im Prototyp
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.session_factory = create_session_factory(settings.database_url)
    app.state.storage = LocalStorageService(settings.storage_dir)
    app.state.text_extractor = TextExtractor(
        settings.tesseract_cmd, enable_ocr=settings.enable_ocr, ocr_engine=settings.ocr_engine
    )

    app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
    app.include_router(dashboard.router)
    app.include_router(customers.router)
    app.include_router(documents.router)
    app.include_router(uploads.router)
    return app
