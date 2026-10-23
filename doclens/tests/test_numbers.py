from backend.verify import check_numbers


def test_commas_ignored():
    assert check_numbers("Current is 1500 mA [1].", ["current 1,500 mA"]) == []


def test_decimals():
    assert check_numbers("It weighs 2.50 kg.", ["Weight: 2.5 kg"]) == []


def test_missing_number_flagged():
    assert check_numbers("Revenue was 120 and 999 [1].", ["Revenue 120"]) == ["999"]


def test_full_width_digits():
    assert check_numbers("It weighs 250 g.", ["重量 ２５０ g"]) == []


def test_citation_markers_ignored():
    assert check_numbers("See [3].", []) == []


def test_no_numbers():
    assert check_numbers("Insufficient evidence.", ["anything 42"]) == []
