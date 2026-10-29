"""Chart image → data table (F6). A VLM reads the chart into series and points; matplotlib re-plots what it read, so a
person can compare the two side by side; relative_errors scores it against known values.

Points are {x, y} objects rather than [x, y] pairs: constrained decoders handle objects more reliably than tuples.
"""
import base64
import io
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

from backend import llm

PROMPT = (
    "Read this chart into data. Return the title, the axis labels, and for every series its name and its points, "
    "where x is the category or x value exactly as labelled on the axis (as text) and y is the number read from the chart, "
    "without units. If the chart has one series and no legend, call the series by the y-axis label. "
    "Read values as precisely as the gridlines and any printed data labels allow. Keep the chart's language for labels.")


class Point(BaseModel):
    x: str
    y: float


class Series(BaseModel):
    name: str
    points: list[Point]


class ChartData(BaseModel):
    title: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    series: list[Series]


def read_chart(png: bytes) -> ChartData:
    """One VLM call. VLM_MODEL / VLM_BASE_URL select the model (LLM_MODEL / LLM_BASE_URL otherwise)."""
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    raw = llm.chat(
        [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": PROMPT}]}],
        schema=ChartData.model_json_schema(), max_tokens=2000,
        model=os.environ.get("VLM_MODEL"), base_url=os.environ.get("VLM_BASE_URL"))
    try:
        return ChartData.model_validate_json(raw)
    except (ValidationError, ValueError) as e:
        raise ValueError(f"the model did not return a chart: {str(e)[:200]}") from e


def _as_number(x: str) -> float | None:
    try:
        return float(x.replace(",", ""))
    except ValueError:
        return None


def replot(chart: ChartData, out: Path) -> Path:
    """Draw the data the model read: grouped bars for categories, lines for numeric x."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    jp = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
    if Path(jp).exists():
        font_manager.fontManager.addfont(jp)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=jp).get_name()
    fig, ax = plt.subplots(figsize=(5, 3.4), dpi=110)
    numeric = all(_as_number(p.x) is not None for s in chart.series for p in s.points) and bool(chart.series)
    if numeric:
        for s in chart.series:
            ax.plot([_as_number(p.x) for p in s.points], [p.y for p in s.points], marker="o", label=s.name)
    else:
        cats = list(dict.fromkeys(p.x for s in chart.series for p in s.points))
        width = 0.8 / max(len(chart.series), 1)
        for i, s in enumerate(chart.series):
            ys = {p.x: p.y for p in s.points}
            ax.bar([c + i * width for c in range(len(cats))], [ys.get(c, 0) for c in cats], width=width, label=s.name)
        ax.set_xticks([c + 0.4 - width / 2 for c in range(len(cats))], cats)
    ax.set_title(chart.title or "")
    ax.set_xlabel(chart.x_label or "")
    ax.set_ylabel(chart.y_label or "")
    if len(chart.series) > 1:
        ax.legend()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
    return out


def side_by_side(original_png: bytes, chart: ChartData, out: Path) -> Path:
    """The original chart on the left, the re-plot of what the model read on the right."""
    from PIL import Image

    replot_path = replot(chart, out.with_suffix(".replot.png"))
    left, right = Image.open(io.BytesIO(original_png)).convert("RGB"), Image.open(replot_path).convert("RGB")
    h = max(left.height, right.height)
    canvas = Image.new("RGB", (left.width + right.width + 20, h), "white")
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width + 20, 0))
    canvas.save(out)
    return out


def _key(x) -> str:
    """Comparable x label: numbers compare as numbers ('0.0' is '0'), text ignores case and surrounding space."""
    s = str(x).strip().casefold()
    n = _as_number(s)
    return repr(n) if n is not None else s


def relative_errors(pred: ChartData, truth: dict[str, dict[str, float]]) -> dict:
    """Score against known values {series: {x: y}}. A true point is matched by series name (or the only series) and x
    label. `mre` is the mean of |pred - true| / |true| over matched points with a non-zero truth; `coverage` is the
    share of true points the model returned at all."""
    by_name = {s.name.strip().casefold(): {_key(p.x): p.y for p in s.points} for s in pred.series}
    only = next(iter(by_name.values())) if len(by_name) == 1 and len(truth) == 1 else None
    errors, total, found = [], 0, 0
    for name, points in truth.items():
        got = by_name.get(name.strip().casefold(), only) or {}
        for x, y in points.items():
            total += 1
            g = got.get(_key(x))
            if g is None:
                continue
            found += 1
            if y != 0:
                errors.append(abs(g - y) / abs(y))
    return {"mre": round(sum(errors) / len(errors), 4) if errors else None, "coverage": round(found / total, 4) if total else None,
            "points": total, "matched": found}
