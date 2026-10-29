import json

import pytest
from fastapi.testclient import TestClient

from backend import extract, llm
from backend.app import create_app
from tests.conftest import SPACE

SYNTH = __import__("pathlib").Path(__file__).parent.parent / "eval" / "data" / "synth"


@pytest.fixture
def client(tmp_path, fakes, monkeypatch):
    monkeypatch.setenv("PARSER", "pdfium")  # no Docling needed
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "demo-run.json").write_text(json.dumps({"config": {"parser": "pdfium"}, "summary": {"all": {"field_f1": 0.5}}, "documents": [{"id": "x"}]}))
    (eval_dir / "not-a-run.json").write_text(json.dumps({"hello": 1}))
    c = TestClient(create_app(results=tmp_path / "results", cache=tmp_path / "cache", default=SPACE, eval_dir=eval_dir))
    job = c.post("/spaces/thesis/ingest").json()
    assert c.get(f"/jobs/{job['id']}").json()["status"] == "done"
    return c


def upload(path):
    return {"file": (path.name, path.read_bytes(), "application/pdf")}


def test_parse_returns_elements_with_boxes(client):
    r = client.post("/parse", files=upload(SYNTH / "clean" / "clean-000.pdf")).json()
    assert r["parser"] == "pdfium" and r["pages"] == 1 and any("請求書番号" in e["text"] for e in r["elements"])
    assert all(e["bbox"]["x1"] > e["bbox"]["x0"] for e in r["elements"])


def test_extract_with_the_rules_extractor(client):
    gt = json.loads((SYNTH / "clean" / "clean-000.json").read_text(encoding="utf-8"))
    r = client.post("/extract?type=invoice&extractor=rules", files=upload(SYNTH / "clean" / "clean-000.pdf")).json()
    fields = {f["name"]: f for f in r["fields"]}
    assert fields["total"]["value"] == gt["fields"]["total"] and fields["total"]["status"] == "verified"
    assert fields["total"]["page"] == 1 and fields["total"]["bbox"] is not None and r["model"] == "rules"
    assert {c["status"] for c in r["checks"]} == {"pass"}


def test_extract_with_the_llm_extractor(client, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "fake")
    monkeypatch.setattr(extract, "ask_llm", lambda doc_type, els: extract.InvoiceOut(
        **{k: extract.Cited(value=None, quote="", element_id="") for k in extract.Invoice.model_fields},
        line_items=[]))
    r = client.post("/extract?type=invoice", files=upload(SYNTH / "clean" / "clean-000.pdf")).json()
    assert {f["status"] for f in r["fields"]} == {"missing"} and r["model"] == "fake"


def test_errors(client, monkeypatch):
    assert client.post("/parse", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert client.post("/extract?type=nope", files=upload(SYNTH / "clean" / "clean-000.pdf")).status_code == 422
    assert client.post("/extract?type=spec_sheet&extractor=rules", files=upload(SYNTH / "clean" / "clean-000.pdf")).status_code == 422
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(llm.LLMUnavailable("LLM_MODEL is not set")))
    r = client.post("/extract?type=invoice", files=upload(SYNTH / "clean" / "clean-000.pdf"))
    assert r.status_code == 503 and "LLM_MODEL" in r.json()["detail"]
    monkeypatch.setattr(extract, "ask_llm", lambda *a: (_ for _ in ()).throw(extract.ExtractionError("bad json")))
    monkeypatch.setenv("LLM_MODEL", "fake")
    assert client.post("/extract?type=invoice", files=upload(SYNTH / "clean" / "clean-000.pdf")).status_code == 502


def test_stored_extraction_for_a_document(client):
    doc = "papers-2026_client_selection"
    assert client.get(f"/documents/{doc}/extraction").status_code == 404
    r = client.post(f"/documents/{doc}/extract?type=invoice&extractor=rules")
    assert r.status_code == 200 and r.json()["doc_id"] == doc
    assert client.get(f"/documents/{doc}/extraction").json()["doc_type"] == "invoice"
    assert client.get("/documents/nope/extraction").status_code == 404


def test_eval_endpoints(client):
    runs = client.get("/eval").json()
    assert [r["name"] for r in runs] == ["demo-run"] and runs[0]["summary"]["all"]["field_f1"] == 0.5 and "documents" not in runs[0]
    assert client.get("/eval/demo-run").json()["documents"] == [{"id": "x"}]
    assert client.get("/eval/missing").status_code == 404
    assert client.get("/eval/..%2Fsecret").status_code == 404


def test_ask_alias_uses_the_default_space(client):
    r = client.post("/ask", json={"question": "Which papers jointly optimize client selection?"})
    assert r.status_code == 200 and r.json()["citations"]
