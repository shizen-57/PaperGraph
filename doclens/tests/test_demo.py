import json

from backend import demo
from backend.db import DB
from backend.schemas import Extraction


def test_demo_seed_parses_extracts_and_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("PARSER", "pdfium")  # no Docling needed
    db = DB(tmp_path / "doclens.db")
    ids = demo.seed(db, tmp_path / "space", names=["clean/clean-000", "scanned/scan-000"])
    assert ids == ["invoices-clean-000"]  # the scan has no text layer: parsed, but nothing to extract
    ex = db.one(Extraction, "SELECT data FROM extractions WHERE doc_id=?", ("invoices-clean-000",))
    gt = json.loads((demo.SYNTH / "clean" / "clean-000.json").read_text(encoding="utf-8"))
    assert {f.name: f.value for f in ex.fields}["total"] == gt["fields"]["total"]
    assert db.rows("SELECT COUNT(*) FROM documents")[0][0] == 2
    demo.seed(db, tmp_path / "space", names=["clean/clean-000"])  # re-seeding replaces, never duplicates
    assert db.rows("SELECT COUNT(*) FROM extractions")[0][0] == 1
