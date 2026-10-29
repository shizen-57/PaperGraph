import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend import consistency, extract, extract_rules, parse
from backend.schemas import Element

INTL = Path(__file__).parent.parent / "eval" / "data" / "intl"


def seg(x0, x1, text, y0=0, y1=10):
    return (x0, y0, x1, y1, text)


def test_language_detection_by_script():
    assert parse.lang_of("請求書番号 R8-3579 合計 85,448円") == "ja"
    assert parse.lang_of("চালান নম্বর: BD-2026-1140 তারিখ ০১ আগস্ট ২০২৬") == "bn"
    assert parse.lang_of("Invoice No. EN/2026/650 Due Date May 23, 2026") == "en"


def test_overlapping_boxes_from_chromium_are_cleaned():
    # 'To' inside 'Bill To', and 'Sales Ta' overlapping 'Tax (8%)' by the letters 'Ta'
    inner = parse._dedupe([seg(0, 40, "Bill To"), seg(30, 40, "To")])
    assert [s[4] for s in inner] == ["Bill To"]
    assert parse._join([seg(0, 40, "Sales Ta"), seg(32, 70, "Tax (8%)")]) == "Sales Tax (8%)"
    assert len(parse._dedupe([seg(0, 40, "Total"), seg(0, 40, "Total")])) == 1  # an exact duplicate keeps one
    assert len(parse._dedupe([seg(0, 40, "Total"), seg(60, 100, "Total")])) == 2  # the same word elsewhere stays


def test_join_spaces_words_when_asked():
    a, b = seg(0, 30, "পণ্যের"), seg(32, 60, "বিবরণ")  # a 2 pt gap: glued for CJK, a space for Bengali OCR
    assert parse._join([a, b]) == "পণ্যেরবিবরণ" and parse._join([a, b], spaced=True) == "পণ্যের বিবরণ"


def test_a_bangla_text_layer_is_detected_so_it_can_be_ocrd():
    assert parse.has_bengali_text(INTL / "bn" / "bn-000.pdf") and not parse.has_bengali_text(INTL / "en" / "en-000.pdf")


def test_ruling_lines_are_removed_before_ocr():
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    from PIL import Image
    a = np.full((400, 600, 3), 255, np.uint8)
    cv2.rectangle(a, (50, 50), (550, 350), (0, 0, 0), 2)  # a table border
    cv2.putText(a, "ABC", (200, 200), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
    out = np.array(parse.strip_rules(Image.fromarray(a)).convert("L"))
    assert out[50:53, 100:500].min() == 255 and out[100:300, 49:52].min() == 255  # the border is gone
    assert out[150:230, 190:330].min() < 100  # the text stays


def test_the_tax_rate_rule_is_japans_and_other_countries_skip_it():
    assert consistency.tax_rate([], 1000, 150).status == "fail"  # 15% is not a Japanese rate
    assert consistency.tax_rate([], 1000, 150, allowed=None).status == "skipped"
    checks = {c.name: c.status for c in consistency.check_invoice({"subtotal": 1000, "tax": 150, "total": 1150}, rates=None)}
    assert checks["total_sum"] == "pass" and checks["tax_rate"] == "skipped"  # the sums still run


def test_normalise_falls_back_from_japanese_to_english_and_bangla_notation():
    assert extract.normalise("date", "24 October 2026") == ("2026-10-24", None)
    assert extract.normalise("date", "২৪ অক্টোবর ২০২৬") == ("2026-10-24", None)
    assert extract.normalise("date", "令和8年10月24日") == ("2026-10-24", None)  # Japanese still first
    assert extract.normalise("amount", "$1,234.50")[0] == 1234.5
    assert extract.normalise("amount", "৳ ১২,৩৪,৫৬৭")[0] == 1234567
    assert extract.normalise("amount", "¥1,234")[0] == 1234
    assert extract.normalise("amount", "1億2,000万円")[0] == 120_000_000
    assert extract.normalise("number", "১৬")[0] == 16 and extract.normalise("percent", "১৫%")[0] == 0.15


def els(*texts):
    return [Element(id=f"e{i}", doc_id="d", type="text", page=1, bbox=None, text=t) for i, t in enumerate(texts)]


def test_rules_read_english_labels_and_parties():
    ex = extract_rules.extract("d", "invoice", els(
        "Invoice No. INV-7\nINVOICE\nInvoice Date Apr 23, 2026\nDue Date May 23, 2026",
        "From\nAcme Ltd\n1 Main St", "Bill To\nBeta Inc", "Subtotal USD 1,000.00\nSales Tax (8%) USD 80.00\nTotal Due USD 1,080.00"))
    v = {f.name: f.value for f in ex.fields}
    assert (v["invoice_number"], v["issue_date"], v["due_date"]) == ("INV-7", "2026-04-23", "2026-05-23")
    assert (v["issuer"], v["recipient"]) == ("Acme Ltd", "Beta Inc")
    assert (v["subtotal"], v["tax"], v["total"]) == (1000, 80, 1080)
    assert {c.name: c.status for c in ex.checks}["tax_rate"] == "skipped"  # no Japanese text: Japan's rates don't apply


def test_rules_read_bangla_labels_digits_and_a_misread_taka_sign():
    ex = extract_rules.extract("d", "invoice", els(
        "বিক্রেতা: আলম ট্রেডার্স", "ক্রেতা: পাল এন্টারপ্রাইজ", "চালান নম্বর: BD-2026-1140", "তারিখ: ০১ আগস্ট ২০২৬", "পরিশোধের শেষ তারিখ: ১৫ সেপ্টেম্বর ২০২৬",
        "উপমোট ট ৫,৭৩,৬০০", "ভ্যাট (১৫%) ৳ ৮৬,০৪০", "সর্বমোট & ৬,৫৯,৬৪০"))
    v = {f.name: f.value for f in ex.fields}
    assert (v["issue_date"], v["due_date"]) == ("2026-08-01", "2026-09-15")  # the due-date line is not the issue date
    assert (v["issuer"], v["recipient"]) == ("আলম ট্রেডার্স", "পাল এন্টারপ্রাইজ")
    assert (v["subtotal"], v["tax"], v["total"]) == (573600, 86040, 659640)


@pytest.mark.parametrize("name", ["en-000", "en-001", "en-002"])
def test_committed_english_invoices_through_the_text_layer(name):
    pdf = INTL / "en" / f"{name}.pdf"
    gt = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    elements, _, _ = parse.parse_pdf_textlayer(pdf, name)
    v = {f.name: f.value for f in extract_rules.extract(name, "invoice", elements).fields}
    for k, want in gt["fields"].items():
        assert v[k] == want, k
    assert [v[f"line_items[{i}].amount"] for i in range(len(gt["line_items"]))] == [r["amount"] for r in gt["line_items"]]


@pytest.mark.skipif(not shutil.which("tesseract") or "ben" not in subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout,
                    reason="needs tesseract with the Bengali language data (apt install tesseract-ocr-ben)")
def test_committed_bangla_invoice_through_bengali_ocr():
    pdf = INTL / "bn" / "bn-001.pdf"
    gt = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    elements, _, _ = parse.parse_path(pdf, "bn-001", "pdf")  # default parser: the Bengali text layer sends it to OCR
    v = {f.name: f.value for f in extract_rules.extract("bn-001", "invoice", elements).fields}
    assert v["invoice_number"] == gt["fields"]["invoice_number"] and v["issue_date"] == gt["fields"]["issue_date"]
    assert v["total"] == gt["fields"]["total"] and parse.lang_of(" ".join(e.text for e in elements)) == "bn"
