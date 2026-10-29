import json

from eval import render_tables as rt


def run(parser="docling", extractor="rules", clean=0.9, scanned=0.4, gpu=None):
    ev = {"predicted": 100, "wrong": 10, "hallucination_catch_rate": 0.5, "false_alarm_rate": 0.1,
          "docs_with_a_wrong_value": 4, "wrong_docs_caught_by_either": 0.75}
    return {"_stem": f"{parser}-{extractor}",
            "config": {"parser": parser, "extractor": extractor, "llm": None, "hardware": {"gpu": gpu, "cores": 4, "cpu": "x"},
                       "dataset": {"n_docs": 24}},
            "summary": {"clean": {"field_f1": clean, "field_accuracy_by_field": {"total": 0.8, "tax": 1.0}},
                        "scanned": {"field_f1": scanned, "field_accuracy_by_field": {"total": 0.4, "tax": 0.5}},
                        "all": {"teds": 0.95, "n_docs": 24, "parse": {"pages_per_sec": 0.17, "seconds": 48.0}, "extract": {"seconds": 24.0},
                                "peak_vram_mb": None, "evidence": ev,
                                "cost_per_1k_pages_parse_usd": None, "field_accuracy_by_field": {"total": 0.8, "tax": 1.0}}}}


def test_numbers_come_from_the_results_and_missing_ones_are_dashes():
    t = rt.arena_table([run()])
    assert "| Docling + rules (regex) | CPU, 4 cores | 0.90 | 0.40 | 0.95 | 0.17 | 3.0 | — | — |" in t


def test_unrun_gpu_configurations_are_marked_not_run():
    t = rt.arena_table([run()])
    assert "PaddleOCR-VL" in t and t.count("not run") >= 3 * 7
    have = [run("vlm", "llm", gpu="Tesla T4") | {"_stem": "qwen-vl-qwen2.5-7b"}]
    assert "Qwen2.5-VL-7B zero-shot" not in rt.arena_table(have)  # a result file replaces its pending row


def test_evidence_and_field_tables():
    assert "| 50% | 10% | 4 | 75% |" in rt.evidence_table([run()])
    t = rt.field_table([run()])
    assert "| Docling + rules (regex) | clean | 80% | 100% |" in t and "| scanned | 40% | 50% |" in t


def test_write_into_replaces_only_the_marked_block(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("before\n<!-- results:start -->\nold\n<!-- results:end -->\nafter\n", encoding="utf-8")
    rt.write_into(readme, "NEW TABLE")
    assert readme.read_text(encoding="utf-8") == "before\n<!-- results:start -->\nNEW TABLE\n<!-- results:end -->\nafter\n"


def test_load_skips_non_run_files(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"summary": {}, "config": {}}))
    (tmp_path / "b.json").write_text(json.dumps([1, 2]))
    assert [r["_stem"] for r in rt.load(tmp_path)] == ["a"]


def test_other_result_shapes_and_their_not_run_notices(tmp_path):
    assert "Not run yet" in rt.chart_section([]) and "Not run yet" in rt.direct_section([]) and "Not run yet" in rt.router_section([])
    chart = {"config": {"vlm": "vlm-x"}, "chart_summary": {k: {"n": 6, "valid_rate": 1.0, "mean_relative_error": e, "coverage": 0.9}
                                                           for k, e in (("all", 0.12), ("with_data_labels", 0.02), ("without_data_labels", 0.22))}}
    assert "| vlm-x | 6 | 100% | 12.0% | 2.0% | 22.0% | 90% |" in rt.chart_section([chart])
    direct = {"config": {"model": "invoice-lora"}, "direct_summary": {
        "clean": {"field_f1": 0.9}, "scanned": {"field_f1": 0.7},
        "all": {"valid_json_rate": 1.0, "docs_all_fields_correct": 10, "n_docs": 24, "docs_failing_an_arithmetic_check": 3, "seconds_per_doc": 4.2}}}
    assert "| invoice-lora | 100% | 0.90 | 0.70 | 10/24 | 3 | 4.2 |" in rt.direct_section([direct])
    router = {"router_summary": {"all": {"pages": 24, "correct": 24, "reasons": {"scanned": 12}},
                                 "clean": {"pages": 12, "to_vlm": 0}, "scanned": {"pages": 12, "to_vlm": 12}}}
    assert "12/12 scanned pages" in rt.router_section([router]) and "0/12 clean pages" in rt.router_section([router])


def test_render_lists_missing_gpu_work_as_not_run(tmp_path):
    out = rt.render([run()], tmp_path)
    assert "Exact-match accuracy per field" not in out and "Why values are wrong" in rt.render([run()], tmp_path, full=True)
    assert out.count("Not run yet") == 4 and "**Router (F2)**" in out and "**PowerPoint input (F5)**" in out


def test_deck_section():
    deck = {"deck_summary": {"decks": 2, "slides": 6, "fact_recall": 1.0, "cell_recall": 0.9}}
    assert "**100% of key facts** and **90% of table cells**" in rt.deck_section([deck]) and "Not run yet" in rt.deck_section([])


def test_headline_comes_from_the_llm_run(tmp_path):
    assert "none have been run" in rt.headline([run()])  # rules only: no LLM run to quote
    llm = run("docling", "llm")
    llm["config"]["llm"] = "qwen-x"
    llm["summary"]["all"]["n_docs"] = 24
    llm["summary"]["all"]["evidence"] |= {"wrong": 67, "predicted": 316, "docs_with_a_wrong_value": 24}
    text = rt.headline([run(), llm])
    assert "24 synthetic Japanese invoices" in text and "qwen-x" in text and "**0.90**" in text and "**0.40**" in text
    assert "predicted 67 wrong values out of 316" in text and "**50%**" in text and "**75%**" in text
    readme = tmp_path / "R.md"
    readme.write_text("a <!-- headline:start -->x<!-- headline:end --> b")
    rt.write_into(readme, "H", "headline")
    assert readme.read_text() == "a <!-- headline:start -->\nH\n<!-- headline:end --> b"


def test_sample_and_single_variant_runs_are_labelled():
    full = run()
    full["config"]["dataset"] = {"n_docs": 24, "variants": ["clean", "scanned"]}
    sample = run("vlm", "llm")
    sample["config"]["dataset"] = {"n_docs": 6, "variants": ["clean", "scanned"]}
    clean_only = run("pdfium", "rules")
    clean_only["config"]["dataset"] = {"n_docs": 12, "variants": ["clean"]}
    runs = [full, sample, clean_only]
    assert rt.name_of(full, runs) == "Docling + rules (regex)"
    assert rt.name_of(sample, runs).endswith("(sample: 6 docs)")
    assert rt.name_of(clean_only, runs).endswith("(clean only)")


def test_same_documents_table_rescoring_other_runs_on_the_sample():
    def doc(i, variant, tp):
        return {"id": i, "variant": variant, "tp": tp, "n_pred": 10, "n_gold": 10, "pages": 1, "parse_seconds": 2.0, "extract_seconds": 3.0}
    full = run()
    full["config"]["dataset"] = {"n_docs": 4, "variants": ["clean", "scanned"]}
    full["documents"] = [doc("clean-0", "clean", 9), doc("clean-1", "clean", 1), doc("scan-0", "scanned", 5), doc("scan-1", "scanned", 5)]
    sample = run("vlm", "llm")
    sample["config"]["dataset"] = {"n_docs": 2, "variants": ["clean", "scanned"]}
    sample["documents"] = [doc("clean-0", "clean", 6), doc("scan-0", "scanned", 4)]
    t = rt.same_documents_table([full, sample])
    assert "clean-0, scan-0" in t and "| Docling + rules (regex) | 0.90 | 0.50 | 2.00 | 3.0 |" in t and "(sample: 2 docs) | 0.60 | 0.40 |" in t
    assert rt.same_documents_table([full]) == ""


def test_small_numbers_keep_their_digits_and_the_vlm_is_named():
    assert rt.fmt(0.004) == "0.004" and rt.fmt(0.0) == "0.00" and rt.fmt(0.17) == "0.17"
    v = run("vlm", "llm")
    v["config"]["vlm"] = "qwen-vl-x"
    assert rt.name_of(v).startswith("VLM (qwen-vl-x) + ")
