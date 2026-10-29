import json

from backend import demo
from backend.db import DB
from backend.schemas import Extraction


def test_demo_seed_parses_extracts_and_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("PARSER", "pdfium")  # no Docling needed
    db = DB(tmp_path / "doclens.db")
    ids = demo.seed(db, tmp_path / "space", names=["synth/clean/clean-000", "synth/scanned/scan-000"])
    assert ids == ["invoices-clean-000"]  # the scan has no text layer: parsed, but nothing to extract
    ex = db.one(Extraction, "SELECT data FROM extractions WHERE doc_id=?", ("invoices-clean-000",))
    gt = json.loads((demo.DATA / "synth" / "clean" / "clean-000.json").read_text(encoding="utf-8"))
    assert {f.name: f.value for f in ex.fields}["total"] == gt["fields"]["total"]
    assert db.rows("SELECT COUNT(*) FROM documents")[0][0] == 2
    demo.seed(db, tmp_path / "space", names=["synth/clean/clean-000"])  # re-seeding replaces, never duplicates
    assert db.rows("SELECT COUNT(*) FROM extractions")[0][0] == 1


def test_demo_seeds_an_english_invoice(tmp_path, monkeypatch):
    monkeypatch.setenv("PARSER", "pdfium")
    db = DB(tmp_path / "doclens.db")
    assert demo.seed(db, tmp_path / "space", names=["intl/en/en-000"]) == ["invoices-en-000"]
    ex = db.one(Extraction, "SELECT data FROM extractions WHERE doc_id=?", ("invoices-en-000",))
    gt = json.loads((demo.DATA / "intl" / "en" / "en-000.json").read_text(encoding="utf-8"))
    values = {f.name: f.value for f in ex.fields}
    assert values["total"] == gt["fields"]["total"] and values["issue_date"] == gt["fields"]["issue_date"]
    assert db.rows("SELECT json_extract(data, '$.lang') FROM documents")[0][0] == "en"
