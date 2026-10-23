import json

import pytest

from backend import extract_direct as direct
from backend import llm
from eval import metrics

GT = {"id": "x-001", "variant": "clean",
      "fields": {"invoice_number": "INV-1", "issue_date": "2026-10-24", "due_date": "2026-11-30", "issuer": "株式会社A",
                 "recipient": "株式会社B", "subtotal": 1000, "tax": 100, "total": 1100},
      "line_items": [{"name": "商品A", "quantity": 2, "unit_price": 500, "amount": 1000, "tax_rate": None}]}


def test_target_is_the_ground_truth_in_schema_form():
    t = json.loads(direct.target_json(GT))
    assert t["total"] == 1100 and t["issue_date"] == "2026-10-24" and t["line_items"][0]["amount"] == 1000
    assert direct.InvoiceValues.model_validate(t)


def test_read_invoice_validates_and_checks_arithmetic(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: direct.target_json(GT))
    v = direct.read_invoice(b"png", model="m")
    assert v.total == 1100 and {c.status for c in direct.checks_of(v)} == {"pass"}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: '{"total": "a lot"}')
    with pytest.raises(ValueError, match="did not return an invoice"):
        direct.read_invoice(b"png")


def test_direct_output_scores_with_the_same_metrics(monkeypatch):
    v = json.loads(direct.target_json(GT))
    gold = metrics.gt_values(GT)
    assert all(metrics.field_correct(v, gold).values())
    wrong = {**v, "total": 9999}
    assert not metrics.field_correct(wrong, gold)["total"]


@pytest.mark.slow
def test_dataset_builder_writes_images_and_jsonl(tmp_path):
    from train import build_dataset
    train, val = build_dataset.build(n=3, seed=5, out=tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    assert train + val == 6 and len(rows) == train
    r = rows[0]
    assert (tmp_path / r["image"]).stat().st_size > 5000
    assert r["messages"][0]["content"][0] == {"type": "image"} and json.loads(r["messages"][1]["content"][0]["text"])["total"] > 0


def test_run_direct_scores_a_perfect_and_a_broken_model(tmp_path, monkeypatch):
    import sys

    from eval import run_direct
    gt = lambda pdf: json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))  # noqa: E731
    answers = {}

    def chat(messages, schema=None, **kw):
        return answers["reply"]
    monkeypatch.setattr(llm, "chat", chat)
    out = tmp_path / "direct.json"

    def run(reply):
        answers["reply"] = reply
        monkeypatch.setattr(sys, "argv", ["run_direct", "--model", "m", "--variants", "clean", "--limit", "2", "--out", str(out)])
        run_direct.main()
        return json.loads(out.read_text(encoding="utf-8"))

    # a model that returns the first document's truth for both documents: right for one, wrong for the other
    first = run_direct.DATA / "clean" / "clean-000.pdf"
    res = run(direct.target_json(gt(first)))
    docs = {d["id"]: d for d in res["documents"]}
    assert docs["clean-000"]["correct"]["total"] and not docs["clean-001"]["correct"]["total"]
    assert res["direct_summary"]["clean"]["valid_json_rate"] == 1.0 and 0 < res["direct_summary"]["all"]["field_f1"] < 1
    res = run("not json")
    assert res["direct_summary"]["all"]["valid_json_rate"] == 0.0 and res["direct_summary"]["all"]["field_f1"] == 0.0
