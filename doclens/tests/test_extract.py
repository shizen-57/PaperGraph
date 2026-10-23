import json

import pytest

from backend import extract, llm
from backend.schemas import BBox, Element

PAGE = [
    ("e0", "text", "請求書\n請求書番号: INV-2026-0042\n発行日: 令和8年10月24日\n支払期限: 2026/11/30"),
    ("e1", "text", "株式会社サンプル商事 御中"),
    ("e2", "table", "| 品名 | 数量 | 単価 | 金額 |\n|---|---|---|---|\n| 商品A | 2 | 500 | 1,000 |\n| 商品B | 1 | 2,000 | 2,000 |"),
    ("e3", "text", "小計 ¥3,000\n消費税(10%) ¥300\n合計 ¥3,300"),
]
ELEMENTS = [Element(id=i, doc_id="inv", type=t, page=1, bbox=BBox(x0=0, y0=k * 100, x1=500, y1=k * 100 + 90), text=x)
            for k, (i, t, x) in enumerate(PAGE)]


def cited(value, quote, eid):
    return {"value": value, "quote": quote, "element_id": eid}


def reply(**override):
    out = {
        "invoice_number": cited("INV-2026-0042", "請求書番号: INV-2026-0042", "e0"),
        "issue_date": cited("令和8年10月24日", "発行日: 令和8年10月24日", "e0"),
        "due_date": cited("2026/11/30", "支払期限: 2026/11/30", "e0"),
        "issuer": cited(None, "", ""),
        "recipient": cited("株式会社サンプル商事", "株式会社サンプル商事 御中", "e1"),
        "subtotal": cited("¥3,000", "小計 ¥3,000", "e3"),
        "tax": cited("¥300", "消費税(10%) ¥300", "e3"),
        "total": cited("¥3,300", "合計 ¥3,300", "e3"),
        "line_items": [
            {"name": "商品A", "quantity": "2", "unit_price": "500", "amount": "1,000", "tax_rate": None,
             "quote": "| 商品A | 2 | 500 | 1,000 |", "element_id": "e2"},
            {"name": "商品B", "quantity": "1", "unit_price": "2,000", "amount": "2,000", "tax_rate": None,
             "quote": "商品B 1 2,000 2,000", "element_id": "e2"},  # pipes dropped: still found
        ],
    }
    out.update(override)
    return json.dumps(out, ensure_ascii=False)


@pytest.fixture
def say(monkeypatch):
    replies, calls = [], []

    def chat(messages, schema=None, **kw):
        calls.append(messages)
        return replies.pop(0)
    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setenv("LLM_MODEL", "fake")
    return replies, calls


def by_name(ex):
    return {f.name: f for f in ex.fields}


def test_clean_invoice_is_verified_and_consistent(say):
    say[0].append(reply())
    ex = extract.extract("inv", "invoice", ELEMENTS)
    f = by_name(ex)
    assert f["issue_date"].value == "2026-10-24" and f["issue_date"].raw == "令和8年10月24日"
    assert f["total"].value == 3300 and f["total"].page == 1 and f["total"].bbox.y0 == 300
    assert f["issuer"].status == "missing" and f["issuer"].value is None
    assert all(x.status == "verified" for x in ex.fields if x.status != "missing")
    assert {c.status for c in ex.checks} == {"pass"}
    assert f["line_items[1].amount"].value == 2000 and f["line_items[1].amount"].element_id == "e2"


def test_invented_quote_is_unverified(say):
    say[0].append(reply(total=cited("¥9,999", "合計 ¥9,999", "e3")))
    ex = extract.extract("inv", "invoice", ELEMENTS)
    t = by_name(ex)["total"]
    assert t.status == "unverified" and t.quote_match < 0.9 and t.value == 9999
    assert {c.name: c.status for c in ex.checks}["total_sum"] == "fail"  # the arithmetic catches it too


def test_value_not_in_its_quote_is_unverified(say):
    # a real quote, but the model reports a different number than the one in it
    say[0].append(reply(total=cited("¥3,330", "合計 ¥3,300", "e3")))
    t = by_name(extract.extract("inv", "invoice", ELEMENTS))["total"]
    assert t.quote_match == 1.0 and not t.value_in_quote and t.status == "unverified"


def test_real_quote_wrong_number_is_caught_by_consistency_not_evidence(say):
    wrong = {"name": "商品A", "quantity": "2", "unit_price": "500", "amount": "1,200", "tax_rate": None,
             "quote": "商品A 2 500 1,200", "element_id": "e2"}
    say[0].append(reply(line_items=[wrong]))
    ex = extract.extract("inv", "invoice", ELEMENTS)
    amount = by_name(ex)["line_items[0].amount"]
    assert amount.quote_match >= 0.9 and not amount.value_in_quote  # the quote was edited to fit the value: fuzzy-found, but 1,200 is not in the document
    assert amount.status == "unverified"
    assert {c.name: c.status for c in ex.checks}["line_amounts"] == "fail"


def test_invalid_json_is_retried_once_with_the_error(say):
    replies, calls = say
    replies += ["not json at all", reply()]
    ex = extract.extract("inv", "invoice", ELEMENTS)
    assert by_name(ex)["total"].status == "verified" and len(calls) == 2
    assert "invalid" in calls[1][-1]["content"]


def test_two_invalid_replies_raise(say):
    say[0].extend(["{}", "{}"])
    with pytest.raises(extract.ExtractionError):
        extract.extract("inv", "invoice", ELEMENTS)


def test_fenced_json_is_accepted(say):
    say[0].append("```json\n" + reply() + "\n```")
    assert by_name(extract.extract("inv", "invoice", ELEMENTS))["subtotal"].value == 3000


def test_financial_report_applies_the_unit(say):
    els = [Element(id="e0", doc_id="r", type="text", page=1, bbox=None,
                   text="(単位:百万円)\n売上高 1,234\n営業利益 △56\n決算期 2026年3月期")]
    out = {k: cited(None, "", "") for k in extract.FinancialReport.model_fields}
    out.update(unit=cited("百万円", "(単位:百万円)", "e0"), revenue=cited("1,234", "売上高 1,234", "e0"),
               operating_income=cited("△56", "営業利益 △56", "e0"), fiscal_period_end=cited("2026年3月期", "決算期 2026年3月期", "e0"))
    say[0].append(json.dumps(out, ensure_ascii=False))
    f = by_name(extract.extract("r", "financial_report", els))
    assert f["revenue"].value == 1_234_000_000 and f["operating_income"].value == -56_000_000
    assert f["fiscal_period_end"].value == "2026-03" and f["revenue"].status == "verified"


def test_to_values_regroups_line_items(say):
    say[0].append(reply())
    v = extract.to_values(extract.extract("inv", "invoice", ELEMENTS).fields)
    assert v["total"] == 3300 and v["line_items"][0] == {"name": "商品A", "quantity": 2, "unit_price": 500, "amount": 1000, "tax_rate": None}
