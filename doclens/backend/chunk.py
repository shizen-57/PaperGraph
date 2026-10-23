"""Structure-aware chunking: paragraphs merged within a section, split only at paragraph boundaries;
tables and figures stay whole; a new section always starts a new chunk."""
import re

from backend.schemas import Chunk, Element

MAX_TOKENS = 350
_TOKEN = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9]")


def tokens(s: str) -> int:
    # ponytail: words + single non-space symbols (so each CJK character counts 1); a real tokenizer if budgets get tight
    return len(_TOKEN.findall(s))


def chunk_doc(elements: list[Element]) -> list[Chunk]:
    chunks: list[Chunk] = []
    buf: list[Element] = []

    def emit(els: list[Element]):
        doc_id = els[0].doc_id
        chunks.append(Chunk(
            id=f"{doc_id}:c{len(chunks)}", doc_id=doc_id, seq=len(chunks),
            page_start=min(e.page for e in els), page_end=max(e.page for e in els),
            section_path=els[0].heading or "", text="\n\n".join(e.text for e in els),
            element_ids=[e.id for e in els],
        ))

    def flush():
        if buf:
            emit(buf[:])
            buf.clear()

    for el in elements:
        if el.type == "caption":  # already part of its figure's / table's text
            continue
        if buf and el.heading != buf[0].heading:
            flush()
        if el.type in ("table", "figure", "chart"):
            flush()
            if el.text.strip():
                emit([el])
            continue
        if buf and sum(tokens(e.text) for e in buf) + tokens(el.text) > MAX_TOKENS:
            last = buf[-1]
            flush()
            if tokens(last.text) < MAX_TOKENS // 2:  # one paragraph of overlap keeps context across the split
                buf.append(last)
        buf.append(el)
    flush()
    return chunks
