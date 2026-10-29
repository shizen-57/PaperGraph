"""What would the router do with the eval set? Uses only the cheap signals (text layer, and Docling's tables from the
parse cache), so it needs no VLM and no GPU. The ground truth is the document's variant: scanned pages need a VLM,
clean ones don't.

    python eval/run_eval.py --parser docling --extractor rules --out eval/results/docling-rules.json   # fills eval/.cache/docling
    python eval/router_report.py --out eval/results/router-decisions.json

The GPU-seconds side of the experiment (Docling-only vs VLM-only vs router) is eval/run_eval.py --parser router, on a GPU.
"""
import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import router  # noqa: E402
from backend.schemas import Element  # noqa: E402

DATA = ROOT / "eval" / "data" / "synth"
CACHE = ROOT / "eval" / ".cache" / "docling"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rows = []
    for variant in ("clean", "scanned"):
        for pdf in sorted((DATA / variant).glob("*.pdf")):
            cached = CACHE / f"{pdf.stem}.json"
            elements = [Element.model_validate(e) for e in json.loads(cached.read_text(encoding="utf-8"))["elements"]] if cached.exists() else []
            for d in router.decide(router.page_text_chars(pdf), elements):
                rows.append({"id": pdf.stem, "variant": variant, "page": d.page, "route": d.route, "reasons": d.reasons,
                             "needs_vlm": variant == "scanned", "docling_cache": cached.exists()})

    def part(rs):
        flagged = [r for r in rs if r["route"] == "vlm"]
        return {"pages": len(rs), "to_vlm": len(flagged), "share_to_vlm": round(len(flagged) / len(rs), 4) if rs else None,
                "correct": sum((r["route"] == "vlm") == r["needs_vlm"] for r in rs),
                "reasons": dict(Counter(x.split(":")[0] for r in flagged for x in r["reasons"]))}

    result = {"config": {"name": args.out.stem, "signals": "text layer + Docling table quality (cached); no figure or second-pass signal",
                         "min_text_chars": router.MIN_TEXT_CHARS, "max_empty_cells": router.MAX_EMPTY_CELLS,
                         "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")},
              "router_summary": {"all": part(rows), "clean": part([r for r in rows if r["variant"] == "clean"]),
                                 "scanned": part([r for r in rows if r["variant"] == "scanned"])},
              "pages": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result["router_summary"], ensure_ascii=False, indent=1))
    for r in rows:
        if r["variant"] == "clean" and r["route"] == "vlm":
            print("false positive:", r["id"], r["reasons"])


if __name__ == "__main__":
    main()
