"""
Document extractor using PyMuPDF (digital PDFs) + Tesseract (scanned/fax images).
Runs entirely locally on Mac — no API calls, no cost.
"""
import io
import base64
from pathlib import Path
from dataclasses import dataclass

import fitz                 # PyMuPDF
import pytesseract
from PIL import Image
import pdf2image


@dataclass
class ExtractedPage:
    page_number: int
    raw_text: str
    image_b64: str      # base64 PNG — sent to the vision model


@dataclass
class ExtractedDocument:
    filename: str
    total_pages: int
    pages: list[ExtractedPage]
    full_text: str


def _to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def extract_document(file_bytes: bytes, filename: str) -> ExtractedDocument:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}:
        return _extract_image(file_bytes, filename)
    return _extract_pdf(file_bytes, filename)


def _extract_pdf(file_bytes: bytes, filename: str) -> ExtractedDocument:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    texts = []

    for i, page in enumerate(doc):
        # 1. Try native text extraction (fast, works for digital PDFs)
        text = page.get_text("text").strip()

        # 2. If page looks scanned (little native text), run Tesseract OCR
        if len(text) < 50:
            pil_pages = pdf2image.convert_from_bytes(
                file_bytes, dpi=200, first_page=i + 1, last_page=i + 1
            )
            if pil_pages:
                text = pytesseract.image_to_string(pil_pages[0])
                img = pil_pages[0]
            else:
                img = Image.new("RGB", (800, 1000), "white")
        else:
            # Render page as image for the vision model regardless
            pix = page.get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        texts.append(text)
        pages.append(ExtractedPage(
            page_number=i + 1,
            raw_text=text,
            image_b64=_to_b64(img),
        ))

    doc.close()
    return ExtractedDocument(
        filename=filename,
        total_pages=len(pages),
        pages=pages,
        full_text="\n\n--- Page Break ---\n\n".join(texts),
    )


def _extract_image(file_bytes: bytes, filename: str) -> ExtractedDocument:
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    text = pytesseract.image_to_string(img)
    page = ExtractedPage(page_number=1, raw_text=text, image_b64=_to_b64(img))
    return ExtractedDocument(
        filename=filename,
        total_pages=1,
        pages=[page],
        full_text=text,
    )
