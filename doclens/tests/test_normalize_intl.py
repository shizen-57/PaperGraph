import pytest

from backend.normalize_intl import Amount, parse_amount, parse_date, to_ascii_digits


def test_bangla_digits_become_ascii():
    assert to_ascii_digits("২০২৬-১০-২৪ ১২,৩৪,৫৬৭") == "2026-10-24 12,34,567"


@pytest.mark.parametrize("raw,iso", [
    ("24 October 2026", "2026-10-24"),
    ("Oct 24, 2026", "2026-10-24"),
    ("October 24th, 2026", "2026-10-24"),
    ("1 Jan 2027", "2027-01-01"),
    ("2026-10-24", "2026-10-24"),
    ("Date: 05 sept 2026", "2026-09-05"),
    ("২৪ অক্টোবর ২০২৬", "2026-10-24"),
    ("০১ জানুয়ারি ২০২৭", "2027-01-01"),
    ("১৫ ফেব্রুয়ারী ২০২৬", "2026-02-15"),
])
def test_dates(raw, iso):
    assert parse_date(raw) == iso


@pytest.mark.parametrize("raw", ["", "03/04/2026", "31 February 2026", "yesterday", "October 2026"])
def test_ambiguous_or_impossible_dates_are_not_guessed(raw):
    assert parse_date(raw) is None


@pytest.mark.parametrize("raw,value", [
    ("$1,234.50", 1234.5),
    ("USD 1,000", 1000),
    ("£ 99", 99),
    ("1,234.00", 1234),
    ("৳ ১২,৩৪,৫৬৭", 1234567),  # lakh grouping, Bangla digits
    ("৳১,২০০", 1200),
    ("Tk 12,34,567", 1234567),
    ("১২ লাখ টাকা", 1_200_000),
    ("2.5 crore", 25_000_000),
    ("১ কোটি ২০ লাখ", 12_000_000),
    ("500 টাকা", 500),
    ("BDT 7,500.00", 7500),
])
def test_amounts(raw, value):
    assert parse_amount(raw) == Amount(value, None)


@pytest.mark.parametrize("raw,value", [("-$50", -50), ("($1,200.00)", -1200), ("−৳ ৫০০", -500)])
def test_negative_amounts(raw, value):
    assert parse_amount(raw).value == value


@pytest.mark.parametrize("raw", ["", "N/A", "twelve dollars", "$", "১২ abc", "1,2,x"])
def test_not_an_amount(raw):
    assert parse_amount(raw) is None
