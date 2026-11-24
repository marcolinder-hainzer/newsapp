"""Kostenlose Übersetzung: Zusammenfassungen in beiden Sprachen und sprachübergreifende Gruppierung."""

from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from app.translate import Translator
from tests.conftest import FakeTranslator


def test_translated_summaries_and_cross_language_merge(test_settings, feed_transport):
    translator = FakeTranslator()
    app = create_app(test_settings, translator=translator, transport=feed_transport, start_scheduler=False)
    app.state.pipeline.run_cycle()
    client = TestClient(app)
    items = client.get("/api/stories", params={"hours": 24}).json()["items"]

    # Deutsche Meldung (3 Quellen) + englische BBC-Meldung werden über die Übersetzung zusammengeführt
    rail = [s for s in items if "Bahn" in s["title"]["de"]]
    assert len(rail) == 1 and rail[0]["source_count"] == 4
    detail = client.get(f"/api/stories/{rail[0]['id']}").json()
    assert detail["summary"]["de"]["machine_translated"] is False
    assert detail["summary"]["en"]["machine_translated"] is False  # BBC liefert die englische Fassung nativ

    # Rein deutschsprachige Meldung bekommt eine maschinell übersetzte englische Fassung
    router = next(s for s in items if "Router" in s["title"]["de"])
    detail = client.get(f"/api/stories/{router['id']}").json()
    en = detail["summary"]["en"]
    assert en["available"] and en["machine_translated"] and en["source_lang"] == "de"
    assert en["title"].startswith("[en] Neues Open-Source-Werkzeug")
    assert detail["speech"]["en"]["lang"] == "en"
    assert router["title_is_original"]["en"] is False

    # Briefings sind zweisprachig
    day = client.get("/api/digest", params={"scope": "top:day"}).json()
    assert day["content"]["en"]["overview"].startswith("Today's most widely covered stories")
    assert "Meldung 1:" in day["speech"]["de"]


def test_translation_budget_continues_next_cycle(test_settings, feed_transport):
    translator = FakeTranslator(budget_segments=3)
    app = create_app(test_settings, translator=translator, transport=feed_transport, start_scheduler=False)
    pipeline = app.state.pipeline
    pipeline.run_cycle()
    db = app.state.db
    with db.connect() as conn:
        pending = conn.execute("SELECT COUNT(*) FROM stories WHERE summary_json LIKE '%\"translation_pending\": true%'"
                               ).fetchone()[0]
    assert pending > 0
    translator.budget = None  # nächster Durchlauf hat wieder Zeit
    pipeline.run_cycle(fetch=False)
    with db.connect() as conn:
        pending = conn.execute("SELECT COUNT(*) FROM stories WHERE summary_json LIKE '%\"translation_pending\": true%'"
                               ).fetchone()[0]
    assert pending == 0


def test_translator_cache_and_budget(test_settings, monkeypatch):
    db = Database(test_settings.db_path)
    translator = Translator(db, enabled=False)
    translator.enabled = True  # Modelle werden simuliert
    calls = []

    def fake_batch(texts, src, tgt):
        calls.append(list(texts))
        return [f"EN:{t}" for t in texts]

    monkeypatch.setattr(translator, "_translate_batch", fake_batch)
    translator.start_budget(60)
    assert translator.translate(["Hallo Welt", "", "Guten Tag"], "de", "en") == ["EN:Hallo Welt", "", "EN:Guten Tag"]
    assert translator.translate(["Hallo Welt"], "de", "en") == ["EN:Hallo Welt"]
    assert len(calls) == 1  # zweiter Aufruf kommt aus dem Zwischenspeicher
    assert translator.stats["cached"] == 1

    translator.start_budget(0)  # Zeitbudget erschöpft → nichts Neues übersetzen
    assert translator.translate(["Neuer Satz"], "de", "en") == [None]
    assert translator.translate(["Hallo Welt"], "de", "en") == ["EN:Hallo Welt"]  # Cache geht immer
