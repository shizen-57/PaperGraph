"""Record the README demo from the running app: open a document, click fields, show a highlight and an unverified field.

    python -m backend.demo --extractor llm                  # or the default rules extractor; seeds the 'demo' space
    uvicorn backend.app:app --port 8000 &
    (cd frontend && NEXT_PUBLIC_SPACE=demo npm run build && npm start) &
    python scripts/record_demo.py --doc invoices-clean-000 --out ../docs/demo.gif

Takes screenshots with Playwright (Chromium) and joins them into a GIF with Pillow: no screen recorder needed.
Fields to click are picked by name from the page, so the script follows whatever the extractor returned: it clicks the
first verified field, the total, and the first unverified field if there is one.
"""
import argparse
from io import BytesIO
from pathlib import Path

from PIL import Image


def shot(page, clip=None) -> Image.Image:
    return Image.open(BytesIO(page.screenshot(clip=clip))).convert("RGB")


def main():
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", required=True, help="document id, e.g. invoices-clean-000")
    ap.add_argument("--url", default="http://localhost:3000")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--width", type=int, default=1100)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--chromium", default="/opt/pw-browsers/chromium")
    args = ap.parse_args()

    frames: list[tuple[Image.Image, int]] = []  # (image, milliseconds)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium) if Path(args.chromium).exists() else p.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.goto(f"{args.url}/docs/{args.doc}", wait_until="networkidle")
        page.wait_for_selector(".field", timeout=30000)
        page.wait_for_selector(".pdf-page canvas", timeout=30000)
        page.wait_for_timeout(800)
        frames.append((shot(page), 1600))

        def click(locator, hold=2000):
            locator.first.click()
            page.wait_for_timeout(900)  # scroll + highlight animation
            frames.append((shot(page), hold))

        fields = page.locator("button.field")
        verified = page.locator("button.field.status-verified")
        if verified.count():
            click(verified)
        total = page.locator("button.field", has_text="Total").filter(has_not_text="Subtotal")
        if total.count():
            click(total)
        unverified = page.locator("button.field.status-unverified")
        if unverified.count():
            click(unverified, 2600)
        if fields.count() and page.locator(".checks").count():
            page.locator(".checks").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            frames.append((shot(page), 2200))
        browser.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    small = [(im.resize((im.width * 9 // 10, im.height * 9 // 10), Image.LANCZOS), ms) for im, ms in frames]
    quantised = [im.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for im, _ in small]
    quantised[0].save(args.out, save_all=True, append_images=quantised[1:], duration=[ms for _, ms in small], loop=0, optimize=True)
    print(f"{args.out}: {len(frames)} frames, {args.out.stat().st_size / 1e6:.1f} MB, {sum(ms for _, ms in frames) / 1000:.1f} s")


if __name__ == "__main__":
    main()
