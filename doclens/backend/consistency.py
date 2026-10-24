"""Arithmetic and logic checks on a normalised invoice. They catch extraction errors the evidence check can't:
a quote can be real and still be the wrong number.

`check_invoice` takes plain values (ints, ISO dates) so it can run on predictions and on ground truth alike:

    {"subtotal": 1000, "tax": 100, "total": 1100, "issue_date": "2026-10-24", "due_date": "2026-11-30",
     "line_items": [{"quantity": 2, "unit_price": 500, "amount": 1000, "tax_rate": 0.1}]}
"""
import math

from backend.schemas import Check

TOLERANCE = 1  # yen: tax is rounded per invoice or per tax-rate group, and the rounding rule varies
RATES = (0.10, 0.08)  # standard and reduced consumption tax


def _near(a: float, b: float, tol: float = TOLERANCE) -> bool:
    return abs(a - b) <= tol


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _skip(name: str, why: str) -> Check:
    return Check(name=name, status="skipped", message=why)


def line_amounts(items: list[dict]) -> Check:
    """quantity × unit price = amount, per row (rows missing a number are not checked)."""
    bad, checked = [], 0
    for i, it in enumerate(items):
        q, u, a = _num(it.get("quantity")), _num(it.get("unit_price")), _num(it.get("amount"))
        if None in (q, u, a):
            continue
        checked += 1
        if not _near(q * u, a):
            bad.append((i, q, u, a))
    if not checked:
        return _skip("line_amounts", "no line item has quantity, unit price and amount")
    if bad:
        msg = "; ".join(f"row {i + 1}: {q:g} × {u:,.0f} = {q * u:,.0f}, but the amount is {a:,.0f}" for i, q, u, a in bad)
        return Check(name="line_amounts", status="fail", message=msg, fields=[f"line_items[{i}].amount" for i, *_ in bad])
    return Check(name="line_amounts", status="pass", message=f"{checked} rows: quantity × unit price = amount")


def subtotal_matches_lines(items: list[dict], subtotal) -> Check:
    amounts = [_num(it.get("amount")) for it in items]
    s = _num(subtotal)
    if s is None or not amounts or None in amounts:
        return _skip("subtotal_sum", "needs a subtotal and an amount on every line item")
    total = sum(amounts)
    if _near(total, s):
        return Check(name="subtotal_sum", status="pass", message=f"line amounts add up to the subtotal ({s:,.0f})")
    return Check(name="subtotal_sum", status="fail", fields=["subtotal"],
                 message=f"line amounts add up to {total:,.0f}, but the subtotal is {s:,.0f}")


def total_matches(subtotal, tax, total) -> Check:
    s, t, g = _num(subtotal), _num(tax), _num(total)
    if None in (s, t, g):
        return _skip("total_sum", "needs subtotal, tax and total")
    if _near(s + t, g):
        return Check(name="total_sum", status="pass", message=f"subtotal + tax = total ({g:,.0f})")
    return Check(name="total_sum", status="fail", fields=["subtotal", "tax", "total"],
                 message=f"subtotal {s:,.0f} + tax {t:,.0f} = {s + t:,.0f}, but the total is {g:,.0f}")


def tax_rate(items: list[dict], subtotal, tax) -> Check:
    """Tax must be 10% or 8% of the base. With a rate on every line, each rate group is checked separately
    (rounding tolerance of 1 yen per group). Otherwise the tax must be 10% or 8% of the subtotal, or anywhere between the two:
    a mixed-rate invoice whose lines carry no rate cannot be pinned down further."""
    t, s = _num(tax), _num(subtotal)
    if t is None:
        return _skip("tax_rate", "needs the tax amount")
    rates = [_num(it.get("tax_rate")) for it in items]
    amounts = [_num(it.get("amount")) for it in items]
    if items and None not in rates and None not in amounts:
        groups: dict[float, float] = {}
        for r, a in zip(rates, amounts):
            groups[r] = groups.get(r, 0) + a
        if any(not any(math.isclose(r, k) for k in RATES) for r in groups):
            return Check(name="tax_rate", status="fail", fields=["tax"],
                         message=f"line items use rates {sorted(groups)}, expected 10% or 8%")
        expected = sum(base * r for r, base in groups.items())
        if _near(t, expected, TOLERANCE * len(groups)):
            return Check(name="tax_rate", status="pass", message=f"tax matches {len(groups)} rate group(s): {expected:,.0f}")
        return Check(name="tax_rate", status="fail", fields=["tax"],
                     message=f"tax by line rate should be about {expected:,.0f}, but the tax is {t:,.0f}")
    if s is None:
        return _skip("tax_rate", "needs the subtotal")
    if any(_near(s * r, t) for r in RATES):
        return Check(name="tax_rate", status="pass", message="tax is 10% or 8% of the subtotal")
    if s * min(RATES) - TOLERANCE <= t <= s * max(RATES) + TOLERANCE:  # without per-line rates a mixed-rate invoice lands in between
        return Check(name="tax_rate", status="pass", message="tax is between 8% and 10% of the subtotal (mixed rates are possible; per-line rates would settle it)")
    return Check(name="tax_rate", status="fail", fields=["tax", "subtotal"],
                 message=f"tax {t:,.0f} is outside 8% ({s * 0.08:,.0f}) to 10% ({s * 0.10:,.0f}) of {s:,.0f}")


def dates_in_order(issue_date, due_date) -> Check:
    if not (isinstance(issue_date, str) and isinstance(due_date, str)):
        return _skip("date_order", "needs issue and due dates")
    if issue_date <= due_date:  # ISO strings sort like dates; YYYY-MM sorts correctly against YYYY-MM-DD
        return Check(name="date_order", status="pass", message="issue date is not after the due date")
    return Check(name="date_order", status="fail", fields=["issue_date", "due_date"],
                 message=f"issue date {issue_date} is after the due date {due_date}")


def check_invoice(v: dict) -> list[Check]:
    items = v.get("line_items") or []
    return [
        line_amounts(items),
        subtotal_matches_lines(items, v.get("subtotal")),
        total_matches(v.get("subtotal"), v.get("tax"), v.get("total")),
        tax_rate(items, v.get("subtotal"), v.get("tax")),
        dates_in_order(v.get("issue_date"), v.get("due_date")),
    ]
