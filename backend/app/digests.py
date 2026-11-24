"""Briefings: Top-Meldungen des Tages/der Woche und das Wichtigste je Kategorie.

Die Briefings werden kostenlos und automatisch aus den relevantesten Meldungen erzeugt
(Relevanz = Zahl unabhängiger Quellen × Aktualität × Vertrauen) – zweisprachig, weil jede
Meldung eine deutsche und eine englische Fassung hat.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from . import categories
from .db import Database, dumps, iso, loads, utcnow
from .stories import importance, localized, serialize_many
from .textutil import split_sentences

log = logging.getLogger(__name__)

SCOPE_SETTINGS = {
    "top:day": {"hours": 24, "half_life": 12.0, "limit": 12},
    "top:week": {"hours": 24 * 7, "half_life": 72.0, "limit": 15},
}


def all_scopes() -> list[str]:
    return ["top:day", "top:week"] + [f"category:{slug}" for slug in categories.SLUGS]


def scope_title(scope: str, lang: str) -> str:
    if scope == "top:day":
        return "Top-Meldungen des Tages" if lang == "de" else "Top stories of the day"
    if scope == "top:week":
        return "Top-Meldungen der Woche" if lang == "de" else "Top stories of the week"
    slug = scope.split(":", 1)[1]
    name = categories.label(slug, lang)
    return f"Das Wichtigste: {name}" if lang == "de" else f"Key developments: {name}"


def select_stories(db: Database, scope: str) -> list[dict]:
    now = utcnow()
    if scope in SCOPE_SETTINGS:
        cfg = SCOPE_SETTINGS[scope]
        with db.connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM stories WHERE last_updated >= ?", (iso(now - timedelta(hours=cfg["hours"])),)
            ).fetchall()]
        rows.sort(key=lambda r: importance(r, now, cfg["half_life"]), reverse=True)
        return rows[: cfg["limit"]]

    slug = scope.split(":", 1)[1]
    rows: list[dict] = []
    for hours in (24, 72):
        with db.connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM stories WHERE category = ? AND last_updated >= ?",
                (slug, iso(now - timedelta(hours=hours))),
            ).fetchall()]
        if len(rows) >= 4:
            break
    rows.sort(key=lambda r: importance(r, now, 18.0), reverse=True)
    return rows[:10]


def _quote(text: str, lang: str) -> str:
    return f"„{text}“" if lang == "de" else f"“{text}”"


def _join(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    word = " und " if lang == "de" else " and "
    return ", ".join(items[:-1]) + word + items[-1]


def build_digest(scope: str, stories: list[dict]) -> dict:
    out = {}
    for lang in ("de", "en"):
        items = []
        for s in stories[:8]:
            loc = localized(s, lang)
            first = split_sentences(loc["teaser"])[:1]
            text = loc["title"]
            if first and first[0].rstrip(".") not in text and len(first[0]) <= 240:
                text += f" – {first[0]}"
            items.append({"story_id": s["id"], "text": text})

        def sources_label(n: int) -> str:
            if lang == "de":
                return "1 Quelle" if n == 1 else f"{n} Quellen"
            return "1 source" if n == 1 else f"{n} sources"

        top = [f"{_quote(localized(s, lang)['title'], lang)} ({sources_label(s.get('source_count') or 0)})"
               for s in stories[:3]]
        if not stories:
            overview = ("Für diesen Bereich liegen aktuell keine Meldungen vor." if lang == "de"
                        else "There are currently no stories in this section.")
        elif scope == "top:day":
            overview = (f"Am meisten berichtet wird heute über {_join(top, lang)}." if lang == "de"
                        else f"Today's most widely covered stories: {_join(top, lang)}.")
        elif scope == "top:week":
            overview = (f"Die meistbeachteten Themen der vergangenen sieben Tage: {_join(top, lang)}."
                        if lang == "de" else f"The most widely covered stories of the past seven days: {_join(top, lang)}.")
        else:
            name = categories.label(scope.split(":", 1)[1], lang)
            overview = (f"In der Kategorie {name} berichten derzeit die meisten Medien über {_join(top, lang)}."
                        if lang == "de" else f"Most widely covered in {name} right now: {_join(top, lang)}.")
        out[lang] = {"headline": scope_title(scope, lang), "overview": overview, "items": items}
    return out


def generate_digest(db: Database, scope: str) -> dict:
    stories = select_stories(db, scope)
    content = build_digest(scope, stories)
    with db.write() as conn:
        conn.execute(
            """INSERT INTO digests(scope, content_json, story_ids, generated_by, generated_at) VALUES(?,?,?,?,?)
               ON CONFLICT(scope) DO UPDATE SET content_json=excluded.content_json, story_ids=excluded.story_ids,
                 generated_by=excluded.generated_by, generated_at=excluded.generated_at""",
            (scope, dumps(content), dumps([s["id"] for s in stories]), "template", iso(utcnow())),
        )
    return content


def refresh_digests(db: Database) -> int:
    """Erstellt alle Briefings neu (kostenlos und schnell, daher bei jedem Durchlauf)."""
    for scope in all_scopes():
        generate_digest(db, scope)
    return len(all_scopes())


def get_digest(db: Database, scope: str, sources: dict[str, dict]) -> dict | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM digests WHERE scope = ?", (scope,)).fetchone()
        if row is None:
            return None
        ids = loads(row["story_ids"], [])
        stories = []
        if ids:
            placeholders = ",".join("?" * len(ids))
            stories = [dict(r) for r in conn.execute(
                f"SELECT * FROM stories WHERE id IN ({placeholders})", ids).fetchall()]
    order = {sid: i for i, sid in enumerate(ids)}
    stories.sort(key=lambda s: order.get(s["id"], 999))
    content = loads(row["content_json"], {}) or {}
    existing = {s["id"] for s in stories}
    for lang in ("de", "en"):
        if lang in content:
            content[lang]["items"] = [i for i in content[lang].get("items", []) if i.get("story_id") in existing]
    return {
        "scope": scope,
        "title": {"de": scope_title(scope, "de"), "en": scope_title(scope, "en")},
        "generated_at": row["generated_at"],
        "generated_by": row["generated_by"],
        "content": content,
        "stories": serialize_many(db, stories, sources),
    }


def digest_speech(digest: dict, lang: str) -> str:
    content = (digest.get("content") or {}).get(lang) or {}
    pieces = [content.get("headline") or digest["title"][lang]]
    items = content.get("items") or []
    if not items and content.get("overview"):
        pieces.append(content["overview"])
    for i, item in enumerate(items, 1):
        text = item.get("text", "").strip()
        if text and text[-1] not in ".!?…":
            text += "."
        if text:
            pieces.append((f"Meldung {i}: " if lang == "de" else f"Story {i}: ") + text)
    return " ".join(p.strip() for p in pieces if p)
