from pathlib import Path

from backend import parse, router, vlm_parser
from backend.schemas import Element, ExtractedField, Extraction, Table

SYNTH = Path(__file__).parent.parent / "eval" / "data" / "synth"


def el(id_, page, type_="text", table=None):
    return Element(id=id_, doc_id="d", type=type_, page=page, bbox=None, text=id_, table=table)


def test_text_layer_tells_clean_from_scanned_pages():
    assert router.page_text_chars(SYNTH / "clean" / "clean-000.pdf")[0] > 200
    assert router.page_text_chars(SYNTH / "scanned" / "scan-000.pdf")[0] < router.MIN_TEXT_CHARS


def test_decide_by_signal():
    good = Table(header=["a", "b"], rows=[["1", "2"], ["3", "4"]])
    sparse = Table(header=["a", "b"], rows=[["1", ""], ["", ""]])
    ragged = Table(header=["a", "b"], rows=[["1"], ["3", "4"]])
    els = [el("t1", 1, "table", good), el("t2", 2, "table", sparse), el("t3", 3, "table", ragged), el("f", 4, "figure")]
    d = router.decide([500, 500, 500, 500, 5], els)
    assert [x.route for x in d] == ["docling", "vlm", "vlm", "vlm", "vlm"]
    assert "empty" in d[1].reasons[0] and "different lengths" in d[2].reasons[0]
    assert d[3].reasons == ["figure on the page"] and d[4].reasons[0].startswith("scanned")


def test_second_pass_signal():
    d = router.decide([500, 500], [], unverified={1: 2, 2: 3})
    assert [x.route for x in d] == ["docling", "vlm"]


def field(page, status):
    return ExtractedField(name="x", kind="text", raw="a", value="a", quote="a", page=page, element_id="e0", bbox=None,
                          quote_match=1.0, value_in_quote=True, status=status)


def test_escalate_pages_with_too_many_unverified_fields():
    ex = Extraction(doc_id="d", doc_type="invoice", checks=[], model="m", seconds=0,
                    fields=[field(1, "unverified")] * 3 + [field(2, "unverified")] * 2 + [field(2, "verified")])
    assert router.escalate(ex) == {1}


def test_router_keeps_docling_pages_and_swaps_in_vlm_pages(monkeypatch):
    path = SYNTH / "scanned" / "scan-000.pdf"  # one page, no text layer: the whole document goes to the VLM
    called = []
    monkeypatch.setattr(parse, "parse_pdf", lambda *a: called.append("docling") or ([], [], None))
    monkeypatch.setattr(vlm_parser, "parse_pdf_vlm", lambda p, d, pages=None: ([el("v", 1)], [(595.0, 842.0)], None))
    elements, sizes, _ = router.parse_pdf_router(path, "d")
    assert called == [] and [e.id for e in elements] == ["e0"] and router.LAST["routes"][0]["route"] == "vlm"

    clean = SYNTH / "clean" / "clean-000.pdf"
    monkeypatch.setattr(parse, "parse_pdf", lambda *a: ([el("a", 1), el("b", 1)], [(595.0, 842.0)], "T"))
    monkeypatch.setattr(vlm_parser, "parse_pdf_vlm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no VLM expected")))
    elements, _, title = router.parse_pdf_router(clean, "d")
    assert len(elements) == 2 and title == "T" and router.LAST["routes"][0]["route"] == "docling"
    assert router.LAST["vlm_seconds"] == 0.0
