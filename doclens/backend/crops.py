"""Render a box from a PDF page. Used by the VLM pass and the /crops route."""
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from backend.schemas import BBox


def render_crop(pdf_path: Path, page: int, bbox: BBox, scale: float = 2.0) -> Image.Image:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        img = pdf[page - 1].render(scale=scale).to_pil()
    finally:
        pdf.close()
    return img.crop(tuple(round(v * scale) for v in (bbox.x0, bbox.y0, bbox.x1, bbox.y1)))
