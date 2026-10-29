"""Failure-case figures for the README, drawn from the real pages and the stored results (nothing is mocked):

    python scripts/make_failure_figures.py --out ../docs/failures

Each figure puts a crop of the page next to what a parser or model made of it. Needs the parse caches that eval/run_eval.py wrote.
"""
import argparse
import json
import sys
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import parse  # noqa: E402

DATA = ROOT / "eval" / "data" / "synth"
RESULTS = ROOT / "eval" / "results"
CACHE = ROOT / "eval" / ".cache"
FONT = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
RED, GREEN, GREY, INK = (190, 40, 40), (30, 120, 60), (90, 90, 90), (20, 20, 20)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


def crop(pdf: Path, box: tuple[float, float, float, float], scale: float = 2.0, pad: float = 8) -> Image.Image:
    doc = pdfium.PdfDocument(str(pdf))
    try:
        img = doc[0].render(scale=scale).to_pil().convert("RGB")
    finally:
        doc.close()
    x0, y0, x1, y1 = (v * scale for v in (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad))
    return img.crop((max(x0, 0), max(y0, 0), min(x1, img.width), min(y1, img.height)))


def union(elements, pick) -> tuple[float, float, float, float]:
    boxes = [e.bbox for e in elements if pick(e)]
    return (min(b.x0 for b in boxes), min(b.y0 for b in boxes), max(b.x1 for b in boxes), max(b.y1 for b in boxes))


def panel(title: str, lines: list[tuple[str, tuple[int, int, int]]], width: int, size: int = 17) -> Image.Image:
    line_h = size + 8
    img = Image.new("RGB", (width, line_h * (len(lines) + 1) + 18), "white")
    d = ImageDraw.Draw(img)
    d.text((10, 8), title, font=font(size), fill=GREY)
    for i, (text, colour) in enumerate(lines):
        d.text((10, 12 + line_h * (i + 1)), text, font=font(size), fill=colour)
    return img


def wrap(text: str, width: int, size: int) -> list[str]:
    f, lines, cur = font(size), [], ""
    for word in text.split(" "):
        if f.getlength(cur + " " + word) > width - 20 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    return lines + [cur]


def stack(parts: list[Image.Image], width: int, caption: str) -> Image.Image:
    parts = [p if p.width <= width else p.resize((width, int(p.height * width / p.width))) for p in parts]
    cap_lines = wrap(caption, width, 17)
    cap = Image.new("RGB", (width, 14 + 24 * len(cap_lines)), (245, 245, 245))
    for i, line in enumerate(cap_lines):
        ImageDraw.Draw(cap).text((10, 8 + 24 * i), line, font=font(17), fill=INK)
    out = Image.new("RGB", (width, cap.height + sum(p.height + 8 for p in parts)), "white")
    out.paste(cap, (0, 0))
    y = cap.height + 4
    for p in parts:
        out.paste(p, ((width - p.width) // 2, y))
        y += p.height + 8
    ImageDraw.Draw(out).rectangle([0, 0, width - 1, out.height - 1], outline=(180, 180, 180))
    return out


def pdfium_elements(pdf: Path):
    return parse.parse_pdf_textlayer(pdf, pdf.stem)[0]


def cached(parser: str, doc: str):
    from backend.schemas import Element
    d = json.loads((CACHE / parser / f"{doc}.json").read_text(encoding="utf-8"))
    return [Element.model_validate(e) for e in d["elements"]]


def digits_in_names(out: Path) -> Path:
    """Item names with numbers in them, read from a flat text layer: the model splits the name at the digits."""
    pdf = DATA / "clean" / "clean-001.pdf"
    els = pdfium_elements(pdf)
    rows = [e for e in els if e.text.startswith(("Description", "LAN", "ボールペン", "出張", "ワイヤレス"))]
    page = crop(pdf, union(rows, lambda e: True))
    run = json.loads((RESULTS / "pdfium-qwen2.5-3b.json").read_text(encoding="utf-8"))
    doc = next(d for d in run["documents"] if d["id"] == "clean-001")
    lines = [("what the PDF text layer gives the model:", GREY)] + [(e.text, INK) for e in rows]
    lines += [("", INK), ("truth → what the model returned (name | qty | unit price | amount):", GREY)]
    for t, p in zip(doc["gold"]["line_items"][:3], doc["pred"]["line_items"][:3]):
        ok = (t["name"], t["quantity"], t["unit_price"], t["amount"]) == (p["name"], p["quantity"], p["unit_price"], p["amount"])
        lines.append((f"{t['name']} | {t['quantity']} | {t['unit_price']:,} | {t['amount']:,}", GREEN))
        lines.append((f"{p['name']} | {p['quantity']} | {p['unit_price']:,} | {p['amount']:,}   {'ok' if ok else 'WRONG: columns shifted'}", GREEN if ok else RED))
    path = out / "digits-in-names.png"
    stack([page, panel("", lines, 900)], 900, "Item names that contain numbers break the columns once the table is flat text (PDF text layer + Qwen2.5-3B)").save(path)
    return path


def stamp_over_header(out: Path) -> Path:
    """A red 印 over the 'Amount' header and OCR confusions on a scan: Docling's table comes out with the wrong header."""
    pdf = DATA / "scanned" / "scan-001.pdf"
    els = cached("docling", "scan-001")
    table = next(e for e in els if e.type == "table")
    page = crop(pdf, (table.bbox.x0, table.bbox.y0 - 40, table.bbox.x1, table.bbox.y1), scale=1.0, pad=6)
    t = table.table
    lines = [("what Docling (RapidOCR) read:", GREY), ("header: " + " | ".join(t.header), RED)]
    lines += [("row 2:  " + " | ".join(t.rows[1]), INK), ("row 3:  " + " | ".join(t.rows[2]), INK)]
    lines += [("", INK), ("the page says: 'Amount', 'ボールペン', '出張技術料' and '12,800'", GREY)]
    path = out / "stamp-and-ocr.png"
    stack([page, panel("", lines, 900)], 900, "A hanko over a header and OCR confusions on a scanned invoice (Docling): ペン read as ベン, 張 read as a simplified-Chinese character the figure font cannot draw (the empty box), '12,800' read as '12,80 0'").save(path)
    return path


def reading_order(out: Path) -> Path:
    """A two-column header: Docling returns the labels, then the values, so label and value are no longer neighbours."""
    pdf = DATA / "clean" / "clean-001.pdf"
    pe = pdfium_elements(pdf)
    head = [e for e in pe if e.text.startswith(("O C", "Invoice No.", "I N V"))] or pe[:2]
    page = crop(pdf, union(pe[:2], lambda e: True), scale=2.0)
    de = cached("docling", "clean-001")
    lines = [("Docling's elements, in reading order:", GREY)]
    for e in de[:11]:
        lines.append((f"e{e.id[1:]:>2}  {e.text.splitlines()[0][:60]}", INK if e.text not in ("Invoice No.", "Date", "Due") else RED))
    path = out / "reading-order.png"
    stack([page, panel("", lines, 900, 16)], 900, "Labels and values end up in different elements (Docling, layout B): a regex or a small model must re-pair them").save(path)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT.parent / "docs" / "failures")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for fn in (digits_in_names, stamp_over_header, reading_order):
        print(fn(a.out))
