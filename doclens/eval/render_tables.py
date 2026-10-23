"""Markdown tables from eval/results/*.json, so that no number in the README is typed by hand.

    python eval/render_tables.py                      # print the tables
    python eval/render_tables.py --write ../README.md # replace what sits between <!-- results:start --> and <!-- results:end -->

Configurations that need a GPU and have not been run yet appear as 'not run' rows (see PENDING), never as numbers.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"

# (label, result file stem written by notebooks/kaggle_arena.ipynb). No file, no numbers.
PENDING = [
    ("PaddleOCR-VL + Qwen2.5-7B", "paddleocr-vl-qwen2.5-7b"),
    ("Qwen2.5-VL-7B zero-shot + Qwen2.5-7B", "qwen-vl-qwen2.5-7b"),
    ("Router (Docling, VLM on hard pages) + Qwen2.5-7B", "router-qwen2.5-7b"),
]


def fmt(x, digits=2, suffix=""):
    return "—" if x is None else f"{x:.{digits}f}{suffix}"


def pct(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def load(results: Path = RESULTS) -> list[dict]:
    runs = []
    for f in sorted(results.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, dict) and "summary" in d:
            d["_stem"] = f.stem
            runs.append(d)
    return runs


def name_of(run: dict) -> str:
    c = run["config"]
    parser = {"docling": "Docling", "pdfium": "PDF text layer (pdfium)", "tesseract": "Tesseract jpn+eng",
              "vlm": "VLM", "router": "Router"}.get(c["parser"], c["parser"])
    extractor = "rules (regex)" if c["extractor"] == "rules" else (c.get("llm") or "LLM")
    return f"{parser} + {extractor}"


def where(run: dict) -> str:
    hw = run["config"]["hardware"]
    return hw["gpu"] or f"CPU, {hw['cores']} cores"


def end_to_end(summary: dict) -> float | None:
    """Seconds per document for parse + extraction together (the parse figure alone hides an LLM that dominates it)."""
    if not summary or not summary.get("n_docs"):
        return None
    return (summary["parse"]["seconds"] + summary["extract"]["seconds"]) / summary["n_docs"]


def arena_table(runs: list[dict]) -> str:
    head = ("| Parser + extractor | Hardware | Field F1 (clean) | Field F1 (scanned) | Table TEDS | Parse pages/s | End-to-end s/doc | Peak VRAM | $/1k pages |\n"
            "|---|---|---|---|---|---|---|---|---|\n")
    rows = []
    have = {r["_stem"] for r in runs}
    for r in runs:
        s = r["summary"]
        al = s.get("all", {})
        rows.append(f"| {name_of(r)} | {where(r)} | {fmt(s.get('clean', {}).get('field_f1'))} | "
                    f"{fmt(s['scanned']['field_f1']) if 'scanned' in s else 'not in this run'} | {fmt(al.get('teds'))} | "
                    f"{fmt(al.get('parse', {}).get('pages_per_sec'))} | {fmt(end_to_end(al), 1)} | "
                    f"{'—' if al.get('peak_vram_mb') is None else str(al['peak_vram_mb']) + ' MB'} | "
                    f"{'—' if al.get('cost_per_1k_pages_parse_usd') is None else '$' + str(al['cost_per_1k_pages_parse_usd'])} |")
    rows += [f"| {label} | GPU | not run | not run | not run | not run | not run | not run | not run |"
             for label, stem in PENDING if stem not in have]
    return head + "\n".join(rows)


def evidence_table(runs: list[dict]) -> str:
    head = ("| Run | Values predicted | Wrong | Wrong values flagged by the evidence check | Right values flagged anyway | "
            "Documents with a wrong value | …caught by evidence or arithmetic |\n|---|---|---|---|---|---|---|\n")
    rows = []
    for r in runs:
        e = r["summary"]["all"]["evidence"]
        rows.append(f"| {name_of(r)} | {e['predicted']} | {e['wrong']} | {pct(e['hallucination_catch_rate'])} | "
                    f"{pct(e['false_alarm_rate'])} | {e['docs_with_a_wrong_value']} | {pct(e['wrong_docs_caught_by_either'])} |")
    return head + "\n".join(rows)


def field_table(runs: list[dict]) -> str:
    fields = next((list(r["summary"]["all"]["field_accuracy_by_field"]) for r in runs), [])
    head = "| Run | " + " | ".join(fields) + " |\n|---|" + "---|" * len(fields) + "\n"
    rows = [f"| {name_of(r)} | " + " | ".join(pct(r["summary"]["all"]["field_accuracy_by_field"].get(f)) for f in fields) + " |"
            for r in runs]
    return head + "\n".join(rows)


def load_kind(key: str, results: Path = RESULTS) -> list[dict]:
    """Result files of the other shapes: charts (chart_summary), direct image→JSON runs (direct_summary), the router report."""
    out = []
    for f in sorted(results.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, dict) and key in d:
            d["_stem"] = f.stem
            out.append(d)
    return out


def chart_section(runs: list[dict]) -> str:
    if not runs:
        return "_Not run yet: needs a VLM (`python eval/run_charts.py`, see notebooks/kaggle_arena.ipynb)._"
    head = ("| VLM | Charts | Valid JSON | Mean relative error (all) | …with printed data labels | …without | Points found |\n"
            "|---|---|---|---|---|---|---|\n")
    rows = []
    for r in runs:
        s = r["chart_summary"]
        rows.append(f"| {r['config']['vlm']} | {s['all']['n']} | {pct(s['all']['valid_rate'])} | {pct(s['all']['mean_relative_error'])} | "
                    f"{pct(s['with_data_labels']['mean_relative_error'])} | {pct(s['without_data_labels']['mean_relative_error'])} | "
                    f"{pct(s['all']['coverage'])} |")
    return head + "\n".join(rows)


def direct_section(runs: list[dict]) -> str:
    if not runs:
        return "_Not run yet: needs a GPU (`notebooks/kaggle_lora.ipynb`)._"
    head = ("| Model | Valid JSON | Field F1 (clean) | Field F1 (scanned) | Docs with every field right | Docs failing an arithmetic check | s/doc |\n"
            "|---|---|---|---|---|---|---|\n")
    rows = []
    for r in runs:
        s = r["direct_summary"]
        a = s["all"]
        rows.append(f"| {r['config']['model']} | {pct(a['valid_json_rate'])} | {fmt(s.get('clean', {}).get('field_f1'))} | "
                    f"{fmt(s.get('scanned', {}).get('field_f1'))} | {a['docs_all_fields_correct']}/{a['n_docs']} | "
                    f"{a['docs_failing_an_arithmetic_check']} | {fmt(a['seconds_per_doc'], 1)} |")
    return head + "\n".join(rows)


def router_section(runs: list[dict]) -> str:
    if not runs:
        return "_Not run yet: `python eval/router_report.py`._"
    s = runs[0]["router_summary"]
    return (f"Cheap signals only (text layer, Docling table quality; no VLM involved): of {s['all']['pages']} pages, "
            f"**{s['scanned']['to_vlm']}/{s['scanned']['pages']} scanned pages** were sent to the VLM and "
            f"**{s['clean']['to_vlm']}/{s['clean']['pages']} clean pages** were; "
            f"{s['all']['correct']}/{s['all']['pages']} routed as the ground truth says. "
            f"Reasons: {', '.join(f'{k} ×{v}' for k, v in s['all']['reasons'].items()) or 'none'}.")


def deck_section(runs: list[dict]) -> str:
    if not runs:
        return "_Not run yet: `python eval/run_decks.py`._"
    s = runs[0]["deck_summary"]
    return (f"{s['decks']} synthetic decks ({s['slides']} slides: bullets, a table and a chart each), read by Docling's PPTX backend: "
            f"**{pct(s['fact_recall'])} of key facts** and **{pct(s['cell_recall'])} of table cells** recovered. "
            f"Charts come out as figures without values.")


def render(runs: list[dict], results: Path = RESULTS) -> str:
    if not runs:
        return "_No results yet: run `python eval/run_eval.py` (see below)._"
    first = runs[0]["config"]
    n = first["dataset"]["n_docs"]
    return (f"**Parsers and extractors** on {n} synthetic Japanese invoices (clean text-layer PDFs and scanned image-only PDFs).\n\n"
            f"{arena_table(runs)}\n\n**Does the evidence check catch wrong values?**\n\n{evidence_table(runs)}\n\n"
            f"**Exact-match accuracy per field**\n\n{field_table(runs)}\n\n"
            f"**Router (F2)**\n\n{router_section(load_kind('router_summary', results))}\n\n"
            f"**PowerPoint input (F5)**\n\n{deck_section(load_kind('deck_summary', results))}\n\n"
            f"**Chart → table (F6)**\n\n{chart_section(load_kind('chart_summary', results))}\n\n"
            f"**LoRA fine-tune, image → JSON (F8)**\n\n{direct_section(load_kind('direct_summary', results))}")


def write_into(readme: Path, tables: str) -> None:
    text = readme.read_text(encoding="utf-8")
    pattern = re.compile(r"(<!-- results:start -->).*?(<!-- results:end -->)", re.S)
    if not pattern.search(text):
        sys.exit(f"{readme} has no <!-- results:start --> ... <!-- results:end --> block")
    readme.write_text(pattern.sub(lambda m: f"{m.group(1)}\n{tables}\n{m.group(2)}", text), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=RESULTS)
    ap.add_argument("--write", type=Path, help="README to update in place")
    args = ap.parse_args()
    tables = render(load(args.results), args.results)
    if args.write:
        write_into(args.write, tables)
        print(f"updated {args.write}")
    else:
        print(tables)


if __name__ == "__main__":
    main()
