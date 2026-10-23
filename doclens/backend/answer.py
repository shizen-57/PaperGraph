"""Cross-document cited Q&A. The LLM writes the answer and one quote per citation; verify.py checks everything."""
import json
import re
import time
import uuid

from pydantic import ValidationError

from backend import llm, verify
from backend.expand import expand
from backend.norm import norm
from backend.schemas import Answer, AnswerOut, Citation, Filters, Relation
from backend.search import Index

SYSTEM = """You are a research assistant answering questions over a collection of documents \
(research papers, the user's own drafts, supervisor feedback and notes).

Rules:
1. Use ONLY the numbered sources given.
2. If the sources are insufficient, answer exactly: Insufficient evidence.
3. Cite every factual statement with its source number in square brackets, e.g. [2] or [1][4].
4. Do not invent page numbers, authors, titles or claims. Copy numbers exactly as they appear.
5. For every source number you cite, give one short quote copied EXACTLY from that source.
6. If sources disagree, say so instead of picking one."""

INSUFFICIENT = "Insufficient evidence."


def crop_url(doc_id: str, el_id: str, type_: str) -> str | None:
    return f"/crops/{doc_id}/{el_id}.png" if type_ in ("figure", "chart") else None


def answer(question: str, index: Index, relations: list[Relation], filters: Filters = Filters(), k: int = 8) -> Answer:
    t0 = time.perf_counter()
    hits, dense = index.search(question, filters, k)
    ctx, path = expand(hits, dense, index, relations, filters) if hits else ([], [])

    def done(text, citations, unverified, conf, label) -> Answer:
        return Answer(
            id=uuid.uuid4().hex[:12], question=question, answer=text, confidence=conf, confidence_label=label,
            citations=citations, unverified_numbers=unverified,
            approximate=any(c.type == "chart" for c in citations), used_chunk_ids=[c.id for c in ctx],
            relationship_path=path, latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    if not ctx:
        return done(INSUFFICIENT, [], [], 0.0, "Insufficient")

    sources = "\n\n".join(
        f"[{n}] {index.docs[c.doc_id].title} ({index.docs[c.doc_id].folder}), page {c.page_start}"
        f"{' — ' + c.section_path if c.section_path else ''}\n{c.text}"
        for n, c in enumerate(ctx, 1)
    )
    raw = llm.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": f"Sources:\n{sources}\n\nQuestion: {question}"}],
        schema=AnswerOut.model_json_schema(), max_tokens=1500,
    )
    try:
        out = AnswerOut.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError):  # server ignored the schema: keep the text, no quotes to check
        out = AnswerOut(answer=raw.strip(), citations=[])

    if norm(out.answer).startswith(norm(INSUFFICIENT)):
        return done(out.answer, [], [], 0.0, "Insufficient")

    quotes: dict[int, str] = {}
    for q in out.citations:
        quotes.setdefault(q.n, q.quote)
    markers = [int(n) for n in re.findall(r"\[(\d+)\]", out.answer)]
    cited = [n for n in dict.fromkeys(markers) if 1 <= n <= len(ctx)]

    citations = []
    for n in cited:
        c = ctx[n - 1]
        els = [index.elements[c.doc_id][i] for i in c.element_ids]
        chk = verify.locate(quotes.get(n, ""), els)
        el = index.elements[c.doc_id].get(chk.element_id) if chk.element_id else els[0]
        citations.append(Citation(
            n=n, chunk_id=c.id, document_id=c.doc_id, document_title=index.docs[c.doc_id].title,
            page=el.page, element_id=el.id, bbox=el.bbox, type=el.type, quote=quotes.get(n, ""),
            quote_match=chk.score, verification="verified" if chk.found else "unverified",
            crop_url=crop_url(c.doc_id, el.id, el.type), table=el.table,
        ))

    unverified = verify.check_numbers(out.answer, [ctx[c.n - 1].text for c in citations])
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
    conf, label = verify.confidence({
        "retrieval": mean([verify.rescale_cos(float(dense[index.row[c.chunk_id]])) for c in citations]),
        "quote": mean([c.quote_match for c in citations]),
        "citations": sum(1 <= n <= len(ctx) for n in markers) / len(markers) if markers else 0.0,
        "numbers": 0.0 if unverified else 1.0,
        "coverage": verify.coverage(out.answer),
    })
    return done(out.answer, citations, unverified, conf, label)
