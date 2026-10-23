"""Deterministic document relations. Every edge stores the evidence it was built from.

supersedes   problem_formulation_v2 → problem_formulation_v1 (same folder and name, higher version)
cites        a paper's reference list contains another document's title
same_topic   document embeddings are close (each document keeps its 2 nearest, above a floor)
feedback_on  a supervisor/ file names a draft
"""
from pathlib import PurePosixPath

import numpy as np

from backend.claims import REFS
from backend.norm import norm
from backend.schemas import Document, Relation
from backend.search import Index
from backend.walk import _VERSION

SAME_TOPIC_MIN = 0.75
SAME_TOPIC_PER_DOC = 2
MIN_TITLE = 15  # shorter titles match by accident


def _rel(type_, src: str, tgt: str, evidence: str, confidence: float) -> Relation:
    return Relation(id=f"{type_}:{src}->{tgt}", source_id=src, target_id=tgt, type=type_,
                    evidence=evidence, confidence=round(confidence, 3))


def _short(s: str, n: int = 160) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "…"


def supersedes(docs: list[Document]) -> list[Relation]:
    groups: dict[tuple[str, str], list[tuple[int, Document]]] = {}
    for d in docs:
        stem = PurePosixPath(d.path).stem
        if m := _VERSION.search(stem):
            groups.setdefault((d.folder, stem[:m.start()].lower()), []).append((int(m.group(1)), d))
    out = []
    for versions in groups.values():
        versions.sort(key=lambda v: v[0])
        for (_, old), (_, new) in zip(versions, versions[1:]):
            out.append(_rel("supersedes", new.id, old.id, f"{new.path} is a later version of {old.path}", 1.0))
    return out


def cites(docs: list[Document], index: Index) -> list[Relation]:
    out = []
    for d in docs:
        refs = [e for e in index.elements.get(d.id, {}).values() if REFS.search(e.heading or "")]
        for o in docs:
            t = norm(o.title)
            if o.id == d.id or len(t) < MIN_TITLE:
                continue
            hit = next((e for e in refs if t in norm(e.text)), None)
            if hit:
                out.append(_rel("cites", d.id, o.id, f"Reference list, page {hit.page}: “{_short(hit.text)}”", 1.0))
    return out


def same_topic(docs: list[Document], index: Index) -> list[Relation]:
    ids = [d.id for d in docs if index.by_doc.get(d.id)]
    if len(ids) < 2:
        return []
    rows = {d: [index.row[c.id] for c in index.by_doc[d]] for d in ids}
    cent = np.stack([index.matrix[rows[d]].mean(axis=0) for d in ids])
    cent /= np.linalg.norm(cent, axis=1, keepdims=True)
    sims = cent @ cent.T
    np.fill_diagonal(sims, -1)
    pairs = set()
    for i in range(len(ids)):
        for j in np.argsort(-sims[i])[:SAME_TOPIC_PER_DOC]:
            if sims[i, j] >= SAME_TOPIC_MIN:
                pairs.add((min(i, j), max(i, j)))
    out = []
    for i, j in sorted(pairs):
        a, b = ids[i], ids[j]
        pair = index.matrix[rows[a]] @ index.matrix[rows[b]].T
        x, y = np.unravel_index(int(np.argmax(pair)), pair.shape)
        ca, cb = index.by_doc[a][x], index.by_doc[b][y]
        out.append(_rel("same_topic", a, b, f"Closest passages: “{_short(ca.text)}” ↔ “{_short(cb.text)}”",
                        float(sims[i, j])))
    return out


def feedback_on(docs: list[Document], index: Index) -> list[Relation]:
    drafts = [d for d in docs if d.folder == "drafts"]
    out = []
    for s in (d for d in docs if d.folder == "supervisor"):
        for d in drafts:
            names = [n for n in (norm(PurePosixPath(d.path).stem), norm(d.title)) if len(n) >= 8]
            hit = next((e for e in index.elements.get(s.id, {}).values() if any(n in norm(e.text) for n in names)), None)
            if hit:
                out.append(_rel("feedback_on", s.id, d.id, f"Page {hit.page}: “{_short(hit.text)}”", 1.0))
    return out


def build(docs: list[Document], index: Index) -> list[Relation]:
    return supersedes(docs) + cites(docs, index) + same_topic(docs, index) + feedback_on(docs, index)
