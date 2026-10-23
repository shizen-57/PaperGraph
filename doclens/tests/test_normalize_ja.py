import pytest

from backend.normalize_ja import (Amount, parse_amount, parse_date, parse_number, parse_percent, tax_flag, to_halfwidth,
                                  unit_multiplier)


def test_fullwidth_to_halfwidth():
    assert to_halfwidth("１２３ ＡＢＣ") == "123 ABC"


@pytest.mark.parametrize("raw,iso", [
    ("令和8年10月24日", "2026-10-24"),
    ("令和元年5月1日", "2019-05-01"),
    ("平成31年4月30日", "2019-04-30"),
    ("昭和64年1月7日", "1989-01-07"),
    ("大正15年12月25日", "1926-12-25"),
    ("明治45年7月30日", "1912-07-30"),
    ("令和８年１０月２４日", "2026-10-24"),
    ("R8.10.24", "2026-10-24"),
    ("H31.4.30", "2019-04-30"),
    ("R08/10/24", "2026-10-24"),
    ("2026/10/24", "2026-10-24"),
    ("２０２６年１０月２４日", "2026-10-24"),
    ("2026-1-5", "2026-01-05"),
    ("発行日: 2026.10.24", "2026-10-24"),
])
def test_dates(raw, iso):
    assert parse_date(raw) == iso


def test_year_month_only():
    assert parse_date("2026年3月期") == "2026-03"
    assert parse_date("令和8年3月") == "2026-03"


@pytest.mark.parametrize("raw", ["", "お支払い期限", "令和8年13月1日", "2026/02/30", "R8.2.30"])
def test_unreadable_or_impossible_dates(raw):
    assert parse_date(raw) is None


@pytest.mark.parametrize("raw,value", [
    ("1億2,000万円", 120_000_000),
    ("¥1,234", 1234),
    ("￥１２，３００－", 12300),  # full-width yen sign, comma and a trailing dash
    ("12,300円也", 12300),
    ("3千5百円", 3500),
    ("100万円", 1_000_000),
    ("1.5億円", 150_000_000),
    ("1,234百万円", 1_234_000_000),
    ("千万円", 10_000_000),
    ("一万二千円", 12000),
    ("壱万円", 10000),
    ("2兆3千億円", 2_300_000_000_000),
    ("1,234", 1234),
    ("0", 0),
])
def test_amounts(raw, value):
    assert parse_amount(raw) == Amount(value, None)


@pytest.mark.parametrize("raw", ["-1,234", "△1,234", "▲1,234円", "(1,234)", "−1,234"])
def test_negative_amounts(raw):
    assert parse_amount(raw).value == -1234


@pytest.mark.parametrize("raw", ["", "-", "―", "N/A", "約", "12abc"])
def test_not_an_amount(raw):
    assert parse_amount(raw) is None


@pytest.mark.parametrize("raw,tax", [
    ("¥11,000(税込)", "included"),
    ("11,000円 税込み", "included"),
    ("10,000円（税抜）", "excluded"),
    ("10,000円 税別", "excluded"),
    ("内税 1,000", "included"),
    ("外税 1,000", "excluded"),
    ("¥11,000", None),
])
def test_tax_flags_attach_to_the_amount(raw, tax):
    assert tax_flag(raw) == tax
    assert parse_amount(raw).tax == tax
    assert parse_amount(raw).value in (11000, 10000, 1000)


def test_percent_and_numbers():
    assert parse_percent("10%") == 0.1
    assert parse_percent("軽減税率 ８％") == 0.08
    assert parse_percent("※") is None
    assert parse_number("２個") == 2
    assert parse_number("1,200 kg") == 1200
    assert parse_number("3.5kg") == 3.5
    assert parse_number("なし") is None


def test_report_units():
    assert unit_multiplier("(単位:百万円)") == 1_000_000
    assert unit_multiplier("単位：千円") == 1000
    assert unit_multiplier("円") == 1
    assert unit_multiplier("Millions of yen") == 1
