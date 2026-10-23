"""Japanese business-document normalisation: full-width → half-width, era dates → ISO, amounts with 万/億, tax flags.

Everything here is deterministic code, so the LLM only has to copy a value as printed and this module turns it
into a typed value. The raw string stays available for the evidence check.

    parse_date("令和8年10月24日")  -> "2026-10-24"
    parse_date("R8.10.24")         -> "2026-10-24"
    parse_amount("1億2,000万円")    -> Amount(value=120000000, tax=None)
    parse_amount("△1,234")         -> Amount(value=-1234, tax=None)
    parse_amount("¥11,000(税込)")   -> Amount(value=11000, tax="included")
"""
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal, NamedTuple

# First year of each era (Gregorian). Year = base + n - 1, and 元年 is year 1.
ERA_BASE = {"明治": 1868, "大正": 1912, "昭和": 1926, "平成": 1989, "令和": 2019,
            "M": 1868, "T": 1912, "S": 1926, "H": 1989, "R": 2019}

_ERA_KANJI = re.compile(r"(明治|大正|昭和|平成|令和)\s*(元|\d{1,2})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?")
_ERA_ABBR = re.compile(r"(?<![A-Za-z])([MTSHR])\s*(\d{1,2})\s*[./\-]\s*(\d{1,2})(?:\s*[./\-]\s*(\d{1,2}))?(?![\d/])")
_WESTERN = re.compile(r"(?<!\d)(\d{4})\s*[年/\-.]\s*(\d{1,2})(?:\s*[月/\-.]\s*(\d{1,2}))?\s*日?(?![\d])")

Tax = Literal["included", "excluded"]


class Amount(NamedTuple):
    value: int | float
    tax: Tax | None = None


def to_halfwidth(s: str) -> str:
    """NFKC: １２３ → 123, ＡＢＣ → ABC, ￥ → ¥, （） → ()."""
    return unicodedata.normalize("NFKC", s)


# --- dates ---

def _iso(year: int, month: int, day: int | None) -> str | None:
    try:
        if day is None:
            return f"{year:04d}-{date(year, month, 1).month:02d}"  # year + month only, e.g. "2026年3月期"
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_date(s: str) -> str | None:
    """ISO date (or YYYY-MM when the day is missing) from Western, era or abbreviated-era notation; None if unreadable."""
    s = to_halfwidth(s)
    if m := _ERA_KANJI.search(s):
        era, n, month, day = m.groups()
        return _iso(ERA_BASE[era] + (1 if n == "元" else int(n)) - 1, int(month), int(day) if day else None)
    if m := _ERA_ABBR.search(s):
        era, n, month, day = m.groups()
        return _iso(ERA_BASE[era] + int(n) - 1, int(month), int(day) if day else None)
    if m := _WESTERN.search(s):
        year, month, day = m.groups()
        return _iso(int(year), int(month), int(day) if day else None)
    return None


# --- amounts ---

_KDIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
           "壱": 1, "弐": 2, "参": 3}  # 壱弐参 are the formal numerals used on invoices and contracts
_SMALL = {"十": 10, "拾": 10, "百": 100, "千": 1000}
_LARGE = {"万": 10**4, "億": 10**8, "兆": 10**12}
_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?|[〇零一二三四五六七八九壱弐参]+|[十拾百千万億兆]")
_TAX_WORDS = re.compile(r"税込み?|税抜き?|税別|内税|外税")
_NEGATIVE = ("-", "−", "▲", "△", "マイナス")
_NOISE = re.compile(r"JPY|yen|円也|円|也|約|[¥\s]", re.I)


def tax_flag(s: str) -> Tax | None:
    """税込 / 内税 → included; 税抜 / 税別 / 外税 → excluded. The first one in the text wins."""
    m = re.search(r"税込|内税|税抜|税別|外税", to_halfwidth(s))
    if not m:
        return None
    return "included" if m.group() in ("税込", "内税") else "excluded"


def _evaluate(tokens: list[str]) -> Decimal:
    """Left-to-right evaluation: numbers wait for a unit; 十百千 add to the current block, 万億兆 close it."""
    total, section, pending = Decimal(0), Decimal(0), None
    for t in tokens:
        if t in _SMALL:
            section += (pending if pending is not None else 1) * _SMALL[t]
            pending = None
        elif t in _LARGE:
            block = section + (pending or 0)
            total += (block or 1) * _LARGE[t]
            section, pending = Decimal(0), None
        elif t[0] in _KDIGIT:
            pending = Decimal("".join(str(_KDIGIT[c]) for c in t))  # 二〇二六 is positional
        else:
            pending = Decimal(t.replace(",", ""))
    return total + section + (pending or 0)


def parse_amount(s: str) -> Amount | None:
    """Yen amount with its tax flag. Handles ¥/円, commas, 千/万/億/兆 (also 百万), kanji numerals, a leading
    -, △ or ▲ and accounting parentheses as negative, and a trailing - or 円也. A lone dash is 'no value' → None."""
    s = to_halfwidth(s)
    tax = tax_flag(s)
    s = _TAX_WORDS.sub("", s).strip()
    negative = False
    if re.fullmatch(r"\(.*\)", s):  # accounting negative; after stripping a (税込) note so it isn't mistaken for one
        negative, s = True, s[1:-1]
    s = s.replace("(", "").replace(")", "")
    for sign in _NEGATIVE:
        if s.startswith(sign):
            negative, s = True, s[len(sign):]
            break
    s = s.rstrip("-―ー")
    s = _NOISE.sub("", s)
    s = s.rstrip("-―")
    if not s:
        return None
    tokens = _TOKEN.findall(s)
    if "".join(tokens) != s:  # something we don't understand is left over: better None than a wrong number
        return None
    try:
        value = _evaluate(tokens)
    except InvalidOperation:
        return None
    value = -value if negative else value
    return Amount(int(value) if value == value.to_integral_value() else float(value), tax)


def parse_percent(s: str) -> float | None:
    """'10%' / '８％' / '軽減税率8%' → 0.1 / 0.08. A bare '※' (reduced-rate mark) is not a number → None."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", to_halfwidth(s))
    return round(float(m.group(1)) / 100, 4) if m else None


def parse_number(s: str) -> int | float | None:
    """Plain quantity: 1,200 / ２個 / 3.5kg → the first number in the text."""
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", to_halfwidth(s))
    if not m:
        return None
    v = float(m.group().replace(",", ""))
    return int(v) if v == int(v) else v


def unit_multiplier(s: str) -> int:
    """'(単位:百万円)' → 1_000_000, '千円' → 1000, 'Millions of yen' is not understood → 1."""
    m = re.search(r"([十百千万億兆]+)円", to_halfwidth(s))
    if not m:
        return 1
    a = parse_amount("1" + m.group(1))
    return int(a.value) if a else 1
