from backend.eval import p95, rate, supports


def test_rate():
    assert rate([True, False, True]) == 2 / 3
    assert rate([]) is None


def test_supports_doc_and_page():
    q = {"expected_documents": ["a"], "expected_pages": [4]}
    assert supports("a", 3, 5, q)
    assert not supports("a", 5, 6, q)
    assert not supports("b", 4, 4, q)
    assert supports("a", 9, 9, {"expected_documents": ["a"]})  # no pages given: document is enough


def test_p95():
    assert p95(list(range(1, 101))) == 95
    assert p95([]) is None
