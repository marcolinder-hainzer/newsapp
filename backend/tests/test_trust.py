from app.trust import compute_trust

SOURCES = {
    "a": {"name": "A", "bias": "center", "reliability": 90, "country": "DE"},
    "b": {"name": "B", "bias": "lean_left", "reliability": 85, "country": "DE"},
    "c": {"name": "C", "bias": "right", "reliability": 45, "country": "GB"},
    "d": {"name": "D", "bias": "lean_right", "reliability": 80, "country": "AT"},
}


def art(source, title="Neutrale Überschrift", opinion=0):
    return {"source_id": source, "title": title, "is_opinion": opinion}


def test_single_source_is_flagged_and_scores_lower():
    single = compute_trust([art("a")], SOURCES)
    multi = compute_trust([art("a"), art("b"), art("d")], SOURCES)
    assert single["score"] < multi["score"]
    assert "nur eine Quelle" in single["notes"]["de"][0]
    assert single["components"]["diversity"] == 0


def test_full_spectrum_note_and_range():
    result = compute_trust([art("a"), art("b"), art("d"), art("c")], SOURCES)
    assert 0 <= result["score"] <= 100
    assert any("gesamten politischen Spektrum" in n for n in result["notes"]["de"])


def test_clickbait_and_opinion_reduce_content_score():
    clean = compute_trust([art("c"), art("c")], SOURCES)
    bait = compute_trust([art("c", "SCHOCK! Unglaublich"), art("c", "Kommentar: X", 1)], SOURCES)
    assert bait["components"]["content"] < clean["components"]["content"]


def test_llm_assessment_is_used():
    result = compute_trust([art("a")], SOURCES, {"score": 20, "notes_de": ["Unbestätigt"], "notes_en": ["Unconfirmed"]})
    assert result["components"]["content"] == 20
    assert result["content_method"] == "ai"
    assert "Unbestätigt" in result["notes"]["de"]
