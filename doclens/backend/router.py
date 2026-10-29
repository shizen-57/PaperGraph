"""Smart router: parse cheaply first, spend VLM time only on pages that need it.

Signals that send a page to the VLM:
  scanned      the page has (almost) no text layer
  table        a Docling table on the page has many empty cells or ragged rows
  figure       the page has a figure (it may be a chart whose values need a vision model)
  unverified   (second pass) more than N extracted fields traced to the page failed the evidence check

Pages without a signal keep their Docling elements. `parse_pdf_router` is registered as PARSER=router;
`escalate` is the second pass. Decisions are plain data, so they can be inspected and tested without any model.
"""
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from backend import parse, vlm_parser
from backend.schemas import Element, Extraction

MIN_TEXT_CHARS = 40  # fewer characters than this on a page: no usable text layer
MAX_EMPTY_CELLS = 0.30  # share of empty cells above which a table is suspect
MAX_UNVERIFIED = 2  # per page, for the second pass

LAST: dict = {}  # ponytail: the last parse_pdf_router call's routes and timings, read by eval/run_eval.py


@dataclass
class PageDecision:
    page: int
    route: Literal["docling", "vlm"]
    reasons: list[str] = field(default_factory=list)


def page_text_chars(pdf_path: Path) -> list[int]:
    """Characters in each page's text layer (pdfium, no model)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return [page.get_textpage().count_chars() for page in pdf]
    finally:
        pdf.close()


def table_problem(el: Element) -> str | None:
    t = el.table
    if t is None or not t.rows:
        return None
    cells = [c for r in [t.header, *t.rows] for c in r]
    empty = sum(not c.strip() for c in cells) / max(len(cells), 1)
    if empty > MAX_EMPTY_CELLS:
        return f"{empty:.0%} of table cells are empty"
    if any(len(r) != len(t.header) for r in t.rows):
        return "table rows have different lengths"
    return None


def decide(chars: list[int], elements: list[Element], unverified: dict[int, int] | None = None) -> list[PageDecision]:
    out = []
    for page, n in enumerate(chars, 1):
        reasons = []
        if n < MIN_TEXT_CHARS:
            reasons.append(f"scanned: {n} characters of text layer")
        on_page = [e for e in elements if e.page == page]
        reasons += [f"table: {p}" for e in on_page if e.type == "table" and (p := table_problem(e))]
        if any(e.type in ("figure", "chart") for e in on_page):
            reasons.append("figure on the page")
        if unverified and unverified.get(page, 0) > MAX_UNVERIFIED:
            reasons.append(f"unverified: {unverified[page]} fields failed the evidence check")
        out.append(PageDecision(page, "vlm" if reasons else "docling", reasons))
    return out


def parse_pdf_router(path: Path, doc_id: str, force_vlm: set[int] | None = None):
    """Docling for pages that have a text layer, the VLM for pages the signals send there."""
    chars = page_text_chars(path)
    t0 = time.perf_counter()
    if any(n >= MIN_TEXT_CHARS for n in chars):  # an all-scanned document never needs Docling
        elements, sizes, title = parse.parse_pdf(path, doc_id)
    else:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(path))
        elements, sizes, title = [], [page.get_size() for page in pdf], None
        pdf.close()
    docling_s = time.perf_counter() - t0
    decisions = decide(chars, elements)
    for d in decisions:
        if force_vlm and d.page in force_vlm and d.route == "docling":
            d.route, d.reasons = "vlm", ["unverified: second pass"]
    vlm_pages = {d.page for d in decisions if d.route == "vlm"}
    t1 = time.perf_counter()
    vlm_elements = vlm_parser.parse_pdf_vlm(path, doc_id, pages=vlm_pages)[0] if vlm_pages else []
    LAST.update(routes=[{"page": d.page, "route": d.route, "reasons": d.reasons} for d in decisions],
                docling_seconds=round(docling_s, 3), vlm_seconds=round(time.perf_counter() - t1, 3))
    merged = sorted([e for e in elements if e.page not in vlm_pages] + vlm_elements, key=lambda e: e.page)  # stable
    for i, e in enumerate(merged):
        e.id = f"e{i}"
    return merged, sizes, title


def unverified_by_page(ex: Extraction) -> dict[int, int]:
    counts: dict[int, int] = {}
    for f in ex.fields:
        if f.status == "unverified" and f.page is not None:
            counts[f.page] = counts.get(f.page, 0) + 1
    return counts


def escalate(ex: Extraction) -> set[int]:
    """Pages whose extraction was poor enough to be re-parsed with the VLM (the second pass)."""
    return {p for p, n in unverified_by_page(ex).items() if n > MAX_UNVERIFIED}
