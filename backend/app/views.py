"""Gemeinsame Aufbereitung der Daten – genutzt von der REST-API und vom statischen Export."""

from __future__ import annotations

from datetime import timedelta

from . import categories, digests, stories
from .db import Database, iso, loads, utcnow

APP_NAME = "Weitblick"
APP_VERSION = "2.0.0"


def meta_payload(db: Database, sources: dict[str, dict], translation_info: dict,
                 refresh_interval_minutes: int, running: bool = False, static: bool = False) -> dict:
    since = iso(utcnow() - timedelta(hours=24))
    with db.connect() as conn:
        story_count = conn.execute("SELECT COUNT(*) FROM stories WHERE last_updated >= ?", (since,)).fetchone()[0]
        article_count = conn.execute("SELECT COUNT(*) FROM articles WHERE published_at >= ?", (since,)).fetchone()[0]
    countries = sorted({s.get("country") for s in sources.values() if s.get("country")})
    return {
        "app": {"name": APP_NAME, "version": APP_VERSION},
        "static": static,
        "categories": categories.CATEGORIES,
        "countries": countries,
        "translation": translation_info,
        "last_update": db.get_meta("last_update"),
        "cycle_running": running,
        "refresh_interval_minutes": refresh_interval_minutes,
        "stats": {"stories_24h": story_count, "articles_24h": article_count, "sources": len(sources)},
    }


def story_detail_payload(db: Database, story: dict, sources: dict[str, dict]) -> dict:
    item = stories.serialize_many(db, [story], sources)[0]
    summary = loads(story.get("summary_json"), {}) or {}
    trust = loads(story.get("trust_json"), {}) or {}
    item.update({
        "summary": {
            "generated_by": summary.get("generated_by"),
            "model": summary.get("model"),
            "generated_at": summary.get("generated_at"),
            "de": summary.get("de") or {"available": False},
            "en": summary.get("en") or {"available": False},
        },
        "trust": {**trust, "score": story.get("trust_score") or 0},
        "articles": stories.story_articles(db, story["id"], sources),
        "speech": {lang: dict(zip(("text", "lang"), stories.story_speech(story, lang))) for lang in ("de", "en")},
    })
    return item


def digest_payload(db: Database, scope: str, sources: dict[str, dict]) -> dict:
    """Briefing für einen Bereich; fehlt es noch, wird es sofort erstellt."""
    digest = digests.get_digest(db, scope, sources)
    if digest is None:
        digests.generate_digest(db, scope)
        digest = digests.get_digest(db, scope, sources)
    digest["speech"] = {lang: digests.digest_speech(digest, lang) for lang in ("de", "en")}
    return digest


def sources_payload(db: Database, sources: dict[str, dict]) -> dict:
    since = iso(utcnow() - timedelta(hours=24))
    with db.connect() as conn:
        counts = {r["source_id"]: r["n"] for r in conn.execute(
            "SELECT source_id, COUNT(*) AS n FROM articles WHERE published_at >= ? GROUP BY source_id",
            (since,)).fetchall()}
        feed_rows = conn.execute("SELECT source_id, last_status FROM feeds").fetchall()
    feed_status: dict[str, dict] = {}
    for r in feed_rows:
        st = feed_status.setdefault(r["source_id"], {"feeds": 0, "errors": 0})
        st["feeds"] += 1
        st["errors"] += 1 if r["last_status"] == "error" else 0
    out = []
    for src in sorted(sources.values(), key=lambda s: (s.get("language") != "de", s["name"].lower())):
        item = stories.public_source(src)
        item["articles_24h"] = counts.get(src["id"], 0)
        item.update(feed_status.get(src["id"], {"feeds": 0, "errors": 0}))
        out.append(item)
    return {"items": out}
