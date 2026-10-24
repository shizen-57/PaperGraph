from backend.consistency import check_invoice, dates_in_order, line_amounts, tax_rate, total_matches

GOOD = {
    "subtotal": 3000, "tax": 300, "total": 3300, "issue_date": "2026-10-24", "due_date": "2026-11-30",
    "line_items": [{"quantity": 2, "unit_price": 500, "amount": 1000}, {"quantity": 1, "unit_price": 2000, "amount": 2000}],
}


def by_name(checks):
    return {c.name: c for c in checks}


def test_consistent_invoice_passes_everything():
    assert {c.status for c in check_invoice(GOOD)} == {"pass"}


def test_wrong_row_amount_names_the_field():
    bad = {**GOOD, "line_items": [{"quantity": 2, "unit_price": 500, "amount": 1200}, GOOD["line_items"][1]]}
    c = by_name(check_invoice(bad))
    assert c["line_amounts"].status == "fail" and c["line_amounts"].fields == ["line_items[0].amount"]
    assert "row 1" in c["line_amounts"].message
    assert c["subtotal_sum"].status == "fail"  # 3200 ≠ 3000, so the same error shows up twice


def test_one_yen_rounding_is_allowed():
    assert line_amounts([{"quantity": 3, "unit_price": 33.33, "amount": 100}]).status == "pass"
    assert total_matches(1000, 100, 1101).status == "pass"
    assert total_matches(1000, 100, 1102).status == "fail"


def test_total_check_lists_fields():
    c = total_matches(1000, 100, 1500)
    assert c.status == "fail" and c.fields == ["subtotal", "tax", "total"]


def test_tax_must_be_ten_or_eight_percent_or_between():
    assert tax_rate([], 1000, 100).status == "pass"
    assert tax_rate([], 1000, 80).status == "pass"
    assert tax_rate([], 1000, 93).status == "pass"  # between: a mixed-rate invoice whose lines have no rate
    assert tax_rate([], 1000, 150).status == "fail" and tax_rate([], 1000, 30).status == "fail"


def test_mixed_rates_are_checked_per_group():
    items = [{"amount": 1000, "tax_rate": 0.10}, {"amount": 500, "tax_rate": 0.08}]
    assert tax_rate(items, 1500, 140).status == "pass"  # 100 + 40
    assert tax_rate(items, 1500, 150).status == "fail"  # 10% of everything is wrong when rates are mixed
    assert tax_rate([{"amount": 100, "tax_rate": 0.05}], 100, 5).status == "fail"


def test_dates():
    assert dates_in_order("2026-10-24", "2026-10-24").status == "pass"
    assert dates_in_order("2026-11-01", "2026-10-24").status == "fail"
    assert dates_in_order("2026-10-24", None).status == "skipped"


def test_missing_numbers_are_skipped_not_failed():
    c = by_name(check_invoice({"total": 1100}))
    assert {x.status for x in c.values()} == {"skipped"}
    assert line_amounts([{"quantity": 2, "amount": 1000}]).status == "skipped"
