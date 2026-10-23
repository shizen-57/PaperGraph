import pytest
from fastapi.testclient import TestClient

from backend import llm
from backend.app import create_app
from tests.conftest import SPACE


@pytest.fixture
def client(tmp_path, fakes):
    c = TestClient(create_app(results=tmp_path / "results", cache=tmp_path / "cache", default=SPACE))
    job = c.post("/spaces/thesis/ingest").json()  # background tasks run before the test client returns
    assert c.get(f"/jobs/{job['id']}").json()["status"] == "done"
    return c


def test_space_summary(client):
    s = client.get("/spaces/thesis").json()
    assert s["counts"]["documents"] == 5 and s["counts"]["chunks"] > 5 and s["counts"]["relations"] >= 3
    assert s["folders"] == {"drafts": 2, "papers": 2, "supervisor": 1}
    assert s["last_job"]["status"] == "done"


def test_documents_and_detail(client):
    docs = client.get("/spaces/thesis/documents").json()
    assert len(docs) == 5
    d = client.get("/documents/papers-2026_client_selection").json()
    assert d["file_url"] == "/files/papers-2026_client_selection"
    assert any(e["type"] == "table" and e["table"]["header"] == ["method", "accuracy"] for e in d["elements"])
    assert d["claims"] == 2 and d["verified_claims"] == 1
    assert client.get("/files/papers-2026_client_selection").status_code == 200


def test_ask_across_documents(client):
    a = client.post("/spaces/thesis/ask", json={"question": "Which papers jointly optimize client selection and resource allocation?"}).json()
    c1, c2 = a["citations"]
    assert c1["verification"] == "verified" and c1["quote_match"] == 1.0 and c1["document_id"] and c1["document_title"]
    assert c2["verification"] == "unverified"  # the invented quote
    assert a["unverified_numbers"] == ["999"]
    assert a["confidence_label"] in ("High", "Medium", "Low", "Unverified") and a["latency_ms"] >= 0
    assert client.get(f"/answers/{a['id']}").json()["question"] == a["question"]
    assert client.get("/spaces/thesis").json()["recent"][0]["id"] == a["id"]


def test_ask_filters_to_one_folder(client):
    r = client.post("/spaces/thesis/search", json={"query": "fairness", "filters": {"folders": ["drafts"]}}).json()
    assert r and all(h["chunk"]["doc_id"].startswith("drafts-") for h in r)


def test_compare_endpoint(client):
    r = client.post("/spaces/thesis/compare", json={"doc_a": "drafts-problem_formulation_v1",
                                                    "doc_b": "drafts-problem_formulation_v2"}).json()
    assert r["a"]["version_label"] == "v1" and {row["change"] for row in r["rows"]} & {"unchanged", "added"}


def test_graph(client):
    g = client.get("/spaces/thesis/graph").json()
    assert len(g["nodes"]) == 5 and {e["type"] for e in g["edges"]} >= {"supersedes", "cites", "feedback_on"}


def test_errors(client, monkeypatch):
    assert client.get("/documents/nope").status_code == 404
    assert client.get("/spaces/nope").status_code == 404
    assert client.post("/spaces/thesis/ask", json={"question": ""}).status_code == 422

    def down(*a, **kw):
        raise llm.LLMUnavailable("LLM unreachable — check LLM_BASE_URL")
    monkeypatch.setattr(llm, "chat", down)
    r = client.post("/spaces/thesis/ask", json={"question": "anything"})
    assert r.status_code == 503 and "LLM_BASE_URL" in r.json()["detail"]


def test_crop_needs_a_pdf_element(client):
    assert client.get("/crops/papers-2026_client_selection/e0.png").status_code == 404  # md has no boxes
