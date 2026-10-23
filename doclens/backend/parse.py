"""Files → Element[]. PDFs go through Docling (boxes converted to top-left origin here, once); md/txt are split
into paragraphs. Every element carries its section path, e.g. "3 Method > 3.2 Client selection"."""
import re
from functools import lru_cache
from pathlib import Path

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
    sizes = [(doc.pages[p].size.width, doc.pages[p].size.height) for p in sorted(doc.pages)]
    elements: list[Element] = []
    sections = Sections()
    title = None

    def add(type_, prov, text, table=None):
        h = doc.pages[prov.page_no].size.height
        bb = prov.bbox
        elements.append(Element(
            id=f"e{len(elements)}", doc_id=doc_id, type=type_, page=prov.page_no,
            bbox=bbox_top_left(bb.l, bb.t, bb.r, bb.b, h, bb.coord_origin == CoordOrigin.BOTTOMLEFT),
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
