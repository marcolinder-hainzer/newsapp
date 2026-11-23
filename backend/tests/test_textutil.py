from app import categories
from app.textutil import (canonical_url, clean_html, clickbait_hits, guess_language, looks_like_opinion,
                          split_sentences, tokenize)


def test_clean_html_strips_tags_and_entities():
    assert clean_html("<p>Hallo&nbsp;<b>Welt</b> &amp; mehr</p>") == "Hallo Welt & mehr"
    assert clean_html("Text The post Foo appeared first on Bar.") == "Text"


def test_canonical_url_removes_tracking():
    url = "https://WWW.Example.com/a/b?utm_source=x&id=5&fbclid=1#frag"
    assert canonical_url(url) == "https://www.example.com/a/b?id=5"


def test_tokenize_language_specific_stopwords():
    assert "war" in tokenize("The war in the north", "en")
    assert "war" not in tokenize("Es war einmal", "de")
    tokens = tokenize("Die Regierungen beschließen Reformen", "de")
    assert "regier" in tokens or "regierung" in tokens


def test_split_sentences():
    text = "Erster Satz. Zweiter Satz! Dritter? Ja."
    assert split_sentences(text) == ["Erster Satz.", "Zweiter Satz!", "Dritter?", "Ja."]


def test_clickbait_and_opinion():
    assert clickbait_hits("SCHOCK-Sturm! Unglaubliche Bilder") >= 2
    assert clickbait_hits("Bundestag beschließt Reform") == 0
    assert looks_like_opinion("Kommentar: Die Reform ist richtig", "https://x.de/a")
    assert looks_like_opinion("Titel", "https://x.de/meinung/abc")
    assert not looks_like_opinion("Bundestag beschließt Reform", "https://x.de/politik/a")


def test_guess_language():
    assert guess_language("Der Bundestag hat die Reform beschlossen und das ist neu") == "de"
    assert guess_language("The parliament has approved the reform and it is new") == "en"


def test_category_rules():
    assert categories.category_from_url("https://www.spiegel.de/sport/fussball/x") == "sport"
    assert categories.category_from_url("https://www.tagesschau.de/ausland/europa/x.html") == "international"
    assert categories.category_from_keywords("Die EZB senkt den Zins wegen der Inflation") == "wirtschaft"
    assert categories.category_from_keywords("Lorem ipsum dolor") is None
