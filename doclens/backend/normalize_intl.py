"""English and Bangla normalisation for the same job normalize_ja.py does for Japanese: the model copies a value as printed,
and code turns it into an ISO date or an integer amount.

    parse_date("24 October 2026")        -> "2026-10-24"
    parse_date("২৪ অক্টোবর ২০২৬")          -> "2026-10-24"
    parse_amount("$1,234.50")            -> Amount(value=1234.5)
    parse_amount("৳ ১২,৩৪,৫৬৭")            -> Amount(value=1234567)      # lakh grouping: 12,34,567
    parse_amount("১২ লাখ টাকা")             -> Amount(value=1200000)
    parse_amount("Tk 2.5 crore")         -> Amount(value=25000000)

Only unambiguous dates are read: `03/04/2026` is day-first in Bangladesh and month-first in the US, so it returns None rather than a guess.
"""
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from backend.normalize_ja import Amount

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12,
    "জানুয়ারি": 1, "জানুয়ারী": 1, "ফেব্রুয়ারি": 2, "ফেব্রুয়ারী": 2, "মার্চ": 3, "এপ্রিল": 4, "মে": 5, "জুন": 6, "জুলাই": 7,
    "আগস্ট": 8, "সেপ্টেম্বর": 9, "অক্টোবর": 10, "নভেম্বর": 11, "ডিসেম্বর": 12,
}
_MONTH = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
_DAY_MONTH_YEAR = re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[\s.,-]+({_MONTH})\.?[\s.,-]+(\d{{4}})(?!\d)", re.I)
_MONTH_DAY_YEAR = re.compile(rf"({_MONTH})\.?[\s.,-]+(\d{{1,2}})(?:st|nd|rd|th)?[\s.,-]+(\d{{4}})(?!\d)", re.I)
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")

# Units: lakh (লাখ / লক্ষ) = 100,000 and crore (কোটি) = 10,000,000 are the everyday units in Bangladesh and India.
_UNITS = {"lakh": 10**5, "lac": 10**5, "লাখ": 10**5, "লক্ষ": 10**5, "crore": 10**7, "কোটি": 10**7, "thousand": 10**3, "হাজার": 10**3,
          "million": 10**6, "মিলিয়ন": 10**6, "billion": 10**9, "k": 10**3}
_UNIT_RE = "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True))
_NUMBER = re.compile(rf"(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_RE})?", re.I)
_CURRENCY = re.compile(r"[$€£₹৳¥]|\b(?:USD|EUR|GBP|BDT|INR|JPY|Tk|Taka|Rs|US\$)\b\.?|টাকা|ডলার|\s", re.I)


def to_ascii_digits(s: str) -> str:
    """NFKC, then Bangla digits to ASCII (NFKC leaves ০১২৩ alone)."""
    return unicodedata.normalize("NFKC", s).translate(BN_DIGITS)


def parse_date(s: str) -> str | None:
    """ISO date from '24 October 2026', 'Oct 24, 2026', '২৪ অক্টোবর ২০২৬' or '2026-10-24'; None if unreadable or impossible."""
    s = to_ascii_digits(s)
    if m := _DAY_MONTH_YEAR.search(s):
        day, month, year = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
    elif m := _MONTH_DAY_YEAR.search(s):
        month, day, year = MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
    elif m := _ISO.search(s):
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        return None
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_amount(s: str) -> Amount | None:
    """Money with a currency sign or code, Bangla or ASCII digits, Western (1,234,567) or lakh (12,34,567) grouping, decimals,
    and optional lakh/crore/thousand words. A leading '-' or accounting parentheses make it negative. None if anything is left over."""
    s = to_ascii_digits(s).strip()
    negative = s.startswith("-") or s.startswith("−") or bool(re.fullmatch(r"\(.*\)", s))
    s = s.strip("()-−")
    s = _CURRENCY.sub(" ", s).strip()
    if not s or not re.fullmatch(rf"(?:{_NUMBER.pattern}\s*)+", s, re.I):
        return None
    total = Decimal(0)
    try:
        for num, unit in _NUMBER.findall(s):
            total += Decimal(num.replace(",", "")) * (_UNITS[unit.lower()] if unit else 1)
    except InvalidOperation:
        return None
    total = -total if negative else total
    return Amount(int(total) if total == total.to_integral_value() else float(total), None)
