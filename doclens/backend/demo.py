"""Seed a demo space for a first look and for screenshots: a few synthetic invoices, parsed and extracted, stored in the
database. No embeddings, so it needs no model download (Q&A needs `python -m backend.ingest`).

    python -m backend.demo                      # parse with PARSER (Docling if installed, else the PDF text layer), rules extractor
                                                # Bangla pages are always OCR'd with Tesseract (ben+eng): see parse.has_bengali_text
    python -m backend.demo --extractor llm      # use LLM_MODEL instead (see .env.example)
    NEXT_PUBLIC_SPACE=demo npm run dev          # in frontend/, then open http://localhost:3000/docs
"""
import argparse
import shutil
from pathlib import Path

from backend import extract, extract_rules, ingest, llm
from backend.db import DB, RESULTS, ROOT, dump
from backend.schemas import Space
from backend.walk import walk

DATA = ROOT / "eval" / "data"
SYNTH = DATA / "synth"  # kept for callers that import it
# Japanese (three layouts, clean and scanned), then English and Bangla. Paths are relative to eval/data.
DEMO = ["synth/clean/clean-000", "synth/clean/clean-002", "synth/scanned/scan-000", "synth/scanned/scan-001",
        "intl/en/en-000", "intl/en/en-001", "intl/bn/bn-000", "intl/bn/bn-001"]


def seed(db: DB, root: Path, space_id: str = "demo", extractor: str = "rules", names: list[str] = DEMO) -> list[str]:
    """Copies the invoices into `root`, parses and extracts them. Returns the document ids that got an extraction."""
    (root / "invoices").mkdir(parents=True, exist_ok=True)
    for n in names:
        shutil.copy(DATA / f"{n}.pdf", root / "invoices" / f"{Path(n).name}.pdf")
    space = Space(id=space_id, name="Demo invoices", root=str(root))
    ingest.ensure_space(db, space)
    done = []
    for f in walk(root):
        doc, elements = ingest.parse_file(f, space_id)
        ingest.save_elements(db, doc.id, elements)
        ingest.save_doc(db, doc)
        db.exec("DELETE FROM extractions WHERE doc_id=?", (doc.id,))
        if not elements:  # nothing was parsed (a scan with a text-layer parser): nothing to extract
            continue
        try:
            ex = (extract_rules.extract if extractor == "rules" else extract.extract)(doc.id, "invoice", elements)
        except (llm.LLMUnavailable, extract.ExtractionError) as e:
            print(f"{doc.id}: not extracted ({e})")
            continue
        db.exec("INSERT OR REPLACE INTO extractions VALUES (?, ?)", (doc.id, dump(ex)))
        done.append(doc.id)
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extractor", choices=["rules", "llm"], default="rules")
    ap.add_argument("--space", default="demo")
    ap.add_argument("--root", type=Path, default=ROOT / "data" / "demo_space")
    ap.add_argument("--only", nargs="+", metavar="PATH", help="seed just these documents, e.g. intl/en/en-000 (default: all of DEMO)")
    args = ap.parse_args()
    ids = seed(DB(RESULTS / "doclens.db"), args.root, args.space, args.extractor, args.only or DEMO)
    print(f"seeded {len(ids)} documents in space '{args.space}': {', '.join(ids)}")
    print(f"start the API, then in frontend/: NEXT_PUBLIC_SPACE={args.space} npm run dev")


if __name__ == "__main__":
    main()
