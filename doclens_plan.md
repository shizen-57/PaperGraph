# DocLens: project plan

A showcase project for the INDX application ([job_posting.md](job_posting.md), [interview_prep.md](interview_prep.md)).

**One line:** upload business PDFs in English or Japanese, with text, tables, charts and images. DocLens extracts structured fields and answers questions, and every answer points back to the exact spot in the document it came from.

**Order:** submit the INDX application first (deadline 23 Oct 2026, 06:00 Dhaka). Build after that. Your GitHub profile link will show the repo once it's pushed, even after the deadline.

---

## 1. Why this project

It mirrors INDX's own product and job description:

| INDX says | DocLens shows |
|---|---|
| "Structuring documents and extracting information using LLMs" | Field extraction into a fixed format, with evidence for every value |
| "Searching and analyzing collected information" | Search plus cited Q&A (RAG) |
| "Applications and user interfaces" | Next.js PDF viewer with highlights |
| Python and JavaScript/TypeScript | FastAPI backend, TypeScript frontend |
| "Write and execute tests and evaluate feature quality" | pytest, an eval set and a results table |
| "Technical documentation" | README with architecture, results and failure cases |
| On-prem, confidential data | Open model (Qwen) run on Kaggle; no API needed for the core pipeline |
| Drawings, specifications, contracts | Handles tables, charts and images, not just text |

## 2. Features

**Core (must ship):**
1. **Parse:** PDF → typed elements (text, table, figure, caption), each with page and position.
2. **Extract:** fields per document type (e.g. spec sheet: product, model no., dimensions, voltage; report: company, period, revenue). Each value comes with the quote it was taken from and its page.
3. **Evidence check:** the quote must actually exist in the document. If it doesn't, the field is flagged "unverified". This catches the model making things up.
4. **Highlight:** clicking a field highlights its source on the PDF page.
5. **Ask:** answers questions using search over the document and cites its pages; clicking a citation jumps to the highlighted passage.
6. **Number check:** every number in an answer must appear in a cited source, or the answer is flagged.
7. **Tables:** kept whole, rebuilt as rows and columns, and shown as real tables in the UI.
8. **Eval page:** accuracy, search and speed numbers from the Kaggle run.

**Second wave (if time):**
9. **Charts:** a VLM (an LLM that reads images) turns charts into data tables, and answers using them are labelled "approximate, read from chart".
10. **Images, diagrams, drawings:** VLM descriptions plus OCR of labels; the answer shows the cropped image.
11. **Scanned pages:** OCR, with a fallback to sending the whole page to the VLM.

**Out of scope:** user accounts, permissions, a vector database, Docker, deployment, searching page images directly (ColPali). Mention them as next steps in the README.

## 3. Architecture

```
            ┌──────────────── Kaggle notebook (GPU) ────────────────┐
PDFs ──────►│ Docling parse → Qwen2.5-7B extract → Qwen2.5-VL charts │──► results/*.json
            │ + eval scores (accuracy, speed)                         │    (committed)
            └─────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
Next.js (TS) ◄──── FastAPI (Python, local CPU) ◄── elements + extractions + embeddings
 PDF viewer         /docs /docs/{id} /ask /eval
 highlights         search: numpy cosine over embeddings
 Q&A, eval          LLM for /ask: OpenAI-compatible URL (Kaggle vLLM or free API)
```

- **Heavy work runs on Kaggle, once:** parsing, extraction, VLM passes and eval. The outputs are JSON files the app loads, so the app runs on a laptop CPU.
- **Live Q&A** needs an LLM at request time. The client is OpenAI-compatible, so switching is one setting (`LLM_BASE_URL`): either vLLM on Kaggle (exposed through a tunnel while you demo) or a free API. Record a demo video as backup, because Kaggle sessions and tunnels drop.

## 4. Stack

| Part | Choice | Note |
|---|---|---|
| Parsing | **Docling** | Layout detection, table structure, OCR, figure crops, page positions |
| Text LLM | **Qwen2.5-7B-Instruct** via **vLLM** on Kaggle | Its JSON-forcing mode (guided decoding) guarantees valid output |
| Vision LLM | **Qwen2.5-VL-7B-Instruct** on Kaggle | Charts → tables, images → descriptions |
| Schemas | **Pydantic** | One schema per document type |
| Embeddings | **multilingual-e5-small** (CPU) | Handles Japanese; small enough for laptop query embedding |
| Search | numpy cosine similarity | Fine for a few thousand chunks. Mark it as a deliberate simplification; a vector DB comes when the corpus grows |
| Backend | **FastAPI** | |
| Frontend | **Next.js + TypeScript**, **react-pdf** | Highlight overlay from element positions |
| Tests | **pytest** | |

Change of plan if time runs out: Streamlit instead of Next.js (all Python, faster, but no TypeScript evidence).

## 5. How each element type is handled

| Element | Processing | Searched as | Answer shows |
|---|---|---|---|
| Text | Split into chunks by heading | Chunk text | Highlighted passage |
| Table | Docling rebuilds rows and columns → Markdown + DataFrame. Kept whole; very large tables are split by row groups with the header repeated | Caption + headers + Markdown | Rendered table + highlight |
| Chart | VLM → data table + one-line summary, labelled approximate | Summary + table | Chart crop + values read |
| Image / diagram / drawing | VLM description + OCR of labels (e.g. a drawing's title block) | Description | Image crop |
| Scanned page | OCR; if the text is bad, the page goes to the VLM | Text | Highlighted region |

Every element keeps `{doc_id, type, page, bbox, text, crop_path}`, so any answer can point back to its source.

**Gotcha:** Docling measures page positions from the bottom-left corner, while the PDF viewer measures from the top-left. Convert once in the backend, and add a test for it.

## 6. Dataset

- **15–20 public PDFs**, mixing English and Japanese, chosen so they contain tables, charts, images and 2–3 scanned pages. Good sources: product spec sheets, Japanese companies' integrated reports (統合報告書) or annual reports, and government statistics PDFs.
- **Don't commit the PDFs.** Commit `data/sources.csv` (URL plus licence notes) and a `download.py`.
- **Labels (hand-made):** labelling is the slowest part, so start it on day 1.
  - `labels/fields/*.json`: the correct field values per document
  - `labels/qa.jsonl`: about 30 questions with answer and page, some needing tables or charts
  - `labels/charts.json`: true values for about 5 charts
  - `labels/tables/`: true cells for about 5 tables

## 7. Evaluation

Each metric runs on the Kaggle notebook and is saved to `results/`:

| What | Metric |
|---|---|
| Field extraction | Exact match after normalising (spaces, units, full-width/half-width characters), per field and overall |
| Evidence check | Share of values whose quote is found in the document |
| Tables | Cell accuracy against the labelled tables (TEDS if time) |
| Charts | Average relative error of the values read |
| Search | Recall@5 on the QA set: is the correct page in the top 5 |
| Answers | Correct / partly / wrong, **graded by you by hand** on the 30 questions (more credible than an LLM judge at this size) |
| Speed | Seconds per page for parsing, extraction and VLM; peak GPU memory |
| Model comparison | Qwen 7B on Kaggle vs one API model on the same set (optional) |

**Rule: the README only shows numbers produced by `run_eval`. Never estimate or round them up.**

Failure analysis: pick 3–5 real failures (merged cells, dense charts, Japanese scans, vertical text, multi-column layouts), show a screenshot of each, and write what went wrong and what would fix it.

## 8. Repo layout

```
doclens/
  backend/
    app.py          FastAPI routes
    parse.py        Docling → elements JSON
    extract.py      LLM extraction + evidence check
    search.py       embeddings + cosine search
    answer.py       Q&A with citations + number check
    schemas.py      Pydantic schemas per doc type
    llm.py          OpenAI-compatible client (LLM_BASE_URL)
  frontend/         Next.js + TypeScript
  notebooks/
    kaggle_pipeline.ipynb   parse, extract, VLM, eval on GPU
  data/
    sources.csv, download.py
  labels/
  results/          JSON outputs + eval scores (committed)
  tests/            pytest: schemas, evidence check, number check, bbox conversion, metrics
  README.md
```

## 9. Milestones

| Day | Date | Work | Done when |
|---|---|---|---|
| 0 | 21–22 Oct | **INDX application only** | Submitted |
| 1 | 23 Oct | Repo, pick documents, start labels, Docling parse → elements JSON | Elements JSON for all docs; labels for 5 |
| 2 | 24 Oct | Kaggle notebook: vLLM + Qwen extraction with guided JSON; evidence check; pytest | Extractions JSON + passing tests |
| 3 | 25 Oct | FastAPI routes; Next.js PDF viewer + fields panel + highlights | Click a field → its source is highlighted |
| 4 | 26 Oct | Embeddings, search, `/ask` with citations + number check; Ask page | Cited answers that jump to the page |
| 5 | 27 Oct | VLM pass for charts and images; tables rendered in the UI | Chart question answered with a crop |
| 6 | 28 Oct | Finish labels, run eval, eval page, failure cases | Real results table |
| 7 | 29 Oct | README, architecture diagram, demo GIF + 2-minute video; buffer | Repo pinned on GitHub |

If the INDX technical test or interview lands mid-build, that takes priority.

**Cut order if short on time:**
1. Model comparison
2. Scanned pages
3. Images/diagrams (keep charts)
4. Charts (keep tables)
5. Next.js → Streamlit

**Never cut:** tables, evidence check, eval, README.

## 10. Risks

| Risk | Plan |
|---|---|
| Japanese OCR is poor | Use born-digital Japanese PDFs for the core; treat scans as a failure-analysis case |
| Kaggle GPU quota and session limits | Run the batch work once, commit the JSON, and keep the notebook restartable |
| Tunnel to Kaggle drops in a live demo | Free API fallback via `LLM_BASE_URL` + recorded video |
| A 7B model in 4-bit doesn't fit with the VLM at the same time | Run text and VLM passes in separate notebook sessions |
| Labelling takes longer than planned | Fewer documents with good labels beat many unlabelled ones |

## 11. README must have

1. GIF at the top: question → cited answer → highlighted chart or table
2. What it does, in 3 lines
3. Architecture diagram
4. Results table (real numbers only) and failure cases with screenshots
5. How to run: `download.py`, Kaggle notebook link, `uvicorn` + `npm run dev`
6. Design decisions and trade-offs (see below)
7. Next steps: permission-aware search, vector DB, on-prem packaging, page-image search

## 12. Interview talking points

Be ready to explain each decision:
- **Why an evidence quote for every field?** It makes hallucinations visible and checkable, and users can trust what they can verify.
- **Why number grounding?** LLMs invent plausible numbers, and in finance or insurance documents that's the worst kind of error.
- **Why keep tables whole?** Splitting rows breaks their meaning, and the header gives each cell its context.
- **Why run the VLM in batch?** Cost and latency: describe each chart once, search it many times.
- **Why an open model?** INDX sells on-prem; this shows the pipeline works without sending data to an external API.
- **Why numpy and not a vector DB?** The corpus is small. Say what would change at 1M chunks.
- **What failed, and what would you do next?** Use the failure cases.
- **How did you use AI tools to build it?** Be honest: what you delegated, what you checked, and what you wrote tests for.
