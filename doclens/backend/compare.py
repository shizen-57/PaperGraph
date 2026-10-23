"""Compare two documents (typically draft v1 and v2) passage by passage, with evidence on both sides."""
import json

import numpy as np
from pydantic import ValidationError

from backend import llm, verify
from backend.norm import norm
from backend.schemas import ChangeOut, Chunk, CompareRow, Document, Side
from backend.search import Index

MATCH = 0.75  # below this two passages are not the same passage
SAME = 0.97  # at or above this they count as unchanged
MAX_LLM = 25  # ponytail: caps LLM calls per comparison; later modified rows get no summary

SYSTEM = (
    "You compare two versions of a passage from a research document. In one sentence, say what changed "
    "(ideas added, removed or redefined; ignore wording-only edits). Then copy one short quote EXACTLY from "
    "version A and one from version B that show the change."
)


def _side(c: Chunk, index: Index, quote: str = "") -> Side:
    els = [index.elements[c.doc_id][i] for i in c.element_ids]
    chk = verify.locate(quote, els) if quote else None
    el = index.elements[c.doc_id][chk.element_id] if chk and chk.element_id else els[0]
    return Side(doc_id=c.doc_id, chunk_id=c.id, page=el.page, section_path=c.section_path, text=c.text,
                quote=quote, quote_match=chk.score if chk else 0.0, element_id=el.id, bbox=el.bbox)


def _summarise(a: Chunk, b: Chunk) -> ChangeOut | None:
    raw = llm.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": f"Version A:\n{a.text}\n\nVersion B:\n{b.text}"}],
        schema=ChangeOut.model_json_schema(), max_tokens=400,
    )
    try:
        return ChangeOut.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError):
        return None


def compare(a: Document, b: Document, index: Index) -> list[CompareRow]:
    ca, cb = index.by_doc.get(a.id, []), index.by_doc.get(b.id, [])
    pairs: list[tuple[int, int, float]] = []
    if ca and cb:
        sims = index.matrix[[index.row[c.id] for c in ca]] @ index.matrix[[index.row[c.id] for c in cb]].T
        used_a, used_b = set(), set()
        for flat in np.argsort(-sims, axis=None):  # greedy best-first matching
            i, j = np.unravel_index(int(flat), sims.shape)
            if sims[i, j] < MATCH:
                break
            if i not in used_a and j not in used_b:
                used_a.add(i)
                used_b.add(j)
                pairs.append((int(i), int(j), float(sims[i, j])))

    keyed: list[tuple[float, CompareRow]] = []
    llm_ok, calls = True, 0
    for i, j, sim in pairs:
        if sim >= SAME or norm(ca[i].text) == norm(cb[j].text):
            keyed.append((j, CompareRow(change="unchanged", a=_side(ca[i], index), b=_side(cb[j], index),
                                        similarity=round(sim, 3), summary=None)))
            continue
        out = None
        if llm_ok and calls < MAX_LLM:
            calls += 1
            try:
                out = _summarise(ca[i], cb[j])
            except llm.LLMUnavailable:
                llm_ok = False  # still return the aligned passages, just without summaries
        keyed.append((j, CompareRow(
            change="modified", a=_side(ca[i], index, out.quote_a if out else ""),
            b=_side(cb[j], index, out.quote_b if out else ""), similarity=round(sim, 3),
            summary=out.summary if out else None,
        )))

    a_to_b = {i: j for i, j, _ in pairs}
    for i, c in enumerate(ca):  # removed passages sit after the B row their predecessor matched
        if i not in a_to_b:
            prev = max((p for p in a_to_b if p < i), default=None)
            keyed.append(((a_to_b[prev] if prev is not None else -1) + 0.5,
                          CompareRow(change="removed", a=_side(c, index), b=None, similarity=None, summary=None)))
    matched_b = set(a_to_b.values())
    for j, c in enumerate(cb):
        if j not in matched_b:
            keyed.append((j, CompareRow(change="added", a=None, b=_side(c, index), similarity=None, summary=None)))
    return [row for _, row in sorted(keyed, key=lambda kr: kr[0])]
