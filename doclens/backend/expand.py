"""Graph expansion: widen the retrieved context with neighbouring chunks and the best chunk of related documents."""
import numpy as np

from backend.schemas import Chunk, Filters, Relation
from backend.search import Hit, Index

MAX_EXPANDED = 6  # added on top of the 8 retrieved chunks...
MAX_CONTEXT = 12  # ...but the prompt never gets more than 12 sources


def expand(hits: list[Hit], dense: np.ndarray, index: Index, relations: list[Relation],
           filters: Filters = Filters()) -> tuple[list[Chunk], list[str]]:
    """Returns the context chunks (hits first) and a readable path for every relation that was used."""
    ctx = [h.chunk for h in hits]
    seen = {c.id for c in ctx}
    ok = index.allowed(filters)
    hit_docs = {c.doc_id for c in ctx}
    related, neighbours, path = [], [], []

    for r in relations:  # related documents first: they are what single-document RAG can't find
        if (r.source_id in hit_docs) == (r.target_id in hit_docs):
            continue  # both already in context, or neither
        other = r.target_id if r.source_id in hit_docs else r.source_id
        cands = [c for c in index.by_doc.get(other, []) if ok[index.row[c.id]] and c.id not in seen]
        if not cands:
            continue
        best = max(cands, key=lambda c: dense[index.row[c.id]])
        related.append(best)
        seen.add(best.id)
        path.append(f"{index.docs[r.source_id].title} —{r.type}→ {index.docs[r.target_id].title}")

    for c in ctx[:3]:
        for seq in (c.seq - 1, c.seq + 1):
            cid = f"{c.doc_id}:c{seq}"
            if cid in index.row and cid not in seen and ok[index.row[cid]]:
                neighbours.append(index.chunks[index.row[cid]])
                seen.add(cid)

    extra = (related + neighbours)[:MAX_EXPANDED]
    return (ctx + extra)[:MAX_CONTEXT], path
