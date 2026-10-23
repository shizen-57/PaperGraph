"""PPTX slice (F5): how many key facts and table cells does the parser recover from the slides?

    python eval/run_decks.py --out eval/results/decks-docling.json

PPTX has no pixels to OCR: Docling reads the slide XML, so text, tables and slide numbers should come out exactly. A fact counts as
recovered if it appears in any element's text (NFKC, no whitespace); a table cell if it appears in a table element. Charts become
`figure` elements without values (reading them is the chart experiment, eval/run_charts.py).
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import parse  # noqa: E402
from backend.norm import norm  # noqa: E402
from eval import metrics  # noqa: E402

DATA = ROOT / "eval" / "data" / "decks"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rows = []
    for pptx in sorted(args.data.glob("*.pptx")):
        gt = json.loads(pptx.with_suffix(".json").read_text(encoding="utf-8"))
        t = time.perf_counter()
        elements, sizes, _ = parse.parse_path(pptx, pptx.stem, "pptx", parser="docling")
        seconds = time.perf_counter() - t
        text = norm(" ".join(e.text for e in elements))
        table_text = norm(" ".join(e.text for e in elements if e.type == "table"))
        cells = [c for row in gt["table"] for c in row]
        rows.append({"id": pptx.stem, "slides": len(sizes), "elements": len(elements),
                     "figures": sum(e.type == "figure" for e in elements), "tables": sum(e.type == "table" for e in elements),
                     "facts_found": [f for f in gt["facts"] if norm(f) in text], "facts_missing": [f for f in gt["facts"] if norm(f) not in text],
                     "cells_found": sum(norm(c) in table_text for c in cells), "cells": len(cells), "seconds": round(seconds, 2)})
        print(f"{pptx.stem}: facts {len(rows[-1]['facts_found'])}/{len(gt['facts'])}, cells {rows[-1]['cells_found']}/{len(cells)}", flush=True)
    facts = sum(len(r["facts_found"]) + len(r["facts_missing"]) for r in rows)
    result = {"config": {"name": args.out.stem, "parser": "docling", "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")},
              "deck_summary": {"decks": len(rows), "fact_recall": metrics.rate(sum(len(r["facts_found"]) for r in rows), facts),
                               "cell_recall": metrics.rate(sum(r["cells_found"] for r in rows), sum(r["cells"] for r in rows)),
                               "slides": sum(r["slides"] for r in rows), "seconds": round(sum(r["seconds"] for r in rows), 2)},
              "decks": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result["deck_summary"], indent=1))


if __name__ == "__main__":
    main()
