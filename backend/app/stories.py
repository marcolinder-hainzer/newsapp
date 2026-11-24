"""Meldungen: Kennzahlen berechnen, filtern, sortieren und für die API aufbereiten."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta

from . import categories
from .db import Database, dumps, iso, loads, parse_iso, utcnow
from .sources import BIAS_BUCKET, factuality
from .textutil import split_sentences
from .trust import compute_trust, trust_label


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------

def _pick_headline(articles: list[dict], sources: dict[str, dict]) -> dict:
    def key(a):
        rel = int(sources.get(a["source_id"], {}).get("reliability") or 50)
        return (a["is_opinion"], -rel, a["published_at"])
    return sorted(articles, key=key)[0]


def coverage_score(source_count: int, article_count: int, countries: int, buckets: int) -> float:
    return (math.log2(1 + source_count) + 0.25 * min(countries, 4) + 0.05 * min(article_count, 30)
            + 0.3 * max(buckets - 1, 0))


def recompute_stories(db: Database, sources: dict[str, dict], story_ids: set[int] | None = None) -> int:
    """Berechnet Quellenanzahl, Ausrichtung, Vertrauens-Score usw. für geänderte Meldungen neu."""
    with db.connect() as conn:
        if story_ids:
            placeholders = ",".join("?" * len(story_ids))
            rows = conn.execute(f"SELECT * FROM stories WHERE dirty = 1 OR id IN ({placeholders})",
                                list(story_ids)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM stories WHERE dirty = 1").fetchall()
        stories = [dict(r) for r in rows]
        if not stories:
            return 0
        ids = [s["id"] for s in stories]
        placeholders = ",".join("?" * len(ids))
        article_rows = conn.execute(
            f"""SELECT id, story_id, source_id, title, description, image_url, language, category,
                       category_conf, is_opinion, published_at FROM articles WHERE story_id IN ({placeholders})""",
            ids,
        ).fetchall()

    by_story: dict[int, list[dict]] = {}
    for a in article_rows:
        by_story.setdefault(a["story_id"], []).append(dict(a))

    updates, deletions = [], []
    for story in stories:
        arts = [a for a in by_story.get(story["id"], []) if a["source_id"] in sources]
        if not arts:
            deletions.append(story["id"])
            continue
        source_ids = {a["source_id"] for a in arts}
        bias = Counter(BIAS_BUCKET.get(sources[s]["bias"], "center") for s in source_ids)
        countries = sorted({sources[s].get("country") for s in source_ids if sources[s].get("country")})
        languages = sorted({a["language"] for a in arts if a["language"]})
        headline_article = _pick_headline(arts, sources)
        image = headline_article["image_url"] or next((a["image_url"] for a in sorted(
            arts, key=lambda a: -int(sources[a["source_id"]].get("reliability") or 0)) if a["image_url"]), None)

        votes = Counter()
        for a in arts:
            votes[a["category"]] += 1 + (a["category_conf"] or 0)
        category = votes.most_common(1)[0][0] if votes else categories.DEFAULT_CATEGORY
        if category not in categories.SLUGS:
            category = categories.DEFAULT_CATEGORY

        trust = compute_trust(arts, sources)
        published = sorted(a["published_at"] for a in arts)
        coverage = coverage_score(len(source_ids), len(arts), len(countries), len(bias))
        updates.append((
            category, headline_article["title"], headline_article["language"], image, published[0], published[-1],
            len(arts), len(source_ids), dumps(languages), dumps(countries), bias.get("left", 0),
            bias.get("center", 0), bias.get("right", 0), trust["score"], dumps(trust), coverage, story["id"],
        ))

    with db.write() as conn:
        conn.executemany(
            """UPDATE stories SET category=?, headline=?, headline_lang=?, image_url=?, first_seen=?, last_updated=?,
                   article_count=?, source_count=?, languages=?, countries=?, bias_left=?, bias_center=?,
                   bias_right=?, trust_score=?, trust_json=?, coverage=?, dirty=0 WHERE id=?""",
            updates,
        )
        if deletions:
            placeholders = ",".join("?" * len(deletions))
            conn.execute(f"DELETE FROM stories WHERE id IN ({placeholders})", deletions)
    return len(updates)


def importance(story: dict, now: datetime, half_life_hours: float = 12.0) -> float:
    last = parse_iso(story.get("last_updated")) or now
    first = parse_iso(story.get("first_seen")) or last
    age_h = max(0.0, 0.6 * (now - last).total_seconds() / 3600 + 0.4 * (now - first).total_seconds() / 3600)
    trust_factor = 0.6 + 0.4 * (story.get("trust_score") or 50) / 100
    return (story.get("coverage") or 0) * trust_factor * 0.5 ** (age_h / half_life_hours)


# ---------------------------------------------------------------------------
# Aufbereitung für die API
# ---------------------------------------------------------------------------

def _teaser_from_text(text: str, max_chars: int = 260) -> str:
    sentences = split_sentences(text or "")
    out = ""
    for s in sentences:
        if len(out) + len(s) > max_chars and out:
            break
        out = f"{out} {s}".strip()
    return out or (text or "")[:max_chars]


def blindspot(story: dict) -> str | None:
    left, right = story.get("bias_left") or 0, story.get("bias_right") or 0
    if (story.get("source_count") or 0) < 3:
        return None
    if left == 0 and right >= 2:
        return "left"   # wird von linken Medien kaum beachtet
    if right == 0 and left >= 2:
        return "right"  # wird von rechten Medien kaum beachtet
    return None


def localized(story: dict, lang: str) -> dict:
    summary = loads(story.get("summary_json"), {}) or {}
    part = summary.get(lang) or {}
    if part.get("available", True) and part.get("title"):
        return {"title": part["title"], "teaser": _teaser_from_text(part.get("summary", "")), "original": False}
    return {"title": story.get("headline") or "", "teaser": "", "original": story.get("headline_lang") != lang}


def serialize_story(story: dict, sources: dict[str, dict], top_sources: list[str] | None = None,
                    teaser_fallback: str = "") -> dict:
    loc = {lang: localized(story, lang) for lang in ("de", "en")}
    for lang in ("de", "en"):
        if not loc[lang]["teaser"] and teaser_fallback:
            loc[lang]["teaser"] = _teaser_from_text(teaser_fallback)
    trust = loads(story.get("trust_json"), {}) or {}
    return {
        "id": story["id"],
        "category": story.get("category") or categories.DEFAULT_CATEGORY,
        "title": {"de": loc["de"]["title"], "en": loc["en"]["title"]},
        "teaser": {"de": loc["de"]["teaser"], "en": loc["en"]["teaser"]},
        "title_is_original": {"de": loc["de"]["original"], "en": loc["en"]["original"]},
        "headline_lang": story.get("headline_lang"),
        "image_url": story.get("image_url"),
        "first_seen": story.get("first_seen"),
        "last_updated": story.get("last_updated"),
        "article_count": story.get("article_count") or 0,
        "source_count": story.get("source_count") or 0,
        "languages": loads(story.get("languages"), []),
        "countries": loads(story.get("countries"), []),
        "bias": {"left": story.get("bias_left") or 0, "center": story.get("bias_center") or 0,
                 "right": story.get("bias_right") or 0},
        "blindspot": blindspot(story),
        "trust": {"score": story.get("trust_score") or 0,
                  "label": trust.get("label") or trust_label(story.get("trust_score") or 0)},
        "summary_status": story.get("summary_status") or "none",
        "top_sources": [{"id": s, "name": sources[s]["name"]} for s in (top_sources or []) if s in sources],
    }


def _top_sources_and_teasers(conn, story_ids: list[int], sources: dict[str, dict]) -> tuple[dict, dict]:
    if not story_ids:
        return {}, {}
    placeholders = ",".join("?" * len(story_ids))
    rows = conn.execute(
        f"SELECT story_id, source_id, title, description FROM articles WHERE story_id IN ({placeholders})",
        story_ids,
    ).fetchall()
    tops: dict[int, list[str]] = {}
    teasers: dict[int, str] = {}
    best_rel: dict[int, int] = {}
    for r in rows:
        lst = tops.setdefault(r["story_id"], [])
        if r["source_id"] not in lst:
            lst.append(r["source_id"])
        rel = int(sources.get(r["source_id"], {}).get("reliability") or 0)
        if r["description"] and rel > best_rel.get(r["story_id"], -1):
            best_rel[r["story_id"]] = rel
            teasers[r["story_id"]] = r["description"]
    for sid, lst in tops.items():
        lst.sort(key=lambda s: -int(sources.get(s, {}).get("reliability") or 0))
        tops[sid] = lst[:4]
    return tops, teasers


def serialize_many(db: Database, stories: list[dict], sources: dict[str, dict]) -> list[dict]:
    with db.connect() as conn:
        tops, teasers = _top_sources_and_teasers(conn, [s["id"] for s in stories], sources)
    return [serialize_story(s, sources, tops.get(s["id"]), teasers.get(s["id"], "")) for s in stories]


PERSPECTIVES = {"all", "balanced", "left", "right", "blindspot"}
SORTS = {"relevance", "latest", "sources", "trust"}


def query_stories(db: Database, *, categories_filter: list[str] | None = None, q: str | None = None,
                  lang: str | None = None, country: str | None = None, source: str | None = None,
                  perspective: str = "all", min_trust: int = 0, min_sources: int = 1, hours: int | None = 48,
                  sort: str = "relevance", limit: int = 30, offset: int = 0) -> tuple[list[dict], int]:
    now = utcnow()
    where = ["source_count >= ?"]
    params: list = [max(1, min_sources)]
    if hours:
        where.append("last_updated >= ?")
        params.append(iso(now - timedelta(hours=hours)))
    if categories_filter:
        where.append(f"category IN ({','.join('?' * len(categories_filter))})")
        params.extend(categories_filter)
    if min_trust:
        where.append("trust_score >= ?")
        params.append(min_trust)
    if lang in ("de", "en"):
        where.append("languages LIKE ?")
        params.append(f'%"{lang}"%')
    if country:
        where.append("countries LIKE ?")
        params.append(f'%"{country.upper()}"%')
    if source:
        where.append("id IN (SELECT story_id FROM articles WHERE source_id = ?)")
        params.append(source)
    if q:
        for term in q.split()[:6]:
            like = f"%{term}%"
            where.append("(headline LIKE ? OR summary_json LIKE ? OR id IN "
                         "(SELECT story_id FROM articles WHERE title LIKE ?))")
            params.extend([like, like, like])

    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            f"SELECT * FROM stories WHERE {' AND '.join(where)}", params).fetchall()]

    if perspective == "balanced":
        rows = [r for r in rows if r["bias_left"] and r["bias_center"] and r["bias_right"]]
    elif perspective in ("left", "right"):
        key, other = ("bias_left", "bias_right") if perspective == "left" else ("bias_right", "bias_left")
        rows = [r for r in rows if r[key] > 0 and r[key] >= 0.6 * (r["bias_left"] + r["bias_center"] + r["bias_right"])
                or (r[key] >= 2 and r[other] == 0)]
    elif perspective == "blindspot":
        rows = [r for r in rows if blindspot(r)]

    if sort == "latest":
        rows.sort(key=lambda r: r["last_updated"] or "", reverse=True)
    elif sort == "sources":
        rows.sort(key=lambda r: (r["source_count"], r["last_updated"] or ""), reverse=True)
    elif sort == "trust":
        rows.sort(key=lambda r: (r["trust_score"] or 0, r["source_count"]), reverse=True)
    else:
        rows.sort(key=lambda r: importance(r, now), reverse=True)

    return rows[offset:offset + limit], len(rows)


def get_story(db: Database, story_id: int) -> dict | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
    return dict(row) if row else None


def story_articles(db: Database, story_id: int, sources: dict[str, dict]) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT id, source_id, url, title, description, image_url, language, is_opinion, published_at
               FROM articles WHERE story_id = ? ORDER BY published_at DESC""",
            (story_id,),
        ).fetchall()
    out = []
    for r in rows:
        src = sources.get(r["source_id"])
        if not src:
            continue
        out.append({
            "id": r["id"],
            "url": r["url"],
            "title": r["title"],
            "description": r["description"],
            "image_url": r["image_url"],
            "language": r["language"],
            "is_opinion": bool(r["is_opinion"]),
            "published_at": r["published_at"],
            "source": public_source(src),
        })
    return out


def public_source(src: dict) -> dict:
    return {
        "id": src["id"],
        "name": src["name"],
        "homepage": src.get("homepage"),
        "country": src.get("country"),
        "language": src.get("language"),
        "bias": src.get("bias"),
        "bias_bucket": BIAS_BUCKET.get(src.get("bias"), "center"),
        "reliability": src.get("reliability"),
        "factuality": factuality(src.get("reliability")),
        "ownership": src.get("ownership"),
        "type": src.get("type"),
        "note": src.get("note") or "",
    }


# ---------------------------------------------------------------------------
# Vorlesetexte
# ---------------------------------------------------------------------------

def _sentence(text: str) -> str:
    text = (text or "").strip()
    if text and text[-1] not in ".!?…:":
        text += "."
    return text


def story_speech(story: dict, lang: str) -> tuple[str, str]:
    """Vorlesetext einer Meldung. Gibt (Text, tatsächliche Sprache) zurück – fehlt eine Fassung,
    wird die Originalsprache vorgelesen."""
    summary = loads(story.get("summary_json"), {}) or {}
    part = summary.get(lang) or {}
    if not part.get("available", True) or not part.get("title"):
        other = "en" if lang == "de" else "de"
        part = summary.get(other) or {}
        lang = other if part.get("title") else (story.get("headline_lang") or lang)
    title = part.get("title") or story.get("headline") or ""
    pieces = [_sentence(title)]
    if part.get("summary"):
        pieces.append(_sentence(part["summary"]))
    points = part.get("key_points") or []
    if points:
        pieces.append("So berichten weitere Medien:" if lang == "de" else "How other outlets report it:")
        pieces.extend(_sentence(p) for p in points)
    if part.get("context"):
        pieces.append(("Warum das wichtig ist: " if lang == "de" else "Why it matters: ") + _sentence(part["context"]))
    return " ".join(p for p in pieces if p), lang
