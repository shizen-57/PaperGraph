# DocLens

Upload business PDFs in English or Japanese, with text, tables, charts and images. DocLens extracts structured fields and answers questions, and every value and answer points back to the exact spot in the PDF it came from.

> GIF, results table and failure cases go here. Only numbers from `results/eval.json`.

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
| `GET /docs`, `GET /docs/{id}` | Documents, elements, fields (boxes in PDF points, top-left origin) |
| `GET /files/{id}.pdf`, `GET /crops/{id}/{element}.png` | PDF and cropped figures |
| `POST /ask` `{doc_id, question}` | Answer with citations; 503 if the LLM is unreachable |
| `GET /eval` | `results/eval.json` |
| `GET /swagger` | API explorer |

## Run the frontend

```bash
python data/make_demo.py         # optional: a demo document, so the site has something to show
cd frontend
npm install                      # also copies the pdf.js worker and cMaps into public/
npm run dev                      # http://localhost:3000, proxies /api/* to the API on :8000 (API_URL to change)
```

## Pipeline

Run on Kaggle with [notebooks/kaggle_pipeline.ipynb](notebooks/kaggle_pipeline.ipynb), which calls:

```bash
python -m backend.pipeline parse     # Docling
python -m backend.pipeline vlm       # VLM behind LLM_BASE_URL; re-run parse before re-running this
python -m backend.pipeline embed
python -m backend.pipeline extract   # text LLM behind LLM_BASE_URL
python -m backend.pipeline answers   # QA set → results/answers.jsonl + grading template
python -m backend.pipeline eval      # → results/eval.json
```

Add `--docs id1 id2` to run on some documents only.

## Data and labels

`data/sources.csv`: `doc_id,url,title,doc_type,lang,licence` where `doc_type` is `spec_sheet` or `report` (see `backend/schemas.py`) and `lang` is `en` or `ja`.

| File | Format |
|---|---|
| `labels/fields/{doc_id}.json` | `{"field_name": "correct value" or null}` |
| `labels/qa.jsonl` | One per line: `{"id", "doc_id", "question", "answer", "page"}` |
| `labels/tables/{doc_id}__{element_id}.json` | `{"rows": [[header…], [row…], …]}` |
| `labels/charts.json` | `[{"doc_id", "element_id", "values": {"label": number}}]` |
| `labels/answer_grades.csv` | `question_id,grade` with grade `correct`, `partly` or `wrong` (template made by `answers`) |

## Known limits

- Kanji numerals (三百) aren't caught by the number check.
- Elements that span two pages keep only their first box.
- Search is brute-force numpy over a small corpus; a vector DB and permission-aware retrieval are next steps.
