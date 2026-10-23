"""Hybrid search over one space: dense (BGE-M3) + BM25, fused with Reciprocal Rank Fusion, then filtered."""
import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from backend.db import DB, read_emb
from backend.schemas import Chunk, Document, Element, Filters

MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")  # EMBED_MODEL=intfloat/multilingual-e5-small if CPU is too slow
RRF_K = 60
POOL = 50  # candidates per retriever before fusion


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL)


def embed(texts: list[str]) -> np.ndarray:
    """L2-normalised float32 rows."""
    return _model().encode(texts, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)


def _prefix(kind: str) -> str:
    return f"{kind}: " if "e5" in MODEL else ""  # e5 needs 'query: ' / 'passage: '; BGE-M3 needs nothing


def embed_query(q: str) -> np.ndarray:
    return embed([_prefix("query") + q])[0]


def passage(c: Chunk, title: str) -> str:
    return _prefix("passage") + "\n".join(p for p in (title, c.section_path, c.text) if p)


def terms(s: str) -> list[str]:
    """Latin words + CJK character bigrams (Japanese has no spaces)."""
    s = unicodedata.normalize("NFKC", s).casefold()
    out = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", s)
    for run in re.findall(r"[぀-ヿ一-鿿]+", s):
        out += [run[i:i + 2] for i in range(max(len(run) - 1, 1))]
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = np.array([len(d) for d in docs], dtype=np.float32)
        self.avg = float(self.len.mean()) if len(docs) else 0.0
        df = Counter(t for d in self.tf for t in d)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(len(self.tf), dtype=np.float32)
        norm = self.k1 * (1 - self.b + self.b * self.len / (self.avg or 1))
        for t in set(query):
            if t not in self.idf:
                continue
            f = np.array([tf.get(t, 0) for tf in self.tf], dtype=np.float32)
            out += self.idf[t] * f * (self.k1 + 1) / (f + norm)
        return out


def rrf(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking):
            fused[i] = fused.get(i, 0.0) + 1 / (k + rank + 1)
    return fused


@dataclass
class Hit:
    chunk: Chunk
    score: float  # dense cosine, used for confidence
    fused: float


@dataclass
class Index:
    """Everything search needs for one space, held in memory.

    ponytail: brute-force numpy + in-memory BM25, fine for a few thousand chunks; Qdrant (dense + sparse) at ~100k.
    """
    chunks: list[Chunk]
    matrix: np.ndarray  # one row per chunk
    docs: dict[str, Document]
    elements: dict[str, dict[str, Element]]  # doc_id → element_id → Element (quotes are checked against these)

    def __post_init__(self):
        self.bm25 = BM25([terms(c.text) for c in self.chunks])
        self.row = {c.id: i for i, c in enumerate(self.chunks)}
        self.by_doc: dict[str, list[Chunk]] = {}
        for c in self.chunks:
            self.by_doc.setdefault(c.doc_id, []).append(c)

    def allowed(self, f: Filters) -> np.ndarray:
        ok = np.ones(len(self.chunks), dtype=bool)
        for i, c in enumerate(self.chunks):
            d = self.docs[c.doc_id]
            ok[i] = ((not f.folders or d.folder in f.folders) and (not f.doc_ids or d.id in f.doc_ids)
                     and (not f.years or d.year in f.years))
        return ok

    def search(self, query: str, filters: Filters = Filters(), k: int = 8) -> tuple[list[Hit], np.ndarray]:
        """Top-k hits plus the dense score of every chunk (expand.py reuses it)."""
        if not self.chunks:
            return [], np.zeros(0, dtype=np.float32)
        dense = self.matrix @ embed_query(query)
        sparse = self.bm25.scores(terms(query))
        ok = self.allowed(filters)
        dense_rank = [int(i) for i in np.argsort(-dense) if ok[i]][:POOL]
        sparse_rank = [int(i) for i in np.argsort(-sparse) if ok[i] and sparse[i] > 0][:POOL]
        fused = rrf([dense_rank, sparse_rank])
        # a reranker would go here; add one if recall@5 on the QA set is low
        top = sorted(fused, key=fused.get, reverse=True)[:k]
        return [Hit(self.chunks[i], float(dense[i]), fused[i]) for i in top], dense


def load_index(db: DB, space_id: str, results) -> Index:
    """Documents without embeddings yet are left out of search (their chunks have no rows)."""
    docs = {d.id: d for d in db.models(Document, "SELECT data FROM documents WHERE space_id=? ORDER BY id", (space_id,))}
    chunks, rows = [], []
    for doc_id in docs:
        m = read_emb(results, doc_id)
        cs = db.models(Chunk, "SELECT data FROM chunks WHERE doc_id=? ORDER BY seq", (doc_id,))
        if m is not None and len(m) == len(cs):
            chunks += cs
            rows.append(m)
    elements = {d: {e.id: e for e in db.models(Element, "SELECT data FROM elements WHERE doc_id=? ORDER BY seq", (d,))}
                for d in docs}
    matrix = np.vstack(rows) if rows else np.zeros((0, 1), dtype=np.float32)
    return Index(chunks=chunks, matrix=matrix, docs=docs, elements=elements)
