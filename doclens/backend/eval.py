"""Metrics. Only numbers produced here go in the README.

    python -m backend.eval answers   # answers every question in labels/qa.jsonl → results/answers.jsonl (needs the LLM)
    python -m backend.eval           # → results/eval.json

labels/qa.jsonl, one question per line:
    {"id": "q1", "question": "...", "expected_documents": ["papers-..."], "expected_pages": [4],
     "required_quote": "jointly optimize client selection"}      # expected_pages and required_quote are optional
Answer faithfulness is graded by hand in labels/answer_grades.csv (question_id,grade = correct / partly / wrong).
"""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

from backend import answer
from backend.db import DB, LABELS, RESULTS, read_json, write_json
from backend.norm import norm
from backend.schemas import Claim, Relation
from backend.search import Index, load_index


def read_qa(labels: Path) -> list[dict]:
    path = labels / "qa.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_answers(results: Path) -> list[dict]:
    path = results / "answers.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def supports(doc_id: str, page_start: int, page_end: int, q: dict) -> bool:
    """Is this (document, page range) one of the gold sources for question q?"""
    pages = q.get("expected_pages") or []
    return doc_id in q["expected_documents"] and (not pages or any(page_start <= p <= page_end for p in pages))


def rate(hits: list[bool]) -> float | None:
    return sum(hits) / len(hits) if hits else None


def p95(xs: list[float]) -> float | None:
    return sorted(xs)[math.ceil(0.95 * len(xs)) - 1] if xs else None


def answer_all(index: Index, rels: list[Relation], results: Path, labels: Path) -> int:
    lines = []
    for q in read_qa(labels):
        a = answer.answer(q["question"], index, rels)
        cited = [index.chunks[index.row[c.chunk_id]] for c in a.citations]
        lines.append(json.dumps({
            "id": q["id"], "question": q["question"], "answer": a.answer, "confidence": a.confidence,
            "confidence_label": a.confidence_label, "latency_ms": a.latency_ms,
            "unverified_numbers": a.unverified_numbers,
            "citations": [{"document_id": c.document_id, "page": c.page, "verification": c.verification,
                           "quote_match": c.quote_match} for c in a.citations],
            "required_quote_found": (norm(q["required_quote"]) in norm(" ".join(c.text for c in cited))
                                     if q.get("required_quote") else None),
        }, ensure_ascii=False))
    (results / "answers.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    grades = labels / "answer_grades.csv"
    if not grades.exists():  # template for hand grading
        grades.write_text("question_id,grade\n" + "".join(f"{json.loads(l)['id']},\n" for l in lines), encoding="utf-8")
    return len(lines)


def run_eval(db: DB, space_id: str, results: Path, labels: Path) -> dict:
    index = load_index(db, space_id, results)
    qa = {q["id"]: q for q in read_qa(labels)}

    recall = []
    for q in qa.values():
        hits, _ = index.search(q["question"], k=5)
        recall.append(any(supports(h.chunk.doc_id, h.chunk.page_start, h.chunk.page_end, q) for h in hits))

    answers = [a for a in read_answers(results) if a["id"] in qa]
    cits = [(c, qa[a["id"]]) for a in answers for c in a["citations"]]
    claims = db.models(Claim, "SELECT c.data FROM claims c JOIN documents d ON d.id = c.doc_id WHERE d.space_id=?", (space_id,))

    grades = Counter()
    if (labels / "answer_grades.csv").exists():
        with open(labels / "answer_grades.csv", encoding="utf-8") as f:
            grades = Counter(r["grade"].strip() for r in csv.DictReader(f) if r["grade"].strip())

    latency = [a["latency_ms"] for a in answers]
    out = {
        "search": {"recall_at_5": rate(recall), "n": len(recall)},
        "citations": {
            "validity": rate([supports(c["document_id"], c["page"], c["page"], q) for c, q in cits]),
            "quote_support": rate([c["verification"] == "verified" for c, _ in cits]),
            "n": len(cits),
        },
        "answers": {
            "numeric_consistency": rate([not a["unverified_numbers"] for a in answers]),
            "required_quote": rate([a["required_quote_found"] for a in answers if a["required_quote_found"] is not None]),
            "latency_ms": {"mean": round(sum(latency) / len(latency)) if latency else None, "p95": p95(latency)},
            "n": len(answers),
            "grades": dict(grades),  # hand-graded faithfulness
        },
        "claims": {"quote_verified": rate([c.verification == "verified" for c in claims]), "n": len(claims)},
        "corpus": {"documents": len(index.docs), "chunks": len(index.chunks)},
        "speed": read_json(results / "speed.json", {}),
    }
    write_json(results / "eval.json", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", nargs="?", choices=["answers", "metrics"], default="metrics")
    ap.add_argument("--space", default="thesis")
    args = ap.parse_args()
    db = DB(RESULTS / "doclens.db")
    if args.step == "answers":
        rels = db.models(Relation, "SELECT data FROM relations WHERE space_id=?", (args.space,))
        n = answer_all(load_index(db, args.space, RESULTS), rels, RESULTS, LABELS)
        print(f"answered {n} questions; grade them in {LABELS / 'answer_grades.csv'}")
    else:
        print(json.dumps(run_eval(db, args.space, RESULTS, LABELS), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
