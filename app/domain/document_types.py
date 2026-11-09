"""Katalog aller Dokumentarten – die einzige Wahrheitsquelle.

Aus diesem Katalog werden abgeleitet:
  * die Auswahl im Upload-Formular,
  * die Validierung der Dokumentart,
  * der Zielordner (Routing),
  * die Standard-Ordnerstruktur eines Mandanten,
  * der Bezeichner im Dateinamen.

Eine neue Dokumentart = eine neue Zeile in ``DOCUMENT_TYPES``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.exceptions import MissingDocumentTypeError, UnknownDocumentTypeError


class DocumentGroup(str, Enum):
    STAMMDATEN = "Stammdaten"
    FIBU = "FIBU"
    POSTEINGANG = "Posteingang"  # automatisch nicht zuordenbar -> Prüfung durch Mitarbeiter


@dataclass(frozen=True)
class DocumentType:
    key: str             # technischer Schlüssel (Formularwert, DB-Wert)
    label: str           # Anzeigename für Mandant und Mitarbeiter
    group: DocumentGroup
    folder: str          # Zielordner unterhalb von Stammdaten/ bzw. FIBU/<Jahr>/<Monat>/
    filename_label: str  # Bezeichner im gespeicherten Dateinamen

    @property
    def requires_period(self) -> bool:
        return self.group is DocumentGroup.FIBU


DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    # --- FIBU (Monat + Jahr erforderlich) -----------------------------------
    DocumentType("eingangsrechnung", "Eingangsrechnung", DocumentGroup.FIBU, "Eingangsrechnungen", "Eingangsrechnung"),
    DocumentType("ausgangsrechnung", "Ausgangsrechnung", DocumentGroup.FIBU, "Ausgangsrechnungen", "Ausgangsrechnung"),
    DocumentType("kontoauszug", "Kontoauszug / Bank", DocumentGroup.FIBU, "Bank", "Kontoauszug"),
    DocumentType("kassenbeleg", "Kassenbeleg", DocumentGroup.FIBU, "Kasse_Z_Berichte", "Kassenbeleg"),
    DocumentType("z_bericht", "Z-Bericht", DocumentGroup.FIBU, "Kasse_Z_Berichte", "Z-Bericht"),
    # --- Stammdaten (kein Zeitraum) ------------------------------------------
    DocumentType("gewerbeanmeldung", "Gewerbeanmeldung", DocumentGroup.STAMMDATEN, "Gewerbeanmeldung", "Gewerbeanmeldung"),
    DocumentType("steuernummer", "Steuernummer", DocumentGroup.STAMMDATEN, "Steuernummer", "Steuernummer"),
    DocumentType("betriebsnummer", "Betriebsnummer", DocumentGroup.STAMMDATEN, "Betriebsnummer", "Betriebsnummer"),
    DocumentType("unternehmensnummer_bg", "Unternehmensnummer / BG", DocumentGroup.STAMMDATEN, "Unternehmensnummer_BG", "Unternehmensnummer_BG"),
    DocumentType("bankverbindung", "Bankverbindungsdaten", DocumentGroup.STAMMDATEN, "Bankverbindungsdaten", "Bankverbindung"),
    DocumentType("vollmacht", "Vollmacht / Dienstleistungsvertrag", DocumentGroup.STAMMDATEN, "Vollmacht_Dienstleistungsvertrag", "Vollmacht"),
    DocumentType("ausweis", "Ausweis", DocumentGroup.STAMMDATEN, "Ausweis", "Ausweis"),
    DocumentType("eroeffnungsbilanz", "Eröffnungsbilanz", DocumentGroup.STAMMDATEN, "Eroeffnungsbilanz", "Eroeffnungsbilanz"),
    DocumentType("ust_idnr", "USt-IdNr.", DocumentGroup.STAMMDATEN, "USt_IdNr", "USt-IdNr"),
    DocumentType("sonstige_stammdaten", "Sonstige Stammdaten", DocumentGroup.STAMMDATEN, "Sonstige", "Sonstige"),
)

DOCUMENT_TYPES_BY_KEY: dict[str, DocumentType] = {t.key: t for t in DOCUMENT_TYPES}

# Formularwert für "Automatisch erkennen".
AUTO = "auto"

# Kein auswählbarer Typ: Ziel für Dokumente, die nicht sicher erkannt wurden.
UNCLASSIFIED = DocumentType(
    "ungeklaert", "Ungeklärt (Prüfung nötig)", DocumentGroup.POSTEINGANG, "Posteingang_Ungeklaert", "Ungeklaert"
)


def _unique_folders(group: DocumentGroup) -> tuple[str, ...]:
    """Ordnernamen einer Gruppe in Katalog-Reihenfolge, ohne Duplikate."""
    return tuple(dict.fromkeys(t.folder for t in DOCUMENT_TYPES if t.group is group))


STAMMDATEN_FOLDERS = _unique_folders(DocumentGroup.STAMMDATEN)
FIBU_FOLDERS = _unique_folders(DocumentGroup.FIBU)


def get_document_type(key: str | None) -> DocumentType:
    """Liefert die Dokumentart zu einem Schlüssel oder wirft einen fachlichen Fehler."""
    if not key or not key.strip():
        raise MissingDocumentTypeError()
    try:
        return DOCUMENT_TYPES_BY_KEY[key.strip()]
    except KeyError:
        raise UnknownDocumentTypeError() from None


def document_type_label(key: str | None) -> str:
    """Anzeigename für einen gespeicherten Schlüssel (robust auch für unbekannte Werte)."""
    if key == UNCLASSIFIED.key:
        return UNCLASSIFIED.label
    if key == AUTO:
        return "Automatisch erkennen"
    doc_type = DOCUMENT_TYPES_BY_KEY.get(key or "")
    return doc_type.label if doc_type else (key or "–")
