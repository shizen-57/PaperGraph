from collections import Counter

import pytest

from eval import metrics
from backend.schemas import Check, ExtractedField, Extraction

GT = {"fields": {"invoice_number": "INV-1", "issue_date": "2026-10-24", "due_date": "2026-11-30", "issuer": "株式会社A",
                 "recipient": "株式会社B", "subtotal": 1000, "tax": 100, "total": 1100},
      "line_items": [{"name": "商品A", "quantity": 2, "unit_price": 500, "amount": 1000}]}


def field(name, value, status="verified"):
    return ExtractedField(name=name, kind="text", raw=str(value), value=value, quote="q", page=1, element_id="e0", bbox=None,
                          quote_match=1.0, value_in_quote=status == "verified", status=status)


def extraction(overrides=None, statuses=None, checks=()):
    values = {**GT["fields"], **(overrides or {})}
    fields = [field(k, v, (statuses or {}).get(k, "verified")) for k, v in values.items()]
    row = GT["line_items"][0]
    fields += [field(f"line_items[0].{k}", row[k], (statuses or {}).get(f"line_items[0].{k}", "verified")) for k in metrics.ROW]
    return Extraction(doc_id="d", doc_type="invoice", fields=fields, checks=list(checks), model="m", seconds=0)


def test_canon_ignores_width_spacing_and_number_type():
    assert metrics.canon("３，８００") == metrics.canon("3,800")
    assert metrics.canon("ボールペン 黒") == metrics.canon("ボールペン黒")
    assert metrics.canon(1000.0) == metrics.canon(1000) == 1000
    assert metrics.canon(None) is None


def test_f1_counts_rows_as_one_pair():
    pred = {**GT["fields"], "total": 9999, "line_items": GT["line_items"]}
    tp, n_pred, n_gold = metrics.prf(metrics.pairs(pred), metrics.pairs(metrics.gt_values(GT)))
    assert (tp, n_pred, n_gold) == (8, 9, 9)  # 7 header fields + the row; total is wrong
    assert metrics.f1(tp, n_pred, n_gold) == pytest.approx(8 / 9)
    assert metrics.f1(0, 0, 0) is None and metrics.f1(0, 3, 0) == 0.0


def test_field_accuracy_needs_every_row():
    gold = metrics.gt_values(GT)
    assert all(metrics.field_correct(gold, gold).values())
    wrong_row = {**gold, "line_items": [{**GT["line_items"][0], "amount": 1200}]}
    assert not metrics.field_correct(wrong_row, gold)["line_items"] and metrics.field_correct(wrong_row, gold)["total"]


def test_hallucination_catch_and_false_alarm():
    ex = extraction({"total": 9999, "tax": 100}, statuses={"total": "unverified", "issuer": "unverified"})
    j = metrics.judge(ex, metrics.gt_values(GT))
    flagged = {i["name"]: i for i in j["items"]}
    assert not flagged["total"]["correct"] and flagged["total"]["flagged"]  # a caught hallucination
    assert flagged["issuer"]["correct"] and flagged["issuer"]["flagged"]  # a false alarm
    s = metrics.evidence_summary([j])
    assert s["wrong"] == 1 and s["hallucination_catch_rate"] == 1.0 and s["false_alarm_rate"] == pytest.approx(1 / 8)


def test_wrong_value_that_the_evidence_check_misses_can_still_be_caught_by_arithmetic():
    ex = extraction({"total": 1500}, checks=[Check(name="total_sum", status="fail", message="")])
    s = metrics.evidence_summary([metrics.judge(ex, metrics.gt_values(GT))])
    assert s["hallucination_catch_rate"] == 0.0 and s["wrong_docs_caught_by_either"] == 1.0


def test_missing_fields_are_not_hallucinations():
    ex = extraction()
    ex.fields = [f for f in ex.fields if f.name != "issuer"] + [field("issuer", None, "missing")]
    ex.fields[-1].raw = None
    assert all(i["name"] != "issuer" for i in metrics.judge(ex, metrics.gt_values(GT))["items"])


def test_row_flagged_when_any_cell_is_unverified():
    ex = extraction(statuses={"line_items[0].amount": "unverified"})
    row = next(i for i in metrics.judge(ex, metrics.gt_values(GT))["items"] if i["name"] == "line_items[0]")
    assert row["correct"] and row["flagged"]


TABLE = metrics.table_html(["品名", "数量", "金額"], [["商品A", "2", "1,000"], ["商品B", "1", "2,000"]])


def test_teds():
    assert metrics.teds(TABLE, TABLE) == 1.0
    assert metrics.teds(None, TABLE) == 0.0
    one_cell = metrics.table_html(["品名", "数量", "金額"], [["商品A", "2", "1,001"], ["商品B", "1", "2,000"]])
    assert 0.9 < metrics.teds(one_cell, TABLE) < 1.0  # a one-character error costs a little
    missing_row = metrics.table_html(["品名", "数量", "金額"], [["商品A", "2", "1,000"]])
    assert metrics.teds(missing_row, TABLE) < metrics.teds(one_cell, TABLE)
    fullwidth = metrics.table_html(["品名", "数量", "金額"], [["商品A", "２", "１，０００"], ["商品B", "１", "２，０００"]])
    assert metrics.teds(fullwidth, TABLE) == 1.0  # NFKC


def test_items_table_picks_the_one_with_quantity_and_amount():
    from backend.schemas import Element, Table
    totals = Element(id="e0", doc_id="d", type="table", page=1, bbox=None, text="", table=Table(header=["0", "1"], rows=[["小計", "1"]] * 5))
    items = Element(id="e1", doc_id="d", type="table", page=1, bbox=None, text="", table=Table(header=["品名", "数量", "金額"], rows=[["a", "1", "2"]]))
    assert "数量" in metrics.items_table_html([totals, items])
    assert metrics.items_table_html([]) is None


def test_cost_and_recall():
    assert metrics.cost_per_1k_pages(1.8, 0.35) == pytest.approx(0.175)
    assert metrics.recall_at_k([["a", "b"], ["c", "d"]], [{"b"}, {"z"}], k=2) == 0.5
    assert metrics.recall_at_k([["a", "b"]], [{"b"}], k=1) == 0.0


def test_vram_sampler_keeps_the_peak(monkeypatch):
    import subprocess
    import threading
    from types import SimpleNamespace

    from eval import run_eval

    readings = iter(["1200\n", "5400\n", "3100\n"])
    stop, calls, peak = threading.Event(), [], [0]

    def run(cmd, **kw):
        calls.append(cmd)
        try:
            return SimpleNamespace(stdout=next(readings))
        except StopIteration:  # out of readings: end the loop
            stop.set()
            return SimpleNamespace(stdout="")
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(stop, "wait", lambda t: None)  # don't sleep in a test
    run_eval.sample_vram(1, stop, peak)
    assert peak[0] == 5400 and "--id=1" in calls[0]


def test_rescore_reapplies_the_checks_to_stored_predictions():
    from eval import rescore
    row = {"id": "d", "variant": "clean", "pages": 1, "parse_seconds": 1.0, "extract_seconds": 2.0, "tp": 1, "n_pred": 1, "n_gold": 1,
           "correct": {"total": True}, "teds": 1.0, "table_found": True, "error": None,
           "judge": {"items": [], "check_failed": True}, "checks": [],
           "pred": {"subtotal": 1000, "tax": 93, "total": 1093, "line_items": []}}
    run = {"config": {"notes": [], "hardware": {"gpu": None}, "dataset": {"variants": ["clean"]}},
           "summary": {"all": {"peak_vram_mb": None, "evidence": {}}}, "documents": [row]}
    out = rescore.rescore(run, "rule changed")
    assert out["documents"][0]["judge"]["check_failed"] is False  # 9.3% is between 8% and 10%
    assert out["config"]["notes"] == ["rule changed"] and out["summary"]["all"]["evidence"]["docs_failing_a_consistency_check"] == 0
