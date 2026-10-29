"""Synthetic Japanese invoices with exact ground truth.

    python -m eval.synth.generate --n 12 --seed 0 --out eval/data/synth

    eval/data/synth/clean/clean-000.pdf    vector PDF with a text layer (rendered by Chromium)
    eval/data/synth/scanned/scan-000.pdf   the same invoice as an image-only PDF: rotation, blur, ink bleed, JPEG, 印 stamp
    ...-NNN.json                           ground truth: normalised fields, line items, the items table as HTML

Three layouts rotate through the set so that a parser or extractor can't overfit one template. The same seed always
gives the same documents. Fonts: Noto Sans JP if installed, else IPAGothic.
"""
import argparse
import json
import math
import os
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker
from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).parent
FONT_FILE = os.environ.get("STAMP_FONT", "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
CHROMIUM = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium")
DPI = 150

ITEMS = ["ノートPC用ACアダプター", "コピー用紙 A4 500枚", "ボールペン 黒 10本入", "ワイヤレスマウス", "USBメモリ 64GB",
         "液晶モニター 24インチ", "ホワイトボードマーカー", "A4クリアファイル 100枚", "シュレッダー用オイル", "LANケーブル 5m",
         "モバイルバッテリー", "デスクライト LED", "オフィスチェア用キャスター", "ラベルシール A4 20枚", "外付けHDD 2TB",
         "キーボード 日本語配列", "名刺用紙 マイクロミシン", "電卓 12桁", "ステープラー針 10箱", "インクカートリッジ 黒",
         "保守サポート 月額", "ライセンス更新料", "設置作業費", "出張技術料", "データ移行作業"]
REDUCED = ["ミネラルウォーター 2L ×6本", "お茶 500ml ×24本", "コーヒー豆 1kg", "菓子詰め合わせ", "ドリンクバー用シロップ",
           "インスタントみそ汁 30食", "オレンジジュース 1L ×12本", "クッキーアソート 50袋"]
PRICES = [120, 250, 480, 980, 1200, 1500, 2480, 3800, 5000, 12800, 24800]
BANKS = ["みずほ銀行 渋谷支店 普通 {n}", "三菱UFJ銀行 新宿支店 普通 {n}", "三井住友銀行 大阪支店 当座 {n}", "ゆうちょ銀行 〇一八支店 普通 {n}"]
HEADERS = {"a": ["品名", "数量", "単価", "金額"], "b": ["Description", "Qty", "Unit Price", "Amount"],
           "c": ["品名", "数量", "単価", "税率", "金額"]}

_FULL = str.maketrans("0123456789,¥", "０１２３４５６７８９，￥")


def era_year(d: date) -> int:
    return d.year - 2018  # 令和


def fmt_date(d: date, style: str) -> str:
    if style == "western":
        return f"{d.year}/{d.month:02d}/{d.day:02d}"
    if style == "era":
        return f"令和{era_year(d)}年{d.month}月{d.day}日"
    if style == "fullwidth":
        return f"{d.year}年{d.month}月{d.day}日".translate(_FULL)
    return f"R{era_year(d)}.{d.month}.{d.day}"  # abbreviated era


def fmt_money(n: int, style: str) -> str:
    if style == "yen_sign":
        return f"¥{n:,}"
    if style == "en":
        return f"{n:,}円"
    return f"¥{n:,}".translate(_FULL)  # full-width


def fmt_cell(n: int, style: str) -> str:
    return f"{n:,}".translate(_FULL) if style == "fullwidth" else f"{n:,}"


def make_spec(i: int, rng: random.Random, fake: Faker) -> dict:
    layout = "abc"[i % 3]
    issue = date(2026, rng.randint(1, 10), rng.randint(1, 28))
    due = issue + timedelta(days=rng.choice([14, 30, 45]))
    names = rng.sample(ITEMS, k=rng.randint(2, 9))
    reduced = rng.sample(REDUCED, k=rng.randint(1, 3)) if layout == "c" else []
    items = []
    for name in names + reduced:
        q, u = rng.randint(1, 20), rng.choice(PRICES)
        items.append({"name": name, "quantity": q, "unit_price": u, "amount": q * u,
                      "tax_rate": 0.08 if name in reduced else 0.10})
    rng.shuffle(items)
    groups: dict[float, int] = {}
    for it in items:
        groups[it["tax_rate"]] = groups.get(it["tax_rate"], 0) + it["amount"]
    subtotal = sum(it["amount"] for it in items)
    tax = sum(math.floor(base * r) for r, base in groups.items())
    number = rng.choice([f"INV-2026-{rng.randint(1, 9999):04d}", f"No.{2026}{issue.month:02d}-{rng.randint(1, 999):03d}",
                         f"R{era_year(issue)}-{rng.randint(1, 9999):04d}"])
    return {
        "layout": layout, "date_style": rng.choice(["western", "era", "fullwidth", "abbr"]),
        "money_style": rng.choice(["yen_sign", "en", "fullwidth"]),
        "invoice_number": number, "issue_date": issue, "due_date": due,
        "issuer": fake.company(), "issuer_address": fake.address().replace("\n", " "), "issuer_phone": fake.phone_number(),
        "recipient": fake.company(), "stamp": fake.last_name(),
        "bank": rng.choice(BANKS).format(n=rng.randint(1000000, 9999999)),
        "items": items, "groups": groups, "subtotal": subtotal, "tax": tax, "total": subtotal + tax,
    }


def render_html(spec: dict, env: Environment) -> tuple[str, dict]:
    """HTML for the invoice and its ground truth. The items table is built here, so GT matches what is printed."""
    ds, ms, layout = spec["date_style"], spec["money_style"], spec["layout"]
    rows = []
    for it in spec["items"]:
        row = [it["name"], fmt_cell(it["quantity"], ms), fmt_cell(it["unit_price"], ms)]
        if layout == "c":
            row.append("10%" if it["tax_rate"] == 0.10 else "8%(軽減)")
        rows.append(row + [fmt_cell(it["amount"], ms)])
    header = HEADERS[layout]
    shown = {"issue_date": fmt_date(spec["issue_date"], ds), "due_date": fmt_date(spec["due_date"], ds)}
    fmt = {k: fmt_money(spec[k], ms) for k in ("subtotal", "tax", "total")}
    groups = [{"rate_pct": round(r * 100), "base_fmt": fmt_money(base, ms), "tax_fmt": fmt_money(math.floor(base * r), ms)}
              for r, base in sorted(groups_items(spec), reverse=True)]
    html = env.get_template(f"invoice_{layout}.html").render(s=spec, shown=shown, fmt=fmt, header=header, rows=rows,
                                                             tax_groups=groups)
    cell = lambda tag, c: f"<{tag}>{c}</{tag}>"  # noqa: E731
    table_html = ("<table><thead><tr>" + "".join(cell("td", h) for h in header) + "</tr></thead><tbody>"
                  + "".join("<tr>" + "".join(cell("td", c) for c in r) + "</tr>" for r in rows) + "</tbody></table>")
    gt = {
        "layout": layout, "date_style": ds, "money_style": ms,
        "fields": {"invoice_number": spec["invoice_number"], "issue_date": spec["issue_date"].isoformat(),
                   "due_date": spec["due_date"].isoformat(), "issuer": spec["issuer"], "recipient": spec["recipient"],
                   "subtotal": spec["subtotal"], "tax": spec["tax"], "total": spec["total"]},
        "line_items": [{**it, "tax_rate": it["tax_rate"] if layout == "c" else None} for it in spec["items"]],
        "shown": {**shown, **fmt}, "table_html": table_html,
    }
    return html, gt


def groups_items(spec: dict):
    return spec["groups"].items()


def html_to_pdf(html: str, out: Path, page) -> None:
    page.set_content(html)
    page.pdf(path=str(out), format="A4", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})


# --- scanned look ---

def stamp(img, text: str, rng: random.Random):
    """A red hanko: a ring with the family name, placed over the issuer block so it overlaps text like a real one."""
    from PIL import ImageDraw, ImageFont

    w, h = img.size
    r = int(0.045 * w)
    cx, cy = int(rng.uniform(0.78, 0.86) * w), int(rng.uniform(0.15, 0.21) * h)
    layer = img.copy()
    d = ImageDraw.Draw(layer)
    red = (205, 35, 35)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=red, width=max(2, r // 9))
    font = ImageFont.truetype(FONT_FILE, int(r * 1.0 if len(text) > 1 else r * 1.4))
    d.multiline_text((cx, cy), "\n".join(text[:2]), fill=red, font=font, anchor="mm", align="center")
    from PIL import Image
    return Image.blend(img, layer, 0.8)


def scan_like(clean_pdf: Path, out_pdf: Path, stamp_text: str, seed: int) -> None:
    import numpy as np
    import pypdfium2 as pdfium
    from augraphy import AugraphyPipeline, InkBleed, Jpeg, NoiseTexturize
    from PIL import Image, ImageFilter

    rng = random.Random(seed)
    pdf = pdfium.PdfDocument(str(clean_pdf))
    img = pdf[0].render(scale=DPI / 72).to_pil().convert("RGB")
    pdf.close()
    img = stamp(img, stamp_text, rng)
    img = img.rotate(rng.uniform(-2, 2), resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 1.0)))
    random.seed(seed)
    np.random.seed(seed)
    pipe = AugraphyPipeline(ink_phase=[InkBleed(p=1)], paper_phase=[NoiseTexturize(sigma_range=(1, 2), turbulence_range=(2, 3), p=1)],
                            post_phase=[Jpeg(quality_range=(35, 60), p=1)])
    out = pipe(np.array(img))
    Image.fromarray(out if isinstance(out, np.ndarray) else out["output"]).convert("RGB").save(
        out_pdf, "PDF", resolution=float(DPI))


def generate(n: int, seed: int, out: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    fake = Faker("ja_JP")
    Faker.seed(seed)
    rng = random.Random(seed)
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))
    (out / "clean").mkdir(parents=True, exist_ok=True)
    (out / "scanned").mkdir(parents=True, exist_ok=True)
    written = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM) if Path(CHROMIUM).exists() else p.chromium.launch()
        page = browser.new_page()
        for i in range(n):
            spec = make_spec(i, rng, fake)
            html, gt = render_html(spec, env)
            clean_pdf = out / "clean" / f"clean-{i:03d}.pdf"
            html_to_pdf(html, clean_pdf, page)
            scan_pdf = out / "scanned" / f"scan-{i:03d}.pdf"
            scan_like(clean_pdf, scan_pdf, spec["stamp"], seed * 1000 + i)
            for pdf, name, variant in ((clean_pdf, clean_pdf.stem, "clean"), (scan_pdf, scan_pdf.stem, "scanned")):
                pdf.with_suffix(".json").write_text(
                    json.dumps({"id": name, "variant": variant, **gt}, ensure_ascii=False, indent=1), encoding="utf-8")
                written.append(pdf)
        browser.close()
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="invoices; each is written twice, clean and scanned")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=HERE.parent / "data" / "synth")
    args = ap.parse_args()
    files = generate(args.n, args.seed, args.out)
    print(f"wrote {len(files)} documents to {args.out}")


if __name__ == "__main__":
    main()
