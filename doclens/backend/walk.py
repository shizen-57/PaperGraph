"""Walk a space folder: which files exist, what kind they are, and their content hash."""
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED = {".pdf": "pdf", ".pptx": "pptx", ".md": "md", ".markdown": "md", ".txt": "txt",
             ".png": "image", ".jpg": "image", ".jpeg": "image", ".tif": "image", ".tiff": "image", ".bmp": "image",
             ".webp": "image"}
_YEAR = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
_VERSION = re.compile(r"[ _-]v(\d+)$", re.I)


@dataclass
class SourceFile:
    path: Path
    rel: str  # relative to the space root, forward slashes
    doc_id: str
    folder: str
    file_type: str
    sha256: str
    year: int | None
    version: int | None  # 2 for problem_formulation_v2.pdf
    base: str  # stem without the version suffix, used to pair drafts


def doc_id_for(rel: str) -> str:
    """papers/2026 Client Selection.pdf -> papers-2026-client-selection"""
    stem = rel.rsplit(".", 1)[0]
    return re.sub(r"[^a-z0-9_]+", "-", stem.lower()).strip("-")


def walk(root: Path) -> list[SourceFile]:
    files = []
    for p in sorted(root.rglob("*")):
        rel_parts = p.relative_to(root).parts
        if not p.is_file() or p.suffix.lower() not in SUPPORTED or any(s.startswith(".") for s in rel_parts):
            continue
        rel = "/".join(rel_parts)
        with open(p, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        v = _VERSION.search(p.stem)
        y = _YEAR.search(p.stem)
        files.append(SourceFile(
            path=p, rel=rel, doc_id=doc_id_for(rel), folder=rel_parts[0] if len(rel_parts) > 1 else "misc",
            file_type=SUPPORTED[p.suffix.lower()], sha256=digest,
            year=int(y.group()) if y else None, version=int(v.group(1)) if v else None,
            base=p.stem[:v.start()] if v else p.stem,
        ))
    dupes = {f.doc_id for f in files if sum(g.doc_id == f.doc_id for g in files) > 1}
    if dupes:
        raise ValueError(f"Two files map to the same document id, rename one: {sorted(dupes)}")
    return files
