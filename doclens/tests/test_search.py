from backend.search import BM25, rrf, terms


def test_terms_latin_and_cjk_bigrams():
    assert terms("Client-Selection ２０２６") == ["client-selection", "2026"]
    assert terms("公平性") == ["公平", "平性"]


def test_bm25_exact_phrase_ranks_first():
    docs = [terms("fairness in general terms"), terms("we define fairness debt here"), terms("resource allocation")]
    scores = BM25(docs).scores(terms("fairness debt"))
    assert scores.argmax() == 1 and scores[2] == 0


def test_rrf_rewards_agreement():
    fused = rrf([[0, 1, 2], [1, 0, 2]])
    assert fused[0] == fused[1] > fused[2]
