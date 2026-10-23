"""The fixture space end to end: walk, parse, relations, claims, compare, re-ingest."""
from backend import compare
from backend.ingest import ingest
from backend.schemas import Claim, Document, Relation
from backend.search import load_index
from tests.conftest import SPACE


def test_walk_parse_and_metadata(ingested):
    db, _, log = ingested
    docs = {d.id: d for d in db.models(Document, "SELECT data FROM documents")}
    assert set(docs) == {"papers-2026_client_selection", "papers-2025_fairness_survey", "drafts-problem_formulation_v1",
                         "drafts-problem_formulation_v2", "supervisor-feedback_2026-09"}
    cs = docs["papers-2026_client_selection"]
    assert cs.title == "Joint Client Selection and Resource Allocation for Federated Learning"
    assert (cs.folder, cs.year, cs.file_type) == ("papers", 2026, "md")
    assert docs["drafts-problem_formulation_v2"].version_label == "v2"
    assert "parse: 5 parsed, skipped 0 unchanged" in log


def test_relations(ingested):
    db, _, _ = ingested
    rels = {(r.type, r.source_id, r.target_id): r for r in db.models(Relation, "SELECT data FROM relations")}
    assert ("supersedes", "drafts-problem_formulation_v2", "drafts-problem_formulation_v1") in rels
    cites = rels[("cites", "papers-2025_fairness_survey", "papers-2026_client_selection")]
    assert "Joint Client Selection" in cites.evidence
    assert ("feedback_on", "supervisor-feedback_2026-09", "drafts-problem_formulation_v2") in rels
    assert ("feedback_on", "supervisor-feedback_2026-09", "drafts-problem_formulation_v1") not in rels


def test_claims_verified_against_the_document(ingested):
    db, _, _ = ingested
    claims = db.models(Claim, "SELECT data FROM claims")
    assert {c.doc_id.split("-")[0] for c in claims} == {"papers", "drafts"}  # not supervisor/notes
    by_type = {c.claim_type: c for c in claims if c.doc_id == "papers-2026_client_selection"}
    assert by_type["contribution"].verification == "verified" and by_type["contribution"].element_id
    assert by_type["limitation"].verification == "unverified"


def test_reingest_skips_unchanged(ingested):
    db, results, _ = ingested
    log = ingest(db, SPACE, results)
    assert "parse: 0 parsed, skipped 5 unchanged" in log
    assert "chunk: 0 documents" in log and "embed: 0 documents" in log


def test_compare_drafts(ingested, monkeypatch):
    db, results, _ = ingested
    monkeypatch.setattr(compare, "MATCH", 0.3)  # hashed bag-of-words is much less similar than BGE-M3
    index = load_index(db, "thesis", results)
    rows = compare.compare(index.docs["drafts-problem_formulation_v1"], index.docs["drafts-problem_formulation_v2"], index)
    changes = [(r.change, (r.b or r.a).section_path) for r in rows]
    assert ("unchanged", "2 Objective") in changes
    assert ("added", "3 Client state") in changes
    fairness = next(r for r in rows if (r.b or r.a).section_path == "1 Fairness")
    assert fairness.change == "modified" and fairness.summary == "Redefined fairness."
    assert fairness.b.quote_match == 1.0 and "fairness debt" in fairness.b.text
