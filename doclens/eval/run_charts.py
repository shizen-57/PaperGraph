"""Score a VLM on chart → table (F6): mean relative error and coverage against the known values of eval/data/charts.

    VLM_BASE_URL=http://localhost:8002/v1 VLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct-AWQ \\
        python eval/run_charts.py --out eval/results/charts-qwen2.5-vl-7b.json

Also writes eval/results/charts/<name>/chart-NN.png: the original chart next to a re-plot of what the model read.
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

from backend import chart_to_table, llm  # noqa: E402
from eval import metrics  # noqa: E402

DATA = ROOT / "eval" / "data" / "charts"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--note", action="append", default=[])
    args = ap.parse_args()
    pngs = sorted(args.data.glob("chart-*.png"))
    if not pngs:
        sys.exit(f"no charts under {args.data}: run python -m eval.synth.charts")
    images = args.out.parent / "charts" / args.out.stem
    rows = []
    for png in pngs:
        gt = json.loads(png.with_suffix(".json").read_text(encoding="utf-8"))
        raw = png.read_bytes()
        t = time.perf_counter()
        row = {"id": png.stem, "kind": gt["kind"], "data_labels": gt["data_labels"], "mre": None, "coverage": 0.0, "points": 0,
               "matched": 0, "valid": False}
        try:
            chart = chart_to_table.read_chart(raw)
            row.update(chart_to_table.relative_errors(chart, gt["series"]), valid=True, pred=chart.model_dump())
            chart_to_table.side_by_side(raw, chart, images / png.name)
        except (llm.LLMUnavailable, ValueError) as e:
            row["error"] = str(e)[:200]
        row["seconds"] = round(time.perf_counter() - t, 2)
        rows.append(row)
        print(f"{png.stem}: mre {row['mre']} coverage {row['coverage']} {row.get('error', '')}", flush=True)

    def part(rs):
        return {"n": len(rs), "valid_rate": metrics.rate(sum(r["valid"] for r in rs), len(rs)),
                "mean_relative_error": metrics.mean([r["mre"] for r in rs]), "coverage": metrics.mean([r["coverage"] for r in rs]),
                "seconds_per_chart": metrics.mean([r["seconds"] for r in rs])}

    result = {
        "config": {"name": args.out.stem, "vlm": os.environ.get("VLM_MODEL") or os.environ.get("LLM_MODEL"),
                   "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "notes": args.note},
        "chart_summary": {"all": part(rows), "with_data_labels": part([r for r in rows if r["data_labels"]]),
                          "without_data_labels": part([r for r in rows if not r["data_labels"]])},
        "charts": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result["chart_summary"], indent=1))


if __name__ == "__main__":
    main()
