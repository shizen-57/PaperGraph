# DocLens: overview

Full plan: [doclens_plan.md](doclens_plan.md). Application context: [interview_prep.md](interview_prep.md).

## What it is

DocLens reads business PDFs in English or Japanese, including their tables, charts and images. It does two things:

- **Extracts structured fields** (for example product, model number, voltage, company, period, revenue). Every value comes with the exact quote and page it was taken from.
- **Answers questions** about the document. Every answer cites its pages, and clicking a citation highlights that spot on the PDF.

## Why build it

It is a small version of what INDX sells: LLM-based document structuring, search and RAG, and a user interface, in Python and TypeScript. It also gives you something concrete to show for the INDX application and interview, with tests, an eval and a write-up.

## What makes it different from a basic RAG demo

- **Evidence check:** a field whose quote isn't found in the document is flagged "unverified". This makes hallucinations visible.
- **Number check:** every number in an answer must appear in a cited source, or the answer is flagged.
- **Tables kept whole:** rebuilt as rows and columns and shown as real tables, not split into loose text.
- **Real eval:** accuracy, search recall and speed numbers produced by code. The README shows only those numbers, never estimates.

## How it works

1. **Parse:** Docling turns each PDF into typed elements (text, table, figure, caption), each with a page and position.
2. **Extract:** an LLM fills a fixed schema (Pydantic) per document type, with a quote for each value.
3. **Search:** multilingual-e5-small embeddings plus numpy cosine search over the document's chunks.
4. **Ask:** the LLM answers from the retrieved chunks and cites them.
5. **Show:** a Next.js (TypeScript) PDF viewer with highlights, a fields panel, an Ask page and an Eval page.

The LLM sits behind one OpenAI-compatible setting (`LLM_BASE_URL`). It can be an open model (Qwen on Kaggle) or a third-party API, and the code doesn't change. The heavy batch work runs once and its JSON output is committed, so the app itself runs on a laptop CPU.

## Stack

Docling, Qwen2.5-7B / Qwen2.5-VL (or an API model), Pydantic, FastAPI, Next.js + TypeScript, react-pdf, pytest.

## Scope

- **Core:** parse, extract, evidence check, highlights, cited Q&A, number check, tables, eval page.
- **If time allows:** charts read by a vision model, images and diagrams, scanned pages.
- **Out of scope:** accounts, permissions, vector database, Docker, deployment. These go in the README as next steps.

## Timeline

7 days, 23–29 Oct 2026, **after** the INDX application is submitted (deadline 23 Oct, 06:00 Dhaka). An INDX test or interview takes priority over the build.

## Deliverable

A GitHub repo with a README that has: a demo GIF, an architecture diagram, a results table with real numbers, 3–5 failure cases with screenshots, run instructions, and the design trade-offs.
