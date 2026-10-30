"""Re-apply the arithmetic checks to the predictions stored in a results file, without running any parser or model.

    python eval/rescore.py eval/results/*.json --note "tax_rate check: tax between 8% and 10% passes when lines carry no rate"

Use it after changing backend/consistency.py: the stored `pred` values are enough to re-run the checks, so a multi-hour LLM run
does not need repeating. The evidence results (quotes, verified/unverified) are untouched. The note is added to the file, so the
results say which rule they were last scored with.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import consistency  # noqa: E402
from eval import metrics, run_eval  # noqa: E402


def rescore(run: dict, note: str | None = None) -> dict:
    variants = run["config"]["dataset"]["variants"]
    rates = consistency.RATES if {"clean", "scanned"} & set(variants) else None  # Japan's 10% / 8% apply to the Japanese set only
    for row in run["documents"]:
        checks = consistency.check_invoice(row["pred"], rates=rates)
        row["checks"] = [c.model_dump() for c in checks]
        row["judge"]["check_failed"] = any(c.status == "fail" for c in checks)
    cfg = run["config"]
    gpu = bool(cfg["hardware"]["gpu"])
    peak = run["summary"]["all"].get("peak_vram_mb")
    usd = cfg.get("gpu_hourly_usd")
    run["summary"] = {v: run_eval.summarise([r for r in run["documents"] if r["variant"] == v], usd, gpu, peak) for v in variants}
    run["summary"]["all"] = run_eval.summarise(run["documents"], usd, gpu, peak)
    if note and note not in cfg["notes"]:
        cfg["notes"].append(note)
    return run


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--note")
    args = ap.parse_args()
    for path in args.runs:
        run = json.loads(path.read_text(encoding="utf-8"))
        if "summary" not in run or "documents" not in run or "pred" not in run["documents"][0]:
            continue
        before = run["summary"]["all"]["evidence"]
        rescore(run, args.note)
        after = run["summary"]["all"]["evidence"]
        path.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{path.name}: docs failing a check {before['docs_failing_a_consistency_check']} -> {after['docs_failing_a_consistency_check']}; "
              f"wrong docs caught by either {before['wrong_docs_caught_by_either']} -> {after['wrong_docs_caught_by_either']}")


if __name__ == "__main__":
    main()
