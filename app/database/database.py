"""Datenbank-Setup (SQLAlchemy 2.0 + SQLite)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Basisklasse aller ORM-Modelle."""


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """Erzeugt Engine + Session-Factory und legt fehlende Tabellen an.

    Für einen Proof of Concept genügt ``create_all``; Migrationen (Alembic)
    wären erst für einen produktiven Betrieb nötig.
    """
    url = make_url(database_url)
    connect_args: dict = {}
    if url.get_backend_name() == "sqlite":
        # FastAPI kann Requests in unterschiedlichen Threads bearbeiten.
        connect_args["check_same_thread"] = False
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, connect_args=connect_args)

    # Modelle importieren, damit sie in Base.metadata registriert sind.
    from app.database import models  # noqa: F401

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
