"""FastAPI-Abhängigkeiten (Dependency Injection).

Datenbank-Session, Storage und Einstellungen hängen am App-Objekt
(``app.state``). Dadurch können Tests eine eigene App mit Temp-Verzeichnissen
erzeugen, ohne das echte ``storage/`` oder ``docflow.db`` zu berühren.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.config import Settings
from app.services.storage_service import StorageService
from app.services.text_extraction_service import TextExtractor

_basic_auth = HTTPBasic(realm="DocFlow Mitarbeiterbereich")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> StorageService:
    return request.app.state.storage


def get_text_extractor(request: Request) -> TextExtractor:
    return request.app.state.text_extractor


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def require_admin(
    credentials: HTTPBasicCredentials = Depends(_basic_auth),
    settings: Settings = Depends(get_settings),
) -> str:
    """Einfacher Schutz des Mitarbeiterbereichs (bewusst keine Benutzerverwaltung)."""
    user_ok = secrets.compare_digest(credentials.username.encode(), settings.admin_username.encode())
    password_ok = secrets.compare_digest(credentials.password.encode(), settings.admin_password.encode())
    if not (user_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Anmeldung fehlgeschlagen",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
