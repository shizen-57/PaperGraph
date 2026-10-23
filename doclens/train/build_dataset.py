"""Training data for the invoice LoRA (F8): synthetic invoices rendered as images, each with its JSON target.

    python -m train.build_dataset --n 1500 --seed 1 --out train/data      # seed 1: the eval set uses seed 0
    -> train/data/images/*.png, train/data/train.jsonl, train/data/val.jsonl (one chat example per line)

Half of the examples are clean renders and half are scanned-look ones, so the adapter sees both. The held-out
eval set (eval/data/synth, seed 0) is never used for training. Generating 1,500 invoices takes tens of minutes.
"""
import argparse
import json
import random
import tempfile
from pathlib import Path

from backend import extract_direct as direct
from eval.synth import generate


def build(n: int, seed: int, out: Path, val_share: float = 0.05) -> tuple[int, int]:
    images = out / "images"
    images.mkdir(parents=True, exist_ok=True)
    examples = []
    with tempfile.TemporaryDirectory() as tmp:
        for pdf in generate.generate(n, seed, Path(tmp)):
            gt = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
            png = images / f"{gt['id']}.png"
            png.write_bytes(direct.render_page(pdf))
            examples.append({
                "id": gt["id"], "variant": gt["variant"], "image": str(png.relative_to(out)),
                "messages": [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": direct.PROMPT}]},
                             {"role": "assistant", "content": [{"type": "text", "text": direct.target_json(gt)}]}],
            })
    random.Random(seed).shuffle(examples)
    cut = max(1, int(len(examples) * val_share))
    for name, rows in (("val", examples[:cut]), ("train", examples[cut:])):
        (out / f"{name}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return len(examples) - cut, cut


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1500, help="invoices; each is written clean and scanned")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    a = ap.parse_args()
    train, val = build(a.n, a.seed, a.out)
    print(f"{train} training and {val} validation examples in {a.out}")
