"""VLM pass: each figure becomes a chart (with a data table) or a described figure."""
import base64
import io
from pathlib import Path

from backend import llm
from backend.crops import render_crop
from backend.parse import table_md
from backend.schemas import Element, VLMResult

PROMPT = (
    "Is this image a chart (bar, line, pie, etc.) or another figure (photo, diagram, drawing)? "
    "If it is a chart: set kind='chart', read its data into table (first column = category or x label, "
    "one column per series, numbers without units) and summarise it in one sentence. "
    "If it is another figure: set kind='figure', describe it in 2-3 sentences and list any visible "
    "text labels (e.g. a drawing's title block). Keep the document's language for labels."
)


def describe(png: bytes) -> VLMResult:
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    raw = llm.chat(
        [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": url}},
            {"type": "text", "text": PROMPT},
        ]}],
        schema=VLMResult.model_json_schema(), max_tokens=1500,
    )
    return VLMResult.model_validate_json(raw)


def vlm_doc(elements: list[Element], pdf_path: Path) -> list[Element]:
    # ponytail: rewrites figures in place, so run it on fresh parse output only (re-run parse before re-running vlm)
    for el in elements:
        if el.type != "figure":
            continue
        buf = io.BytesIO()
        render_crop(pdf_path, el.page, el.bbox).save(buf, format="PNG")
        r = describe(buf.getvalue())
        el.type, el.table = r.kind, r.table if r.kind == "chart" else None
        el.text = "\n".join(p for p in (el.text, r.summary, table_md(el.table) if el.table else "") if p)
    return elements
