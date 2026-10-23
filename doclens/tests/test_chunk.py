from backend import chunk
from backend.parse import Sections
from backend.schemas import Element, Table


def el(i, text, heading="2 Method", type="text", page=1, table=None):
    return Element(id=f"e{i}", doc_id="d", type=type, page=page, bbox=None, text=text, heading=heading, table=table)


def test_section_change_starts_new_chunk():
    cs = chunk.chunk_doc([el(0, "intro", "1 Intro"), el(1, "method a"), el(2, "method b")])
    assert [c.text for c in cs] == ["intro", "method a\n\nmethod b"]
    assert cs[1].section_path == "2 Method" and cs[1].id == "d:c1" and cs[1].element_ids == ["e1", "e2"]


def test_tables_stay_whole_and_alone():
    t = Table(header=["k", "v"], rows=[["a", "1"]] * 100)
    cs = chunk.chunk_doc([el(0, "before"), el(1, "x " * 1000, type="table", table=t), el(2, "after")])
    assert [c.element_ids for c in cs] == [["e0"], ["e1"], ["e2"]]


def test_split_only_at_paragraph_boundaries_with_overlap(monkeypatch):
    monkeypatch.setattr(chunk, "MAX_TOKENS", 10)
    cs = chunk.chunk_doc([el(0, "one two three four"), el(1, "five six seven eight"), el(2, "nine ten eleven twelve")])
    assert [c.element_ids for c in cs] == [["e0", "e1"], ["e1", "e2"]]  # e1 repeated as overlap
    assert cs[1].page_start == 1


def test_captions_skipped():
    assert chunk.chunk_doc([el(0, "Figure 1: x", type="caption")]) == []


def test_section_path_from_numbering():
    s = Sections()
    s.push("3 Method")
    s.push("3.2 Client selection")
    assert s.path == "3 Method > 3.2 Client selection"
    s.push("4 Results")
    assert s.path == "4 Results"
