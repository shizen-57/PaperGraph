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


def name_of(run: dict, runs: list[dict] | None = None) -> str:
    c = run["config"]
    parser = {"docling": "Docling", "pdfium": "PDF text layer (pdfium)", "tesseract": "Tesseract jpn+eng",
              "vlm": "VLM", "router": "Router"}.get(c["parser"], c["parser"])
    extractor = "rules (regex)" if c["extractor"] == "rules" else (c.get("llm") or "LLM")
    label = f"{parser} + {extractor}"
    variants = c["dataset"].get("variants") or []
    full = max((r["config"]["dataset"]["n_docs"] / max(len(r["config"]["dataset"].get("variants") or [1]), 1) for r in runs or [run]), default=0)
    per_variant = c["dataset"]["n_docs"] / max(len(variants), 1)
    if per_variant < full:
        label += f" (sample: {c['dataset']['n_docs']} docs)"
    elif len(variants) == 1:
        label += f" ({variants[0]} only)"
    return label


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
        rows.append(f"| {name_of(r, runs)} | {where(r)} | {fmt(s.get('clean', {}).get('field_f1'))} | "
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
        rows.append(f"| {name_of(r, runs)} | {e['predicted']} | {e['wrong']} | {pct(e['hallucination_catch_rate'])} | "
                    f"{pct(e['false_alarm_rate'])} | {e['docs_with_a_wrong_value']} | {pct(e['wrong_docs_caught_by_either'])} |")
    return head + "\n".join(rows)


def field_table(runs: list[dict]) -> str:
    """Per-field exact match, one row per run and slice (clean / scanned): averaging the two would hide what each parser can read."""
    fields = next((list(r["summary"]["all"]["field_accuracy_by_field"]) for r in runs), [])
    head = "| Run | Slice | " + " | ".join(fields) + " |\n|---|---|" + "---|" * len(fields) + "\n"
    rows = []
    for r in runs:
        for variant in ("clean", "scanned"):
            acc = r["summary"].get(variant, {}).get("field_accuracy_by_field")
            if acc:
                rows.append(f"| {name_of(r, runs)} | {variant} | " + " | ".join(pct(acc.get(f)) for f in fields) + " |")
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


def headline(runs: list[dict]) -> str:
    """One sentence for the top of the README, from the LLM run with the most documents (ties: the best clean-slice F1)."""
    llm = [r for r in runs if r["config"]["extractor"] == "llm" and "scanned" in r["summary"] and "clean" in r["summary"]]
    if not llm:
        return "_Results are generated by `python eval/run_eval.py`; none have been run yet._"
    r = max(llm, key=lambda r: (r["summary"]["all"]["n_docs"], r["summary"]["clean"]["field_f1"]))
    a, e = r["summary"]["all"], r["summary"]["all"]["evidence"]
    return (f"On {a['n_docs']} synthetic Japanese invoices, {name_of(r, runs)} ({where(r)}) reached field F1 "
            f"**{r['summary']['clean']['field_f1']:.2f}** on clean PDFs and **{r['summary']['scanned']['field_f1']:.2f}** on scans. "
            f"It predicted {e['wrong']} wrong values out of {e['predicted']}: the evidence check flagged **{pct(e['hallucination_catch_rate'])}** of them, "
            f"and the evidence and arithmetic checks together flagged a problem in **{pct(e['wrong_docs_caught_by_either'])}** of the "
            f"{e['docs_with_a_wrong_value']} documents that contained a wrong value.")


def write_into(readme: Path, tables: str, block: str = "results") -> None:
    text = readme.read_text(encoding="utf-8")
    pattern = re.compile(rf"(<!-- {block}:start -->).*?(<!-- {block}:end -->)", re.S)
    if not pattern.search(text):
        sys.exit(f"{readme} has no <!-- {block}:start --> ... <!-- {block}:end --> block")
    readme.write_text(pattern.sub(lambda m: f"{m.group(1)}\n{tables}\n{m.group(2)}", text), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=RESULTS)
    ap.add_argument("--write", type=Path, help="README to update in place")
    args = ap.parse_args()
    runs = load(args.results)
    tables = render(runs, args.results)
    if args.write:
        write_into(args.write, tables)
        if "<!-- headline:start -->" in args.write.read_text(encoding="utf-8"):
            write_into(args.write, headline(runs), "headline")
        print(f"updated {args.write}")
    else:
        print(tables)


if __name__ == "__main__":
    main()
