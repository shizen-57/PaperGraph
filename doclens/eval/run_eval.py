"""Run one configuration (parser + extractor) over the eval set and write per-document results and a summary.

    python eval/run_eval.py --parser pdfium --extractor rules --out eval/results/pdfium-rules.json
    python eval/run_eval.py --parser docling --extractor llm --llm $LLM_MODEL --out eval/results/docling-qwen.json
    python eval/run_eval.py --parser docling --extractor rules --reuse-parse ...   # replay parse output (and its timings) from a cache

The data is eval/data/synth/{clean,scanned}/*.pdf with ground truth beside each file (eval/synth/generate.py).
Speed: the first document is parsed once untimed (model load), then every parse is timed. Nothing is estimated.
Then `python eval/render_tables.py` turns the results into the Markdown tables used in the README.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import extract, extract_rules, llm, offline, parse  # noqa: E402
from backend.schemas import Element, Extraction  # noqa: E402
from eval import metrics  # noqa: E402

DATA = ROOT / "eval" / "data" / "synth"
CACHE = ROOT / "eval" / ".cache"


def hardware() -> dict:
    cpu = next((ln.split(":", 1)[1].strip() for ln in Path("/proc/cpuinfo").read_text().splitlines()
                if ln.startswith("model name")), platform.processor()) if Path("/proc/cpuinfo").exists() else platform.processor()
    gpu = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    return {"cpu": cpu, "cores": os.cpu_count(), "gpu": gpu}


def versions(parser: str) -> str | None:
    from importlib import metadata
    pkg = {"docling": "docling", "pdfium": "pypdfium2", "tesseract": "pytesseract"}.get(parser)
    try:
        v = metadata.version(pkg) if pkg else None
    except metadata.PackageNotFoundError:
        return None
    if parser == "tesseract":
        v = f"pytesseract {v}, " + subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    return v


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def sample_vram(device: int, stop: threading.Event, peak: list[int]) -> None:
    """Poll nvidia-smi for the memory in use on one GPU. Needed when the model runs in a separate vLLM server:
    torch in this process can't see it. The figure includes whatever the server reserved (weights + KV cache)."""
    while not stop.is_set():
        try:
            out = subprocess.run(["nvidia-smi", f"--id={device}", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=5).stdout
            peak[0] = max(peak[0], int(out.strip().splitlines()[0]))
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
        stop.wait(0.5)


def documents(data: Path, variants: list[str], limit: int | None) -> list[Path]:
    out = []
    for v in variants:
        out += sorted((data / v).glob("*.pdf"))[:limit]
    return out


def parse_one(parser: str, pdf: Path, reuse: bool):
    """(elements, sizes, seconds). With reuse, the cached output and the seconds measured when it was produced."""
    key = CACHE / parser / f"{pdf.stem}.json"
    if reuse and key.exists():
        d = json.loads(key.read_text(encoding="utf-8"))
        return [Element.model_validate(e) for e in d["elements"]], d["sizes"], d["seconds"]
    t = time.perf_counter()
    elements, sizes, _ = parse.PARSERS[parser](pdf, pdf.stem)
    seconds = time.perf_counter() - t
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps({"elements": [e.model_dump() for e in elements], "sizes": sizes, "seconds": seconds},
                              ensure_ascii=False), encoding="utf-8")
    return elements, sizes, seconds


def empty(doc_id: str, why: str) -> Extraction:
    return Extraction(doc_id=doc_id, doc_type="invoice", fields=[], checks=[], model=why, seconds=0)


def run_doc(pdf: Path, args, vram) -> dict:
    gt = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    elements, sizes, parse_s = parse_one(args.parser, pdf, args.reuse_parse)
    error = None
    t = time.perf_counter()
    try:
        if not elements:  # nothing was parsed (e.g. a text-layer parser on a scan): no LLM call on an empty document
            ex, error = empty(pdf.stem, "no text parsed"), "no text parsed"
        else:
            ex = (extract_rules.extract if args.extractor == "rules" else extract.extract)(pdf.stem, "invoice", elements)
    except (llm.LLMUnavailable, extract.ExtractionError) as e:  # a failed extraction scores as all-missing
        error, ex = f"{type(e).__name__}: {e}"[:300], empty(pdf.stem, "error")
    extract_s = time.perf_counter() - t
    pred, gold = extract.to_values(ex.fields), metrics.gt_values(gt)
    items_html = metrics.items_table_html(elements)
    tp, n_pred, n_gold = metrics.prf(metrics.pairs(pred), metrics.pairs(gold))
    return {
        "id": pdf.stem, "variant": gt["variant"], "layout": gt["layout"], "pages": len(sizes),
        "parse_seconds": round(parse_s, 3), "extract_seconds": round(extract_s, 3), "n_elements": len(elements),
        "tp": tp, "n_pred": n_pred, "n_gold": n_gold, "correct": metrics.field_correct(pred, gold),
        "teds": metrics.teds(items_html, gt["table_html"]), "table_found": items_html is not None,
        "judge": metrics.judge(ex, gold), "pred": pred, "gold": gold, "checks": [c.model_dump() for c in ex.checks],
        "fields": [{"name": f.name, "raw": f.raw, "status": f.status, "quote_match": f.quote_match,
                    "value_in_quote": f.value_in_quote, "quote": f.quote[:200], "page": f.page} for f in ex.fields],
        "error": error,
    }


def summarise(rows: list[dict], gpu_hourly_usd: float | None, on_gpu: bool, peak_vram_mb: float | None) -> dict:
    if not rows:
        return {}
    tp, n_pred, n_gold = (sum(r[k] for r in rows) for k in ("tp", "n_pred", "n_gold"))
    fields = rows[0]["correct"].keys()
    acc = {f: metrics.mean([float(r["correct"][f]) for r in rows]) for f in fields}
    pages = sum(r["pages"] for r in rows)
    parse_s, extract_s = sum(r["parse_seconds"] for r in rows), sum(r["extract_seconds"] for r in rows)
    sec_per_page = parse_s / pages
    out = {
        "n_docs": len(rows), "errors": sum(bool(r["error"]) for r in rows),
        "field_f1": round(metrics.f1(tp, n_pred, n_gold) or 0.0, 4), "field_accuracy": metrics.mean(list(acc.values())),
        "field_accuracy_by_field": acc, "docs_all_fields_correct": sum(all(r["correct"].values()) for r in rows),
        "evidence": metrics.evidence_summary([r["judge"] for r in rows]),
        "teds": metrics.mean([r["teds"] for r in rows]), "table_found_rate": metrics.rate(sum(r["table_found"] for r in rows), len(rows)),
        "parse": {"seconds": round(parse_s, 2), "pages": pages, "pages_per_sec": round(pages / parse_s, 3) if parse_s else None,
                  "sec_per_page": round(sec_per_page, 3)},
        "extract": {"seconds": round(extract_s, 2), "sec_per_doc": round(extract_s / len(rows), 3)},
        "peak_vram_mb": peak_vram_mb,
        "cost_per_1k_pages_parse_usd": (metrics.cost_per_1k_pages(sec_per_page, gpu_hourly_usd)
                                        if on_gpu and gpu_hourly_usd else None),
    }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parser", choices=sorted(parse.PARSERS), required=True)
    ap.add_argument("--extractor", choices=["rules", "llm"], required=True)
    ap.add_argument("--llm", help="sets LLM_MODEL (and is recorded in the results)")
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--variants", default="clean,scanned")
    ap.add_argument("--limit", type=int, help="documents per variant (smoke tests)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--vram-device", type=int, action="append", default=[],
                    help="GPU index to sample with nvidia-smi (for models served by vLLM); repeatable, the peaks are summed")
    ap.add_argument("--reuse-parse", action="store_true", help="replay cached parse output and its recorded timings")
    ap.add_argument("--note", action="append", default=[], help="free text stored with the results; repeatable")
    args = ap.parse_args()
    if args.llm:
        os.environ["LLM_MODEL"] = args.llm
    offline.enforce()

    hw = hardware()
    docs = documents(args.data, args.variants.split(","), args.limit)
    if not docs:
        sys.exit(f"no documents under {args.data}: run python -m eval.synth.generate")
    vram = None
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            vram = torch
    except ImportError:
        pass
    if not args.reuse_parse and args.parser in ("docling", "router"):  # in-process models: their load must not count towards pages/sec
        parse.PARSERS[args.parser](docs[0], "warmup")

    stop = threading.Event()
    smi_peaks = {d: [0] for d in args.vram_device}
    samplers = [threading.Thread(target=sample_vram, args=(d, stop, smi_peaks[d]), daemon=True) for d in args.vram_device]
    for t in samplers:
        t.start()
    rows = []
    for i, pdf in enumerate(docs, 1):
        rows.append(run_doc(pdf, args, vram))
        r = rows[-1]
        print(f"[{i}/{len(docs)}] {pdf.stem}: parse {r['parse_seconds']}s, extract {r['extract_seconds']}s, "
              f"F1 {metrics.f1(r['tp'], r['n_pred'], r['n_gold'])}{'  ERROR ' + r['error'] if r['error'] else ''}", flush=True)

    stop.set()
    smi = sum(p[0] for p in smi_peaks.values()) or None
    torch_peak = round(vram.cuda.max_memory_allocated() / 2**20) if vram else None
    peak = smi if smi else torch_peak
    vram_source = (f"nvidia-smi memory.used on GPU {args.vram_device} (includes vLLM's reserved KV cache)" if smi
                   else "torch.cuda.max_memory_allocated in the eval process" if torch_peak else None)
    usd = float(os.environ["GPU_HOURLY_USD"]) if os.environ.get("GPU_HOURLY_USD") else None
    summary = {v: summarise([r for r in rows if r["variant"] == v], usd, bool(hw["gpu"]), peak) for v in args.variants.split(",")}
    summary["all"] = summarise(rows, usd, bool(hw["gpu"]), peak)
    result = {
        "config": {
            "name": args.out.stem, "parser": args.parser, "parser_version": versions(args.parser), "extractor": args.extractor,
            "llm": os.environ.get("LLM_MODEL") if args.extractor == "llm" else None,
            "vlm": os.environ.get("VLM_MODEL") if args.parser in ("vlm", "router") else None,
            "hardware": hw, "gpu_hourly_usd": usd if hw["gpu"] else None, "reuse_parse": args.reuse_parse,
            "vram_source": vram_source,
            "dataset": {"path": str(args.data.relative_to(ROOT)) if args.data.is_relative_to(ROOT) else str(args.data),
                        "n_docs": len(docs), "variants": args.variants.split(",")},
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "git_commit": git_commit(), "notes": args.note,
        },
        "summary": summary, "documents": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")
    for v, s in summary.items():
        print(f"{v:8} F1 {s['field_f1']}  acc {s['field_accuracy']}  verified {s['evidence']['verified_rate']}  "
              f"catch {s['evidence']['hallucination_catch_rate']}  TEDS {s['teds']}  {s['parse']['pages_per_sec']} pages/s")


if __name__ == "__main__":
    main()
