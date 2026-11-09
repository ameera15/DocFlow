"""Erzeugung sicherer, standardisierter und eindeutiger Dateinamen.

Beispiele:
    FIBU:       2026-03_Eingangsrechnung_Rechnung123.pdf
    Stammdaten: 2026-10-11_Gewerbeanmeldung_Scan.pdf
    Kollision:  2026-03_Kontoauszug_Kontoauszug_2.pdf
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import PurePosixPath

from app.domain.document_types import DocumentType
from app.services.storage_service import StorageService

_TRANSLITERATION = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss",
})
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]+")
_MULTI_UNDERSCORE = re.compile(r"_{2,}")

MAX_STEM_LENGTH = 50
MAX_UNIQUE_ATTEMPTS = 1000


def slugify(text: str, max_length: int = MAX_STEM_LENGTH) -> str:
    """Macht aus beliebigem Text einen dateisystemsicheren Namensbestandteil.

    'Müller & Söhne GmbH' -> 'Mueller_Soehne_GmbH'
    '../../etc/passwd'    -> 'etc_passwd'
    """
    text = text.translate(_TRANSLITERATION)
    # Restliche Akzente entfernen (é -> e) und Nicht-ASCII verwerfen.
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = _UNSAFE_CHARS.sub("_", text)
    text = _MULTI_UNDERSCORE.sub("_", text).strip("_-")
    return text[:max_length].rstrip("_-")


def original_stem(original_filename: str) -> str:
    """Dateiname ohne Pfad und ohne Endung – Pfadanteile (auch Windows) werden verworfen."""
    name = original_filename.replace("\\", "/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def build_filename(
    document_type: DocumentType,
    original_filename: str,
    extension: str,
    year: int | None,
    month: int | None,
    upload_date: date | None = None,
) -> str:
    """Setzt den standardisierten Dateinamen zusammen.

    ``extension`` stammt aus der Validierung (bereits geprüft und normalisiert),
    niemals ungeprüft aus dem Original-Dateinamen.
    """
    if document_type.requires_period:
        prefix = f"{year:04d}-{month:02d}"
    else:
        prefix = (upload_date or date.today()).isoformat()

    parts = [prefix, slugify(document_type.filename_label)]
    stem = slugify(original_stem(original_filename))
    if stem:
        parts.append(stem)
    return f"{'_'.join(parts)}.{extension}"


def make_unique(storage: StorageService, directory: PurePosixPath, filename: str) -> str:
    """Hängt _2, _3, ... an, falls der Dateiname im Zielordner schon existiert."""
    if not storage.exists(directory / filename):
        return filename
    stem, extension = filename.rsplit(".", 1)
    for counter in range(2, MAX_UNIQUE_ATTEMPTS + 1):
        candidate = f"{stem}_{counter}.{extension}"
        if not storage.exists(directory / candidate):
            return candidate
    raise RuntimeError(f"Kein freier Dateiname für {filename} in {directory} gefunden.")
