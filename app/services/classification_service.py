"""Regelbasierte Erkennung von Dokumentart und Zeitraum.

Bewusst KEINE KI: Die Erkennung arbeitet mit nachvollziehbaren Regeln
(Schlüsselbegriffe mit Gewichten + Datumsmuster). Jede Entscheidung wird mit
den gefundenen Begriffen begründet und kann von Mitarbeitern geprüft werden.

Ablauf:
  1. Text normalisieren (klein, Umlaute -> ae/oe/ue, Leerraum vereinheitlichen)
  2. Für jede Dokumentart Punkte für gefundene Schlüsselbegriffe vergeben
     (Dateiname zählt mit halbem Gewicht)
  3. Bei Rechnungen: Ist der Mandant Absender (-> Ausgangsrechnung) oder
     Empfänger (-> Eingangsrechnung)?
  4. Für FIBU-Dokumente den Zeitraum aus dem Text bestimmen
  5. Sicherheit (hoch / mittel / niedrig) aus Punktzahl und Abstand zur
     zweitbesten Dokumentart ableiten
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from app.domain.document_types import DOCUMENT_TYPES_BY_KEY, DocumentType
from app.domain.exceptions import InvalidPeriodError
from app.domain.periods import validate_period

# --- Schlüsselbegriffe ----------------------------------------------------------
# Begriffe sind bereits normalisiert (klein, ae/oe/ue/ss). Gewicht = Aussagekraft.
# "rechnung" steht für Eingangs- UND Ausgangsrechnung; die Richtung wird danach bestimmt.
RULES: dict[str, tuple[tuple[str, float], ...]] = {
    "rechnung": (
        ("rechnungsnummer", 4), ("rechnungs-nr", 4), ("rechnungsnr", 4), ("rechnung nr", 4),
        ("rechnungsdatum", 3), ("rechnung", 3), ("invoice", 3),
        ("leistungsdatum", 2), ("leistungszeitraum", 2), ("rechnungsbetrag", 2), ("gesamtbetrag", 2),
        ("zahlbar", 1.5), ("zahlungsziel", 1.5), ("nettobetrag", 1), ("netto", 1), ("zzgl", 1),
        ("umsatzsteuer", 1), ("mwst", 1),
    ),
    "kontoauszug": (
        ("kontoauszug", 6), ("alter saldo", 3), ("neuer saldo", 3), ("alter kontostand", 3),
        ("neuer kontostand", 3), ("buchungstag", 2), ("wertstellung", 2), ("valuta", 2),
        ("kontostand", 1.5), ("saldo", 1), ("umsaetze", 1), ("auszug nr", 2),
    ),
    "z_bericht": (
        ("z-bericht", 6), ("z bericht", 6), ("z-bon", 5), ("zbon", 5), ("tagesabschluss", 5),
        ("kassenabschluss", 4), ("z-nr", 3), ("z-zaehler", 3), ("nullstellung", 3),
        ("kassenbericht", 3), ("tagesumsatz", 2), ("anzahl bons", 2), ("bonanzahl", 2),
    ),
    "kassenbeleg": (
        ("kassenbon", 5), ("kassenbeleg", 5), ("quittung", 4), ("bon-nr", 3), ("bon nr", 3),
        ("rueckgeld", 2.5), ("gegeben", 1.5), ("bar ", 1), ("tse", 1.5), ("kasse", 1),
        ("vielen dank fuer ihren einkauf", 3),
    ),
    "gewerbeanmeldung": (
        ("gewerbeanmeldung", 7), ("gewerbe-anmeldung", 7), ("14 gewo", 4), ("gewerbeordnung", 3),
        ("gewerbeamt", 2.5), ("angemeldete taetigkeit", 3), ("beginn der angemeldeten", 3),
        ("ordnungsamt", 1.5),
    ),
    "steuernummer": (
        ("zuteilung der steuernummer", 7), ("mitteilung ueber die steuernummer", 7),
        ("steuernummer zugeteilt", 6), ("ihre steuernummer lautet", 6), ("steuerliche erfassung", 4),
        ("finanzamt", 1.5), ("steuernummer", 1),
    ),
    "betriebsnummer": (
        ("betriebsnummern-service", 6), ("zuteilung einer betriebsnummer", 7), ("betriebsnummer", 3.5),
        ("bundesagentur fuer arbeit", 2),
    ),
    "unternehmensnummer_bg": (
        ("unternehmensnummer", 5), ("berufsgenossenschaft", 4), ("gesetzliche unfallversicherung", 3),
        ("mitgliedsnummer", 2), ("mitgliedschaft", 1.5),
    ),
    "bankverbindung": (
        ("kontoeroeffnungsbestaetigung", 7), ("kontoeroeffnung", 6), ("bestaetigung der bankverbindung", 6),
        ("bankverbindung", 2.5), ("kontoinhaber", 2), ("bic", 1), ("iban", 1),
    ),
    "vollmacht": (
        ("vollmacht", 6), ("dienstleistungsvertrag", 6), ("mandatsvertrag", 6), ("beratungsvertrag", 5),
        ("bevollmaechtigt", 3), ("auftraggeber", 1), ("auftragnehmer", 1),
    ),
    "ausweis": (
        ("personalausweis", 7), ("reisepass", 7), ("identity card", 4), ("staatsangehoerigkeit", 2.5),
        ("gueltig bis", 1.5), ("geburtsort", 2), ("geburtsdatum", 1),
    ),
    "eroeffnungsbilanz": (
        ("eroeffnungsbilanz", 8), ("aktiva", 2), ("passiva", 2), ("bilanz", 2), ("eigenkapital", 1.5),
        ("stammkapital", 1),
    ),
    "ust_idnr": (
        ("bundeszentralamt fuer steuern", 4), ("umsatzsteuer-identifikationsnummer", 2),
        ("zuteilung einer umsatzsteuer", 6), ("mitteilung ueber die erteilung", 5), ("ust-idnr", 0.5),
    ),
}

# Hinweise darauf, dass eine Zeile den RECHNUNGSSTELLER beschreibt (Briefkopf/Fußzeile).
ISSUER_MARKERS = (
    "ust-idnr", "ust-id", "steuernummer", "st.-nr", "steuer-nr", "iban", "bic", "geschaeftsfuehr",
    "amtsgericht", "hrb", "hra", "handelsregister", "inhaber", "www.", "e-mail", "tel.", "telefon",
    "absender",
)
# Kennzeichnen den Empfänger-Block.
RECIPIENT_MARKERS = ("rechnung an", "rechnungsempfaenger", "empfaenger", "kunde:", "kundennr", "an:")

LEGAL_FORMS = re.compile(
    r"\b(gmbh|ug|ag|kg|ohg|gbr|ek|e\.k\.|mbh|haftungsbeschraenkt|co|und|partg|ev|e\.v\.)\b"
)

HIGH_SCORE, HIGH_MARGIN = 6.0, 2.5
MEDIUM_SCORE = 3.5
FILENAME_WEIGHT = 0.5

# --- Datumserkennung ----------------------------------------------------------------
MONTHS = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "maerz": 3, "marz": 3, "mrz": 3, "april": 4, "apr": 4,
    "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9,
    "sept": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11, "dezember": 12, "dez": 12,
}
_DATE_DMY = re.compile(r"\b(\d{1,2})\s?[./]\s?(\d{1,2})\s?[./]\s?(\d{4}|\d{2})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_MONTH_NAME = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{4})\b")
_DATE_MY = re.compile(r"(?<![\d./])(\d{1,2})\s?/\s?(\d{4})\b")

# Je Dokumentart: Zeilen mit diesen Begriffen bestimmen den Zeitraum (Reihenfolge = Priorität).
PERIOD_LABELS: dict[str, tuple[str, ...]] = {
    "rechnung": ("leistungszeitraum", "leistungsdatum", "lieferdatum", "rechnungsdatum", "datum"),
    "kontoauszug": ("zeitraum", "auszug", "kontoauszug", "vom", "bis"),
    "z_bericht": ("z-bericht", "tagesabschluss", "datum"),
    "kassenbeleg": ("datum",),
}
# Zeilen mit diesen Begriffen sind KEIN Leistungszeitraum (Fälligkeit, Gültigkeit, Geburtstag ...).
PERIOD_IGNORE = ("zahlbar", "faellig", "zahlungsziel", "gueltig", "geburt", "frist", "skonto", "bis zum")

_TRANSLATE = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "\u00a0": " ",
    "ø": "o", "å": "a", "à": "a", "á": "a", "é": "e", "è": "e", "ó": "o", "ò": "o", "ú": "u", "ù": "u",
})

# OCR liest Umlaute oft falsch oder gar nicht ("Rückgeld" -> "Rockgeld"/"Rckgeld").
# Begriffe mit ae/oe/ue/ss werden deshalb tolerant gesucht.
_UMLAUT_VARIANTS = {"ae": "(?:ae|a|)", "oe": "(?:oe|o|)", "ue": "(?:ue|u|o|)", "ss": "(?:ss|s|)"}
_UMLAUT_PATTERN = re.compile("|".join(_UMLAUT_VARIANTS))
_pattern_cache: dict[tuple[str, bool], re.Pattern] = {}


def _pattern(term: str, word_start: bool = False) -> re.Pattern:
    key = (term, word_start)
    if key not in _pattern_cache:
        body = _UMLAUT_PATTERN.sub(lambda m: _UMLAUT_VARIANTS[m.group(0)], re.escape(term))
        _pattern_cache[key] = re.compile(("(?<![a-z0-9])" if word_start else "") + body)
    return _pattern_cache[key]


def contains(text: str, term: str, word_start: bool = False) -> bool:
    """Sucht einen (normalisierten) Begriff – tolerant gegenüber OCR-Umlautfehlern."""
    if not word_start and term in text:
        return True
    return bool(_pattern(term, word_start).search(text))


@dataclass
class ClassificationResult:
    document_type: DocumentType | None
    year: int | None = None
    month: int | None = None
    confidence: str = "niedrig"         # hoch | mittel | niedrig
    score: float = 0.0
    evidence: list[str] = field(default_factory=list)  # Begründung, für Mitarbeiter sichtbar
    customer_name_found: bool | None = None            # None = kein Text vorhanden

    @property
    def is_confident(self) -> bool:
        return self.document_type is not None and self.confidence == "hoch"

    @property
    def is_usable(self) -> bool:
        return self.document_type is not None and self.confidence in {"hoch", "mittel"}


def normalize(text: str) -> str:
    text = text.lower().translate(_TRANSLATE)
    return re.sub(r"[ \t]+", " ", text)


# --- Dokumentart --------------------------------------------------------------------

def _score(text: str, filename: str) -> dict[str, tuple[float, list[str]]]:
    scores: dict[str, tuple[float, list[str]]] = {}
    for kind, keywords in RULES.items():
        total, hits = 0.0, []
        for keyword, weight in keywords:
            if contains(text, keyword):
                total += weight
                hits.append(keyword)
            elif keyword.strip() in filename:
                total += weight * FILENAME_WEIGHT
                hits.append(f"{keyword.strip()} (Dateiname)")
        if total:
            scores[kind] = (total, hits)
    return scores


def core_company_name(company_name: str) -> str:
    """'Muster GmbH' -> 'muster'; 'Alpha Consulting UG (haftungsbeschränkt)' -> 'alpha consulting'."""
    name = normalize(company_name)
    name = re.sub(r"[()&,+]", " ", name)
    name = LEGAL_FORMS.sub(" ", name)
    return re.sub(r"\s+", " ", name).strip()


def _lines_with_name(lines: list[str], core: str) -> list[int]:
    """Zeilen, in denen der Firmenname als ganzes Wort vorkommt ('muster' ≠ 'musterweg')."""
    if not core:
        return []
    pattern = re.compile(r"(?<![a-z0-9])" + re.escape(core) + r"(?![a-z0-9])")
    return [i for i, line in enumerate(lines) if pattern.search(line)]


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    """Merkmal muss am Wortanfang stehen ('an:' darf nicht in 'iban:' gefunden werden)."""
    return any(contains(text, marker, word_start=True) for marker in markers)


def is_customer_issuer(text: str, company_name: str) -> bool | None:
    """True = Mandant hat die Rechnung gestellt; False = Mandant ist Empfänger; None = unklar."""
    core = core_company_name(company_name)
    lines = [line.strip() for line in normalize(text).splitlines() if line.strip()]
    positions = _lines_with_name(lines, core)
    if not positions:
        return None

    for i in positions:
        context = " ".join(lines[max(0, i - 1): i + 2])
        if _contains_marker(context, RECIPIENT_MARKERS):
            return False
    for i in positions:
        context = " ".join(lines[max(0, i - 1): i + 2])
        if _contains_marker(context, ISSUER_MARKERS):
            return True
    return False  # nur im Adressblock erwähnt -> Empfänger


# --- Zeitraum -----------------------------------------------------------------------

def _dates_in_line(line: str) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for d, m, y in _DATE_DMY.findall(line):
        year = int(y) + (2000 if len(y) == 2 else 0)
        found.append((year, int(m)))
    for y, m, _ in _DATE_ISO.findall(line):
        found.append((int(y), int(m)))
    for name, y in _DATE_MONTH_NAME.findall(line):
        found.append((int(y), MONTHS[name]))
    if not found:
        for m, y in _DATE_MY.findall(line):
            found.append((int(y), int(m)))
    return found


def _valid(period: tuple[int, int], today: date) -> bool:
    try:
        validate_period(period[0], period[1], today)
    except InvalidPeriodError:
        return False
    return True


def detect_period(text: str, kind: str, today: date | None = None) -> tuple[tuple[int, int] | None, str | None]:
    """Bestimmt (Jahr, Monat). Gibt zusätzlich die Begründung zurück."""
    today = today or date.today()
    lines = [line.strip() for line in normalize(text).splitlines() if line.strip()]
    candidates: list[tuple[int, int]] = []

    for label in PERIOD_LABELS.get(kind, ("datum",)):
        for line in lines:
            if contains(line, label) and not any(contains(line, skip) for skip in PERIOD_IGNORE):
                dates = [p for p in _dates_in_line(line) if _valid(p, today)]
                if dates:
                    return dates[0], f"Zeitraum aus Zeile „{line[:60]}“"

    for line in lines:
        if any(contains(line, skip) for skip in PERIOD_IGNORE):
            continue
        candidates.extend(p for p in _dates_in_line(line) if _valid(p, today))
    if not candidates:
        return None, None
    (period, count), = Counter(candidates).most_common(1)
    return period, f"häufigster Monat im Dokument ({count} Datumsangaben)"


# --- Gesamtergebnis -------------------------------------------------------------------

def classify(text: str, filename: str, company_name: str, today: date | None = None) -> ClassificationResult:
    """Erkennt Dokumentart und ggf. Zeitraum aus Text (und Dateiname)."""
    norm_text = normalize(text)
    norm_filename = normalize(filename).replace("_", " ")
    scores = _score(norm_text, norm_filename)

    customer_found: bool | None = None
    if norm_text.strip():
        customer_found = bool(_lines_with_name(norm_text.splitlines(), core_company_name(company_name)))

    if not scores:
        reason = "Kein Text erkannt" if not norm_text.strip() else "Keine typischen Begriffe gefunden"
        return ClassificationResult(None, evidence=[reason], customer_name_found=customer_found)

    ranking = sorted(scores.items(), key=lambda item: item[1][0], reverse=True)
    best_kind, (best_score, hits) = ranking[0]
    second_score = ranking[1][1][0] if len(ranking) > 1 else 0.0

    if best_score >= HIGH_SCORE and best_score - second_score >= HIGH_MARGIN:
        confidence = "hoch"
    elif best_score >= MEDIUM_SCORE and best_score > second_score:
        confidence = "mittel"
    else:
        confidence = "niedrig"

    evidence = [f"Begriffe: {', '.join(hits[:6])}"]
    if len(ranking) > 1:
        evidence.append(f"nächstbeste Art: {ranking[1][0]} ({second_score:g} Punkte)")

    key = best_kind
    if best_kind == "rechnung":
        issuer = is_customer_issuer(text, company_name)
        key = "ausgangsrechnung" if issuer else "eingangsrechnung"
        evidence.append(
            "Mandant ist Rechnungssteller" if issuer
            else "Mandant ist Rechnungsempfänger" if issuer is False
            else "Mandantenname nicht gefunden – als Eingangsrechnung gewertet"
        )

    doc_type = DOCUMENT_TYPES_BY_KEY[key]
    result = ClassificationResult(
        doc_type, confidence=confidence, score=best_score, evidence=evidence, customer_name_found=customer_found
    )

    if doc_type.requires_period:
        period, why = detect_period(text, best_kind, today)
        if period:
            result.year, result.month = period
            result.evidence.append(why)
        else:
            result.evidence.append("kein Zeitraum im Dokument gefunden")
    return result


def detect_period_for_type(text: str, document_type: DocumentType, today: date | None = None):
    """Zeitraum für eine vom Mandanten gewählte Dokumentart bestimmen."""
    kind = "rechnung" if document_type.key in {"eingangsrechnung", "ausgangsrechnung"} else document_type.key
    return detect_period(text, kind, today)
