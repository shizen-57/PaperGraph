"""Rule-based invoice extractor: regexes over the parsed lines. No LLM, no network.

It exists as (1) the baseline every LLM run is compared against, and (2) a fallback for `OFFLINE=1` without a local
model. It returns the same InvoiceOut as the LLM, so normalisation, evidence checks and consistency checks are shared.
It knows common Japanese and English labels, not layouts: expect it to break on wording it hasn't seen.
"""
import re
import time

from backend import extract as base
from backend.normalize_intl import MONTHS
from backend.schemas import Cited, DocType, Element, Extraction, not_stated

D = "0-9０-９০-৯"  # ASCII, full-width and Bangla digits
_M = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
DATE = (rf"(?:(?:令和|平成|昭和)\s*[{D}元]+\s*年\s*[{D}]+\s*月\s*[{D}]+\s*日|[RHS][{D}]+[./][{D}]+[./][{D}]+"
        rf"|[{D}]{{4}}\s*[年/.\-]\s*[{D}]+\s*[月/.\-]\s*[{D}]+\s*日?"
        rf"|[{D}]{{1,2}}(?:st|nd|rd|th)?\s+(?i:{_M})\.?\s+[{D}]{{4}}|(?i:{_M})\.?\s+[{D}]{{1,2}}(?:st|nd|rd|th)?,?\s+[{D}]{{4}})")
AMT = rf"(?:[¥￥$€£৳]|USD|Tk\.?|BDT)?\s*[{D}][{D},，]*(?:\.[{D}]+)?\s*(?:円|টাকা)?"
OCR_JUNK = r"(?:[টb&]\s*)?"  # Tesseract reads the taka sign ৳ as ট or &; kept outside the captured value
SEP = r"[\s:：|]*"
COMPANY = r"(?:株式会社|有限会社|合同会社)[^\s\d|]{1,12}|[^\s\d|]{1,12}(?:株式会社|有限会社|合同会社)"

LABELS = {
    "invoice_number": [rf"(?:請求書番号|請求番号|請求書No\.?|(?i:invoice\s*(?:no\.?|number|#))|চালান\s*(?:নম্বর|নং)|ইনভয়েস\s*(?:নম্বর|নং)){SEP}([^\s|]*[0-9A-Za-z০-৯][^\s|]*)"],
    "issue_date": [rf"(?:発行日|請求日|(?i:date of issue|issue date|invoice date)|(?<!(?i:due ))(?i:date)|চালানের\s*তারিখ|(?<!শেষ\s)তারিখ){SEP}({DATE})"],
    "due_date": [rf"(?:支払期限|お支払期限|お支払期日|支払期日|(?i:payment due|due date|due)|পরিশোধের\s*শেষ\s*তারিখ|শেষ\s*তারিখ){SEP}({DATE})"],
    "subtotal": [rf"(?:小計|(?i:sub-?\s?total)|উপমোট|সাব-?টোটাল){SEP}{OCR_JUNK}({AMT})"],
    "tax": [rf"(?:消費税合計|消費税額|税額合計){SEP}({AMT})",
            rf"(?:消費税|税額|(?i:sales tax|vat|gst|tax)|ভ্যাট|কর)\s*(?:[(（][^)）]*[)）])?{SEP}{OCR_JUNK}({AMT})"],
    "total": [rf"(?<![小税উপ])(?:合計金額|合計|ご請求金額|請求金額|(?i:\b(?:total due|grand total|amount due|balance due|total))|সর্বমোট|মোট){SEP}{OCR_JUNK}({AMT})"],
}
LAST = {"total"}  # appears in a headline box and again at the bottom: take the bottom one
NAME_COLS = ("品名", "品目", "摘要", "商品名", "Description", "Item")
COLS = {"quantity": ("数量", "Qty", "Quantity", "পরিমাণ"), "unit_price": ("単価", "Unit Price", "Price", "একক মূল্য"), "tax_rate": ("税率",),
        "amount": ("金額", "Amount", "মোট")}
NUMERIC = re.compile(rf"^[¥￥$€£৳]?[{D},，.]+円?$|^[{D}]+[%％](?:\(軽減\))?$")
STOP = re.compile(r"小計|Subtotal|合計|Total|উপমোট|সর্বমোট")


def lines_of(elements: list[Element]) -> list[tuple[str, str]]:
    """(element_id, line). Table elements contribute their rows in Markdown, caption first."""
    out = []
    for e in elements:
        for ln in e.text.split("\n"):
            if ln.strip() and not re.fullmatch(r"\|[-|\s]+\|", ln.strip()):
                out.append((e.id, ln.strip()))
    return out


def header_fields(lines: list[tuple[str, str]]) -> dict[str, Cited]:
    found = {k: not_stated() for k in LABELS}
    for name, patterns in LABELS.items():
        for pat in patterns:
            hits = [(eid, m) for eid, ln in lines if (m := re.search(pat, ln))]
            if hits:
                eid, m = hits[-1] if name in LAST else hits[0]
                found[name] = Cited(value=m.group(1).strip(" |"), quote=m.group(0).strip(" |"), element_id=eid)
                break
    return found


PARTY_LABELS = {
    "issuer": r"(?i:from|seller|supplier|issued\s+by)|বিক্রেতা|প্রেরক",
    "recipient": r"(?i:bill(?:ed)?\s+to|customer|client)|ক্রেতা|বিল\s*প্রাপক",
}


def labelled_party(lines: list[tuple[str, str]], label: str) -> Cited:
    """English and Bangla invoices name the parties under a label: the name is after it on the same line, or on the next line."""
    for i, (eid, ln) in enumerate(lines):
        m = re.fullmatch(rf"\s*(?:{label})\s*[:：]?\s*(.*?)\s*", ln)
        if not m:
            continue
        if m.group(1):
            return Cited(value=m.group(1), quote=ln.strip(), element_id=eid)
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            return Cited(value=nxt[1].strip(), quote=nxt[1].strip(), element_id=nxt[0])
    return not_stated()


def parties(lines: list[tuple[str, str]]) -> tuple[Cited, Cited]:
    """Recipient: the company before 御中/様, or the line after 'Bill to'. Issuer: the first other company name."""
    recipient, recipient_line = not_stated(), None
    for i, (eid, ln) in enumerate(lines):
        m = re.search(rf"({COMPANY})\s*(?:御中|様)", ln)
        if m:
            recipient, recipient_line = Cited(value=m.group(1), quote=m.group(1), element_id=eid), i
            break
        if re.fullmatch(r"(?:Bill to|請求先|宛先)\s*[:：]?", ln) and i + 1 < len(lines):
            m2 = re.search(COMPANY, lines[i + 1][1])
            if m2:
                recipient, recipient_line = Cited(value=m2.group(), quote=m2.group(), element_id=lines[i + 1][0]), i + 1
                break
    issuer = not_stated()
    for i, (eid, ln) in enumerate(lines):
        if i == recipient_line:
            continue
        m = re.search(COMPANY, ln)
        if m:
            issuer = Cited(value=m.group(), quote=m.group(), element_id=eid)
            break
    if issuer.value is None:
        issuer = labelled_party(lines, PARTY_LABELS["issuer"])
    if recipient.value is None:
        recipient = labelled_party(lines, PARTY_LABELS["recipient"])
    return issuer, recipient


def column_order(header: str) -> list[str] | None:
    """['name', 'quantity', 'unit_price', 'amount'] from a header line, by where each label appears."""
    if not (re.search(r"数量|Qty|Quantity|পরিমাণ", header) and re.search(r"金額|Amount|মোট", header)):
        return None
    at = {}
    for col, words in COLS.items():
        pos = [header.find(w) for w in words if w in header]
        if pos:
            at[col] = min(pos)
    return ["name"] + sorted(at, key=at.get)


def line_items(lines: list[tuple[str, str]]) -> list[base.LineItem]:
    items: list[base.LineItem] = []
    order: list[str] | None = None
    for eid, ln in lines:
        if order is None:
            order = column_order(ln)
            continue
        if STOP.search(ln):
            break
        cells = [c.strip() for c in ln.strip("|").split("|")] if ln.startswith("|") else None
        if cells is None:  # text layer: the row is words, with the numbers at the end
            words = ln.split()
            n = len(order) - 1
            tail = words[-n:] if len(words) > n else []
            if len(tail) != n or not all(NUMERIC.match(w) for w in tail):
                continue
            cells = [" ".join(words[:-n])] + tail
        if len(cells) != len(order):
            continue
        row = dict(zip(order, cells))
        items.append(base.LineItem(name=row.get("name"), quantity=row.get("quantity"), unit_price=row.get("unit_price"),
                                      amount=row.get("amount"), tax_rate=row.get("tax_rate"), quote=ln, element_id=eid))
    return items


def extract_invoice(elements: list[Element]) -> base.InvoiceOut:
    lines = lines_of(elements)
    issuer, recipient = parties(lines)
    return base.InvoiceOut(**header_fields(lines), issuer=issuer, recipient=recipient, line_items=line_items(lines))


def extract(doc_id: str, doc_type: DocType, elements: list[Element]) -> Extraction:
    if doc_type != "invoice":
        raise NotImplementedError("The rules extractor only knows invoices; use the LLM extractor for other types.")
    t0 = time.perf_counter()
    return base.finish(doc_id, doc_type, extract_invoice(elements), elements, "rules", t0)

