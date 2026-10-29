from eval import failures as f


def text(s):
    return f.norm(s)


def test_present_ignores_separators_and_width():
    assert f.present(85448, text("合計 85,448円")) and f.present(85448, text("合計 ８５，４４８円"))
    assert f.present("2026-10-24", text("令和8年10月24日"), shown="令和8年10月24日")
    assert not f.present(85448, text("合計 85,000円"))


def test_field_causes():
    t = text("発行日 令和8年10月24日 合計 ¥3,300 株式会社A 御中 株式会社B")
    check = lambda name, pred, gold, **kw: f.classify_field(name, pred, gold, t, kw.get("shown"), kw.get("raw"), kw.get("other"))  # noqa: E731
    assert check("total", 3300, 3300) is None
    assert check("issuer", "株式会社A", "株式会社B", other="株式会社A") == "role confusion"
    assert check("recipient", "株式会社A 様", "株式会社A") == "copy boundary"
    assert check("invoice_number", "請求書番号：INV-1", "INV-1") == "copy boundary"
    assert check("total", 3300, 9999) == "not in the parsed text"
    assert check("total", None, 3300) == "present, not extracted"
    assert check("total", 3000, 3300) == "hallucinated"  # 3,000 is nowhere in the text
    t2 = text("小計 ¥3,000 合計 ¥3,300")
    assert f.classify_field("total", 3000, 3300, t2, None, None, None) == "wrong choice"
    assert f.classify_field("issue_date", "2026-10-25", "2026-10-24", text("令和8年10月24日"), "令和8年10月24日", "令和8年10月24日", None) == "normalisation"


def test_rows():
    gold = [{"name": "商品A", "quantity": 2, "unit_price": 500, "amount": 1000}, {"name": "商品B", "quantity": 1, "unit_price": 2000, "amount": 2000}]
    t = text("商品A 2 500 1,000 商品B 1 2,000 2,000")
    assert f.classify_rows(gold, gold, t) == []
    assert f.classify_rows(gold[:1], gold, t) == ["row lost or merged"]
    assert f.classify_rows(gold[:1], gold, text("商品A 2 500 1,000")) == ["not in the parsed text"]
    extra = gold + [{"name": "商品C", "quantity": 1, "unit_price": 1, "amount": 1}]
    assert f.classify_rows(extra, gold, t) == ["hallucinated"]
