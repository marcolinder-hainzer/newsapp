"""Zweisprachige Zusammenfassungen (Deutsch/Englisch) – vollständig kostenlos.

Für jede Meldung entsteht automatisch:
* eine Überschrift (vom zuverlässigsten berichtenden Medium),
* eine Kurzfassung aus den aussagekräftigsten Sätzen der Teaser aller Quellen
  (Satzauswahl per TF-IDF-Zentroid, doppelte Aussagen werden aussortiert),
* die Schlagzeilen weiterer Medien („So berichten weitere Medien“).

Fehlt eine Sprachfassung, wird sie mit den freien OPUS-MT-Modellen maschinell übersetzt
(siehe translate.py). Was im Zeitbudget eines Durchlaufs nicht mehr übersetzt wird,
folgt im nächsten Durchlauf – die wichtigsten Meldungen zuerst.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .config import Settings
from .db import Database, dumps, iso, loads, utcnow
from .stories import importance
from .textutil import split_sentences, tokenize
from .translate import Translator

log = logging.getLogger(__name__)

MAX_SENTENCES = 3
MAX_POINTS = 4
SUMMARY_VERSION = 2  # erhöhen, wenn sich das Format ändert – dann werden alle Fassungen neu erstellt


def load_story_articles(db: Database, story_id: int) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT id, source_id, url, title, description, language, is_opinion, published_at
               FROM articles WHERE story_id = ? ORDER BY published_at""",
            (story_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _centroid_sentences(texts: list[str], lang: str, max_sentences: int = MAX_SENTENCES) -> list[str]:
    """Wählt die Sätze, die den gemeinsamen Kern aller Texte am besten treffen."""
    sentences: list[str] = []
    seen = set()
    for text in texts:
        for s in split_sentences(text):
            key = s.lower()[:80]
            if 30 <= len(s) <= 400 and key not in seen:
                seen.add(key)
                sentences.append(s)
    if len(sentences) <= 1:
        return sentences
    try:
        matrix = TfidfVectorizer(analyzer=lambda x: tokenize(x, lang)).fit_transform(sentences)
    except ValueError:
        return sentences[:max_sentences]
    centroid = np.asarray(matrix.mean(axis=0))
    scores = (matrix @ centroid.T).ravel()
    picked: list[int] = []
    for idx in np.argsort(-scores):
        if len(picked) >= max_sentences:
            break
        if any((matrix[idx] @ matrix[p].T).toarray()[0, 0] > 0.45 for p in picked):
            continue  # Redundanz vermeiden
        picked.append(int(idx))
    return [sentences[i] for i in sorted(picked)]


def _native_part(articles: list[dict], sources: dict[str, dict], lang: str) -> dict:
    ranked = sorted(articles, key=lambda a: (a["is_opinion"], -int(sources.get(a["source_id"], {}).get("reliability") or 0),
                                             a["published_at"]))
    lead = ranked[0]
    sentences = _centroid_sentences([a.get("description") or "" for a in ranked], lang)
    points: list[tuple[str, str]] = []
    used_sources = {lead["source_id"]}
    titles = {lead["title"].lower()}
    for a in ranked[1:]:
        if len(points) >= MAX_POINTS:
            break
        if a["source_id"] in used_sources or a["title"].lower() in titles:
            continue
        used_sources.add(a["source_id"])
        titles.add(a["title"].lower())
        points.append((a["title"], sources[a["source_id"]]["name"]))
    return {"title": lead["title"], "sentences": sentences, "points": points}


def _render(part: dict, machine_translated: bool, source_lang: str | None = None) -> dict:
    rendered = {
        "available": True,
        "title": part["title"],
        "summary": " ".join(part["sentences"]),
        "key_points": [f"{name}: {title}" for title, name in part["points"]],
        "context": "",
        "machine_translated": machine_translated,
    }
    if source_lang:
        rendered["source_lang"] = source_lang
    return rendered


def _translated_part(part: dict, src: str, tgt: str, translator: Translator) -> dict | None:
    segments = [part["title"], *part["sentences"], *[title for title, _ in part["points"]]]
    out = translator.translate(segments, src, tgt)
    if any(t is None for t in out):
        return None
    n = len(part["sentences"])
    return {
        "title": out[0],
        "sentences": out[1:1 + n],
        "points": [(t, name) for t, (_, name) in zip(out[1 + n:], part["points"])],
    }


def build_summary(articles: list[dict], sources: dict[str, dict], translator: Translator | None) -> dict:
    articles = [a for a in articles if a["source_id"] in sources]
    result: dict = {"generated_by": "extractive", "generated_at": iso(utcnow()), "translation_pending": False,
                    "version": SUMMARY_VERSION}
    native = {}
    for lang in ("de", "en"):
        in_lang = [a for a in articles if a.get("language") == lang]
        if in_lang:
            native[lang] = _native_part(in_lang, sources, lang)
            result[lang] = _render(native[lang], machine_translated=False)
    for lang in ("de", "en"):
        if lang in native:
            continue
        src = "en" if lang == "de" else "de"
        if src not in native:
            result[lang] = {"available": False}
            continue
        translated = _translated_part(native[src], src, lang, translator) if translator else None
        if translated:
            result[lang] = _render(translated, machine_translated=True, source_lang=src)
        else:
            result[lang] = {"available": False}
            result["translation_pending"] = True
    return result


def summarize_story(db: Database, story_id: int, sources: dict[str, dict], translator: Translator | None) -> str:
    articles = load_story_articles(db, story_id)
    if not articles:
        return "missing"
    summary = build_summary(articles, sources, translator)
    with db.write() as conn:
        conn.execute(
            """UPDATE stories SET summary_json = ?, summary_status = 'extractive', summary_article_count = ?,
                   summary_updated = ? WHERE id = ?""",
            (dumps(summary), len(articles), iso(utcnow()), story_id),
        )
    return "pending" if summary["translation_pending"] else "done"


def _needs_summary(story: dict, translation_on: bool) -> bool:
    if (story["summary_status"] or "none") == "none":
        return True
    if story["article_count"] != (story["summary_article_count"] or 0):
        return True
    summary = loads(story.get("summary_json"), {}) or {}
    if summary.get("version") != SUMMARY_VERSION:
        return True
    return translation_on and bool(summary.get("translation_pending"))


def summarize_pending(db: Database, sources: dict[str, dict], translator: Translator, settings: Settings) -> dict:
    now = utcnow()
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT id, summary_status, summary_json, article_count, summary_article_count, coverage,
                      trust_score, first_seen, last_updated FROM stories WHERE last_updated >= ?""",
            (iso(now - timedelta(hours=settings.max_article_age_hours)),),
        ).fetchall()]
    pending = [r for r in rows if _needs_summary(r, translator.available)]
    pending.sort(key=lambda r: importance(r, now), reverse=True)  # wichtigste zuerst übersetzen

    translator.start_budget(settings.translation_time_budget_seconds)
    stats = {"done": 0, "pending": 0}
    for story in pending:
        status = summarize_story(db, story["id"], sources, translator)
        if status in stats:
            stats[status] += 1
    stats.update({f"translation_{k}": round(v, 1) if isinstance(v, float) else v
                  for k, v in translator.stats.items()})
    if pending:
        log.info("Zusammenfassungen: %s", stats)
    return stats
