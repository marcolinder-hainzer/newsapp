"""Statischer Export für GitHub Pages."""

import json

from app.db import Database
from app.pipeline import Pipeline
from app.static_export import compact_database, export
from app.translate import Translator


def test_export_writes_all_files(test_settings, feed_transport, tmp_path):
    db = Database(test_settings.db_path)
    translator = Translator(db, enabled=False)
    pipeline = Pipeline(test_settings, db, translator, transport=feed_transport)
    pipeline.run_cycle()

    out = tmp_path / "site" / "data"
    stats = export(db, pipeline.sources, translator.info(), test_settings, out)
    assert stats["stories"] == stats["recent"] > 0

    meta = json.loads((out / "meta.json").read_text())
    assert meta["static"] is True and meta["translation"]["enabled"] is False
    assert meta["last_update"] and meta["generated_at"]

    recent = json.loads((out / "stories-recent.json").read_text())["items"]
    assert json.loads((out / "stories-older.json").read_text())["items"] == []
    rail = next(s for s in recent if "Bahn" in s["title"]["de"])
    assert sorted(rail["source_ids"]) == ["spiegel", "tagesschau", "welt"]
    assert "bahnreform" in rail["search"] and rail["coverage"] > 0

    detail = json.loads((out / "stories" / f"{rail['id']}.json").read_text())
    assert len(detail["articles"]) == 3
    assert detail["speech"]["de"]["text"]

    for name in ("top-day", "top-week", "category-politik", "category-sport"):
        digest = json.loads((out / "digests" / f"{name}.json").read_text())
        assert digest["speech"]["de"]
    briefing = json.loads((out / "briefing.json").read_text())
    assert len(briefing["categories"]) == 10
    assert len(json.loads((out / "sources.json").read_text())["items"]) == 8

    # Datenbank für den Zwischenspeicher verkleinern: Volltexte weg, Meldungen bleiben
    with db.write() as conn:
        conn.execute("UPDATE articles SET content = 'Volltext', content_fetched = 1")
    compact_database(db, test_settings)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM articles WHERE content IS NOT NULL").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0] == stats["stories"]

    # Nächster Lauf nach dem Verkleinern: Auszüge müssen ohne Volltext funktionieren (Regression)
    from app.summarize import summarize_story
    assert summarize_story(db, rail["id"], pipeline.sources, translator) == "pending"
    with db.write() as conn:
        conn.execute("UPDATE stories SET summary_article_count = 0")
    result = pipeline.run_cycle(fetch=False)
    assert "error" not in result, result
