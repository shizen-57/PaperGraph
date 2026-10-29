"""Structured extraction: the LLM copies values with their quotes, code normalises and verifies them.

The Pydantic models below do two jobs: their JSON schema is what the LLM is asked to return (guided decoding),
and each field's `kind` says how normalize_ja turns the copied text into a typed value. A value is `verified`
only if its quote is found in the document AND the value appears in that quote (verify.py).

    extraction = extract("inv-001", "invoice", elements)      # needs LLM_MODEL; extract_rules.py is the no-LLM baseline
"""
import os
import re
import time
from typing import Any

from pydantic import BaseModel, Field as PField, ValidationError

from backend import consistency, llm, normalize_intl, normalize_ja, verify
from backend.parse import lang_of
from backend.schemas import Cited, DocType, Element, ExtractedField, Extraction, FieldKind, QuoteCheck

MAX_CHARS = 40_000  # about a 20k-token budget
MAX_ELEMENT_CHARS = 6_000


def F(kind: FieldKind, description: str) -> Any:
    return PField(description=description, json_schema_extra={"kind": kind})


class Invoice(BaseModel):
    invoice_number: Cited = F("text", "Invoice number (請求書番号 / 請求番号 / Invoice No.)")
    issue_date: Cited = F("date", "Date of issue (発行日 / 請求日)")
    due_date: Cited = F("date", "Payment due date (支払期限 / お支払期限)")
    issuer: Cited = F("text", "Company that issued the invoice (請求元 / 発行元)")
    recipient: Cited = F("text", "Company the invoice is addressed to (請求先 / 御中)")
    subtotal: Cited = F("amount", "Subtotal before tax (小計)")
    tax: Cited = F("amount", "Consumption tax amount (消費税)")
    total: Cited = F("amount", "Total amount due (合計 / ご請求金額)")


class LineItem(BaseModel):
    name: str | None = PField(max_length=200, description="Item name, as printed")
    quantity: str | None = PField(max_length=40, description="Quantity, as printed")
    unit_price: str | None = PField(max_length=40, description="Unit price, as printed")
    amount: str | None = PField(max_length=40, description="Line amount, as printed")
    tax_rate: str | None = PField(max_length=40, description="Tax rate of this line if printed, e.g. '10%' or '8%'; else null")
    element_id: str = PField(max_length=12)
    quote: str = PField(max_length=160, description="The table row of this item only, copied EXACTLY")


LINE_KINDS: dict[str, FieldKind] = {"name": "text", "quantity": "number", "unit_price": "amount", "amount": "amount",
                                    "tax_rate": "percent"}


class InvoiceOut(Invoice):
    line_items: list[LineItem] = PField(max_length=30, description="One entry per row of the items table, in order")


class SpecSheet(BaseModel):
    product_name: Cited = F("text", "Product name (製品名 / 品名)")
    model_number: Cited = F("text", "Model or part number (型番 / 型式)")
    manufacturer: Cited = F("text", "Manufacturer (メーカー / 製造元)")
    rated_voltage: Cited = F("text", "Rated or input voltage (定格電圧), with unit")
    rated_current: Cited = F("text", "Rated current (定格電流), with unit")
    power: Cited = F("text", "Power or wattage (消費電力 / 出力), with unit")
    weight: Cited = F("text", "Weight (質量 / 重量), with unit")
    dimensions: Cited = F("text", "Outer dimensions (外形寸法 / サイズ), with unit")
    operating_temperature: Cited = F("text", "Operating temperature range (使用温度範囲), with unit")


class FinancialReport(BaseModel):
    company_name: Cited = F("text", "Company name (会社名)")
    fiscal_period_end: Cited = F("date", "End of the fiscal period (決算期末 / 2026年3月期)")
    unit: Cited = F("text", "Unit the amounts are stated in, e.g. 百万円 (単位)")
    revenue: Cited = F("amount", "Net sales / revenue (売上高)")
    operating_income: Cited = F("amount", "Operating income (営業利益)")
    ordinary_income: Cited = F("amount", "Ordinary income (経常利益)")
    net_income: Cited = F("amount", "Net income attributable to owners of parent (親会社株主に帰属する当期純利益)")
    total_assets: Cited = F("amount", "Total assets (総資産)")


DOC_TYPES: dict[str, type[BaseModel]] = {"invoice": InvoiceOut, "spec_sheet": SpecSheet, "financial_report": FinancialReport}

SYSTEM = """You extract structured data from a business document in Japanese or English. \
The document is given as <element id="..." page="..."> blocks. Tables are Markdown.

Rules:
1. For every field return `value` copied EXACTLY as printed (keep symbols and notation, e.g. ¥1,234 or 令和8年10月24日). \
Never convert, calculate or guess. If the document does not state a field, return null for value and an empty quote.
2. `element_id` is the id of the element that contains the value, e.g. e3. `quote` is ONE line (for a table: ONE row) of that \
element copied EXACTLY, containing the value, under 100 characters. Never copy the header row, several rows, ids or tags into a quote.
3. Return JSON that matches the schema, nothing else."""


class ExtractionError(Exception):
    pass


# The examples in SYSTEM and the field guide are Japanese, and a small model followed them: asked about a Bangla invoice, a 3B model
# answered in Japanese (スタンド＆セットアップ, 2026年8月26日), so every value failed the evidence check. For Bangla the prompt says so.
# Japanese and English documents get no note, so their prompt (and every committed result) is unchanged.
LANGUAGE_NOTE = {"bn": "The document is in Bangla (বাংলা). Copy every value in Bangla script exactly as printed, with Bangla digits "
                       "(১২৩), and never translate or transliterate it into another language or script."}


def field_guide(model: type[BaseModel]) -> str:
    """What each field means, from the model's own descriptions (a small model can't guess from names alone)."""
    lines = []
    for name, info in model.model_fields.items():
        if name == "line_items":
            row = "; ".join(f"{k}: {v.description}" for k, v in LineItem.model_fields.items() if v.description)
            lines.append(f"- line_items: {info.description}. Each entry: {row}.")
        else:
            lines.append(f"- {name}: {info.description}")
    return "\n".join(lines)


def render(elements: list[Element]) -> str:
    out, total = [], 0
    for e in elements:
        if e.type == "caption" and not e.text.strip():
            continue
        line = f'<element id="{e.id}" page="{e.page}">\n{e.text[:MAX_ELEMENT_CHARS]}\n</element>'
        if total + len(line) > MAX_CHARS:
            break
        out.append(line)
        total += len(line)
    return "\n".join(out)


def _fenced(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def ask_llm(doc_type: str, elements: list[Element], model: type[BaseModel] | None = None) -> BaseModel:
    """One structured LLM call. If the JSON doesn't validate, the error is shown to the model once and it retries."""
    model = model or DOC_TYPES[doc_type]
    body = render(elements)
    note = LANGUAGE_NOTE.get(lang_of(body), "")
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Document type: {doc_type}\n\n{note + chr(10) + chr(10) if note else ''}Fields:\n{field_guide(model)}\n\nElements:\n{body}"}]
    error = None
    for _ in range(2):
        raw = llm.chat(messages, schema=model.model_json_schema(), max_tokens=3000)
        try:
            return model.model_validate_json(_fenced(raw))
        except (ValidationError, ValueError) as e:
            error = e
            messages += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": f"That JSON was invalid:\n{str(e)[:1500]}\nReturn corrected JSON only."}]
    raise ExtractionError(f"the model returned invalid JSON twice: {str(error)[:300]}")


# --- normalise + verify ---

def normalise(kind: FieldKind, raw: str | None) -> tuple[str | int | float | None, str | None]:
    """(typed value, tax flag). None when the text can't be read as that kind."""
    if raw is None or not raw.strip():
        return None, None
    if kind == "date":  # Japanese notation first (it is strict), then English and Bangla month names
        return normalize_ja.parse_date(raw) or normalize_intl.parse_date(raw), None
    if kind == "amount":
        a = normalize_ja.parse_amount(raw) or normalize_intl.parse_amount(raw)
        return (a.value, a.tax) if a else (None, None)
    if kind == "number":
        return normalize_ja.parse_number(raw), None
    if kind == "percent":
        return normalize_ja.parse_percent(raw), None
    return " ".join(raw.split()), None


_MARKER = re.compile(r"^\s*(?:\[e\d+\s+p\d+\]|<element[^>]*>)\s*|\s*</element>\s*$")


def clean_quote(quote: str) -> str:
    """Drop an element marker the model copied from the prompt: it is prompt text, not document text."""
    return _MARKER.sub("", quote)


def make_field(name: str, kind: FieldKind, raw: str | None, quote: str, element_id: str,
               elements: list[Element], located: QuoteCheck | None = None) -> ExtractedField:
    if raw is None or not raw.strip():
        return ExtractedField(name=name, kind=kind, raw=None, value=None, quote="", page=None, element_id=None, bbox=None,
                              quote_match=0.0, value_in_quote=False, status="missing")
    quote = clean_quote(quote)
    chk = located or verify.locate(quote, elements, prefer=element_id)
    value, tax = normalise(kind, raw)
    # The value must be in the quote AND in the element the quote was found in. The second half matters: fuzzy
    # matching accepts a quote with one digit changed (1,200 for 1,000), so a model could edit the quote to fit its value.
    source = next((e.text for e in elements if e.id == chk.element_id), "")
    in_quote = verify.value_in_quote(raw, quote) and verify.value_in_quote(raw, source)
    ok = chk.found and in_quote and value is not None
    return ExtractedField(
        name=name, kind=kind, raw=raw, value=value, tax=tax, quote=quote, page=chk.page, element_id=chk.element_id,
        bbox=chk.bbox, quote_match=chk.score, value_in_quote=in_quote, status="verified" if ok else "unverified",
    )


def build_fields(out: BaseModel, elements: list[Element]) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for name, info in type(out).model_fields.items():
        v = getattr(out, name)
        if name == "line_items":
            for i, row in enumerate(v):
                chk = verify.locate(row.quote, elements, prefer=row.element_id)  # one lookup per row
                for col, kind in LINE_KINDS.items():
                    fields.append(make_field(f"line_items[{i}].{col}", kind, getattr(row, col), row.quote, row.element_id,
                                             elements, located=chk))
        else:
            kind = (info.json_schema_extra or {})["kind"]
            fields.append(make_field(name, kind, v.value, v.quote, v.element_id, elements))
    return fields


def apply_report_unit(fields: list[ExtractedField]) -> None:
    """Amounts in a financial report are usually stated in 百万円 (a header, not part of each number)."""
    unit = next((f for f in fields if f.name == "unit" and f.raw), None)
    mult = normalize_ja.unit_multiplier(unit.raw) if unit else 1
    if mult == 1:
        return
    for f in fields:
        if f.kind == "amount" and isinstance(f.value, (int, float)) and not re.search(r"[円万億兆]", f.raw or ""):
            f.value = f.value * mult


def to_values(fields: list[ExtractedField]) -> dict:
    """Flat dict of normalised values, line items regrouped: what consistency.check_invoice and eval compare."""
    values: dict = {}
    rows: dict[int, dict] = {}
    for f in fields:
        m = re.fullmatch(r"line_items\[(\d+)\]\.(\w+)", f.name)
        if m:
            rows.setdefault(int(m.group(1)), {})[m.group(2)] = f.value
        else:
            values[f.name] = f.value
    if rows:
        values["line_items"] = [rows[i] for i in sorted(rows)]
    return values


def finish(doc_id: str, doc_type: DocType, out: BaseModel, elements: list[Element], model: str, t0: float) -> Extraction:
    fields = build_fields(out, elements)
    if doc_type == "financial_report":
        apply_report_unit(fields)
    japanese = bool(re.search(r"[぀-ヿ一-鿿]", " ".join(e.text for e in elements)))
    checks = consistency.check_invoice(to_values(fields), rates=consistency.RATES if japanese else None) if doc_type == "invoice" else []
    return Extraction(doc_id=doc_id, doc_type=doc_type, fields=fields, checks=checks, model=model,
                      seconds=round(time.perf_counter() - t0, 2))


def extract(doc_id: str, doc_type: DocType, elements: list[Element]) -> Extraction:
    t0 = time.perf_counter()
    out = ask_llm(doc_type, elements)
    return finish(doc_id, doc_type, out, elements, os.environ.get("LLM_MODEL", ""), t0)

