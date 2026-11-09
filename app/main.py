"""Einstiegspunkt der FastAPI-Anwendung (uvicorn app.main:app)."""

from app.application import create_app, setup_logging
from app.config import Settings

settings = Settings.from_env()
setup_logging(settings.log_dir)
app = create_app(settings)
