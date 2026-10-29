"""Metrics. Every number in the README comes from these functions, called by eval/run_eval.py.

Values are compared after normalisation: numbers as numbers, strings NFKC + casefold + no whitespace, so that
３，８００ = 3,800 and 'ボールペン 黒' = 'ボールペン黒'. A parser is not marked down for spacing or digit width.

Terms (see REPORT.md for the full definitions):
  field F1                 precision/recall over (field, value) pairs; a line item row counts as one pair
  field accuracy           exact match per field, macro-averaged over the 9 fields (8 header fields + line_items)
  verified rate            share of predicted values that pass the evidence check
  hallucination catch rate share of WRONG predicted values that the evidence check flags as unverified
  false alarm rate         share of RIGHT predicted values that it flags anyway
  TEDS                     tree-edit-distance similarity of predicted and true table HTML, 0 when no table was found
"""
import re
import unicodedata
from collections import Counter

from backend.extract import to_values
from backend.norm import norm
from backend.schemas import Extraction

TOP = ["invoice_number", "issue_date", "due_date", "issuer", "recipient", "subtotal", "tax", "total"]
ROW = ["name", "quantity", "unit_price", "amount"]


def canon(v):
    """Comparable form of a value."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v) if float(v).is_integer() else round(float(v), 4)
    return norm(str(v))


def row_key(row: dict) -> tuple:
    return tuple(canon(row.get(k)) for k in ROW)


def gt_values(gt: dict) -> dict:
    return {**gt["fields"], "line_items": gt["line_items"]}


def pairs(values: dict) -> Counter:
    c: Counter = Counter()
    for k in TOP:
        if (v := canon(values.get(k))) is not None:
            c[(k, v)] += 1
    for row in values.get("line_items") or []:
        c[("line_item", row_key(row))] += 1
    return c


def prf(pred: Counter, gold: Counter) -> tuple[int, int, int]:
    """(true positives, predicted, gold)."""
    return sum((pred & gold).values()), sum(pred.values()), sum(gold.values())


def f1(tp: int, n_pred: int, n_gold: int) -> float | None:
    if not n_pred or not n_gold:
        return 0.0 if (n_pred or n_gold) else None
    p, r = tp / n_pred, tp / n_gold
    return 2 * p * r / (p + r) if p + r else 0.0


def field_correct(pred: dict, gold: dict) -> dict[str, bool]:
    """Per field: exact match. line_items is correct only if every row matches (order ignored)."""
    out = {k: canon(pred.get(k)) == canon(gold.get(k)) for k in TOP}
    out["line_items"] = (Counter(row_key(r) for r in pred.get("line_items") or [])
                         == Counter(row_key(r) for r in gold.get("line_items") or []))
    return out


def judge(ex: Extraction, gold: dict) -> dict:
    """Evidence-check outcomes against the truth. Only predicted values count (a missing field is a recall
    miss, not a hallucination). A line item row is flagged if any of its four cells is unverified."""
    pred = to_values(ex.fields)
    status = {f.name: f.status for f in ex.fields}
    items = []
    for k in TOP:
        if status.get(k) in (None, "missing"):
            continue
        items.append({"name": k, "correct": canon(pred.get(k)) == canon(gold.get(k)), "flagged": status[k] == "unverified"})
    remaining = Counter(row_key(r) for r in gold.get("line_items") or [])
    for i, row in enumerate(pred.get("line_items") or []):
        cells = [status.get(f"line_items[{i}].{c}") for c in ROW]
        if all(s in (None, "missing") for s in cells):
            continue
        key = row_key(row)
        ok = remaining[key] > 0
        if ok:
            remaining[key] -= 1
        items.append({"name": f"line_items[{i}]", "correct": ok, "flagged": "unverified" in cells})
    return {"items": items, "check_failed": any(c.status == "fail" for c in ex.checks)}


def rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def evidence_summary(judgements: list[dict]) -> dict:
    items = [i for j in judgements for i in j["items"]]
    wrong = [i for i in items if not i["correct"]]
    right = [i for i in items if i["correct"]]
    docs_wrong = [j for j in judgements if any(not i["correct"] for i in j["items"])]
    return {
        "predicted": len(items), "wrong": len(wrong),
        "verified_rate": rate(sum(not i["flagged"] for i in items), len(items)),
        "hallucination_catch_rate": rate(sum(i["flagged"] for i in wrong), len(wrong)),
        "false_alarm_rate": rate(sum(i["flagged"] for i in right), len(right)),
        "docs_with_a_wrong_value": len(docs_wrong),
        "consistency_flagged_wrong_docs": rate(sum(j["check_failed"] for j in docs_wrong), len(docs_wrong)),
        "docs_failing_a_consistency_check": sum(j["check_failed"] for j in judgements),
        # a wrong doc counts as caught if either the evidence check or the arithmetic noticed
        "wrong_docs_caught_by_either": rate(
            sum(j["check_failed"] or any(i["flagged"] for i in j["items"] if not i["correct"]) for j in docs_wrong),
            len(docs_wrong)),
    }


# --- TEDS ---

def _tree(el):
    from apted.helpers import Tree  # noqa: F401  (kept for the import check in requirements)
    node = _Node(el.tag, el.get("colspan", "1"), el.get("rowspan", "1"),
                 norm(unicodedata.normalize("NFKC", "".join(el.itertext()))) if el.tag == "td" else "")
    if el.tag != "td":
        node.children = [_tree(c) for c in el if c.tag in ("thead", "tbody", "tr", "td")]
    return node


class _Node:
    def __init__(self, name: str, colspan: str, rowspan: str, content: str):
        self.name, self.colspan, self.rowspan, self.content = name, colspan, rowspan, content
        self.children: list[_Node] = []

    def size(self) -> int:
        return 1 + sum(c.size() for c in self.children)


def teds(pred_html: str | None, gold_html: str) -> float:
    """Tree-edit-distance similarity (Zhong et al., PubTabNet). Insert/delete cost 1; renaming a cell costs the
    normalised Levenshtein distance of its text (1 if tag or spans differ). A missing table scores 0."""
    if not pred_html:
        return 0.0
    from apted import APTED, Config
    from lxml import html as lxml_html
    from rapidfuzz.distance import Levenshtein

    class Cost(Config):
        def rename(self, a, b):
            if (a.name, a.colspan, a.rowspan) != (b.name, b.colspan, b.rowspan):
                return 1.0
            return Levenshtein.normalized_distance(a.content, b.content) if a.name == "td" else 0.0

        def children(self, node):
            return node.children

    def parse(s):
        table = lxml_html.fromstring(s)
        return _tree(table if table.tag == "table" else table.find(".//table"))

    p, g = parse(pred_html), parse(gold_html)
    return round(max(0.0, 1 - APTED(p, g, Cost()).compute_edit_distance() / max(p.size(), g.size())), 4)


def table_html(header: list[str], rows: list[list[str]]) -> str:
    from html import escape
    td = lambda c: f"<td>{escape(str(c))}</td>"  # noqa: E731
    return ("<table><thead><tr>" + "".join(td(h) for h in header) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(td(c) for c in r) + "</tr>" for r in rows) + "</tbody></table>")


def items_table_html(elements) -> str | None:
    """The parser's version of the line-items table: the table with the quantity and amount columns, else the longest."""
    tables = [e.table for e in elements if e.type == "table" and e.table]
    if not tables:
        return None
    keyed = [t for t in tables if re.search(r"数量|Qty", " ".join(t.header)) and re.search(r"金額|Amount", " ".join(t.header))]
    best = (keyed or sorted(tables, key=lambda t: len(t.rows), reverse=True))[0]
    return table_html(best.header, best.rows)


# --- speed and cost ---

def cost_per_1k_pages(seconds_per_page: float, gpu_hourly_usd: float) -> float:
    """(seconds per page × 1000 / 3600) × the GPU's hourly price. The price is an assumption; always state it."""
    return round(seconds_per_page * 1000 / 3600 * gpu_hourly_usd, 4)


def recall_at_k(ranked: list[list[str]], gold: list[set[str]], k: int = 5) -> float | None:
    """Share of questions whose gold document (or page id) is among the first k ranked results."""
    hits = [bool(set(r[:k]) & g) for r, g in zip(ranked, gold)]
    return rate(sum(hits), len(hits))


def mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None
