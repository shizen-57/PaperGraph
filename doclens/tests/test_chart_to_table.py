import json

import pytest

from backend import chart_to_table as ct
from backend import llm

CHART = ct.ChartData(title="売上", x_label="四半期", y_label="百万円",
                     series=[ct.Series(name="売上", points=[ct.Point(x="Q1", y=300), ct.Point(x="Q2", y=320)])])


def test_read_chart_validates_the_reply(monkeypatch):
    seen = {}

    def chat(messages, schema=None, **kw):
        seen.update(kw, schema=schema, parts=messages[0]["content"])
        return json.dumps({"title": "T", "series": [{"name": "s", "points": [{"x": "A", "y": 1.5}]}]})
    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setenv("VLM_MODEL", "vlm")
    chart = ct.read_chart(b"\x89PNG")
    assert chart.series[0].points[0].y == 1.5 and seen["model"] == "vlm" and seen["parts"][0]["type"] == "image_url"
    monkeypatch.setattr(llm, "chat", lambda *a, **k: '{"series": "nope"}')
    with pytest.raises(ValueError, match="did not return a chart"):
        ct.read_chart(b"x")


def test_relative_errors():
    truth = {"売上": {"Q1": 300, "Q2": 320, "Q3": 340}}
    r = ct.relative_errors(CHART, truth)
    assert r["mre"] == 0.0 and r["coverage"] == 0.6667 and r["points"] == 3 and r["matched"] == 2
    off = ct.ChartData(series=[ct.Series(name="売上", points=[ct.Point(x="Q1", y=330), ct.Point(x="Q2", y=320)])])
    assert ct.relative_errors(off, {"売上": {"Q1": 300, "Q2": 320}})["mre"] == pytest.approx(0.05)


def test_single_unnamed_series_matches_the_only_true_series():
    pred = ct.ChartData(series=[ct.Series(name="Revenue (¥M)", points=[ct.Point(x="q1", y=10)])])
    assert ct.relative_errors(pred, {"revenue": {"Q1": 10}})["matched"] == 1  # case-insensitive x, one series each


def test_replot_and_side_by_side_write_images(tmp_path):
    from PIL import Image
    out = ct.replot(CHART, tmp_path / "r.png")
    assert out.exists() and Image.open(out).size[0] > 300
    import io
    buf = io.BytesIO()
    Image.new("RGB", (200, 150), "white").save(buf, "PNG")
    both = ct.side_by_side(buf.getvalue(), CHART, tmp_path / "both.png")
    assert Image.open(both).size[0] > 500


def test_numeric_x_is_drawn_as_a_line(tmp_path):
    line = ct.ChartData(series=[ct.Series(name="y", points=[ct.Point(x="1", y=2), ct.Point(x="2", y=4)])])
    assert ct.replot(line, tmp_path / "l.png").exists()


def test_synthetic_charts_have_exact_ground_truth(tmp_path):
    from eval.synth import charts
    paths = charts.generate(tmp_path, seed=0)
    assert len(paths) == 6 and all(p.exists() for p in paths)
    gt = json.loads(paths[0].with_suffix(".json").read_text(encoding="utf-8"))
    assert gt["kind"] == "bar" and list(gt["series"]) == ["売上高"] and len(gt["series"]["売上高"]) == 4
    assert json.loads(charts.generate(tmp_path / "again", seed=0)[0].with_suffix(".json").read_text(encoding="utf-8")) == gt  # deterministic
