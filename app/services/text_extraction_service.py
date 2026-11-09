"""Text aus hochgeladenen Dokumenten gewinnen – Grundlage der automatischen Erkennung.

Strategie:
  1. PDF mit Textebene (z. B. aus Buchhaltungs-/Rechnungsprogrammen)
     -> Text direkt mit ``pypdf`` auslesen. Immer verfügbar.
  2. Fotos/Scans (PNG, JPG) und PDFs ohne Textebene
     -> OCR (Texterkennung). Gescannte PDFs werden dafür mit ``pypdfium2``
        in Bilder umgewandelt.

OCR-Engines (austauschbar, gleiche Schnittstelle ``image_to_text``):
  * RapidOCR  – Standard. Nur ``pip install``, kein Zusatzprogramm, die
                Erkennungsmodelle sind im Paket enthalten, läuft offline.
  * Tesseract – Alternative, falls das Programm Tesseract installiert ist.

Ist keine OCR installiert, liefert der Service für Bilder einen leeren Text.
Die Anwendung funktioniert dann weiter – das Dokument landet zur Prüfung
im Posteingang.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

logger = logging.getLogger(__name__)

MIN_PDF_TEXT_CHARS = 30   # weniger Text -> vermutlich gescanntes PDF
MAX_PAGES = 3             # die ersten Seiten reichen für die Erkennung
OCR_RENDER_SCALE = 2.5    # ca. 180 dpi – guter Kompromiss aus Qualität und Tempo
OCR_MAX_SIDE = 2500       # sehr große Handyfotos verkleinern (Tempo)

# Typische Installationsorte von Tesseract unter Windows.
_WINDOWS_TESSERACT_PATHS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


@dataclass(frozen=True)
class ExtractedText:
    text: str
    source: str  # "pdf-text" | "ocr" | "keine"

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


# --- OCR-Engines ----------------------------------------------------------------------

class OcrEngine(Protocol):
    name: str

    def image_to_text(self, image) -> str: ...


def group_into_lines(boxes, texts) -> str:
    """Setzt einzeln erkannte Textblöcke wieder zu Zeilen zusammen.

    RapidOCR liefert z. B. „Summe EUR“ und „72,32“ als getrennte Blöcke.
    Blöcke mit ähnlicher vertikaler Position bilden eine Zeile (links nach rechts).
    """
    items = []
    for box, text in zip(boxes, texts):
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        items.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), text))
    items.sort(key=lambda item: item[0])

    lines: list[list[tuple]] = []
    for item in items:
        if lines:
            last = lines[-1]
            center = sum(i[0] for i in last) / len(last)
            height = max(i[1] for i in last)
            if abs(item[0] - center) < 0.6 * max(height, item[1]):
                last.append(item)
                continue
        lines.append([item])
    return "\n".join(" ".join(i[3] for i in sorted(line, key=lambda i: i[2])) for line in lines)


class RapidOcrEngine:
    """OCR nur über pip-Pakete (rapidocr + onnxruntime). Modelle sind im Paket enthalten."""

    name = "RapidOCR"

    def __init__(self) -> None:
        import rapidocr  # noqa: F401 – prüft nur, ob installiert
        import onnxruntime  # noqa: F401

        self._engine = None  # Modelle erst beim ersten Bild laden (schneller Start)

    def _get_engine(self):
        if self._engine is None:
            from rapidocr import RapidOCR

            logging.getLogger("RapidOCR").setLevel(logging.WARNING)
            self._engine = RapidOCR(params={"Global.log_level": "warning"})
        return self._engine

    def image_to_text(self, image) -> str:
        import numpy as np

        result = self._get_engine()(np.array(image.convert("RGB")))
        if result is None or not getattr(result, "txts", None):
            return ""
        return group_into_lines(result.boxes, result.txts)


class TesseractEngine:
    """OCR mit dem externen Programm Tesseract (optional)."""

    name = "Tesseract"

    def __init__(self, tesseract_cmd: str | None = None) -> None:
        import pytesseract

        cmd = tesseract_cmd or shutil.which("tesseract")
        if not cmd:
            cmd = next((str(p) for p in _WINDOWS_TESSERACT_PATHS if p.is_file()), None)
        if not cmd:
            raise RuntimeError("Tesseract wurde nicht gefunden.")
        pytesseract.pytesseract.tesseract_cmd = cmd
        languages = set(pytesseract.get_languages(config=""))
        self.language = "deu" if "deu" in languages else "eng"

    def image_to_text(self, image) -> str:
        import pytesseract

        return pytesseract.image_to_string(image, lang=self.language, config="--psm 3")


def create_ocr_engine(preferred: str = "auto", tesseract_cmd: str | None = None) -> OcrEngine | None:
    """Wählt die erste verfügbare OCR-Engine (Standard: RapidOCR, dann Tesseract)."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        logger.info("OCR deaktiviert: Pillow nicht installiert (siehe requirements-ocr.txt).")
        return None

    order = {"auto": ("rapidocr", "tesseract"), "rapidocr": ("rapidocr",), "tesseract": ("tesseract",)}
    for name in order.get(preferred, order["auto"]):
        try:
            engine = RapidOcrEngine() if name == "rapidocr" else TesseractEngine(tesseract_cmd)
        except Exception as exc:  # nicht installiert / nicht startbar
            logger.debug("OCR-Engine %s nicht verfügbar: %s", name, exc)
            continue
        logger.info("OCR aktiv: %s", engine.name)
        return engine
    logger.info("OCR deaktiviert: keine OCR-Engine installiert (pip install -r requirements-ocr.txt).")
    return None


# --- Textauslesen -------------------------------------------------------------------------

class TextExtractor:
    """Kapselt Textauslesen aus PDFs und (optionale) OCR für Bilder/Scans."""

    def __init__(self, tesseract_cmd: str | None = None, enable_ocr: bool = True,
                 ocr_engine: str = "auto") -> None:
        self.ocr: OcrEngine | None = create_ocr_engine(ocr_engine, tesseract_cmd) if enable_ocr else None

    @property
    def ocr_available(self) -> bool:
        return self.ocr is not None

    def extract(self, stream: BinaryIO, extension: str) -> ExtractedText:
        """Liest den Text einer bereits validierten Datei. Der Stream wird zurückgespult."""
        try:
            if extension == "pdf":
                result = self._from_pdf(stream)
            else:
                result = self._from_image(stream)
        except Exception as exc:
            # Erkennung ist eine Hilfe, kein Muss: Fehler dürfen den Upload nicht verhindern.
            logger.warning("Texterkennung fehlgeschlagen (%s: %s)", type(exc).__name__, exc)
            result = ExtractedText("", "keine")
        finally:
            stream.seek(0)
        return result

    # --- PDF ------------------------------------------------------------------------

    def _from_pdf(self, stream: BinaryIO) -> ExtractedText:
        from pypdf import PdfReader

        stream.seek(0)
        reader = PdfReader(stream)
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PAGES])
        if len(text.strip()) >= MIN_PDF_TEXT_CHARS:
            return ExtractedText(text, "pdf-text")

        if self.ocr_available:
            ocr_text = self._ocr_pdf(stream)
            if ocr_text.strip():
                return ExtractedText(ocr_text, "ocr")
        return ExtractedText(text, "pdf-text" if text.strip() else "keine")

    def _ocr_pdf(self, stream: BinaryIO) -> str:
        try:
            import pypdfium2 as pdfium
        except ImportError:
            logger.info("Gescanntes PDF: pypdfium2 fehlt, daher keine OCR möglich.")
            return ""
        stream.seek(0)
        pdf = pdfium.PdfDocument(stream.read())
        try:
            pages = [pdf[i].render(scale=OCR_RENDER_SCALE).to_pil() for i in range(min(len(pdf), MAX_PAGES))]
        finally:
            pdf.close()
        return "\n".join(self._ocr_image(image) for image in pages)

    # --- Bilder -----------------------------------------------------------------------

    def _from_image(self, stream: BinaryIO) -> ExtractedText:
        if not self.ocr_available:
            return ExtractedText("", "keine")
        from PIL import Image

        stream.seek(0)
        with Image.open(stream) as image:
            image.load()
            text = self._ocr_image(image)
        return ExtractedText(text, "ocr" if text.strip() else "keine")

    def _ocr_image(self, image) -> str:
        from PIL import ImageOps

        image = ImageOps.exif_transpose(image)  # Handyfotos richtig drehen
        if max(image.size) > OCR_MAX_SIDE:
            image = image.copy()
            image.thumbnail((OCR_MAX_SIDE, OCR_MAX_SIDE))
        return self.ocr.image_to_text(image)
