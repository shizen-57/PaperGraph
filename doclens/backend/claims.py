"""Per-document research claims (contribution, limitation, method, dataset, result, future work), each with a
quote that verify.locate must find in the document."""
import re

from backend import llm, verify
from backend.schemas import Claim, ClaimsOut, Document, Element

MAX_CHARS = 40_000  # about a 20k-token budget
FOLDERS = {"papers", "drafts"}  # where claims make sense
# Sections worth reading when a paper is too long to send whole
KEEP = re.compile(r"abstract|introduction|contribution|method|approach|model|formulation|problem|experiment|"
                  r"result|evaluation|conclusion|limitation|discussion|future|概要|はじめに|手法|実験|結論", re.I)
REFS = re.compile(r"references|bibliography|参考文献", re.I)

SYSTEM = (
    "You extract research claims from a document. Elements are given as [element_id page] text. "
    "Return up to 12 claims, each with: claim_type (contribution, limitation, method, dataset, result, "
    "future_work), claim (one sentence in your words), quote (text copied EXACTLY from one element, "
    "at most 2 sentences) and element_id (the element the quote is from). "
    "Only claims the document itself makes; include limitations the authors admit."
)


def select(elements: list[Element]) -> list[Element]:
    els = [e for e in elements if e.type != "caption" and e.text.strip() and not REFS.search(e.heading or "")]
    if sum(len(e.text) for e in els) > MAX_CHARS:
        # ponytail: section-name filter; retrieve per claim type if papers with odd headings lose content
        els = [e for e in els if e.heading is None or KEEP.search(e.heading)]
    out, total = [], 0
    for e in els:
        if total + len(e.text) > MAX_CHARS:
            break
        out.append(e)
        total += len(e.text)
    return out


def extract_claims(doc: Document, elements: list[Element]) -> list[Claim]:
    body = "\n".join(f"[{e.id} p{e.page}] {e.text[:1500]}" for e in select(elements))
    raw = llm.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": f"Document: {doc.title} ({doc.folder})\n\n{body}"}],
        schema=ClaimsOut.model_json_schema(), max_tokens=3000,
    )
    claims = []
    for i, c in enumerate(ClaimsOut.model_validate_json(raw).claims):
        chk = verify.locate(c.quote, elements, prefer=c.element_id)
        claims.append(Claim(
            id=f"{doc.id}:k{i}", doc_id=doc.id, claim_type=c.claim_type, claim=c.claim, quote=c.quote,
            page=chk.page, element_id=chk.element_id, bbox=chk.bbox, quote_match=chk.score,
            verification="verified" if chk.found else "unverified",
        ))
    return claims
