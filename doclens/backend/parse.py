"""Files → Element[]. PDFs go through Docling (boxes converted to top-left origin here, once); md/txt are split
into paragraphs. Every element carries its section path, e.g. "3 Method > 3.2 Client selection"."""
import hashlib
import importlib.util
import os
import re
from functools import lru_cache
from pathlib import Path

from backend.db import ROOT
from backend.schemas import BBox, Element, Table

MAX_TABLE_ROWS = 40  # bigger tables are split into row groups, header repeated
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")


def bbox_top_left(l: float, t: float, r: float, b: float, page_height: float, bottom_left: bool) -> BBox:
    """Docling boxes are (l, t, r, b). With a bottom-left origin, t is the larger y."""
    if bottom_left:
        return BBox(x0=l, y0=page_height - t, x1=r, y1=page_height - b)
    return BBox(x0=l, y0=t, x1=r, y1=b)


class Sections:
    """Heading stack → section path. Depth comes from numbering ("3.2 X" is depth 2), else from the given level."""

    def __init__(self):
        self.stack: list[tuple[int, str]] = []

    def push(self, text: str, level: int = 1) -> None:
        m = _NUMBERED.match(text)
        depth = m.group(1).count(".") + 1 if m else max(level, 1)
        self.stack = [(d, t) for d, t in self.stack if d < depth] + [(depth, text.strip())]

    @property
    def path(self) -> str | None:
        return " > ".join(t for _, t in self.stack) or None


def table_md(t: Table) -> str:
    lines = ["| " + " | ".join(t.header) + " |", "|" + "---|" * len(t.header)]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in t.rows])


def lang_of(text: str) -> str:
    cjk = sum("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in text)
    return "ja" if cjk > 0.1 * max(len(text), 1) else "en"


# --- PDF (Docling) ---

@lru_cache
def _converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = True
    opts.do_table_structure = True
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def _table(item, doc) -> Table:
    try:
        df = item.export_to_dataframe(doc=doc)
    except TypeError:  # older docling-core takes no doc argument
        df = item.export_to_dataframe()
    return Table(header=[str(c) for c in df.columns], rows=df.astype(str).values.tolist())


def parse_pdf(path: Path, doc_id: str) -> tuple[list[Element], list[tuple[float, float]], str | None]:
    """Returns elements in reading order, (width, height) per page, and the title if Docling found one."""
    from docling_core.types.doc import CoordOrigin, DocItemLabel, PictureItem, TableItem

    doc = _converter().convert(str(path)).document
    unit = 1 / 12700 if path.suffix.lower() == ".pptx" else 1  # PowerPoint stores EMU; everything else here is in points
    sizes = [(doc.pages[p].size.width * unit, doc.pages[p].size.height * unit) for p in sorted(doc.pages)]
    elements: list[Element] = []
    sections = Sections()
    title = None

    def add(type_, prov, text, table=None):
        h = doc.pages[prov.page_no].size.height
        bb = prov.bbox
        box = bbox_top_left(bb.l, bb.t, bb.r, bb.b, h, bb.coord_origin == CoordOrigin.BOTTOMLEFT)
        elements.append(Element(
            id=f"e{len(elements)}", doc_id=doc_id, type=type_, page=prov.page_no,
            bbox=BBox(x0=box.x0 * unit, y0=box.y0 * unit, x1=box.x1 * unit, y1=box.y1 * unit),
            text=text, heading=sections.path, table=table,
        ))

    for item, _level in doc.iterate_items():
        if not getattr(item, "prov", None):
            continue
        label = item.label
        if label in (DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER):
            continue
        prov = item.prov[0]
        if isinstance(item, TableItem):
            # ponytail: a table spanning pages keeps only its first box
            table, caption = _table(item, doc), item.caption_text(doc)
            for i in range(0, max(len(table.rows), 1), MAX_TABLE_ROWS):
                part = Table(header=table.header, rows=table.rows[i:i + MAX_TABLE_ROWS])
                add("table", prov, f"{caption}\n{table_md(part)}".strip(), part)
        elif isinstance(item, PictureItem):
            add("figure", prov, item.caption_text(doc))  # vlm.py fills in the description
        elif label == DocItemLabel.CAPTION:
            add("caption", prov, item.text)
        elif getattr(item, "text", "").strip():
            if label == DocItemLabel.TITLE:
                title = title or item.text.strip()
            elif label == DocItemLabel.SECTION_HEADER:
                sections.push(item.text, getattr(item, "level", 1))
            if len(item.prov) > 1:  # a paragraph that runs onto the next page: one element per page
                for p in item.prov:
                    part = item.text[p.charspan[0]:p.charspan[1]].strip()
                    if part:
                        add("text", p, part)
            else:
                add("text", prov, item.text)
    return elements, sizes, title


# --- PDF text layer (pdfium): no models, no GPU. The cheap baseline, and the fallback when Docling isn't installed ---

def _lines(segments: list[tuple[float, float, float, float, str]]) -> list[list[tuple[float, float, float, float, str]]]:
    """Group word boxes (x0, y0, x1, y1, text; top-left origin) into visual lines, each sorted left to right.
    Tall glyphs define the lines; small ones (commas, full stops) join the line whose box contains them."""
    heights = sorted(s[3] - s[1] for s in segments)
    median = heights[len(heights) // 2] if heights else 0
    lines: list[list] = []
    small = []
    for seg in sorted(segments, key=lambda s: ((s[1] + s[3]) / 2, s[0])):
        if seg[3] - seg[1] < 0.6 * median:
            small.append(seg)
            continue
        mid, h = (seg[1] + seg[3]) / 2, seg[3] - seg[1]
        if lines and abs(mid - (lines[-1][0][1] + lines[-1][0][3]) / 2) <= 0.5 * h:
            lines[-1].append(seg)
        else:
            lines.append([seg])
    for seg in small:
        mid = (seg[1] + seg[3]) / 2
        home = next((ln for ln in lines if min(s[1] for s in ln) <= mid <= max(s[3] for s in ln)), None)
        if home is not None:
            home.append(seg)
        else:
            lines.append([seg])
    return sorted((sorted(line) for line in lines), key=lambda ln: min(s[1] for s in ln))


def _join(line: list) -> str:
    """Text of one line. Neighbouring glyph boxes closer than half a line height are one word (CJK glyph boxes sit
    close together and carry no spaces); a wider gap is a space (a column gap, or a letter-spaced title)."""
    out = line[0][4]
    for a, b in zip(line, line[1:]):
        wide = b[0] - a[2] >= 0.5 * max(a[3] - a[1], b[3] - b[1])
        out += (" " if wide and not out.endswith(" ") and not b[4].startswith(" ") else "") + b[4]
    return " ".join(out.split())


def _is_row(line: list) -> bool:
    """A line with three or more words separated by wide gaps is a table row (or a form field), never prose."""
    height = max(s[3] - s[1] for s in line)
    return sum(b[0] - a[2] > 1.5 * height for a, b in zip(line, line[1:])) >= 2


def _page_elements(elements: list[Element], doc_id: str, page_no: int, segs: list) -> None:
    """Word boxes of one page → elements. Table-like lines stay one element each (so a row can be quoted and
    highlighted); prose lines are merged into paragraphs."""
    para: list[list] = []

    def add(group: list[list]):
        flat = [s for line in group for s in line]
        elements.append(Element(
            id=f"e{len(elements)}", doc_id=doc_id, type="text", page=page_no,
            bbox=BBox(x0=min(s[0] for s in flat), y0=min(s[1] for s in flat), x1=max(s[2] for s in flat), y1=max(s[3] for s in flat)),
            text="\n".join(_join(line) for line in group)))

    for line in _lines(segs):
        height = max(s[3] - s[1] for s in line)
        if _is_row(line):
            if para:
                add(para)
                para = []
            add([line])
            continue
        if para and line[0][1] - max(s[3] for s in para[-1]) > 0.8 * height:  # a gap: new paragraph
            add(para)
            para = []
        para.append(line)
    if para:
        add(para)


def parse_pdf_textlayer(path: Path, doc_id: str) -> tuple[list[Element], list[tuple[float, float]], str | None]:
    """Text elements from the PDF's own text layer. Scanned pages have no text layer and yield nothing."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    elements: list[Element] = []
    sizes: list[tuple[float, float]] = []
    try:
        for n, page in enumerate(pdf, 1):
            w, h = page.get_size()
            sizes.append((w, h))
            tp = page.get_textpage()
            segs = []
            for i in range(tp.count_rects()):
                left, bottom, right, top = tp.get_rect(i)
                text = tp.get_text_bounded(left, bottom, right, top)
                if text.strip():
                    segs.append((left, h - top, right, h - bottom, text))
            if segs:
                _page_elements(elements, doc_id, n, segs)
    finally:
        pdf.close()
    return elements, sizes, None


_CJK_GAP = re.compile(r"(?<=[\u3000-\u9fff\uff00-\uffef])\s+(?=[\u3000-\u9fff\uff00-\uffef])")


def parse_pdf_tesseract(path: Path, doc_id: str, lang: str | None = None, dpi: int = 200) -> tuple[list[Element], list[tuple[float, float]], str | None]:
    """Classic OCR baseline: render each page, run Tesseract (TESSERACT_LANG, default jpn+eng; TESSERACT_PSM, default 6).
    Tesseract puts spaces between Japanese characters; they are removed again between two CJK characters."""
    import pypdfium2 as pdfium
    import pytesseract

    lang = lang or os.environ.get("TESSERACT_LANG", "jpn+eng")
    psm = os.environ.get("TESSERACT_PSM", "6")
    pdf = pdfium.PdfDocument(str(path))
    elements: list[Element] = []
    sizes: list[tuple[float, float]] = []
    scale = dpi / 72
    try:
        for n, page in enumerate(pdf, 1):
            sizes.append(page.get_size())
            img = page.render(scale=scale).to_pil().convert("RGB")
            d = pytesseract.image_to_data(img, lang=lang, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
            segs = [(d["left"][i] / scale, d["top"][i] / scale, (d["left"][i] + d["width"][i]) / scale,
                     (d["top"][i] + d["height"][i]) / scale, d["text"][i])
                    for i in range(len(d["text"])) if d["text"][i].strip() and float(d["conf"][i]) >= 0]
            if segs:
                _page_elements(elements, doc_id, n, segs)
    finally:
        pdf.close()
    for e in elements:
        e.text = _CJK_GAP.sub("", e.text)
    return elements, sizes, None


def _vlm(path: Path, doc_id: str):
    from backend import vlm_parser  # imported late: it imports this module
    return vlm_parser.parse_pdf_vlm(path, doc_id)


def _router(path: Path, doc_id: str):
    from backend import router
    return router.parse_pdf_router(path, doc_id)


PARSERS = {"docling": parse_pdf, "pdfium": parse_pdf_textlayer, "tesseract": parse_pdf_tesseract, "vlm": _vlm,
           "router": _router}


class ParserUnavailable(Exception):
    pass


def default_parser() -> str:
    """PARSER=docling|pdfium; otherwise Docling when it is installed."""
    return os.environ.get("PARSER") or ("docling" if importlib.util.find_spec("docling") else "pdfium")


def parse_cached(path: Path, doc_id: str, parser: str | None = None, cache: Path = ROOT / ".cache" / "parse"):
    """parse_pdf with a cache keyed on the file's sha256 and the parser, so a document is parsed once."""
    import json

    parser = parser or default_parser()
    with open(path, "rb") as f:
        key = f"{hashlib.file_digest(f, 'sha256').hexdigest()}-{parser}.json"
    hit = cache / key
    if hit.exists():
        data = json.loads(hit.read_text(encoding="utf-8"))
        return ([Element.model_validate({**e, "doc_id": doc_id}) for e in data["elements"]],
                [tuple(s) for s in data["sizes"]], data["title"])
    elements, sizes, title = PARSERS[parser](path, doc_id)
    cache.mkdir(parents=True, exist_ok=True)
    hit.write_text(json.dumps({"elements": [e.model_dump() for e in elements], "sizes": sizes, "title": title},
                              ensure_ascii=False), encoding="utf-8")
    return elements, sizes, title


# --- Markdown / plain text ---

def _md_table(lines: list[str]) -> Table | None:
    cells = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    cells = [r for r in cells if not all(set(c) <= set("-: ") for c in r)]  # drop the |---| row
    return Table(header=cells[0], rows=cells[1:]) if len(cells) >= 2 else None


def parse_text(path: Path, doc_id: str, markdown: bool) -> tuple[list[Element], str | None]:
    """One element per paragraph (blank-line separated). Markdown '#' lines set the section path."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    elements: list[Element] = []
    sections = Sections()
    title = None
    buf: list[str] = []
    start = 0

    def flush():
        if not buf:
            return
        table = _md_table(buf) if markdown and all(ln.lstrip().startswith("|") for ln in buf) else None
        elements.append(Element(
            id=f"e{len(elements)}", doc_id=doc_id, type="table" if table else "text", page=1, bbox=None,
            line=start, text="\n".join(buf).strip(), heading=sections.path, table=table,
        ))
        buf.clear()

    for i, ln in enumerate(lines, 1):
        h = re.match(r"^(#{1,6})\s+(.*)", ln) if markdown else None
        if h:
            flush()
            level, text = len(h.group(1)), h.group(2).strip()
            if level == 1 and title is None:
                title = text
            else:
                sections.push(text, level - 1 if title else level)
            elements.append(Element(id=f"e{len(elements)}", doc_id=doc_id, type="text", page=1, bbox=None,
                                    line=i, text=text, heading=sections.path))
        elif not ln.strip():
            flush()
        else:
            if not buf:
                start = i
            buf.append(ln)
    flush()
    return elements, title


def parse_path(path: Path, doc_id: str, file_type: str, parser: str | None = None):
    """Any supported file → (elements, page sizes, title). Images and PPTX need Docling (OCR / slide structure)."""
    if file_type in ("md", "txt"):
        els, title = parse_text(path, doc_id, markdown=file_type == "md")
        return els, [], title
    parser = parser or default_parser()
    if file_type == "pdf":
        if parser not in PARSERS:
            raise ParserUnavailable(f"Unknown parser {parser!r}; choose from {sorted(PARSERS)}")
        if parser == "docling" and importlib.util.find_spec("docling") is None:
            raise ParserUnavailable("PARSER=docling but docling is not installed: pip install docling")
        return parse_cached(path, doc_id, parser)
    if importlib.util.find_spec("docling") is None:
        raise ParserUnavailable(f"{file_type} input needs Docling (slide structure / OCR): pip install docling")
    return parse_cached(path, doc_id, "docling")
