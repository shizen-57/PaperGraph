# DocLens: backend plan

The backend for [doclens_plan.md](doclens_plan.md). The API matches [frontend.md](frontend.md) §3. Build it only after the INDX application is submitted.

**Two halves, one codebase:**
- **Batch pipeline (Kaggle GPU, run once):** parse PDFs → extract fields → VLM pass on pictures → embeddings → eval. Writes `results/`.
- **API (laptop CPU):** loads `results/` into memory and serves documents, search and Q&A. It only calls an LLM for `/ask`.

The logic lives in `backend/*.py`. The Kaggle notebook is a thin driver that `git clone`s the repo and calls those functions, so tests cover the real code.

**Implemented** in [doclens/](doclens/) (see its README). Changes from this plan:
- Swagger moved to `/swagger`, because FastAPI's default Swagger page sits at `/docs`.
- `Field.page`, `element_id` and `bbox` can be null (the field wasn't found).
- Extra modules: `store.py` (reads and writes `results/`), `norm.py`, `crops.py`, `vlm.py`, `pipeline.py` (the stage CLI).

## 1. Stack

| Part | Choice | Runs on |
|---|---|---|
| Parsing | **Docling** | Kaggle |
| Text LLM | **Qwen2.5-7B-Instruct** on **vLLM**, guided JSON | Kaggle |
| Vision LLM | **Qwen2.5-VL-7B-Instruct** on vLLM, guided JSON | Kaggle, separate session |
| Schemas | **Pydantic** v2 | Both |
| Embeddings | **multilingual-e5-small** (sentence-transformers) | Passages on Kaggle, queries on CPU |
| Search | numpy cosine, top-5 | CPU |
| API | **FastAPI** + uvicorn | CPU |
| LLM client | `openai` SDK pointed at `LLM_BASE_URL` | CPU → Kaggle tunnel or a free API |
| Crops | **pypdfium2** (already a Docling dependency) | CPU |
| Tests | **pytest** | CPU |

Two requirement sets:
- `requirements.txt` (API): fastapi, uvicorn, pydantic, numpy, sentence-transformers, openai, pypdfium2
- The notebook installs docling and vllm.

Config comes from environment variables only: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`.

## 2. Data on disk

```
data/pdfs/{doc_id}.pdf            downloaded by download.py, not committed
results/
  docs.json                       [{id, title, doc_type, lang, pages, page_sizes}]
  elements/{doc_id}.json          Element[]
  fields/{doc_id}.json            Field[]
  embeddings/{doc_id}.npy         float32, L2-normalised, row i = searchable element i
  embeddings/{doc_id}.ids.json    element id for each row
  eval.json                       every metric from run_eval
  answers.jsonl                   generated answers for the 30 QA questions
labels/answer_grades.csv          your hand grades: question_id, grade (correct/partly/wrong)
```

All of `results/` is committed. PDFs and crops are not (licences), and the API renders crops on demand from the local PDFs.

## 3. Schemas (`schemas.py`)

These mirror `frontend/lib/types.ts`. Change both together.

```python
class BBox(BaseModel):  x0: float; y0: float; x1: float; y1: float   # PDF points, TOP-LEFT origin
class Table(BaseModel): header: list[str]; rows: list[list[str]]
class Element(BaseModel):
    id: str; doc_id: str; type: Literal["text", "table", "figure", "chart", "caption"]
    page: int; bbox: BBox; text: str            # text = what gets searched (paragraph, table md, VLM summary)
    heading: str | None = None                  # nearest section heading, prepended for embedding
    table: Table | None = None
class Field(BaseModel):
    name: str; value: str | None; quote: str; page: int
    element_id: str; bbox: BBox; verified: bool
```

Plus one Pydantic model per document type (e.g. `SpecSheet`, `Report`). Each field is `{value, quote, element_id}`, and `model_json_schema()` from that model is what vLLM's guided JSON gets.

## 4. Pipeline (batch)

**`parse.py`: PDF → `Element[]`**
- Docling `DocumentConverter`, with table structure and picture images enabled.
- Text, table, picture and caption items become Elements, with ids `e0, e1, …` in reading order.
- Tables: Docling's table → `Table(header, rows)`, and `text` = caption + Markdown. Very large tables are split into row groups, with the header repeated.
- **Box conversion happens here, once.** Docling boxes use a bottom-left origin. Convert with `y_top = page_height - y`, using the page height from Docling. There is a test for it (§7).
- Each element keeps the heading it sits under. Captions are attached to their table or figure's text.

**`extract.py`: elements → `Field[]`**
- The prompt lists elements as `[e12 p3] text…` and asks for each field's value, an exact quote and an element_id, using the doc type's schema as guided JSON.
- Long documents (annual reports): if the text exceeds about 20k tokens, retrieve the top 10 elements per field name with `search.py` and extract from those. Spec sheets fit whole.
- **Evidence check** (`verify_field`):
  - NFKC-normalise, casefold and remove all whitespace on both sides (Docling puts line breaks inside Japanese text). NFKC handles full-width vs half-width (`１２３` = `123`), from stdlib `unicodedata`.
  - `verified = quote in element.text and value in quote`.
  - If the element_id is wrong but the quote is found elsewhere in the document, repoint it to the element that contains the quote.

**VLM pass (separate Kaggle session; risk table in doclens_plan.md §10)**
- For each picture crop, one guided-JSON call returns `{kind: "chart" | "figure", summary, table?}`.
- Charts become `type="chart"` with a `table` and summary text. Figures become `type="figure"`, with the description plus OCR'd labels as text.

**Embeddings**
- Each searchable element (all types except captions; skip text under 20 characters) is embedded as `"passage: " + heading + "\n" + text`.
- **e5 needs the `passage: ` / `query: ` prefixes.** Without them, retrieval quality drops quietly.

**One element = one chunk.** Citations then point to exactly one box, which is what the frontend highlights. Adding the heading gives a paragraph its context. Merge chunks only if recall@5 turns out poor.

## 5. API (`app.py`)

Load everything from `results/` into dicts at startup (lifespan), and load the e5 model once.

| Route | Does |
|---|---|
| `GET /docs` | `docs.json` + `verified_rate` computed from fields |
| `GET /docs/{id}` | Summary + `pdf_url` + elements + fields; 404 if unknown |
| `GET /files/{id}.pdf` | `StaticFiles` mount on `data/pdfs` |
| `GET /crops/{doc_id}/{element_id}.png` | Renders the page with pypdfium2, crops the box, caches it to `.cache/crops/` |
| `POST /ask` `{doc_id, question}` | §6 |
| `GET /eval` | `eval.json` |

Returned URLs are relative to the API (`/files/x.pdf`), and the frontend's `api.ts` adds the `/api` prefix.

## 6. `/ask`: search, answer, number check

1. **`search.py`:** embed `"query: " + question`, take the dot product with the document's matrix, keep the top 5 element ids.
2. **`answer.py`:** the prompt numbers the chunks `[1]…[5]` and says: answer only from them, cite as `[n]`, and say "Not found in the document" if they don't contain the answer.
3. **`llm.py`:** `OpenAI(base_url=LLM_BASE_URL).chat.completions.create(…, timeout=60)`. Connection or timeout errors → **HTTP 503** "LLM unreachable — check LLM_BASE_URL", which the frontend shows as is.
4. Parse the `[n]` markers in the answer and return only the cited chunks as `Citation`s (element id, page, box, type, crop_url, table).
5. **Number check** (`check_numbers`):
   - Use a regex for numbers in the NFKC-normalised answer (`\d[\d,]*(\.\d+)?`), and strip commas.
   - Any number not found in the cited elements' normalised text goes in `unverified_numbers`.
   - Kanji numerals (三百) aren't caught. Mark that limit with a `ponytail:` comment and use it as a failure case.
6. `approximate = any(citation.type == "chart")`.

## 7. Tests (`tests/`, pytest, CPU only)

| Test | Checks |
|---|---|
| `test_bbox.py` | Bottom-left → top-left conversion on a known box and page height |
| `test_evidence.py` | Exact quote, full-width quote, quote missing, wrong element id repointed |
| `test_numbers.py` | `1,234` = `1234`, decimals, a number missing from the citations, no numbers at all |
| `test_schemas.py` | Every file in `results/` validates against its Pydantic model |
| `test_metrics.py` | Each metric function on a 3-item toy input with a known answer |
| `test_api.py` | `TestClient`: `/docs`, `/docs/{id}`, 404, and `/ask` with `llm.chat` monkeypatched to a fixed answer, plus the 503 path |

No GPU and no network in tests. The LLM is always faked.

## 8. Evaluation (`eval.py`, `run_eval`)

Implements doclens_plan.md §7, writing to `results/eval.json`:
- **Fields:** exact match after NFKC + unit/space normalisation, per field and overall.
- **Evidence:** the share of fields with `verified=True`.
- **Tables:** cell accuracy against `labels/tables/`.
- **Charts:** mean relative error against `labels/charts.json`.
- **Search:** recall@5 over `labels/qa.jsonl`, using the correct page as the target. Runs on CPU.
- **Answers:** read `labels/answer_grades.csv` (you grade `results/answers.jsonl` by hand) and report counts of correct, partly and wrong.
- **Speed:** seconds per page for each stage and peak GPU memory, timed inside the notebook and saved alongside.

The README and the eval page show only these numbers.

## 9. Day-by-day (fits doclens_plan.md §9)

| Day | Date | Backend work | Done when |
|---|---|---|---|
| 1 | 23 Oct | `schemas.py`, `parse.py`, box conversion + test; parse every PDF (Docling runs on CPU too, but faster on Kaggle) | `results/elements/*.json` for all docs |
| 2 | 24 Oct | Kaggle notebook: vLLM + Qwen, `extract.py`, evidence check + tests | `results/fields/*.json`; `pytest` passes |
| 3 | 25 Oct | `app.py`: `/docs`, `/docs/{id}`, `/files`, startup loading; `test_api.py` | Frontend shows fields with highlights |
| 4 | 26 Oct | Embeddings, `search.py`, `answer.py`, `llm.py`, number check + tests | `/ask` returns cited answers (free API or tunnel) |
| 5 | 27 Oct | VLM pass, `/crops` route | A chart question cites a chart with a table |
| 6 | 28 Oct | `eval.py`: generate answers, grade them by hand, run_eval | `results/eval.json` with real numbers |
| 7 | 29 Oct | README sections: architecture, results, failures, how to run | Fresh clone → `download.py` → app runs |

**Cut order:** model comparison → retrieval for long documents during extraction (use spec sheets plus shorter reports only) → VLM pass on figures (keep charts) → VLM pass entirely (charts become plain figures) → `/crops` (send the full page instead).

**Never cut:** box conversion test, evidence check, number check, `run_eval`.

## 10. Interview talking points (backend)

- **Why one element per chunk?** Every citation maps to exactly one box, so the highlight is exact. The heading adds the context a bare paragraph lacks.
- **Why NFKC?** Japanese documents mix full-width and half-width digits and letters. One stdlib call makes `１２３` match `123`.
- **Why guided JSON?** The model can't return invalid JSON, so the retry logic is only for wrong values, not broken output.
- **Why is the notebook a thin driver?** The same code runs in tests and on Kaggle, so tests cover what produced the results.
- **Why load everything into memory?** A few thousand elements fit in RAM. At 1M chunks: a vector DB, an ANN index, and permission filters applied before retrieval.
- **Why does the LLM failure return a 503?** The demo depends on a tunnel. A clear error is better than a hang.

## 11. Verification

1. `pytest`: all green, with no GPU or network.
2. `python -c "…"` or `pytest tests/test_schemas.py`: every committed results file validates.
3. `uvicorn backend.app:app`, then `curl localhost:8000/docs` and `curl localhost:8000/docs/<id>` return JSON with top-left boxes.
4. `curl -X POST localhost:8000/ask -d '{"doc_id": "<id>", "question": "…"}' -H 'Content-Type: application/json'` returns an answer with citations. With a bad `LLM_BASE_URL`, it returns a 503 with the message.
5. Open `/crops/<id>/<element>.png` and check that the crop matches the chart.
6. End to end with the frontend: frontend.md §8.
