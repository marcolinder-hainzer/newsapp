"""Gruppierung von Artikeln verschiedener Quellen zu Meldungen ("Stories").

Ablauf:
1. Neue Artikel werden per TF-IDF/Kosinus-Ähnlichkeit (Titel + Teaser) mit den Artikeln der
   letzten Tage verglichen und der ähnlichsten bestehenden Meldung zugeordnet – oder bilden eine neue.
   Meldungen mit KI-Zusammenfassung bringen zusätzlich einen deutschen und einen englischen
   "Anker"-Text mit, so dass auch sprachübergreifend zugeordnet werden kann.
2. Ein Zusammenführungs-Durchlauf vereint Meldungen, deren englische Zusammenfassungen sehr ähnlich
   sind (z. B. eine deutsch- und eine englischsprachige Meldung zum selben Ereignis).
"""

from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .db import Database, iso, loads, parse_iso, utcnow
from .textutil import tokenize

log = logging.getLogger(__name__)

ASSIGN_THRESHOLD = 0.28
MERGE_THRESHOLD = 0.40
MAX_TIME_GAP_HOURS = 48


def _features(text: str, lang: str | None) -> list[str]:
    return tokenize(text, lang)


def _vectorize(docs: list[list[str]]):
    vectorizer = TfidfVectorizer(analyzer=lambda x: x, sublinear_tf=True, min_df=1)
    return vectorizer.fit_transform(docs)


def _article_doc(row) -> str:
    title = row["title"] or ""
    return f"{title} {title} {(row['description'] or '')[:500]}"


def assign_articles(db: Database, window_hours: int = 96, threshold: float = ASSIGN_THRESHOLD) -> set[int]:
    """Ordnet alle noch nicht zugeordneten Artikel Meldungen zu. Gibt die betroffenen Story-IDs zurück."""
    now = utcnow()
    since = iso(now - timedelta(hours=window_hours))
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT id, title, description, language, story_id, published_at FROM articles
               WHERE published_at >= ? OR story_id IS NULL ORDER BY published_at""",
            (since,),
        ).fetchall()
        anchor_rows = conn.execute(
            """SELECT id, summary_json, last_updated FROM stories
               WHERE summary_status = 'llm' AND last_updated >= ?""",
            (since,),
        ).fetchall()

    unassigned_positions = [i for i, r in enumerate(rows) if r["story_id"] is None]
    if not unassigned_positions:
        return set()

    docs: list[list[str]] = []
    story_of: list[int | None] = []
    times: list[float] = []
    token_sets: list[set[str]] = []
    for r in rows:
        feats = _features(_article_doc(r), r["language"])
        docs.append(feats)
        token_sets.append(set(feats))
        story_of.append(r["story_id"])
        times.append((parse_iso(r["published_at"]) or now).timestamp())

    for a in anchor_rows:
        summary = loads(a["summary_json"], {})
        ts = (parse_iso(a["last_updated"]) or now).timestamp()
        for lang in ("de", "en"):
            part = summary.get(lang) or {}
            if not part.get("title"):
                continue
            text = f"{part['title']} {part['title']} {part.get('summary', '')}"
            feats = _features(text, lang)
            docs.append(feats)
            token_sets.append(set(feats))
            story_of.append(a["id"])
            times.append(ts)

    matrix = _vectorize(docs)
    times_arr = np.array(times)
    max_gap = MAX_TIME_GAP_HOURS * 3600
    touched: set[int] = set()
    assignments: dict[int, int] = {}  # Artikel-ID -> Story-ID
    new_story_members: dict[int, list[int]] = {}  # Platzhalter -> Artikel-IDs

    next_placeholder = -1
    chunk = 256
    for start in range(0, len(unassigned_positions), chunk):
        block = unassigned_positions[start:start + chunk]
        sims = (matrix[block] @ matrix.T).toarray()
        for row_idx, pos in enumerate(block):
            scores = sims[row_idx]
            scores[pos] = 0.0
            candidates = np.where(scores >= threshold)[0]
            best_story, best_score = None, 0.0
            for cand in candidates:
                sid = story_of[cand]
                if sid is None or abs(times_arr[cand] - times_arr[pos]) > max_gap:
                    continue
                if len(token_sets[cand] & token_sets[pos]) < 2:
                    continue
                if scores[cand] > best_score:
                    best_story, best_score = sid, float(scores[cand])
            if best_story is None:
                best_story = next_placeholder
                next_placeholder -= 1
            story_of[pos] = best_story
            article_id = rows[pos]["id"]
            if best_story < 0:
                new_story_members.setdefault(best_story, []).append(article_id)
            else:
                assignments[article_id] = best_story

    with db.write() as conn:
        for placeholder, members in new_story_members.items():
            cur = conn.execute("INSERT INTO stories(first_seen, last_updated, dirty) VALUES(?, ?, 1)",
                               (iso(now), iso(now)))
            sid = cur.lastrowid
            touched.add(sid)
            conn.executemany("UPDATE articles SET story_id = ? WHERE id = ?", [(sid, aid) for aid in members])
        for article_id, sid in assignments.items():
            touched.add(sid)
            conn.execute("UPDATE articles SET story_id = ? WHERE id = ?", (sid, article_id))
        if touched:
            placeholders = ",".join("?" * len(touched))
            conn.execute(f"UPDATE stories SET dirty = 1 WHERE id IN ({placeholders})", list(touched))

    log.info("%d Artikel zugeordnet, %d neue Meldungen", len(unassigned_positions), len(new_story_members))
    return touched


def merge_similar_stories(db: Database, window_hours: int = 72, threshold: float = MERGE_THRESHOLD) -> set[int]:
    """Führt Meldungen zusammen, deren (englische) KI-Zusammenfassungen dasselbe Ereignis beschreiben."""
    since = iso(utcnow() - timedelta(hours=window_hours))
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT id, summary_json, source_count, first_seen FROM stories
               WHERE summary_status = 'llm' AND last_updated >= ?""",
            (since,),
        ).fetchall()
    if len(rows) < 2:
        return set()

    docs, ids, sizes, times = [], [], [], []
    for r in rows:
        en = (loads(r["summary_json"], {}) or {}).get("en") or {}
        text = " ".join([en.get("title", "")] * 2 + [en.get("summary", "")] + list(en.get("key_points", [])))
        feats = _features(text, "en")
        if len(feats) < 5:
            continue
        docs.append(feats)
        ids.append(r["id"])
        sizes.append(r["source_count"] or 0)
        times.append((parse_iso(r["first_seen"]) or utcnow()).timestamp())
    if len(docs) < 2:
        return set()

    matrix = _vectorize(docs)
    sims = (matrix @ matrix.T).toarray()
    np.fill_diagonal(sims, 0.0)

    parent = list(range(len(ids)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    max_gap = MAX_TIME_GAP_HOURS * 3600
    pairs = np.argwhere(sims >= threshold)
    for i, j in pairs:
        if i >= j or abs(times[i] - times[j]) > max_gap:
            continue
        ri, rj = find(i), find(j)
        if ri != rj:
            # Die größere (bzw. ältere) Meldung bleibt bestehen
            keep, drop = (ri, rj) if (sizes[ri], -ids[ri]) >= (sizes[rj], -ids[rj]) else (rj, ri)
            parent[drop] = keep

    merges: dict[int, list[int]] = {}
    for idx in range(len(ids)):
        root = find(idx)
        if root != idx:
            merges.setdefault(ids[root], []).append(ids[idx])
    if not merges:
        return set()

    with db.write() as conn:
        for target, sources in merges.items():
            placeholders = ",".join("?" * len(sources))
            conn.execute(f"UPDATE articles SET story_id = ? WHERE story_id IN ({placeholders})", [target, *sources])
            conn.execute(f"DELETE FROM stories WHERE id IN ({placeholders})", sources)
            conn.execute("UPDATE stories SET dirty = 1 WHERE id = ?", (target,))
    log.info("%d Meldungen zusammengeführt", sum(len(v) for v in merges.values()))
    return set(merges)
