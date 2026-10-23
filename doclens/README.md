# DocLens

Upload business PDFs in English or Japanese, with text, tables, charts and images. DocLens extracts structured fields and answers questions, and every value and answer points back to the exact spot in the PDF it came from.

> The front page, results and failure cases are in the [repository README](../README.md). This file is the developer guide for the `doclens/` app.

## How it works

```
Kaggle GPU (once):  PDFs → Docling parse → Qwen2.5-VL charts/figures → e5 embeddings → Qwen2.5 extraction → results/*.json
Laptop CPU:         Next.js ─/api─► FastAPI (loads results/) ─LLM_BASE_URL─► vLLM on Kaggle (tunnel) or any OpenAI-compatible API
```

- **One element = one search chunk**, so every citation maps to exactly one box on the page.
- **Evidence check:** a field is `verified` only if its quote exists in the document and contains the value (after NFKC normalisation, so `１２３` = `123`).
- **Number check:** numbers in an answer that don't appear in its cited sources are flagged.

## Start both services on Windows

After installing the Python requirements and frontend dependencies, run this from the workspace root:

```powershell
python .\start_app.py
```

Open http://127.0.0.1:3000. Both services write logs to the same terminal; Ctrl+C stops both. The launcher uses your current Python environment and inherits your LLM settings. It stops the other service if either exits and refuses to start if port 3000 or 8000 is already in use. The script resolves paths from its own location, so it can also be run by its full path from another directory.

## Run the API

```bash
pip install -r requirements.txt
python data/download.py          # PDFs from data/sources.csv → data/pdfs/ (not committed)
LLM_BASE_URL=https://<tunnel>/v1 LLM_API_KEY=<key> LLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ \
  uvicorn backend.app:app --port 8000
pytest                           # no GPU or network needed
```

PowerShell: set each variable first, e.g. `$env:LLM_BASE_URL="https://<tunnel>/v1"`.

| Route | Returns |
|---|---|
| `POST /parse` (file) | Elements of an uploaded PDF, image, PPTX, `.md` or `.txt`: type, page, box in points, text, table |
| `POST /extract?type=invoice\|spec_sheet\|financial_report&extractor=llm\|rules` (file) | Fields with value, quote, page, box and `verified`/`unverified`, plus arithmetic checks; nothing is stored |
| `POST /documents/{id}/extract`, `GET /documents/{id}/extraction` | The same for a stored document, kept in the database |
| `GET /docs`, `GET /documents/{id}` | Documents, elements, claims (boxes in PDF points, top-left origin) |
| `GET /files/{id}`, `GET /crops/{id}/{element}.png` | The original file and cropped figures |
| `POST /ask` `{question}`, `POST /spaces/{id}/ask` | Cited answer; 503 if the LLM is unreachable |
| `GET /eval`, `GET /eval/{name}` | Summaries / full results of `eval/results/*.json` (written by `eval/run_eval.py`) |
| `GET /spaces/{id}/eval` | `results/eval.json` (question answering, from `python -m backend.eval`) |
| `GET /swagger` | API explorer |

## Run the frontend

```bash
python data/make_demo.py         # optional: a demo document, so the site has something to show
cd frontend
npm install                      # also copies the pdf.js worker and cMaps into public/
npm run dev                      # http://localhost:3000, proxies /api/* to the API on :8000 (API_URL to change)
```

## Pipelines

**Ingest a folder** (parse, chunk, embed, relations, claims), resumable per document:

```bash
python -m backend.ingest data/space                          # default stages
python -m backend.ingest data/space --stages vlm,chunk,embed # force-rerun stages; vlm needs a VLM behind LLM_BASE_URL
python -m backend.demo                                       # four synthetic invoices, parsed and extracted, no embeddings
```

**Evaluate** a parser + extractor on the synthetic invoices (see [eval/](eval/)):

```bash
python eval/run_eval.py --parser pdfium --extractor rules --out eval/results/pdfium-rules.json
python eval/run_eval.py --parser docling --extractor llm --llm $LLM_MODEL --out eval/results/docling-llm.json
python eval/render_tables.py --write ../README.md           # the README tables come from eval/results/*.json
```

Parsers: `PARSER=docling | pdfium | tesseract | vlm | router`. GPU runs (VLM parsers, vLLM, quantisation, LoRA) are in
`notebooks/kaggle_arena.ipynb` and `notebooks/kaggle_lora.ipynb`.

**Offline:** `OFFLINE=1` allows only local models and refuses any connection that is not loopback or on the LAN (`backend/offline.py`).

## Data and labels

`data/sources.csv`: public input documents (`filename,url,title,licence`); `python data/download.py` fetches them. The evaluation data for
invoices is generated, not downloaded: `python -m eval.synth.generate` (committed under `eval/data/synth`).

The question-answering evaluation (`python -m backend.eval`) reads hand-made labels that are **not** in this repository; the
formats are below.

| File | Format |
|---|---|
| `labels/fields/{doc_id}.json` | `{"field_name": "correct value" or null}` |
| `labels/qa.jsonl` | One per line: `{"id", "doc_id", "question", "answer", "page"}` |
| `labels/tables/{doc_id}__{element_id}.json` | `{"rows": [[header…], [row…], …]}` |
| `labels/charts.json` | `[{"doc_id", "element_id", "values": {"label": number}}]` |
| `labels/answer_grades.csv` | `question_id,grade` with grade `correct`, `partly` or `wrong` (template made by `answers`) |

## Known limits

- Kanji numerals (三百) aren't caught by the Q&A number check (`normalize_ja.parse_amount` does read them for extraction).
- Table spans are not kept: a table is a header and rows, so merged cells are flattened.
- Element-level boxes: a value in a table highlights the whole table, not its cell.
- Elements that span two pages keep only their first box.
- Search is brute-force numpy over a small corpus; a vector DB and permission-aware retrieval are next steps.
