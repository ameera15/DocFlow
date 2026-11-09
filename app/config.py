"""Zentrale Konfiguration von DocFlow.

Alle Einstellungen werden an genau einer Stelle definiert. Werte können über
Umgebungsvariablen überschrieben werden (z. B. ``DOCFLOW_MAX_UPLOAD_SIZE_MB=20``).
Pfade werden ausschließlich mit ``pathlib`` relativ zum Projektverzeichnis
gebildet – es gibt keine hartcodierten absoluten Pfade.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Projektwurzel: .../docflow/
BASE_DIR = Path(__file__).resolve().parent.parent

# Zeitzone für die Anzeige in der Oberfläche (gespeichert wird in UTC).
DISPLAY_TIMEZONE = "Europe/Berlin"

# Erlaubte Dateiendungen für Uploads (klein geschrieben, ohne Punkt).
ALLOWED_EXTENSIONS = frozenset({"pdf", "jpg", "jpeg", "png"})


def _sqlite_url(path: Path) -> str:
    """Erzeugt eine SQLite-URL, die unter Windows, macOS und Linux funktioniert."""
    return f"sqlite:///{path.as_posix()}"


@dataclass(frozen=True)
class Settings:
    """Laufzeit-Einstellungen. Tests erzeugen eigene Instanzen mit Temp-Pfaden."""

    storage_dir: Path = BASE_DIR / "storage"
    database_url: str = _sqlite_url(BASE_DIR / "docflow.db")
    log_dir: Path = BASE_DIR / "logs"
    max_upload_size_mb: int = 10
    base_url: str = "http://localhost:8000"
    admin_username: str = "admin"
    admin_password: str = "docflow"
    # Automatische Erkennung: OCR für Fotos/Scans (optional, siehe requirements-ocr.txt)
    enable_ocr: bool = True
    ocr_engine: str = "auto"          # auto | rapidocr | tesseract
    tesseract_cmd: str | None = None  # nur für Tesseract; None = automatisch suchen

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        """Liest Einstellungen aus Umgebungsvariablen, sonst gelten die Standardwerte."""
        defaults = cls()
        return cls(
            storage_dir=Path(os.getenv("DOCFLOW_STORAGE_DIR", defaults.storage_dir)),
            database_url=os.getenv("DOCFLOW_DATABASE_URL", defaults.database_url),
            log_dir=Path(os.getenv("DOCFLOW_LOG_DIR", defaults.log_dir)),
            max_upload_size_mb=int(
                os.getenv("DOCFLOW_MAX_UPLOAD_SIZE_MB", defaults.max_upload_size_mb)
            ),
            base_url=os.getenv("DOCFLOW_BASE_URL", defaults.base_url).rstrip("/"),
            admin_username=os.getenv("DOCFLOW_ADMIN_USER", defaults.admin_username),
            admin_password=os.getenv("DOCFLOW_ADMIN_PASSWORD", defaults.admin_password),
            enable_ocr=os.getenv("DOCFLOW_OCR", "1").strip().lower() not in {"0", "false", "nein", "off"},
            ocr_engine=os.getenv("DOCFLOW_OCR_ENGINE", defaults.ocr_engine).strip().lower(),
            tesseract_cmd=os.getenv("DOCFLOW_TESSERACT_CMD") or None,
        )
