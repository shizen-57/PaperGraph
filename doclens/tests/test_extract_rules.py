import json
from pathlib import Path

import pytest

from backend import extract_rules, parse
from backend.schemas import Element

SYNTH = Path(__file__).parent.parent / "eval" / "data" / "synth"


def els(*texts, table=None):
    return [Element(id=f"e{i}", doc_id="d", type="table" if i == table else "text", page=1, bbox=None, text=t)
            for i, t in enumerate(texts)]


def test_labels_in_japanese_and_english():
    ex = extract_rules.extract("d", "invoice", els(
        "請求書番号: INV-1\n発行日: 令和8年10月24日\n支払期限: 2026/11/30",
        "Subtotal ¥1,000\nTax (10%) ¥100\nTotal ¥1,100"))
    v = {f.name: f.value for f in ex.fields}
    assert (v["invoice_number"], v["issue_date"], v["due_date"]) == ("INV-1", "2026-10-24", "2026-11-30")
    assert (v["subtotal"], v["tax"], v["total"]) == (1000, 100, 1100)


def test_total_is_not_taken_from_subtotal_or_tax_total_lines():
    ex = extract_rules.extract("d", "invoice", els("小計 1,000円\n消費税合計 100円\n合計 1,100円"))
    v = {f.name: f.value for f in ex.fields}
    assert (v["subtotal"], v["tax"], v["total"]) == (1000, 100, 1100)


def test_table_rows_with_empty_cells_and_pipes():
    ex = extract_rules.extract("d", "invoice", els(
        "| 品名 | 数量 | 単価 | 金額 |\n|---|---|---|---|\n| 商品A | 2 | 500 | 1,000 |",
        "| 0 | 1 | 2 |\n|---|---|---|\n| 小計 |  | 1,000円 |\n| 合計 |  | 1,100円 |", table=0))
    v = {f.name: f.value for f in ex.fields}
    assert v["line_items[0].name"] == "商品A" and v["line_items[0].amount"] == 1000
    assert v["subtotal"] == 1000 and v["total"] == 1100


def test_party_names():
    ex = extract_rules.extract("d", "invoice", els("株式会社青木情報 御中\n前田電気株式会社"))
    v = {f.name: f.value for f in ex.fields}
    assert v["recipient"] == "株式会社青木情報" and v["issuer"] == "前田電気株式会社"


def test_only_invoices():
    with pytest.raises(NotImplementedError):
        extract_rules.extract("d", "spec_sheet", [])


@pytest.mark.parametrize("name", ["clean-000", "clean-001", "clean-002"])
def test_text_layer_of_the_committed_synthetic_invoices(name):
    """pdfium text layer → rules extractor. Totals and every line item must match the generator's ground truth."""
    pdf = SYNTH / "clean" / f"{name}.pdf"
    gt = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    elements, _, _ = parse.parse_pdf_textlayer(pdf, name)
    ex = extract_rules.extract(name, "invoice", elements)
    v = {f.name: f.value for f in ex.fields}
    for k in ("invoice_number", "issue_date", "due_date", "subtotal", "tax", "total"):
        assert v[k] == gt["fields"][k], k
    rows = [(v[f"line_items[{i}].name"], v[f"line_items[{i}].quantity"], v[f"line_items[{i}].unit_price"],
             v[f"line_items[{i}].amount"]) for i in range(len(gt["line_items"]))]
    assert rows == [(r["name"], r["quantity"], r["unit_price"], r["amount"]) for r in gt["line_items"]]
    assert {c.status for c in ex.checks} == {"pass"}


def test_a_label_alone_is_not_a_value():
    """Docling can put 'Invoice No.' and its value in different elements; punctuation must not be returned as the number."""
    ex = extract_rules.extract("d", "invoice", els("Invoice No.", "No.202610-887"))
    assert {f.name: f.status for f in ex.fields}["invoice_number"] == "missing"
