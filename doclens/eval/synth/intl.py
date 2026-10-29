"""English and Bangla invoices with exact ground truth, in the same schema as the Japanese set (ISO dates, integer amounts).

    python -m eval.synth.intl --n 6 --seed 0 --out eval/data/intl

    eval/data/intl/en/en-000.pdf + .json    "INVOICE", From / Bill To, USD, Western digit grouping, month-name dates
    eval/data/intl/bn/bn-000.pdf + .json    "কর চালান", বিক্রেতা / ক্রেতা, ৳ with Bangla digits and lakh grouping (12,34,567)

Clean text-layer PDFs only (rendered by Chromium). Note that a Chromium PDF's Bangla text layer is not trustworthy (spaces appear
inside words, boxes overlap), so Bangla pages are read by OCR (parse.has_bengali_text); there is no scanned variant.
"""
import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker
from jinja2 import Environment, FileSystemLoader, select_autoescape

from eval.synth.generate import CHROMIUM, HERE, html_to_pdf

EN_ITEMS = ["Ergonomic office chair", "Wireless keyboard", "USB-C docking station", "27-inch monitor", "Standing desk", "Laptop sleeve 15\"",
            "Printer toner cartridge", "A4 copy paper (500 sheets)", "Whiteboard markers (12 pack)", "Cloud hosting, monthly",
            "Software licence renewal", "On-site installation", "Network switch 24-port", "Webcam 1080p", "Desk lamp", "Cable organiser kit"]
BN_ITEMS = ["অফিস চেয়ার", "ওয়্যারলেস মাউস", "প্রিন্টারের কালি", "এ৪ কাগজ (৫০০ শিট)", "ল্যাপটপ ব্যাগ", "ওয়াইফাই রাউটার", "ডেস্ক ল্যাম্প",
            "হোয়াইটবোর্ড মার্কার (১২টি)", "ইউএসবি হাব", "নোটবুক (১০০ পৃষ্ঠা)", "মনিটর ২৪ ইঞ্চি", "কিবোর্ড", "সার্ভার মাসিক ভাড়া", "সফটওয়্যার লাইসেন্স", "স্থাপন ও সেটআপ"]
BN_SUFFIX = ["ট্রেডার্স", "এন্টারপ্রাইজ", "টেক্সটাইল লিমিটেড", "ইলেকট্রনিক্স", "ফুড প্রোডাক্টস লিমিটেড", "সলিউশনস", "ব্রাদার্স"]
EN_PRICES = [12, 25, 40, 75, 120, 250, 499, 1200, 2400]
BN_PRICES = [150, 250, 480, 750, 1200, 2500, 4800, 12500, 45000]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
BN_MONTHS = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]
_BN = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def bn(s: str) -> str:
    return s.translate(_BN)


def lakh(n: int) -> str:
    """12,34,567: the last three digits, then pairs."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail, groups = s[:-3], s[-3:], []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups + [tail])


def fmt_date(d: date, lang: str, style: int) -> str:
    if lang == "en":
        return [f"{d.day} {EN_MONTHS[d.month - 1]} {d.year}", f"{EN_MONTHS[d.month - 1][:3]} {d.day}, {d.year}", d.isoformat()][style % 3]
    return bn(f"{d.day:02d} {BN_MONTHS[d.month - 1]} {d.year}")


def money(n: int, lang: str, style: int) -> str:
    if lang == "en":
        return [f"${n:,}.00", f"USD {n:,}.00", f"${n:,}"][style % 3]
    return f"৳ {bn(lakh(n))}"


def cell(n: int, lang: str) -> str:
    return f"{n:,}" if lang == "en" else bn(lakh(n))


def make_spec(lang: str, i: int, rng: random.Random, fake: Faker, fake_en: Faker) -> dict:
    items_pool, prices = (EN_ITEMS, EN_PRICES) if lang == "en" else (BN_ITEMS, BN_PRICES)
    issue = date(2026, rng.randint(1, 10), rng.randint(1, 26))
    due = issue + timedelta(days=rng.choice([14, 30, 45]))
    items = []
    for name in rng.sample(items_pool, k=rng.randint(3, 9)):
        q, u = rng.randint(1, 20), rng.choice(prices)
        items.append({"name": name, "quantity": q, "unit_price": u, "amount": q * u, "tax_rate": None})
    subtotal = sum(it["amount"] for it in items)
    rate = 0.08 if lang == "en" else 0.15  # sales tax / Bangladesh VAT
    tax = int(subtotal * rate + 0.5)
    if lang == "en":
        company = lambda: next(c for c in iter(fake_en.company, None) if "," not in c)  # noqa: E731
        issuer, recipient = company(), company()
        number = rng.choice([f"INV-2026-{rng.randint(1, 9999):04d}", f"{rng.randint(10000, 99999)}", f"EN/{issue.year}/{rng.randint(1, 999):03d}"])
        address = lambda: fake_en.street_address() + ", " + fake_en.city()  # noqa: E731
        tax_label, phone, bank = f"Sales Tax ({round(rate * 100)}%)", fake_en.phone_number(), f"{fake_en.company()} Bank, account {rng.randint(10**9, 10**10 - 1)}"
    else:
        company = lambda: f"{fake.last_name()} {rng.choice(BN_SUFFIX)}"  # noqa: E731
        issuer, recipient = company(), company()
        number = rng.choice([f"BD-2026-{rng.randint(1, 9999):04d}", f"VAT-{rng.randint(1000, 9999)}"])
        address = lambda: fake.address().replace("\n", ", ")  # noqa: E731
        tax_label, phone, bank = f"ভ্যাট ({bn(str(round(rate * 100)))}%)", "", f"ইসলামী ব্যাংক, হিসাব নং {bn(str(rng.randint(10**9, 10**10 - 1)))}"
    return {"lang": lang, "date_style": rng.randint(0, 2), "money_style": rng.randint(0, 2), "invoice_number": number, "issue_date": issue,
            "due_date": due, "issuer": issuer, "issuer_address": address(), "issuer_phone": phone, "recipient": recipient,
            "recipient_address": address(), "items": items, "subtotal": subtotal, "tax": tax, "total": subtotal + tax,
            "tax_label": tax_label, "bank": bank}


def render_html(spec: dict, env: Environment) -> tuple[str, dict]:
    lang, ds, ms = spec["lang"], spec["date_style"], spec["money_style"]
    header = (["Description", "Qty", "Unit Price", "Amount"] if lang == "en" else ["পণ্যের বিবরণ", "পরিমাণ", "একক মূল্য", "মোট"])
    rows = [[it["name"], cell(it["quantity"], lang), cell(it["unit_price"], lang), cell(it["amount"], lang)] for it in spec["items"]]
    shown = {"issue_date": fmt_date(spec["issue_date"], lang, ds), "due_date": fmt_date(spec["due_date"], lang, ds)}
    fmt = {k: money(spec[k], lang, ms) for k in ("subtotal", "tax", "total")}
    html = env.get_template(f"invoice_{lang}.html").render(s=spec, shown=shown, fmt=fmt, header=header, rows=rows)
    td = lambda c: f"<td>{c}</td>"  # noqa: E731
    table_html = ("<table><thead><tr>" + "".join(td(h) for h in header) + "</tr></thead><tbody>"
                  + "".join("<tr>" + "".join(td(c) for c in r) + "</tr>" for r in rows) + "</tbody></table>")
    gt = {"layout": lang, "date_style": ds, "money_style": ms,
          "fields": {"invoice_number": spec["invoice_number"], "issue_date": spec["issue_date"].isoformat(), "due_date": spec["due_date"].isoformat(),
                     "issuer": spec["issuer"], "recipient": spec["recipient"], "subtotal": spec["subtotal"], "tax": spec["tax"], "total": spec["total"]},
          "line_items": spec["items"], "shown": {**shown, **fmt}, "table_html": table_html}
    return html, gt


def generate(n: int, seed: int, out: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    fake, fake_en = Faker("bn_BD"), Faker("en_US")
    Faker.seed(seed)
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))
    written = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM) if Path(CHROMIUM).exists() else p.chromium.launch()
        page = browser.new_page()
        for lang in ("en", "bn"):
            rng = random.Random(f"{seed}-{lang}")
            (out / lang).mkdir(parents=True, exist_ok=True)
            for i in range(n):
                html, gt = render_html(make_spec(lang, i, rng, fake, fake_en), env)
                pdf = out / lang / f"{lang}-{i:03d}.pdf"
                html_to_pdf(html, pdf, page)
                pdf.with_suffix(".json").write_text(json.dumps({"id": pdf.stem, "variant": lang, **gt}, ensure_ascii=False, indent=1), encoding="utf-8")
                written.append(pdf)
        browser.close()
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6, help="invoices per language")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "data" / "intl")
    a = ap.parse_args()
    print(f"wrote {len(generate(a.n, a.seed, a.out))} documents to {a.out}")
