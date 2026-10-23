"""Verification, kept apart from generation: the LLM never grades its own answer.

Quote matching, the number check, citation validity and the confidence score all live here.
"""
import re
from difflib import SequenceMatcher

from backend.norm import norm, numbers
from backend.schemas import ConfidenceLabel, Element, QuoteCheck

FOUND = 0.9  # quote_match at or above this counts as verified

# Blueprint weights. Each signal is 0..1.
WEIGHTS = {"retrieval": 0.30, "quote": 0.30, "citations": 0.20, "numbers": 0.10, "coverage": 0.10}
BANDS: list[tuple[float, ConfidenceLabel]] = [(0.90, "High"), (0.75, "Medium"), (0.50, "Low"), (0.0, "Unverified")]

# ponytail: linear rescale of BGE-M3 cosine to 0..1; recalibrate on the QA set once it exists
COS_LO, COS_HI = 0.30, 0.75


def quote_score(quote: str, text: str) -> float:
    """1.0 for an exact (normalised) substring; otherwise the share of the quote matched, in order,
    inside the best window of the text. Normalising first absorbs whitespace, line breaks and full-width digits."""
    q, t = norm(quote), norm(text)
    if not q or not t:
        return 0.0
    if q in t:
        return 1.0
    sm = SequenceMatcher(None, q, t, autojunk=False)
    m = sm.find_longest_match(0, len(q), 0, len(t))
    lo = max(0, m.b - m.a - len(q) // 5)
    window = t[lo:lo + len(q) + 2 * (len(q) // 5)]  # where the quote would sit, with some slack
    matched = sum(b.size for b in SequenceMatcher(None, q, window, autojunk=False).get_matching_blocks())
    return min(round(matched / len(q), 3), 0.99)  # 1.0 is reserved for exact matches


def locate(quote: str, elements: list[Element], prefer: str | None = None) -> QuoteCheck:
    """Best-matching element for a quote. `prefer` (the element the model named) wins ties."""
    best, best_score = None, 0.0
    ordered = sorted(elements, key=lambda e: e.id != prefer)
    for el in ordered:
        s = quote_score(quote, el.text)
        if s > best_score:
            best, best_score = el, s
        if s == 1.0:
            break
    return QuoteCheck(score=best_score, found=best_score >= FOUND, element_id=best.id if best else None,
                      page=best.page if best else None, bbox=best.bbox if best else None)


def check_numbers(answer: str, sources: list[str]) -> list[str]:
    """Numbers in the answer that appear in none of the sources."""
    # ponytail: digits only; kanji numerals (三百) and unit conversions slip through. Kept as a failure case.
    found = {float(n) for s in sources for n in numbers(s)}
    return [n for n in dict.fromkeys(numbers(answer)) if float(n) not in found]


def coverage(answer: str) -> float:
    """Share of sentences that carry at least one [n] citation."""
    sentences = [s for s in re.split(r"(?<=[.!?。])\s+", answer.strip()) if len(s.strip()) > 3]
    return sum(bool(re.search(r"\[\d+\]", s)) for s in sentences) / len(sentences) if sentences else 0.0


def rescale_cos(c: float) -> float:
    return min(max((c - COS_LO) / (COS_HI - COS_LO), 0.0), 1.0)


def confidence(signals: dict[str, float]) -> tuple[float, ConfidenceLabel]:
    score = round(sum(WEIGHTS[k] * signals[k] for k in WEIGHTS), 3)
    return score, next(label for floor, label in BANDS if score >= floor)
