"""Synthetic charts with exact ground truth, for scoring chart → table (F6).

    python -m eval.synth.charts --out eval/data/charts

Six charts: simple bars, grouped bars and lines, with Japanese and English labels; half have printed data labels
(easy), half do not (the model has to read the gridlines). Ground truth is {series: {x: y}} from the data that drew them.
"""
import argparse
import json
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

FONT = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
SPECS = [
    ("bar", "四半期別売上高", "四半期", "百万円", ["第1四半期", "第2四半期", "第3四半期", "第4四半期"], ["売上高"], True),
    ("bar", "Monthly active users", "Month", "Users (thousands)", ["Jan", "Feb", "Mar", "Apr", "May"], ["Users"], False),
    ("grouped", "地域別売上", "地域", "億円", ["東京", "大阪", "名古屋"], ["2025年", "2026年"], True),
    ("grouped", "Units shipped by region", "Region", "Units", ["EMEA", "APAC", "AMER"], ["Model A", "Model B"], False),
    ("line", "月次利益", "月", "百万円", ["1", "2", "3", "4", "5", "6"], ["利益"], True),
    ("line", "Temperature over time", "Hour", "°C", ["0", "4", "8", "12", "16", "20"], ["Sensor 1", "Sensor 2"], False),
]


def draw(kind, title, xl, yl, xs, names, labels, rng, out: Path) -> dict:
    if Path(FONT).exists():
        font_manager.fontManager.addfont(FONT)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
    data = {n: {x: rng.randrange(20, 95) * rng.choice([1, 1, 5, 10]) for x in xs} for n in names}
    fig, ax = plt.subplots(figsize=(5.6, 3.6), dpi=120)
    width = 0.8 / len(names)
    for i, n in enumerate(names):
        ys = list(data[n].values())
        if kind == "line":
            ax.plot([float(x) for x in xs], ys, marker="o", label=n)
            if labels:
                for x, y in zip(xs, ys):
                    ax.annotate(str(y), (float(x), y), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)
        else:
            bars = ax.bar([c + i * width for c in range(len(xs))], ys, width=width, label=n)
            if labels:
                ax.bar_label(bars, fontsize=8)
    if kind != "line":
        ax.set_xticks([c + 0.4 - width / 2 for c in range(len(xs))], xs)
    ax.set_title(title), ax.set_xlabel(xl), ax.set_ylabel(yl)
    ax.grid(axis="y", alpha=0.3)
    if len(names) > 1:
        ax.legend()
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return {"title": title, "x_label": xl, "y_label": yl, "kind": kind, "data_labels": labels, "series": data}


def generate(out: Path, seed: int = 0) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    paths = []
    for i, spec in enumerate(SPECS):
        png = out / f"chart-{i:02d}.png"
        gt = draw(*spec, rng, png)
        png.with_suffix(".json").write_text(json.dumps(gt, ensure_ascii=False, indent=1), encoding="utf-8")
        paths.append(png)
    return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "data" / "charts")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    print(f"wrote {len(generate(a.out, a.seed))} charts to {a.out}")
