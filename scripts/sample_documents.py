"""Fiktive, realistisch aufgebaute Testdokumente für Demo und Tests.

Alle Firmen, Personen, Nummern und Beträge sind frei erfunden.
Die PDFs werden ohne Zusatzbibliothek erzeugt und haben eine echte
Textebene (wie PDFs aus einem Rechnungs- oder Bankprogramm).
Der Kassenbon wird als PNG-"Foto" erzeugt (benötigt Pillow) und kann nur
mit OCR gelesen werden.
"""

from __future__ import annotations

import io
from pathlib import Path


# --- Minimaler PDF-Generator --------------------------------------------------------

def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines: list[str], font_size: int = 11) -> bytes:
    """Einseitiges PDF; jede Zeile wird als eigene Textzeile gesetzt (WinAnsi, Umlaute ok)."""
    leading = font_size + 5
    parts = [f"BT /F1 {font_size} Tf {leading} TL 60 790 Td"]
    for line in lines:
        parts.append(f"({_escape(line)}) Tj T*")
    parts.append("ET")
    content = "\n".join(parts).encode("cp1252")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def make_png(lines: list[str]) -> bytes:
    """Rendert Text als Bild (simuliert ein Foto/Scan). Benötigt Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.load_default(size=30)
    except TypeError:  # sehr alte Pillow-Version
        font = ImageFont.load_default()
    width, line_height = 900, 46
    image = Image.new("RGB", (width, 80 + line_height * len(lines)), "white")
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((50, 40 + index * line_height), line, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# --- Inhalte -------------------------------------------------------------------------

def sample_lines(company: str = "Muster GmbH") -> dict[str, list[str]]:
    """Dateiname -> Textzeilen. ``company`` ist der (fiktive) Mandant."""
    return {
        "Eingangsrechnung_Buerobedarf.pdf": [
            "Papierwelt Bürobedarf GmbH · Industriestraße 5 · 12345 Beispielstadt",
            "",
            company,
            "Musterweg 1",
            "54321 Musterstadt",
            "",
            "RECHNUNG",
            "Rechnungsnummer: RE-2026-0815",
            "Rechnungsdatum: 12.03.2026",
            "Leistungsdatum: 10.03.2026",
            "Kundennummer: 4711",
            "",
            "Pos. Menge Artikel Einzelpreis Gesamt",
            "1 10 Kopierpapier A4, 500 Blatt 4,50 EUR 45,00 EUR",
            "2 5 Ordner breit 2,80 EUR 14,00 EUR",
            "Nettobetrag 59,00 EUR",
            "zzgl. 19 % Umsatzsteuer 11,21 EUR",
            "Gesamtbetrag 70,21 EUR",
            "",
            "Zahlbar bis 11.04.2026 ohne Abzug.",
            "",
            "Papierwelt Bürobedarf GmbH · Geschäftsführer: Erika Beispiel",
            "Amtsgericht Beispielstadt HRB 12345 · USt-IdNr.: DE000000001",
            "IBAN: DE00 0000 0000 0000 0000 01",
        ],
        "Ausgangsrechnung_2026-005.pdf": [
            f"{company} · Musterweg 1 · 54321 Musterstadt",
            "",
            "Beispielkunde AG",
            "Kundenallee 9",
            "11111 Kundenstadt",
            "",
            "Rechnung Nr. 2026-005",
            "Rechnungsdatum: 28.05.2026",
            "Leistungszeitraum: Mai 2026",
            "",
            "Beratungsleistungen Mai 2026 12 Std. à 95,00 EUR 1.140,00 EUR",
            "Nettobetrag 1.140,00 EUR",
            "zzgl. 19 % Umsatzsteuer 216,60 EUR",
            "Rechnungsbetrag 1.356,60 EUR",
            "",
            "Zahlungsziel: 14 Tage bis 11.06.2026",
            "",
            f"{company} · Geschäftsführer: Max Mustermann · Amtsgericht Musterstadt HRB 99999",
            "USt-IdNr.: DE000000002 · IBAN: DE00 1111 1111 1111 1111 11",
        ],
        "Kontoauszug_April.pdf": [
            "Musterbank eG",
            "Kontoauszug Nr. 4/2026",
            "Zeitraum: 01.04.2026 bis 30.04.2026",
            f"Kontoinhaber: {company}",
            "IBAN: DE00 2222 2222 2222 2222 22",
            "",
            "Alter Saldo per 31.03.2026 12.450,30 EUR",
            "Buchungstag Wertstellung Verwendungszweck Betrag",
            "02.04.2026 02.04.2026 Miete Büro April -1.200,00",
            "08.04.2026 08.04.2026 Gutschrift Beispielkunde AG 1.356,60",
            "15.04.2026 15.04.2026 Papierwelt Bürobedarf RE-2026-0815 -70,21",
            "28.04.2026 28.04.2026 Gehälter April -4.300,00",
            "Neuer Saldo per 30.04.2026 8.236,69 EUR",
        ],
        "Z-Bericht_Februar.pdf": [
            company,
            "Kasse 1",
            "Z-BERICHT Nr. 0042",
            "Tagesabschluss vom 27.02.2026 22:14",
            "",
            "Anzahl Bons 87",
            "Umsatz 19 % 1.204,50 EUR",
            "Umsatz 7 % 310,20 EUR",
            "Tagesumsatz brutto 1.514,70 EUR",
            "davon bar 932,10 EUR",
            "davon Karte 582,60 EUR",
            "Z-Zähler 42 · Nullstellung durchgeführt",
        ],
        "Gewerbeanmeldung.pdf": [
            "Stadt Musterstadt – Ordnungsamt / Gewerbeamt",
            "Gewerbe-Anmeldung nach § 14 GewO",
            "",
            f"Name des Betriebs: {company}",
            "Betriebsstätte: Musterweg 1, 54321 Musterstadt",
            "Angemeldete Tätigkeit: Unternehmensberatung",
            "Beginn der angemeldeten Tätigkeit: 01.01.2026",
            "",
            "Eingangsbestätigung der Gewerbebehörde",
        ],
        "Besprechungsnotiz.pdf": [
            "Notizen aus dem Telefonat",
            "Termin nächste Woche abstimmen, Unterlagen sammeln.",
            "Fragen zur Planung für das kommende Quartal klären.",
        ],
    }


def receipt_lines() -> list[str]:
    """Kassenbon (fremder Laden, daher ohne Mandantennamen) – wird als Foto erzeugt."""
    return [
        "Tankstelle Beispiel",
        "Hauptstrasse 10, 12345 Beispielstadt",
        "KASSENBON",
        "Bon-Nr. 1234     Datum 05.06.2026",
        "Super E10   40,20 l   72,32 EUR",
        "Summe EUR             72,32",
        "Gegeben bar           80,00",
        "Rueckgeld              7,68",
        "TSE-Signatur vorhanden",
        "Vielen Dank fuer Ihren Einkauf",
    ]


def write_samples(target_dir: Path, company: str = "Muster GmbH") -> list[Path]:
    """Schreibt alle Beispieldokumente nach ``target_dir`` und gibt die Pfade zurück."""
    target_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, lines in sample_lines(company).items():
        path = target_dir / filename
        path.write_bytes(make_pdf(lines))
        written.append(path)
    try:
        path = target_dir / "Kassenbon_Foto.png"
        path.write_bytes(make_png(receipt_lines()))
        written.append(path)
    except ImportError:
        pass  # ohne Pillow kein Bild-Beispiel
    return written
