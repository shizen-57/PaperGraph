# DocLens: frontend plan

The frontend for [doclens_plan.md](doclens_plan.md). Build it only after the INDX application is submitted.

**Implemented** in [doclens/frontend/](doclens/frontend/). Changes from this plan:
- Plain CSS (`app/globals.css`) instead of Tailwind: a glassmorphism theme over the looping corkboard video (`public/bg.mp4`), with a slight parallax on the mouse and a pause button.
- Versions pinned to Next 15.5 and react-pdf 9.2. The pdf.js worker and cMaps are served from `public/`, not unpkg, so Japanese PDFs work offline.
- The highlight scales by the backend's `page_sizes`, not by react-pdf's `onLoadSuccess`.

**Goal:** one screen that sells the project. On the left is the PDF. On the right are the extracted fields and a Q&A box. Clicking any value or citation highlights its source on the page.

## 1. Stack

| Part | Choice | Why |
|---|---|---|
| Framework | **Next.js (App Router) + TypeScript** | From `create-next-app` |
| PDF | **react-pdf** | Renders pages; you draw highlight boxes over them |
| Styling | **Tailwind** | Included with `create-next-app`. No component library |
| Data | `fetch` in server components; `useState` in client components | No SWR, React Query or Redux. One page holds the state |
| Japanese UI text | `Noto_Sans_JP` via `next/font/google` | |
| Backend link | `rewrites()` in `next.config.ts`: `/api/*` → `http://localhost:8000/*` | Same origin, so no CORS setup |

Skipped: a test framework. `npm run build` (which also type-checks) plus the demo flow in §8 is the check. Add vitest if frontend logic grows beyond scaling boxes.

## 2. Pages

| Route | Shows | Built on |
|---|---|---|
| `/` | Document list: title, type, language, pages, % of fields verified | Day 3 |
| `/docs/[id]` | **Main screen:** PDF viewer (left, about 60%) plus a side panel with **Fields** and **Ask** tabs | Days 3–5 |
| `/eval` | Results tables from `results/` and failure cases with screenshots | Day 6 |

Ask is per document (the backend searches one document), so it's a tab on the document screen, not a separate page.

```
┌──────────────────────────────── /docs/[id] ────────────────────────────────┐
│ ← Docs   Sony spec sheet  · EN · 4 pages                                    │
├──────────────────────────────────────────────┬──────────────────────────────┤
│                                              │ [Fields] [Ask]               │
│   page 2                                     │ product     WH-1000XM5  ✓ p2 │
│   ┌──────────────┐  ← highlight box          │ voltage     5 V         ✓ p3 │
│   │ 5 V DC       │                           │ weight      250 g       ⚠ p3 │
│   └──────────────┘                           │   (quote not found)          │
│                                              │                              │
└──────────────────────────────────────────────┴──────────────────────────────┘
```

## 3. API contract (FastAPI ↔ Next.js)

Write these types by hand in `frontend/lib/types.ts`, mirroring `backend/schemas.py`. Generate them from OpenAPI only if the schemas keep changing.

```ts
type BBox = { x0: number; y0: number; x1: number; y1: number }  // PDF points, TOP-LEFT origin (backend converts)
type Element = { id: string; type: "text" | "table" | "figure" | "chart" | "caption";
                 page: number; bbox: BBox; text: string; crop_url?: string;
                 table?: { header: string[]; rows: string[][] } }
type Field = { name: string; value: string | null; quote: string; page: number | null;
               element_id: string | null; bbox: BBox | null; verified: boolean }  // null source = field not found
type DocSummary = { id: string; title: string; doc_type: string; lang: "en" | "ja";
                    pages: number; verified_rate: number }
type Doc = DocSummary & { pdf_url: string; elements: Element[]; fields: Field[] }
type Citation = { n: number; element_id: string; page: number; bbox: BBox;
                  type: Element["type"]; crop_url?: string; table?: Element["table"] }
type Answer = { answer: string; citations: Citation[];
                unverified_numbers: string[]; approximate: boolean }
```

| Route | Returns |
|---|---|
| `GET /docs` | `DocSummary[]` |
| `GET /docs/{id}` | `Doc` |
| `GET /files/{id}.pdf`, `GET /crops/...` | Static files (FastAPI `StaticFiles`) |
| `POST /ask` `{doc_id, question}` | `Answer` |
| `GET /eval` | Contents of `results/eval.json` |

**Two backend rules the frontend depends on:**
- Boxes arrive with a **top-left origin, in PDF points**. Docling's bottom-left conversion happens once in the backend and is tested there (doclens_plan.md §5).
- Tables arrive as `header` + `rows`, not Markdown, so the frontend needs no Markdown library.

## 4. Components

```
frontend/
  app/
    layout.tsx               font, header with Docs / Eval links
    page.tsx                 doc list (server component)
    docs/[id]/page.tsx       fetches Doc, renders <DocView>
    eval/page.tsx            results tables + failure cases
  components/
    DocView.tsx              client; holds `target` state = {page, bbox} | null
    PdfViewer.tsx            client-only (dynamic import, ssr: false); pages + highlight overlay
    FieldsPanel.tsx          field rows → setTarget
    AskPanel.tsx             question box, answer, citation chips → setTarget
    TableView.tsx            plain <table> for Element.table
  lib/
    api.ts                   fetch wrappers (getDocs, getDoc, ask, getEval)
    types.ts
```

The only shared state is `target` in `DocView`. FieldsPanel and AskPanel set it, and PdfViewer reads it.

## 5. Key mechanics

**Highlight overlay**
- Each `<Page>` sits in a `position: relative` wrapper.
- `onLoadSuccess` gives the page's size in points (`originalWidth`). Scale = rendered width ÷ `originalWidth`.
- The highlight is an absolutely positioned div at `bbox × scale`, with a semi-transparent fill and a short pulse.
- When `target` changes, scroll that page's wrapper into view (`ref.scrollIntoView`).

**react-pdf setup (Next.js gotchas)**
- Import the viewer with `dynamic(..., { ssr: false })`. pdf.js needs `window`.
- Set the worker once: `pdfjs.GlobalWorkerOptions.workerSrc` (follow react-pdf's README for its version).
- **Japanese PDFs need cMaps.** Pass `options={{ cMapUrl: \`https://unpkg.com/pdfjs-dist@${pdfjs.version}/cmaps/\`, cMapPacked: true }}`. Without it, Japanese text renders blank or garbled. (This needs internet. For offline use, copy `pdfjs-dist/cmaps` into `public/`.)
- Render pages lazily, or cap at about 20 pages, for long annual reports.

**Fields tab**
- One row per field: name, value, ✓ verified or ⚠ "quote not found", and the page number.
- Click a row → `setTarget`. A missing value shows "—", never a guess.

**Ask tab**
- An input with 3 example questions as buttons, useful for the demo.
- The answer text contains `[1] [2]` markers, rendered as clickable chips → `setTarget`.
- Under the answer, list each citation by type:
  - text: quote snippet
  - table: `<TableView>`
  - chart or figure: crop image
- `approximate: true` → show the badge "approximate, read from chart".
- `unverified_numbers` → wrap those strings in the answer with a warning style and the tooltip "not found in cited sources".
- Loading: a spinner, because the LLM runs over a tunnel and can take 5–20 s.
- Error: "LLM unreachable — check LLM_BASE_URL". During a demo this is the most likely failure, so make it obvious.

**Eval page**
- One table per metric group from `eval.json`: fields, evidence, tables, charts, search, answers, speed.
- Failure cases: screenshot + what went wrong + the fix.
- Show only numbers that `run_eval` produced. Nothing is typed in by hand.

## 6. Day-by-day (fits doclens_plan.md §9)

| Day | Date | Frontend work | Done when |
|---|---|---|---|
| 3 | 25 Oct | `create-next-app`, rewrites, types, doc list, PdfViewer with cMaps, FieldsPanel, highlight | Click a field → box on the right spot of the right page, on an English **and** a Japanese doc |
| 4 | 26 Oct | AskPanel: chips, number flags, loading/error states | Cited answer; clicking `[1]` jumps to the passage |
| 5 | 27 Oct | TableView, crop images, "approximate" badge | Chart question shows the crop and the values read |
| 6 | 28 Oct | Eval page | Real results table rendered from `eval.json` |
| 7 | 29 Oct | Polish (empty states, page-number labels), record GIF + video | GIF for the top of the README |

**Cut order (frontend only):** lazy page rendering → example-question buttons → eval failure-case screenshots (keep them in the README instead) → the whole frontend switches to Streamlit (doclens_plan.md cut 5; the API contract stays the same).

**Never cut:** the highlight on field and citation click. That interaction is the demo.

## 7. Interview talking points (frontend)

- **Why does the backend convert boxes?** One coordinate system on the wire, converted in one tested place. The frontend only scales.
- **Why no state library?** One piece of shared state (`target`) in one component. Add one when several pages share state.
- **Why rewrites instead of CORS?** Same origin in development, and nothing extra to configure.
- **Japanese PDFs:** cMaps, plus the font. Say what broke before you added them, if it did.

## 8. Verification

1. `uvicorn backend.app:app` and `npm run dev`, then open `http://localhost:3000`.
2. On the doc list, open one English doc and one Japanese doc. Japanese text must render (cMaps).
3. Fields tab: click 3 fields. Each box must sit on its quote, including on page 2 or later (scroll plus scale).
4. Ask tab: ask a question that needs a table and one that needs a chart. Chips jump to the right spot, the table renders, the crop appears and the "approximate" badge shows.
5. Stop the LLM (bad `LLM_BASE_URL`) and ask a question. The clear error appears and the page doesn't crash.
6. `npm run build` passes (type errors fail the build).
