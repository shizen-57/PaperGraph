from pathlib import Path

from backend import parse, vlm_parser

MD = """# 請求書

請求書番号: INV-1

<table><tr><td>品名</td><td>数量</td><td>金額</td></tr><tr><td>商品A</td><td>2</td><td>1,000</td></tr></table>

| 小計 | 1,000円 |
|---|---|
| 合計 | 1,100円 |
"""


def test_markdown_becomes_elements(monkeypatch):
    sections = parse.Sections()
    els = []
    vlm_parser.markdown_elements(MD, "d", 2, els, sections)
    assert [e.type for e in els] == ["text", "text", "table", "table"]
    assert els[0].text == "請求書" and els[1].heading == "請求書"
    assert els[2].table.header == ["品名", "数量", "金額"] and els[2].table.rows == [["商品A", "2", "1,000"]]
    assert els[3].table.header == ["小計", "1,000円"] and els[3].table.rows == [["合計", "1,100円"]]
    assert all(e.page == 2 and e.bbox is None for e in els)


def test_parse_pdf_vlm_renders_every_page_and_wraps_fences(monkeypatch):
    calls = []
    monkeypatch.setattr(vlm_parser, "page_markdown", lambda png: (calls.append(len(png)) or "請求書番号: INV-1"))
    pdf = Path(__file__).parent.parent / "eval" / "data" / "synth" / "clean" / "clean-000.pdf"
    els, sizes, _ = vlm_parser.parse_pdf_vlm(pdf, "d")
    assert len(calls) == 1 and calls[0] > 1000 and sizes[0][0] > 500 and els[0].text == "請求書番号: INV-1"
    assert parse.PARSERS["vlm"]  # reachable as PARSER=vlm
