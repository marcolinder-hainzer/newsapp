"""Integrationstest: Feeds abrufen → gruppieren → bewerten → zusammenfassen → API."""

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(test_settings, feed_transport, translator=None):
    app = create_app(test_settings, translator=translator, transport=feed_transport, start_scheduler=False)
    app.state.pipeline.run_cycle()
    return app, TestClient(app)


def find_story(items, needle):
    return next(s for s in items if needle.lower() in (s["title"]["de"] + s["title"]["en"]).lower())


def test_cycle_groups_articles_into_stories(test_settings, feed_transport):
    app, client = make_client(test_settings, feed_transport)
    data = client.get("/api/stories", params={"hours": 24}).json()
    items = data["items"]
    assert data["total"] == len(items)

    rail_de = find_story(items, "Bahn")
    assert rail_de["source_count"] == 3  # Tagesschau, Spiegel, Welt
    assert rail_de["bias"] == {"left": 1, "center": 1, "right": 1}
    assert rail_de["category"] == "politik"

    cup = find_story(items, "Pokalfinale")
    assert cup["source_count"] == 2
    assert cup["category"] == "sport"

    storm_en = find_story(items, "Storm Elara")
    assert storm_en["source_count"] == 2  # BBC + Guardian (englisch)

    tool = find_story(items, "Router")
    assert tool["source_count"] == 1
    assert tool["category"] == "technologie"
    assert tool["trust"]["score"] < rail_de["trust"]["score"]


def test_story_detail_has_bilingual_fallback_summary(test_settings, feed_transport):
    _, client = make_client(test_settings, feed_transport)
    items = client.get("/api/stories", params={"hours": 24}).json()["items"]
    story_id = find_story(items, "Bahn")["id"]
    detail = client.get(f"/api/stories/{story_id}").json()
    assert detail["summary"]["generated_by"] == "extractive"
    assert detail["summary"]["de"]["available"] is True
    assert detail["summary"]["en"]["available"] is False  # ohne KI keine Übersetzung
    assert len(detail["articles"]) == 3
    assert {a["source"]["bias_bucket"] for a in detail["articles"]} == {"left", "center", "right"}
    assert detail["speech"]["de"]["text"].startswith(detail["summary"]["de"]["title"])
    assert detail["speech"]["en"]["lang"] == "de"  # keine englische Fassung → Originalsprache
    assert detail["trust"]["components"]["corroboration"] > 0
    # Weitere Schlagzeilen, nach Zuverlässigkeit der Quelle sortiert
    assert detail["summary"]["de"]["key_points"] == [
        "Das Wochenmagazin (fiktiv): Bahnreform: Bundestag stimmt für neuen Infrastrukturfonds der Bahn",
        "Morgenzeitung (fiktiv): Bundestag beschließt Bahnreform – Kritik an Finanzierung des Infrastrukturfonds",
    ]


def test_filters_and_sorting(test_settings, feed_transport):
    _, client = make_client(test_settings, feed_transport)
    sport = client.get("/api/stories", params={"category": "sport", "hours": 24}).json()["items"]
    assert sport and all(s["category"] == "sport" for s in sport)

    english = client.get("/api/stories", params={"lang": "en", "hours": 24}).json()["items"]
    assert english and all("en" in s["languages"] for s in english)

    multi = client.get("/api/stories", params={"min_sources": 2, "hours": 24}).json()["items"]
    assert multi and all(s["source_count"] >= 2 for s in multi)

    trusted = client.get("/api/stories", params={"min_trust": 70, "hours": 24}).json()["items"]
    assert all(s["trust"]["score"] >= 70 for s in trusted)

    balanced = client.get("/api/stories", params={"perspective": "balanced", "hours": 24}).json()["items"]
    assert [s["source_count"] for s in balanced] == [3]

    search = client.get("/api/stories", params={"q": "Musterstadt", "hours": 24}).json()["items"]
    assert len(search) == 1

    by_source = client.get("/api/stories", params={"source": "heise", "hours": 24}).json()["items"]
    assert len(by_source) == 1

    latest = client.get("/api/stories", params={"sort": "latest", "hours": 24}).json()["items"]
    stamps = [s["last_updated"] for s in latest]
    assert stamps == sorted(stamps, reverse=True)


def test_digests_and_meta(test_settings, feed_transport):
    _, client = make_client(test_settings, feed_transport)
    day = client.get("/api/digest", params={"scope": "top:day"}).json()
    assert day["generated_by"] == "template"
    assert day["content"]["de"]["items"]
    assert day["stories"][0]["source_count"] >= day["stories"][-1]["source_count"]
    assert "Top-Meldungen" in day["speech"]["de"]

    briefing = client.get("/api/briefing").json()
    assert len(briefing["categories"]) == 10
    politik = next(d for d in briefing["categories"] if d["scope"] == "category:politik")
    assert politik["stories"]

    meta = client.get("/api/meta").json()
    assert meta["translation"]["enabled"] is False
    assert "llm" not in meta and "tts" not in meta
    assert meta["stats"]["sources"] == 9
    assert meta["last_update"]

    sources = client.get("/api/sources").json()["items"]
    assert {s["id"] for s in sources} >= {"bbc", "tagesschau"}
    assert client.get("/api/digest", params={"scope": "nope"}).status_code == 404
    assert client.get("/api/tts/story/1").status_code == 404  # keine kostenpflichtigen Stimmen mehr


def test_second_cycle_is_idempotent(test_settings, feed_transport):
    app, client = make_client(test_settings, feed_transport)
    before = client.get("/api/stories", params={"hours": 24}).json()["total"]
    app.state.pipeline.run_cycle()
    after = client.get("/api/stories", params={"hours": 24}).json()["total"]
    assert before == after
