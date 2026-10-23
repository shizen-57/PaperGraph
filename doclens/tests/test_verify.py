from backend.schemas import Element
from backend.verify import confidence, coverage, locate, quote_score


def test_exact_quote():
    assert quote_score("jointly optimize client selection", "We jointly optimize client selection and more.") == 1.0


def test_line_breaks_and_case_ignored():
    assert quote_score("Jointly optimize client\nselection", "we jointly   optimize client selection") == 1.0


def test_full_width_matches_half_width():
    assert quote_score("重量 250 g", "重量 ２５０ g") == 1.0


def test_hyphenation_is_fuzzy_match():
    s = quote_score("multiclient scheduling", "a multi-client scheduling policy")
    assert 0.9 <= s < 1.0


def test_unrelated_quote_rejected():
    assert quote_score("the moon is made of cheese", "We jointly optimize client selection.") < 0.9
    assert quote_score("", "anything") == 0.0


def test_locate_picks_the_element():
    els = [Element(id=f"e{i}", doc_id="d", type="text", page=i + 1, bbox=None, text=t)
           for i, t in enumerate(["first paragraph here", "the quote lives in this one", "third"])]
    chk = locate("quote lives", els)
    assert chk.found and chk.element_id == "e1" and chk.page == 2


def test_confidence_bands():
    one = dict.fromkeys(["retrieval", "quote", "citations", "numbers", "coverage"], 1.0)
    assert confidence(one) == (1.0, "High")
    assert confidence({**one, "numbers": 0.0})[1] == "High"  # exactly 0.90
    assert confidence({**one, "retrieval": 0.0})[1] == "Low"  # 0.70
    assert confidence({**one, "quote": 0.0, "retrieval": 0.0})[1] == "Unverified"  # 0.40


def test_coverage():
    assert coverage("A is true [1]. B is true. C [2].") == 2 / 3
