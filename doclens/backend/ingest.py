"""Ingest a space folder: walk → parse → (vlm) → chunk → embed → relations → claims.

    python -m backend.ingest data/space                       # default space "thesis"
    python -m backend.ingest data/space --stages claims       # force-rerun one stage for every document
    python -m backend.ingest data/space --stages vlm,chunk,embed   # VLM pass over figures (needs a VLM)

Resumable: a document's file hash decides whether it is re-parsed, and each document remembers which later
stages finished (Document.stages_done), so a crash in `embed` doesn't mean re-parsing every PDF.
Stage timings go to results/speed.json.
"""
import argparse
import time
from collections.abc import Callable
from pathlib import Path

from backend import chunk, claims, llm, offline, parse, relations, search, vlm
from backend.db import DB, RESULTS, dump, emb_path, read_json, write_emb, write_json
from backend.schemas import Chunk, Document, Element, Space
from backend.walk import SourceFile, walk

PER_DOC = ["vlm", "chunk", "embed", "claims"]  # vlm only runs when asked for
DEFAULT = ["parse", "chunk", "embed", "relations", "claims"]

Report = Callable[[str, float, str], None]  # (stage, progress 0..1, message)


def ensure_space(db: DB, space: Space) -> None:
    db.exec("INSERT OR REPLACE INTO spaces VALUES (?, ?)", (space.id, dump(space)))


def save_doc(db: DB, d: Document) -> None:
    db.exec("INSERT OR REPLACE INTO documents VALUES (?, ?, ?)", (d.id, d.space_id, dump(d)))


def save_elements(db: DB, doc_id: str, els: list[Element]) -> None:
    db.exec("DELETE FROM elements WHERE doc_id=?", (doc_id,))
    db.exec("INSERT INTO elements VALUES (?, ?, ?, ?)", [(doc_id, e.id, i, dump(e)) for i, e in enumerate(els)], many=True)


def delete_doc(db: DB, results: Path, doc_id: str) -> None:
    for table in ("documents", "elements", "chunks", "claims", "extractions"):
        db.exec(f"DELETE FROM {table} WHERE {'id' if table == 'documents' else 'doc_id'}=?", (doc_id,))
    emb_path(results, doc_id).unlink(missing_ok=True)


def elements_of(db: DB, doc_id: str) -> list[Element]:
    return db.models(Element, "SELECT data FROM elements WHERE doc_id=? ORDER BY seq", (doc_id,))


def parse_file(f: SourceFile, space_id: str) -> tuple[Document, list[Element]]:
    els, sizes, title = parse.parse_path(f.path, f.doc_id, f.file_type)
    text = " ".join(e.text for e in els[:200])
    doc = Document(
        id=f.doc_id, space_id=space_id, title=title or f.path.stem.replace("_", " "), path=f.rel, folder=f.folder,
        file_type=f.file_type, file_hash=f.sha256, lang=parse.lang_of(text), pages=max(len(sizes), 1),
        page_sizes=sizes, year=f.year, version_label=f"v{f.version}" if f.version else None, stages_done=["parse"],
    )
    return doc, els


def run_stage(db: DB, results: Path, space: Space, stage: str, docs: list[Document], force: bool, report: Report) -> str:
    """Runs one per-document stage. Returns a one-line summary."""
    todo = [d for d in docs if force or stage not in d.stages_done]
    if stage == "claims":
        todo = [d for d in todo if d.folder in claims.FOLDERS]
    for n, d in enumerate(todo):
        report(stage, n / max(len(todo), 1), d.path)
        if stage == "vlm":
            if d.file_type != "pdf":
                continue
            els = vlm.vlm_doc(elements_of(db, d.id), Path(space.root) / d.path)
            save_elements(db, d.id, els)
            d.stages_done = [s for s in d.stages_done if s not in ("chunk", "embed")]  # figure text changed
        elif stage == "chunk":
            cs = chunk.chunk_doc(elements_of(db, d.id))
            db.exec("DELETE FROM chunks WHERE doc_id=?", (d.id,))
            db.exec("INSERT INTO chunks VALUES (?, ?, ?, ?)", [(c.id, d.id, c.seq, dump(c)) for c in cs], many=True)
            d.stages_done = [s for s in d.stages_done if s != "embed"]
        elif stage == "embed":
            cs = db.models(Chunk, "SELECT data FROM chunks WHERE doc_id=? ORDER BY seq", (d.id,))
            if cs:
                write_emb(results, d.id, search.embed([search.passage(c, d.title) for c in cs]))
        elif stage == "claims":
            try:
                found = claims.extract_claims(d, elements_of(db, d.id))
            except llm.LLMUnavailable as e:
                return f"claims skipped: {e}"  # documents stay marked as not done, so the next run retries
            db.exec("DELETE FROM claims WHERE doc_id=?", (d.id,))
            db.exec("INSERT INTO claims VALUES (?, ?, ?)", [(c.id, d.id, dump(c)) for c in found], many=True)
        d.stages_done = [s for s in d.stages_done if s != stage] + [stage]
        save_doc(db, d)
    return f"{stage}: {len(todo)} documents"


def ingest(db: DB, space: Space, results: Path = RESULTS, force: list[str] | None = None,
           report: Report = lambda stage, p, msg: None) -> list[str]:
    force = force or []
    stages = [s for s in ["parse", "vlm", "chunk", "embed", "relations", "claims"] if s in DEFAULT or s in force]
    ensure_space(db, space)
    log, speed = [], read_json(results / "speed.json", {})
    files = walk(Path(space.root))
    known = {d.id: d for d in db.models(Document, "SELECT data FROM documents WHERE space_id=?", (space.id,))}

    for gone in set(known) - {f.doc_id for f in files}:
        delete_doc(db, results, gone)
        log.append(f"removed {gone}")

    for stage in stages:
        t = time.perf_counter()
        docs = db.models(Document, "SELECT data FROM documents WHERE space_id=? ORDER BY id", (space.id,))
        if stage == "parse":
            parsed = skipped = pages = 0
            for n, f in enumerate(files):
                report("parse", n / max(len(files), 1), f.rel)
                old = known.get(f.doc_id)
                if old and old.file_hash == f.sha256 and "parse" not in force:
                    skipped += 1
                    continue
                doc, els = parse_file(f, space.id)
                save_elements(db, doc.id, els)
                db.exec("DELETE FROM claims WHERE doc_id=?", (doc.id,))
                db.exec("DELETE FROM extractions WHERE doc_id=?", (doc.id,))  # boxes and element ids changed
                save_doc(db, doc)
                parsed += 1
                pages += doc.pages
            log.append(f"parse: {parsed} parsed, skipped {skipped} unchanged")
        elif stage == "relations":
            report("relations", 0.0, "building")
            index = search.load_index(db, space.id, results)
            rels = relations.build(docs, index)
            db.exec("DELETE FROM relations WHERE space_id=?", (space.id,))
            db.exec("INSERT INTO relations VALUES (?, ?, ?, ?, ?)",
                    [(r.id, space.id, r.source_id, r.target_id, dump(r)) for r in rels], many=True)
            log.append(f"relations: {len(rels)}")
            pages = None
        else:
            log.append(run_stage(db, results, space, stage, docs, stage in force, report))
            pages = sum(d.pages for d in docs)
        secs = time.perf_counter() - t
        speed[stage] = {"seconds": round(secs, 1), "pages": pages,
                        "sec_per_page": round(secs / pages, 2) if pages else None}
    write_json(results / "speed.json", speed)
    report("done", 1.0, "; ".join(log))
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="the space folder, e.g. data/space")
    ap.add_argument("--space", default="thesis")
    ap.add_argument("--name", default="Thesis research")
    ap.add_argument("--stages", default="", help="comma-separated stages to force-rerun: parse,vlm,chunk,embed,relations,claims")
    args = ap.parse_args()
    offline.enforce()
    db = DB(RESULTS / "doclens.db")
    space = Space(id=args.space, name=args.name, root=str(args.root.resolve()))
    for line in ingest(db, space, force=[s for s in args.stages.split(",") if s],
                       report=lambda stage, p, msg: print(f"[{stage} {p:4.0%}] {msg}")):
        print(line)


if __name__ == "__main__":
    main()
