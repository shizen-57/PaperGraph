"""Group the wrong and missing values of a run by cause, by looking at what the parser actually produced.

    python eval/failures.py eval/results/docling-qwen2.5-3b.json            # prints a table, writes eval/results/failures-docling-qwen2.5-3b.json
    python eval/failures.py eval/results/*.json --markdown                  # Markdown for REPORT.md

For every header field whose prediction differs from the truth (or is missing), and for every line-item row, the cause is decided
from the parsed text of that document (the parse cache that run_eval.py wrote), in this order:

  role confusion        issuer and recipient swapped: both are real, both are in the wrong place
  copy boundary         the predicted text contains the true value (or the reverse) but with extra or missing characters:
                        an honorific (様, 御中) or a label (請求書番号：) copied into the value, a cut-off string
  not in the parsed text  the true value is absent from the parser's output (OCR / parse loss)
  hallucinated          the predicted value appears nowhere in the parsed text
  normalisation         the model copied the value as printed, but turning it into a typed value gave a different one
  present, not extracted  the true value is in the parsed text and the extractor returned nothing
  wrong choice          the true value is in the parsed text, but the extractor picked another real value
  row lost or merged    (line items) every cell of a true row is in the parsed text, but no predicted row matches it
  extra row             (line items) a predicted row that matches no true row

A value counts as "in the parsed text" after NFKC, casefold and whitespace removal, with or without thousands separators.
These are heuristics, not labels: they say where to look, and every document is in the results file for checking.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.norm import norm  # noqa: E402
from eval import metrics  # noqa: E402

CATEGORIES = ["role confusion", "copy boundary", "not in the parsed text", "hallucinated", "normalisation", "present, not extracted", "wrong choice",
              "row lost or merged", "extra row"]
AMOUNTS = ("subtotal", "tax", "total")


def forms(value, shown: str | None = None) -> list[str]:
    """Spellings of a true value that may appear in the text (printed form, grouped digits, plain digits)."""
    out = [norm(str(value))]
    if shown:
        out.append(norm(shown))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        out += [norm(f"{int(value):,}"), str(int(value))]
    return [o for o in out if o]


def present(value, text: str, shown: str | None = None) -> bool:
    """Is the value in the parsed text? `text` is already normalised; separators are ignored for numbers."""
    flat = re.sub(r"[,，]", "", text)
    return any(f in text or re.sub(r"[,，]", "", f) in flat for f in forms(value, shown))


def classify_field(name: str, pred, gold, text: str, shown: str | None, raw: str | None, other_gold) -> str | None:
    """None if the field is right. Otherwise one of CATEGORIES."""
    if metrics.canon(pred) == metrics.canon(gold):
        return None
    if pred is not None and name in ("issuer", "recipient") and metrics.canon(pred) == metrics.canon(other_gold):
        return "role confusion"
    if isinstance(pred, str) and isinstance(gold, str) and norm(pred) != norm(gold) and (norm(gold) in norm(pred) or norm(pred) in norm(gold)):
        return "copy boundary"
    if not present(gold, text, shown):
        return "not in the parsed text"
    if pred is None:
        return "present, not extracted"
    if raw is not None and metrics.canon(raw) == metrics.canon(shown or gold):
        return "normalisation"
    if not present(pred, text):
        return "hallucinated"
    return "wrong choice"


def classify_rows(pred_rows: list[dict], gold_rows: list[dict], text: str) -> list[str]:
    left = Counter(metrics.row_key(r) for r in gold_rows)
    out = []
    extra = []
    for r in pred_rows:
        k = metrics.row_key(r)
        if left[k] > 0:
            left[k] -= 1
        else:
            extra.append(r)
    missing = [r for r in gold_rows if left[metrics.row_key(r)] > 0]
    for r in missing:
        cells = [r["name"], r["amount"], r["unit_price"]]
        out.append("row lost or merged" if all(present(c, text) for c in cells) else "not in the parsed text")
    for r in extra:
        out.append("extra row" if present(r.get("name") or "", text) else "hallucinated")
    return out


def analyse(run: dict, parse_text) -> dict:
    """`parse_text(doc_id) -> str` gives the normalised parsed text of a document."""
    counts: dict[str, Counter] = {"clean": Counter(), "scanned": Counter()}
    examples: dict[str, list] = {}
    n_checked = Counter()
    for d in run["documents"]:
        gt = json.loads((ROOT / run["config"]["dataset"]["path"] / d["variant"] / f"{d['id']}.json").read_text(encoding="utf-8"))
        text = parse_text(d["id"])
        raw = {f["name"]: f["raw"] for f in d.get("fields", [])}
        shown = gt["shown"]
        for name in metrics.TOP:
            n_checked[d["variant"]] += 1
            other = d["gold"].get({"issuer": "recipient", "recipient": "issuer"}.get(name, name))
            cat = classify_field(name, d["pred"].get(name), d["gold"].get(name), text, shown.get(name), raw.get(name), other)
            if cat:
                counts[d["variant"]][cat] += 1
                examples.setdefault(cat, []).append({"id": d["id"], "field": name, "pred": d["pred"].get(name), "gold": d["gold"].get(name)})
        for cat in classify_rows(d["pred"].get("line_items") or [], d["gold"].get("line_items") or [], text):
            counts[d["variant"]][cat] += 1
            examples.setdefault(cat, []).append({"id": d["id"], "field": "line_items"})
    return {"config": run["config"]["name"], "counts": {v: dict(c) for v, c in counts.items()},
            "header_fields_checked": dict(n_checked), "examples": {k: v[:5] for k, v in examples.items()}}


def markdown(results: list[dict]) -> str:
    head = "| Run | Variant | " + " | ".join(CATEGORIES) + " |\n|---|---|" + "---|" * len(CATEGORIES) + "\n"
    rows = []
    for r in results:
        for v in ("clean", "scanned"):
            if v in r["counts"] and r["header_fields_checked"].get(v):
                rows.append(f"| {r['config']} | {v} | " + " | ".join(str(r["counts"][v].get(c, 0)) for c in CATEGORIES) + " |")
    return head + "\n".join(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()
    from eval import run_eval

    out = []
    for path in args.runs:
        run = json.loads(path.read_text(encoding="utf-8"))
        if "summary" not in run or "documents" not in run:
            continue
        parser = run["config"]["parser"]
        data = ROOT / run["config"]["dataset"]["path"]

        def parse_text(doc_id, parser=parser, data=data):
            variant = "clean" if doc_id.startswith("clean") else "scanned"
            elements, _, _ = run_eval.parse_one(parser, data / variant / f"{doc_id}.pdf", reuse=True)
            return norm(" ".join(e.text for e in elements))

        res = analyse(run, parse_text)
        (path.parent / f"failures-{path.stem}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        out.append(res)
    print(markdown(out))


if __name__ == "__main__":
    main()
