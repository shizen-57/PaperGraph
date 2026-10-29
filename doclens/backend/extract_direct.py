"""Image → invoice JSON in one VLM call, with no parser and no quotes. This is the shape the LoRA fine-tune
(train/) is trained to produce, and what eval/run_direct.py scores for the base and the fine-tuned model.

Values are normalised already (ISO dates, yen as integers), because there is no parse step to copy from. With no quote there is
nothing for the evidence check to verify, so these results report accuracy and consistency checks but no verified rate.
"""
import base64
import io
import os
from pathlib import Path

from pydantic import BaseModel, Field as PField, ValidationError

from backend import consistency, llm


class Row(BaseModel):
    name: str | None = PField(max_length=200)
    quantity: int | None
    unit_price: int | None
    amount: int | None
    tax_rate: float | None = PField(description="0.1 or 0.08 if printed on the row, else null")


class InvoiceValues(BaseModel):
    invoice_number: str | None = PField(max_length=60)
    issue_date: str | None = PField(max_length=10, description="YYYY-MM-DD")
    due_date: str | None = PField(max_length=10, description="YYYY-MM-DD")
    issuer: str | None = PField(max_length=100)
    recipient: str | None = PField(max_length=100)
    subtotal: int | None
    tax: int | None
    total: int | None
    line_items: list[Row] = PField(max_length=30)


PROMPT = ("Read this Japanese invoice and return its data as JSON: invoice_number, issue_date and due_date as YYYY-MM-DD "
          "(convert era dates: 令和8年 is 2026), issuer, recipient, subtotal, tax, total as integers in yen, and every row of the "
          "items table as line_items (name, quantity, unit_price, amount, tax_rate). Use null for anything not printed.")


def render_page(pdf: Path, dpi: int = 150) -> bytes:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    try:
        buf = io.BytesIO()
        doc[0].render(scale=dpi / 72).to_pil().convert("RGB").save(buf, format="PNG")
        return buf.getvalue()
    finally:
        doc.close()


def target_json(gt: dict) -> str:
    """The training target for one synthetic invoice: its ground truth, in InvoiceValues form."""
    rows = [{k: r.get(k) for k in ("name", "quantity", "unit_price", "amount", "tax_rate")} for r in gt["line_items"]]
    return InvoiceValues(**gt["fields"], line_items=rows).model_dump_json()


def read_invoice(png: bytes, model: str | None = None, base_url: str | None = None) -> InvoiceValues:
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    raw = llm.chat(
        [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": PROMPT}]}],
        schema=InvoiceValues.model_json_schema(), max_tokens=2500,
        model=model or os.environ.get("VLM_MODEL"), base_url=base_url or os.environ.get("VLM_BASE_URL"))
    try:
        return InvoiceValues.model_validate_json(raw)
    except (ValidationError, ValueError) as e:
        raise ValueError(f"the model did not return an invoice: {str(e)[:200]}") from e


def checks_of(v: InvoiceValues) -> list:
    return consistency.check_invoice(v.model_dump())
