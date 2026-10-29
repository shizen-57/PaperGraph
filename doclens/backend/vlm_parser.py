"""VLM page parser: a vision-language model turns each page image into Markdown, and the Markdown becomes elements.

One wrapper serves Qwen2.5-VL, PaddleOCR-VL, GLM-OCR and any other model that vLLM (or another OpenAI-compatible
server) can host: they differ only in model name and prompt.

    PARSER=vlm VLM_BASE_URL=http://localhost:8002/v1 VLM_MODEL=Qwen/Qwen2.5-VL-3B-Instruct python -m eval.run_eval ...

The model returns no boxes, so these elements have page numbers but no bbox: citations point at the page.
"""
import base64
import io
import os
import re
from pathlib import Path

from backend import llm
from backend.parse import Sections, _md_table, table_md
from backend.schemas import Element, Table

PROMPT = os.environ.get("VLM_PROMPT") or (
    "Convert this page to Markdown. Keep every character exactly as printed (Japanese and English). "
    "Render tables as HTML <table> with <tr> and <td>. Output only the page content, no commentary.")
DPI = int(os.environ.get("VLM_DPI", "150"))  # page render resolution: fewer pixels, fewer image tokens, faster on a CPU


def page_markdown(png: bytes) -> str:
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    out = llm.chat(
        [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": PROMPT}]}],
        max_tokens=4000, model=os.environ.get("VLM_MODEL"), base_url=os.environ.get("VLM_BASE_URL"))
    m = re.search(r"```(?:markdown|md|html)?\s*(.*?)```", out, re.S)
    return (m.group(1) if m else out).strip()


def html_table(block: str) -> Table | None:
    from lxml import html as lxml_html
    try:
        root = lxml_html.fromstring(block)
    except Exception:
        return None
    rows = [[" ".join("".join(c.itertext()).split()) for c in tr.xpath("./td|./th")] for tr in root.iter("tr")]
    rows = [r for r in rows if r]
    return Table(header=rows[0], rows=rows[1:]) if rows else None


BLOCKS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "section", "article", "caption", "pre")


def html_blocks(doc: str) -> list[tuple[str, str | Table]]:
    """Qwen-VL style output is a small HTML document. Returns ('text', string) and ('table', Table) blocks in order;
    a block is a leaf element (one with no block-level child), so nested divs don't repeat their children's text."""
    from lxml import html as lxml_html
    try:
        root = lxml_html.fromstring(doc)
    except Exception:
        return [("text", doc)]
    out: list[tuple[str, str | Table]] = []
    inside_table: set = set()
    for el in root.iter():
        if not isinstance(el.tag, str) or el in inside_table:
            continue
        if el.tag == "table":
            inside_table.update(el.iterdescendants())
            t = html_table(lxml_html.tostring(el, encoding="unicode"))
            if t:
                out.append(("table", t))
        elif el.tag in BLOCKS and not any(isinstance(c.tag, str) and c.tag in BLOCKS + ("table",) for c in el.iterdescendants()):
            text = " ".join(el.text_content().split())
            if text:
                out.append(("heading" if el.tag.startswith("h") and len(el.tag) == 2 else "text", text))
    return out


def markdown_elements(md: str, doc_id: str, page: int, elements: list[Element], sections: Sections) -> None:
    """Appends one element per block: <table> HTML and Markdown tables become tables, '#' lines set the section.
    If the model answered with an HTML document instead (Qwen-VL does), its blocks are used instead."""
    if re.match(r"\s*<(!doctype|html|body|p|h[1-6]|div|section)\b", md, re.I):  # an HTML document, not Markdown with a table in it
        for kind, content in html_blocks(md):
            if kind == "table":
                elements.append(Element(id=f"e{len(elements)}", doc_id=doc_id, type="table", page=page, bbox=None,
                                        text=table_md(content), heading=sections.path, table=content))
                continue
            if kind == "heading":
                sections.push(content)
            elements.append(Element(id=f"e{len(elements)}", doc_id=doc_id, type="text", page=page, bbox=None, text=content,
                                    heading=sections.path))
        return
    for block in re.split(r"\n\s*\n", md):
        block = block.strip()
        if not block:
            continue
        table, text, type_ = None, block, "text"
        if block.lower().startswith("<table"):
            table = html_table(block)
        elif all(ln.lstrip().startswith("|") for ln in block.splitlines()):
            table = _md_table(block.splitlines())
        if table:
            type_, text = "table", table_md(table)
        elif block.startswith("#"):
            text = block.lstrip("#").strip()
            sections.push(text)
        elements.append(Element(id=f"e{len(elements)}", doc_id=doc_id, type=type_, page=page, bbox=None, text=text,
                                heading=sections.path, table=table))


def parse_pdf_vlm(path: Path, doc_id: str, dpi: int = DPI, pages: set[int] | None = None) -> tuple[list[Element], list[tuple[float, float]], str | None]:
    """`pages` (1-based) limits which pages go to the model; sizes always cover the whole document."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    elements: list[Element] = []
    sizes: list[tuple[float, float]] = []
    sections = Sections()
    try:
        for n, page in enumerate(pdf, 1):
            sizes.append(page.get_size())
            if pages is not None and n not in pages:
                continue
            buf = io.BytesIO()
            page.render(scale=dpi / 72).to_pil().convert("RGB").save(buf, format="PNG")
            markdown_elements(page_markdown(buf.getvalue()), doc_id, n, elements, sections)
    finally:
        pdf.close()
    return elements, sizes, None
