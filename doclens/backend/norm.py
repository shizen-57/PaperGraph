"""Text normalisation shared by the evidence check, the number check and eval."""
import re
import unicodedata

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CITE = re.compile(r"\[\d+\]")


def norm(s: str) -> str:
    """NFKC (full-width → half-width), casefold, drop all whitespace.

    Whitespace is dropped rather than collapsed because Docling inserts line breaks inside
    Japanese text, and the LLM's quote won't have them.
    """
    return "".join(unicodedata.normalize("NFKC", s).casefold().split())


def numbers(s: str) -> list[str]:
    """Numbers in s, commas stripped, citation markers like [2] ignored."""
    s = _CITE.sub(" ", unicodedata.normalize("NFKC", s))
    return [m.replace(",", "") for m in _NUM.findall(s)]
