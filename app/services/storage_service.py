"""Storage-Abstraktion.

Der Rest der Anwendung arbeitet nur mit *relativen, logischen* Pfaden
(``PurePosixPath``), z. B. ``Muster_GmbH/FIBU/2026/03_Maerz/Eingangsrechnungen``.
Wie und wo diese physisch gespeichert werden, entscheidet die konkrete
Implementierung:

* ``LocalStorageService``  – lokales Verzeichnis ``storage/`` (IU-Prototyp)
* ``SharePointStorageService`` – mögliche spätere Erweiterung (nicht Teil des PoC)
"""

from __future__ import annotations

import logging
import shutil
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.domain.exceptions import StorageError

logger = logging.getLogger(__name__)


class StorageService(ABC):
    """Schnittstelle für die Dokumentenablage."""

    @abstractmethod
    def ensure_directories(self, relative_dirs: Iterable[PurePosixPath]) -> None:
        """Legt die angegebenen Ordner an (bereits vorhandene bleiben unverändert)."""

    @abstractmethod
    def exists(self, relative_path: PurePosixPath) -> bool:
        """Prüft, ob Datei oder Ordner existiert."""

    @abstractmethod
    def save_file(self, source: BinaryIO, destination: PurePosixPath) -> PurePosixPath:
        """Speichert den Inhalt von ``source`` unter ``destination``.

        Eine vorhandene Datei wird niemals überschrieben.
        Gibt den relativen Pfad der gespeicherten Datei zurück.
        """

    @abstractmethod
    def open_file(self, relative_path: PurePosixPath) -> BinaryIO:
        """Öffnet eine gespeicherte Datei zum Lesen (z. B. für die Anzeige)."""

    @abstractmethod
    def move_file(self, source: PurePosixPath, destination: PurePosixPath) -> PurePosixPath:
        """Verschiebt eine Datei (z. B. nach einer Korrektur der Dokumentart).

        Das Ziel darf noch nicht existieren. Gibt den neuen relativen Pfad zurück.
        """


class LocalStorageService(StorageService):
    """Speichert Dokumente im lokalen Dateisystem unterhalb von ``root``."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: PurePosixPath) -> Path:
        """Übersetzt einen relativen Pfad in einen absoluten – mit Path-Traversal-Schutz.

        Zweite Verteidigungslinie: Selbst wenn ein Pfad mit '..' oder ein
        absoluter Pfad hierher gelangt, wird er abgewiesen.
        """
        relative_path = PurePosixPath(relative_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise StorageError("Ungültiger Speicherpfad.")
        target = (self.root / Path(*relative_path.parts)).resolve()
        if not target.is_relative_to(self.root):
            raise StorageError("Ungültiger Speicherpfad.")
        return target

    def ensure_directories(self, relative_dirs: Iterable[PurePosixPath]) -> None:
        try:
            for relative_dir in relative_dirs:
                self._resolve(relative_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.exception("Ordner konnten nicht angelegt werden")
            raise StorageError("Die Ordnerstruktur konnte nicht angelegt werden.") from exc

    def exists(self, relative_path: PurePosixPath) -> bool:
        return self._resolve(relative_path).exists()

    def save_file(self, source: BinaryIO, destination: PurePosixPath) -> PurePosixPath:
        target = self._resolve(destination)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Modus "xb": exklusives Anlegen – schlägt fehl, falls die Datei existiert.
            with target.open("xb") as out:
                shutil.copyfileobj(source, out)
        except FileExistsError as exc:
            raise StorageError("Eine Datei mit diesem Namen existiert bereits.") from exc
        except OSError as exc:
            logger.exception("Datei konnte nicht gespeichert werden: %s", destination)
            target.unlink(missing_ok=True)  # keine halb geschriebenen Dateien zurücklassen
            raise StorageError() from exc
        return PurePosixPath(destination)

    def open_file(self, relative_path: PurePosixPath) -> BinaryIO:
        target = self._resolve(relative_path)
        if not target.is_file():
            raise StorageError("Die Datei wurde in der Ablage nicht gefunden.")
        return target.open("rb")

    def move_file(self, source: PurePosixPath, destination: PurePosixPath) -> PurePosixPath:
        src = self._resolve(source)
        dst = self._resolve(destination)
        if not src.is_file():
            raise StorageError("Die Datei wurde in der Ablage nicht gefunden.")
        if dst.exists():
            raise StorageError("Am Ziel existiert bereits eine Datei mit diesem Namen.")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        except OSError as exc:
            logger.exception("Datei konnte nicht verschoben werden: %s -> %s", source, destination)
            raise StorageError("Die Datei konnte nicht verschoben werden.") from exc
        return PurePosixPath(destination)
