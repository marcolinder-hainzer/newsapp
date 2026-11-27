"""Österreich-Erkennung, Österreich-Filter und Migration älterer Datenbanken."""

import sqlite3

from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from app.regions import austria_hits, story_regions

SOURCES = {
    "orf": {"country": "AT"}, "spiegel": {"country": "DE"}, "bbc": {"country": "GB"},
}


def art(source, title, desc="", region=None):
    return {"source_id": source, "title": title, "description": desc, "region": region}


def test_austria_hits():
    assert austria_hits("Wiener Gemeinderat und Tiroler Landtag beraten") == 2
    assert austria_hits("Die ÖVP und die SPÖ einigen sich") == 2
    assert austria_hits("Bundestag beschließt Reform") == 0
    assert austria_hits("Stewiens Wohnung") == 0  # keine Treffer mitten im Wort


def test_story_regions_rules():
    # Österreichisches Medium + österreichischer Begriff
    assert story_regions([art("orf", "Kickl kritisiert Regierung")], SOURCES) == ["AT"]
    # Österreichisches Medium über ein Auslandsthema → kein Österreich-Thema
    assert story_regions([art("orf", "US-Senat stimmt über Haushalt ab")], SOURCES) == []
    # Deutsches Medium mit zwei eindeutigen Begriffen
    assert story_regions([art("spiegel", "Lawinengefahr in Tirol: Arlberg gesperrt")], SOURCES) == ["AT"]
    # Nur eine beiläufige Erwähnung im Ausland → nein
    assert story_regions([art("bbc", "EU summit: leaders from Austria and others meet")], SOURCES) == []
    # Regionaler Österreich-Feed
    assert story_regions([art("orf", "Unfall auf der Autobahn", region="AT")], SOURCES) == ["AT"]


def test_region_filter_and_digest(test_settings, feed_transport):
    app = create_app(test_settings, transport=feed_transport, start_scheduler=False)
    app.state.pipeline.run_cycle()
    client = TestClient(app)
    at = client.get("/api/stories", params={"region": "AT", "hours": 24}).json()["items"]
    assert [s["title"]["de"] for s in at] == ["Nationalrat beschließt Budget – ÖVP und SPÖ verteidigen Sparpaket"]
    assert at[0]["regions"] == ["AT"]
    digest = client.get("/api/digest", params={"scope": "region:AT"}).json()
    assert digest["title"]["de"] == "Das Wichtigste aus Österreich"
    assert digest["stories"][0]["id"] == at[0]["id"]
    assert client.get("/api/briefing").json()["austria"]["scope"] == "region:AT"

    # Ausgeblendete Medien: Meldungen nur dieser Medien verschwinden
    everything = client.get("/api/stories", params={"hours": 24}).json()["total"]
    without = client.get("/api/stories", params={"hours": 24, "exclude_sources": "orfat,heise"}).json()["total"]
    assert without == everything - 2


def test_migration_adds_region_columns(tmp_path):
    from app.db import SCHEMA

    # Datenbank im alten Format (ohne die neuen Spalten) anlegen
    old_schema = (SCHEMA.replace(",\n    region TEXT\n);", "\n);")
                  .replace("    regions TEXT DEFAULT '[]',\n", ""))
    assert "region" not in old_schema
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(old_schema)
    conn.execute("INSERT INTO stories(id, dirty) VALUES (1, 0)")
    conn.commit()
    conn.close()

    db = Database(path)
    with db.connect() as c:
        assert "region" in {r["name"] for r in c.execute("PRAGMA table_info(articles)")}
        assert "region" in {r["name"] for r in c.execute("PRAGMA table_info(feeds)")}
        assert "regions" in {r["name"] for r in c.execute("PRAGMA table_info(stories)")}
        assert c.execute("SELECT dirty FROM stories WHERE id = 1").fetchone()[0] == 1
