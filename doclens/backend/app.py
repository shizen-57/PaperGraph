"""FastAPI app over the SQLite store. Run: uvicorn backend.app:app --port 8000"""
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend import answer, compare, extract, llm, offline, parse
from backend.crops import render_crop
from backend.db import DB, RESULTS, ROOT, dump, read_json
from backend.ingest import elements_of, ensure_space, ingest
from backend.schemas import (Answer, AskRequest, Claim, CompareRequest, CompareResult, Document, DocumentDetail,
                             DocumentSummary, DocType, Element, Extraction, Job, ParseResult, Relation, SearchHit,
                             SearchRequest, Space, SpaceSummary)
from backend.search import Index, load_index
from backend.walk import SUPPORTED

DEFAULT_SPACE = Space(id="thesis", name="Thesis research", root=str(ROOT / "data" / "space"))
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def create_app(results: Path = RESULTS, cache: Path = ROOT / ".cache" / "crops", default: Space | None = DEFAULT_SPACE,
               eval_dir: Path = ROOT / "eval" / "results") -> FastAPI:
    offline.enforce()  # OFFLINE=1: no network beyond this machine and the LAN
    db = DB(results / "doclens.db")
    if default and not db.rows("SELECT 1 FROM spaces WHERE id=?", (default.id,)):
        ensure_space(db, default)
    indexes: dict[str, Index] = {}  # rebuilt lazily after each ingest
    # /docs was the old document route; Swagger stays at /swagger so the frontend proxy paths don't move
    app = FastAPI(title="DocLens", docs_url="/swagger", swagger_ui_oauth2_redirect_url="/swagger/oauth2-redirect")

    def space_of(space_id: str) -> Space:
        s = db.one(Space, "SELECT data FROM spaces WHERE id=?", (space_id,))
        if s is None:
            raise HTTPException(404, f"Unknown space: {space_id}")
        return s

    def index_of(space_id: str) -> Index:
        if space_id not in indexes:
            indexes[space_id] = load_index(db, space_id, results)
        return indexes[space_id]

    def doc_of(doc_id: str) -> Document:
        d = db.one(Document, "SELECT data FROM documents WHERE id=?", (doc_id,))
        if d is None:
            raise HTTPException(404, f"Unknown document: {doc_id}")
        return d

    def relations_of(space_id: str) -> list[Relation]:
        return db.models(Relation, "SELECT data FROM relations WHERE space_id=?", (space_id,))

    def summarise(d: Document, rels: list[Relation]) -> DocumentSummary:
        verified = db.rows("SELECT COUNT(*), SUM(json_extract(data, '$.verification')='verified') FROM claims WHERE doc_id=?", (d.id,))[0]
        return DocumentSummary(**d.model_dump(), claims=verified[0], verified_claims=verified[1] or 0,
                               relations=sum(d.id in (r.source_id, r.target_id) for r in rels))

    def save_job(job: Job) -> None:
        db.exec("INSERT OR REPLACE INTO jobs VALUES (?, ?, COALESCE((SELECT created FROM jobs WHERE id=?), ?), ?)",
                (job.id, job.space_id, job.id, time.time(), dump(job)))

    # --- spaces ---

    @app.get("/spaces", response_model=list[Space])
    def list_spaces():
        return db.models(Space, "SELECT data FROM spaces ORDER BY id")

    @app.post("/spaces", response_model=Space)
    def create_space(space: Space):
        # local-first tool: the root is any folder on this machine; uvicorn binds to localhost by default
        if not Path(space.root).is_dir():
            raise HTTPException(400, f"Not a folder: {space.root}")
        ensure_space(db, space)
        indexes.pop(space.id, None)
        return space

    @app.get("/spaces/{space_id}", response_model=SpaceSummary)
    def get_space(space_id: str):
        space = space_of(space_id)
        docs = db.models(Document, "SELECT data FROM documents WHERE space_id=?", (space_id,))
        ids = tuple(d.id for d in docs) or ("",)
        marks = ",".join("?" * len(ids))
        folders: dict[str, int] = {}
        for d in docs:
            folders[d.folder] = folders.get(d.folder, 0) + 1
        recent = [{"id": a.id, "question": a.question, "confidence_label": a.confidence_label}
                  for a in db.models(Answer, "SELECT data FROM answers WHERE space_id=? ORDER BY created DESC LIMIT 6", (space_id,))]
        return SpaceSummary(
            space=space, folders=folders, recent=recent,
            counts={"documents": len(docs),
                    "chunks": db.rows(f"SELECT COUNT(*) FROM chunks WHERE doc_id IN ({marks})", ids)[0][0],
                    "claims": db.rows(f"SELECT COUNT(*) FROM claims WHERE doc_id IN ({marks})", ids)[0][0],
                    "relations": len(relations_of(space_id))},
            last_job=db.one(Job, "SELECT data FROM jobs WHERE space_id=? ORDER BY created DESC LIMIT 1", (space_id,)),
        )

    @app.post("/spaces/{space_id}/documents/upload")
    async def upload_documents(space_id: str, files: list[UploadFile] = File(...)):
        space = space_of(space_id)
        if not files or len(files) > 10:
            raise HTTPException(400, "Choose between 1 and 10 files.")

        folder = Path(space.root) / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        staged: list[tuple[Path, Path]] = []
        saved: list[Path] = []
        reserved: set[str] = set()
        total = 0
        try:
            for upload in files:
                name = Path((upload.filename or "").replace("\\", "/")).name
                suffix = Path(name).suffix.lower()
                if not name or name.startswith(".") or suffix not in SUPPORTED:
                    raise HTTPException(400, "Supported files: PDF, PPTX, images, Markdown and plain text.")

                target_name = name
                while target_name in reserved or (folder / target_name).exists():
                    path = Path(name)
                    target_name = f"{path.stem}-{uuid.uuid4().hex[:8]}{path.suffix}"
                reserved.add(target_name)
                temporary = folder / f".{uuid.uuid4().hex}.upload"
                target = folder / target_name
                staged.append((temporary, target))

                size = 0
                with temporary.open("xb") as out:
                    while chunk := await upload.read(1024 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if total > MAX_UPLOAD_BYTES:
                            raise HTTPException(413, "Uploads must total 50 MB or less.")
                        out.write(chunk)
                if size == 0:
                    raise HTTPException(400, f"{name} is empty.")

            for temporary, target in staged:
                temporary.replace(target)
                saved.append(target)
            return {"files": [path.name for path in saved]}
        except Exception:
            for temporary, _ in staged:
                temporary.unlink(missing_ok=True)
            for path in saved:
                path.unlink(missing_ok=True)
            raise
        finally:
            for upload in files:
                await upload.close()

    @app.post("/spaces/{space_id}/ingest", response_model=Job)
    def start_ingest(space_id: str, tasks: BackgroundTasks, stages: str = ""):
        space = space_of(space_id)
        running = db.one(Job, "SELECT data FROM jobs WHERE space_id=? AND json_extract(data, '$.status') IN ('queued','running')", (space_id,))
        if running:
            return running
        job = Job(id=uuid.uuid4().hex[:12], space_id=space_id, status="queued")
        save_job(job)

        def run():
            def report(stage, progress, message):
                job.status, job.stage, job.progress, job.message = "running", stage, progress, message
                save_job(job)
            try:
                ingest(db, space, results, force=[s for s in stages.split(",") if s], report=report)
                job.status = "done"
            except Exception as e:  # the job record is the only place the frontend can see the failure
                job.status, job.message = "error", f"{type(e).__name__}: {e}"
            save_job(job)
            indexes.pop(space_id, None)

        tasks.add_task(run)
        return job

    @app.get("/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str):
        job = db.one(Job, "SELECT data FROM jobs WHERE id=?", (job_id,))
        if job is None:
            raise HTTPException(404, "Unknown job")
        return job

    @app.get("/spaces/{space_id}/documents", response_model=list[DocumentSummary])
    def list_documents(space_id: str):
        space_of(space_id)
        rels = relations_of(space_id)
        return [summarise(d, rels) for d in db.models(Document, "SELECT data FROM documents WHERE space_id=? ORDER BY id", (space_id,))]

    @app.get("/spaces/{space_id}/graph")
    def graph(space_id: str):
        return {"nodes": list_documents(space_id), "edges": relations_of(space_id)}

    # --- documents ---

    @app.get("/documents/{doc_id}", response_model=DocumentDetail)
    def get_document(doc_id: str):
        d = doc_of(doc_id)
        rels = [r for r in relations_of(d.space_id) if d.id in (r.source_id, r.target_id)]
        els = elements_of(db, doc_id)
        for e in els:
            e.crop_url = answer.crop_url(doc_id, e.id, e.type)
        return DocumentDetail(**summarise(d, rels).model_dump(), file_url=f"/files/{doc_id}", elements=els,
                              claim_list=db.models(Claim, "SELECT data FROM claims WHERE doc_id=? ORDER BY id", (doc_id,)),
                              relation_list=rels)

    @app.get("/documents/{doc_id}/relations", response_model=list[Relation])
    def document_relations(doc_id: str):
        d = doc_of(doc_id)
        return [r for r in relations_of(d.space_id) if doc_id in (r.source_id, r.target_id)]

    @app.get("/files/{doc_id}")
    def file(doc_id: str):
        # the path comes from the store, never from the request, so no traversal
        d = doc_of(doc_id)
        path = Path(space_of(d.space_id).root) / d.path
        if not path.exists():
            raise HTTPException(404, f"File missing on disk: {d.path}")
        return FileResponse(path)

    @app.get("/crops/{doc_id}/{element_id}.png")
    def crop(doc_id: str, element_id: str):
        d = doc_of(doc_id)
        el = next((e for e in elements_of(db, doc_id) if e.id == element_id), None)
        if el is None or el.bbox is None:
            raise HTTPException(404, "Unknown element")
        out = cache / doc_id / f"{element_id}.png"
        if not out.exists():
            pdf = Path(space_of(d.space_id).root) / d.path
            if not pdf.exists():
                raise HTTPException(404, f"File missing on disk: {d.path}")
            out.parent.mkdir(parents=True, exist_ok=True)
            render_crop(pdf, el.page, el.bbox).save(out)
        return FileResponse(out, media_type="image/png")

    # --- search, ask, compare ---

    @app.post("/spaces/{space_id}/search", response_model=list[SearchHit])
    def search(space_id: str, req: SearchRequest):
        space_of(space_id)
        index = index_of(space_id)
        hits, _ = index.search(req.query, req.filters, req.k)
        return [SearchHit(chunk=h.chunk, document_title=index.docs[h.chunk.doc_id].title, score=h.score) for h in hits]

    @app.post("/spaces/{space_id}/ask", response_model=Answer)
    def ask(space_id: str, req: AskRequest):
        space_of(space_id)
        index = index_of(space_id)
        if not index.chunks:
            raise HTTPException(409, "Nothing indexed yet: run the ingest (Space page, or python -m backend.ingest)")
        try:
            a = answer.answer(req.question, index, relations_of(space_id), req.filters)
        except llm.LLMUnavailable as e:
            raise HTTPException(503, str(e))
        db.exec("INSERT INTO answers VALUES (?, ?, ?, ?)", (a.id, space_id, time.time(), dump(a)))
        return a

    @app.get("/answers/{answer_id}", response_model=Answer)
    def get_answer(answer_id: str):
        a = db.one(Answer, "SELECT data FROM answers WHERE id=?", (answer_id,))
        if a is None:
            raise HTTPException(404, "Unknown answer")
        return a

    @app.post("/spaces/{space_id}/compare", response_model=CompareResult)
    def compare_docs(space_id: str, req: CompareRequest):
        space_of(space_id)
        a, b = doc_of(req.doc_a), doc_of(req.doc_b)
        return CompareResult(a=a, b=b, rows=compare.compare(a, b, index_of(space_id)))

    # --- parse + extract (the plan's /parse, /extract, /eval) ---

    def staged(file: UploadFile) -> tuple[Path, str]:
        """Save an upload to a temp file and return (path, file_type). The caller deletes the folder."""
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in SUPPORTED:
            raise HTTPException(400, f"Unsupported file type {suffix or '(none)'}: use PDF, PPTX, an image, .md or .txt.")
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        if not data or len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413 if data else 400, "Uploads must be non-empty and 50 MB or less.")
        path = Path(tempfile.mkdtemp(prefix="doclens-")) / f"upload{suffix}"
        path.write_bytes(data)
        return path, SUPPORTED[suffix]

    def parse_upload_sync(path: Path, file_type: str):
        try:
            return parse.parse_path(path, "upload", file_type)
        except parse.ParserUnavailable as e:
            raise HTTPException(501, str(e))

    def run_extraction(doc_id: str, doc_type: DocType, elements: list[Element], extractor: str) -> Extraction:
        try:
            if extractor == "rules":
                from backend import extract_rules
                return extract_rules.extract(doc_id, doc_type, elements)
            return extract.extract(doc_id, doc_type, elements)
        except llm.LLMUnavailable as e:
            raise HTTPException(503, str(e))
        except extract.ExtractionError as e:
            raise HTTPException(502, str(e))
        except NotImplementedError as e:
            raise HTTPException(422, str(e))

    @app.post("/parse", response_model=ParseResult)
    def parse_file(file: UploadFile = File(...)):  # def, not async: parsing is CPU-bound and runs in the threadpool
        path, file_type = staged(file)
        try:
            els, sizes, title = parse_upload_sync(path, file_type)
        finally:
            path.unlink(missing_ok=True)
        return ParseResult(parser=parse.default_parser(), title=title, pages=max(len(sizes), 1), page_sizes=sizes, elements=els)

    @app.post("/extract", response_model=Extraction)
    def extract_file(type: DocType = "invoice", extractor: Literal["llm", "rules"] = "llm", file: UploadFile = File(...)):
        """Parse an upload and extract `type` from it. Nothing is stored; /documents/{id}/extract keeps the result."""
        path, file_type = staged(file)
        try:
            els, _, _ = parse_upload_sync(path, file_type)
        finally:
            path.unlink(missing_ok=True)
        return run_extraction(Path(file.filename or "upload").stem, type, els, extractor)

    @app.post("/documents/{doc_id}/extract", response_model=Extraction)
    def extract_document(doc_id: str, type: DocType = "invoice", extractor: Literal["llm", "rules"] = "llm"):
        doc_of(doc_id)
        ex = run_extraction(doc_id, type, elements_of(db, doc_id), extractor)
        db.exec("INSERT OR REPLACE INTO extractions VALUES (?, ?)", (doc_id, dump(ex)))
        return ex

    @app.get("/documents/{doc_id}/extraction", response_model=Extraction)
    def get_extraction(doc_id: str):
        doc_of(doc_id)
        ex = db.one(Extraction, "SELECT data FROM extractions WHERE doc_id=?", (doc_id,))
        if ex is None:
            raise HTTPException(404, "Not extracted yet")
        return ex

    @app.get("/eval")
    def eval_runs():
        """Summaries of every run in eval/results/*.json (written by eval/run_eval.py). Per-document rows: /eval/{name}."""
        runs = []
        for f in sorted(eval_dir.glob("*.json")):
            run = read_json(f)
            if isinstance(run, dict) and "summary" in run:
                runs.append({"name": f.stem, "config": run.get("config", {}), "summary": run["summary"]})
        return runs

    @app.get("/eval/{name}")
    def eval_run(name: str):
        f = eval_dir / f"{Path(name).name}.json"  # Path(...).name: no traversal
        if not f.exists():
            raise HTTPException(404, f"No eval run named {name}")
        return read_json(f)

    @app.post("/ask", response_model=Answer)
    def ask_default(req: AskRequest):
        """Ask the default space. /spaces/{id}/ask is the same thing for other spaces."""
        return ask(DEFAULT_SPACE.id, req)

    @app.get("/spaces/{space_id}/eval")
    def get_eval(space_id: str):
        space_of(space_id)
        ev = read_json(results / "eval.json")
        if ev is None:
            raise HTTPException(404, "No eval results: run python -m backend.eval")
        return ev

    return app


app = create_app()
