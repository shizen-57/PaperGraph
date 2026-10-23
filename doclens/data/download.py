"""Download the public papers listed in data/sources.csv into data/space/papers/. PDFs are not committed (licences).

Your own drafts, supervisor feedback and notes go in data/space/{drafts,supervisor,notes}/ by hand; they are gitignored.
"""
import csv
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent

if __name__ == "__main__":
    out = DATA / "space" / "papers"
    out.mkdir(parents=True, exist_ok=True)
    with open(DATA / "sources.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            path = out / row["filename"]
            if path.exists():
                continue
            req = urllib.request.Request(row["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if not data.startswith(b"%PDF"):
                print(f"SKIP {row['filename']}: not a PDF ({row['url']})")
                continue
            path.write_bytes(data)
            print(f"ok {row['filename']} ({len(data) // 1024} KB)")
