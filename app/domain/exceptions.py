"""Fachliche Fehlerklassen.

Jede Klasse trägt eine verständliche Meldung für den Benutzer (``user_message``).
Technische Details gehören nicht in diese Meldung, sondern ins Log.
"""

from __future__ import annotations


class DocFlowError(Exception):
    """Basisklasse für alle erwartbaren Fehler in DocFlow."""

    default_message = "Es ist ein Fehler aufgetreten."

    def __init__(self, user_message: str | None = None) -> None:
        self.user_message = user_message or self.default_message
        super().__init__(self.user_message)


# --- Mandanten -------------------------------------------------------------

class InvalidTokenError(DocFlowError):
    default_message = "Dieser Upload-Link ist ungültig. Bitte wenden Sie sich an Ihre Kanzlei."


class CustomerNotFoundError(DocFlowError):
    default_message = "Der Mandant wurde nicht gefunden."


class CustomerValidationError(DocFlowError):
    default_message = "Die Mandantendaten sind ungültig."


class DuplicateCustomerNumberError(CustomerValidationError):
    default_message = "Diese Mandantennummer ist bereits vergeben."


class DocumentNotFoundError(DocFlowError):
    default_message = "Das Dokument wurde nicht gefunden."


# --- Uploads ---------------------------------------------------------------

class InvalidFileError(DocFlowError):
    default_message = "Die Datei ist ungültig."


class MissingDocumentTypeError(DocFlowError):
    default_message = "Bitte wählen Sie eine Dokumentart aus."


class UnknownDocumentTypeError(DocFlowError):
    default_message = "Die gewählte Dokumentart ist unbekannt."


class MissingPeriodError(DocFlowError):
    default_message = "Für Buchhaltungsdokumente muss ein Zeitraum (Monat und Jahr) gewählt werden."


class InvalidPeriodError(DocFlowError):
    default_message = "Der gewählte Zeitraum ist ungültig."


class StorageError(DocFlowError):
    default_message = (
        "Das Dokument konnte nicht gespeichert werden. Bitte versuchen Sie es später erneut."
    )
