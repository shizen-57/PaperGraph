"""Score a VLM that reads the invoice image straight into JSON (no parser, no quotes): the base model and the LoRA (F8).

    VLM_BASE_URL=http://localhost:8002/v1 python eval/run_direct.py --model Qwen/Qwen2-VL-2B-Instruct --out eval/results/direct-base.json
    VLM_BASE_URL=http://localhost:8002/v1 python eval/run_direct.py --model invoice-lora --out eval/results/direct-lora.json

Same documents, same field F1 and accuracy as run_eval.py, and the arithmetic checks. There is no verified rate: without a quote
there is nothing to verify. The held-out set is eval/data/synth (seed 0); the LoRA is trained on other seeds (train/build_dataset.py).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import extract_direct as direct  # noqa: E402
from backend import llm  # noqa: E402
from eval import metrics  # noqa: E402

DATA = ROOT / "eval" / "data" / "synth"


def run_doc(pdf: Path, model: str, base_url: str | None) -> dict:
    gt = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    gold = metrics.gt_values(gt)
    row = {"id": pdf.stem, "variant": gt["variant"], "valid": False, "error": None, "tp": 0, "n_pred": 0,
           "n_gold": sum(metrics.pairs(gold).values()), "correct": {k: False for k in [*metrics.TOP, "line_items"]},
           "check_failed": False}
    t = time.perf_counter()
    try:
        values = direct.read_invoice(direct.render_page(pdf), model=model, base_url=base_url)
        pred = values.model_dump()
        row["tp"], row["n_pred"], _ = metrics.prf(metrics.pairs(pred), metrics.pairs(gold))
        row.update(valid=True, correct=metrics.field_correct(pred, gold), pred=pred,
                   check_failed=any(c.status == "fail" for c in direct.checks_of(values)))
    except (llm.LLMUnavailable, ValueError) as e:
        row["error"] = str(e)[:200]
    row["seconds"] = round(time.perf_counter() - t, 3)
    return row


def summarise(rows: list[dict]) -> dict:
    if not rows:
        return {}
    tp, n_pred, n_gold = (sum(r[k] for r in rows) for k in ("tp", "n_pred", "n_gold"))
    return {"n_docs": len(rows), "valid_json_rate": metrics.rate(sum(r["valid"] for r in rows), len(rows)),
            "field_f1": round(metrics.f1(tp, n_pred, n_gold) or 0.0, 4),
            "field_accuracy": metrics.mean([metrics.mean([float(v) for v in r["correct"].values()]) for r in rows]),
            "docs_all_fields_correct": sum(all(r["correct"].values()) for r in rows),
            "docs_failing_an_arithmetic_check": sum(r["check_failed"] for r in rows),
            "seconds_per_doc": metrics.mean([r["seconds"] for r in rows])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="model name on the server (the LoRA's name for the fine-tune)")
    ap.add_argument("--base-url", default=os.environ.get("VLM_BASE_URL"))
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--variants", default="clean,scanned")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--note", action="append", default=[])
    args = ap.parse_args()
    docs = [p for v in args.variants.split(",") for p in sorted((args.data / v).glob("*.pdf"))[:args.limit]]
    rows = []
    for pdf in docs:
        rows.append(run_doc(pdf, args.model, args.base_url))
        print(f"{pdf.stem}: valid={rows[-1]['valid']} {rows[-1]['error'] or ''}", flush=True)
    summary = {v: summarise([r for r in rows if r["variant"] == v]) for v in args.variants.split(",")}
    summary["all"] = summarise(rows)
    result = {"config": {"name": args.out.stem, "model": args.model, "extractor": "direct image→JSON",
                         "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "notes": args.note,
                         "dataset": {"n_docs": len(docs)}},
              "direct_summary": summary, "documents": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
