import json
import re
import zlib
from pathlib import Path

import numpy as np
import pytest

from backend import llm, search
from backend.db import DB
from backend.ingest import ingest
from backend.schemas import Space

FIXTURE = Path(__file__).parent / "fixtures" / "space"
SPACE = Space(id="thesis", name="Test", root=str(FIXTURE))


def fake_embed(texts: list[str]) -> np.ndarray:
    """Hashed bag of words: similar text → similar vector, no model download."""
    m = np.zeros((len(texts), 256), dtype=np.float32)
    for i, t in enumerate(texts):
        for w in search.terms(t):
            m[i, zlib.crc32(w.encode()) % 256] += 1
    m[:, 0] += 1e-3  # no zero rows
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def fake_chat(messages, schema=None, **kw):
    """Answers with one real quote from source [1] and one invented quote for [2]; claims likewise."""
    user = messages[-1]["content"]
    title = (schema or {}).get("title")
    if title == "AnswerOut":
        first = user.split("Sources:\n", 1)[1].split("\n", 2)[1]  # first line of source [1]'s text
        return json.dumps({"answer": "It jointly optimizes selection and allocation, reaching 999 accuracy [1]. "
                                     "Others disagree [2].",
                           "citations": [{"n": 1, "quote": first[:60]},
                                         {"n": 2, "quote": "a sentence that is nowhere in the corpus at all"}]})
    if title == "ClaimsOut":
        eid, text = re.search(r"\[(e\d+) p\d+\] (.{30,})", user).groups()
        return json.dumps({"claims": [
            {"claim_type": "contribution", "claim": "x", "quote": text[:50], "element_id": eid},
            {"claim_type": "limitation", "claim": "y", "quote": "an invented limitation sentence", "element_id": eid},
        ]})
    if title == "ChangeOut":
        a, b = user.split("Version A:\n", 1)[1].split("\n\nVersion B:\n")
        return json.dumps({"summary": "Redefined fairness.", "quote_a": a.split("\n\n")[-1][:40],
                           "quote_b": b.split("\n\n")[-1][:40]})
    raise AssertionError(f"unexpected LLM call: {title}")


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(search, "embed", fake_embed)
    monkeypatch.setattr(llm, "chat", fake_chat)


@pytest.fixture
def ingested(tmp_path, fakes):
    """The fixture space, ingested into a temp results dir."""
    results = tmp_path / "results"
    db = DB(results / "doclens.db")
    log = ingest(db, SPACE, results)
    return db, results, log
