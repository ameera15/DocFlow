"""Serverseitige Prüfung hochgeladener Dateien.

Geprüft wird:
  1. Datei vorhanden, Dateiname nicht leer
  2. Endung in der Whitelist (pdf, jpg, jpeg, png)
  3. Datei nicht leer und nicht größer als das konfigurierte Maximum
  4. Dateiinhalt passt zur Endung ("Magic Bytes") – damit wird z. B. auch
     eine in 'rechnung.pdf' umbenannte .exe-Datei abgelehnt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import BinaryIO

from app.config import ALLOWED_EXTENSIONS
from app.domain.exceptions import InvalidFileError

# Dateisignaturen der erlaubten Formate.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
}
_HEADER_LENGTH = 8


@dataclass(frozen=True)
class ValidatedFile:
    original_filename: str  # nur Anzeige/Audit – niemals für Pfade verwenden
    extension: str          # normalisiert: pdf | jpg | png
    size: int               # Bytes


def _normalize_extension(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    extension = name.rsplit(".", 1)[1].lower()
    return "jpg" if extension == "jpeg" else extension


def _stream_size(stream: BinaryIO) -> int:
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    return size


def validate_upload(filename: str | None, stream: BinaryIO | None, max_size_bytes: int) -> ValidatedFile:
    """Prüft eine Upload-Datei. Wirft ``InvalidFileError`` mit verständlicher Meldung."""
    if stream is None or not filename or not filename.strip():
        raise InvalidFileError("Bitte wählen Sie eine Datei aus.")

    extension = _normalize_extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidFileError("Dieser Dateityp ist nicht erlaubt. Erlaubt sind PDF, JPG und PNG.")

    size = _stream_size(stream)
    if size == 0:
        raise InvalidFileError("Die Datei ist leer.")
    if size > max_size_bytes:
        limit_mb = max_size_bytes / (1024 * 1024)
        raise InvalidFileError(f"Die Datei ist zu groß. Erlaubt sind maximal {limit_mb:g} MB.")

    header = stream.read(_HEADER_LENGTH)
    stream.seek(0)
    if not header.startswith(_SIGNATURES[extension]):
        raise InvalidFileError(
            "Der Dateiinhalt passt nicht zur Dateiendung. Bitte laden Sie eine echte PDF-, JPG- oder PNG-Datei hoch."
        )

    return ValidatedFile(original_filename=filename.strip(), extension=extension, size=size)
