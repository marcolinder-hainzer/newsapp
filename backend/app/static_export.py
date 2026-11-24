"""Statischer Export für GitHub Pages.

Führt einen Verarbeitungsdurchlauf aus (Abruf, Gruppierung, Zusammenfassungen, Briefings) und schreibt
alle Daten, die das Frontend braucht, als JSON-Dateien in ein Verzeichnis:

    data/meta.json                Konfiguration & Statistik
    data/stories-recent.json      Meldungen der letzten 48 Stunden (für Liste, Filter, Suche)
    data/stories-older.json       Meldungen von vor 2 bis 7 Tagen
    data/stories/<id>.json        Detailansicht jeder Meldung
    data/digests/<bereich>.json   Briefings (top-day, top-week, category-politik, …)
    data/briefing.json            Alle Briefings zusammen
    data/sources.json             Quellen

Aufruf:  python -m app.static_export --out ../site/data [--skip-cycle] [--compact-db]
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

from . import digests, stories, views
from .config import Settings
from .db import Database, iso, utcnow
from .pipeline import Pipeline
from .translate import Translator

log = logging.getLogger(__name__)

RECENT_HOURS = 48
MAX_DAYS = 7


def scope_filename(scope: str) -> str:
    return scope.replace(":", "-")


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _story_extras(db: Database, story_ids: list[int]) -> dict[int, dict]:
    """Quellen-IDs und Suchtext je Meldung (für Filter und Suche im Browser)."""
    extras: dict[int, dict] = {sid: {"source_ids": [], "search": []} for sid in story_ids}
    if not story_ids:
        return extras
    with db.connect() as conn:
        for start in range(0, len(story_ids), 500):
            chunk = story_ids[start:start + 500]
            placeholders = ",".join("?" * len(chunk))
            for r in conn.execute(
                f"SELECT story_id, source_id, title FROM articles WHERE story_id IN ({placeholders})", chunk
            ):
                entry = extras[r["story_id"]]
                if r["source_id"] not in entry["source_ids"]:
                    entry["source_ids"].append(r["source_id"])
                entry["search"].append(r["title"])
    for entry in extras.values():
        entry["search"] = " ".join(entry["search"]).lower()[:800]
    return extras


def export(db: Database, sources: dict[str, dict], translation_info: dict, settings: Settings, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    now = utcnow()

    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM stories WHERE last_updated >= ? ORDER BY last_updated DESC",
            (iso(now - timedelta(days=MAX_DAYS)),),
        ).fetchall()]

    items = stories.serialize_many(db, rows, sources)
    extras = _story_extras(db, [r["id"] for r in rows])
    recent_cutoff = iso(now - timedelta(hours=RECENT_HOURS))
    recent, older = [], []
    for row, item in zip(rows, items):
        item["coverage"] = round(row.get("coverage") or 0, 4)
        item.update(extras.get(row["id"], {}))
        (recent if (row["last_updated"] or "") >= recent_cutoff else older).append(item)
        _write(out / "stories" / f"{row['id']}.json",
               views.story_detail_payload(db, row, sources))

    generated_at = iso(now)
    _write(out / "stories-recent.json", {"generated_at": generated_at, "items": recent})
    _write(out / "stories-older.json", {"generated_at": generated_at, "items": older})

    all_digests = {}
    for scope in digests.all_scopes():
        digest = views.digest_payload(db, scope, sources)
        all_digests[scope] = digest
        _write(out / "digests" / f"{scope_filename(scope)}.json", digest)
    _write(out / "briefing.json", {
        "day": all_digests["top:day"],
        "week": all_digests["top:week"],
        "categories": [d for s, d in all_digests.items() if s.startswith("category:")],
    })

    _write(out / "sources.json", views.sources_payload(db, sources))
    meta = views.meta_payload(db, sources, translation_info, settings.refresh_interval_minutes, static=True)
    meta["generated_at"] = generated_at
    _write(out / "meta.json", meta)
    return {"stories": len(rows), "recent": len(recent), "older": len(older)}


def compact_database(db: Database, settings: Settings) -> None:
    """Verkleinert die Datenbank für die Zwischenspeicherung zwischen zwei Durchläufen
    (alte Einträge löschen, gespeicherte Volltexte älterer Versionen entfernen)."""
    cutoff = iso(utcnow() - timedelta(days=settings.retention_days))
    with db.write() as conn:
        conn.execute("DELETE FROM articles WHERE published_at < ?", (cutoff,))
        conn.execute("DELETE FROM stories WHERE last_updated < ?", (cutoff,))
        conn.execute("UPDATE articles SET content = NULL, content_fetched = 0 WHERE content IS NOT NULL")
        conn.execute("DELETE FROM translations WHERE created < ?", (cutoff,))
    with db.connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw = sqlite3.connect(db.path)
    raw.execute("VACUUM")
    raw.close()


def run_report(db: Database, result: dict, translator: Translator, stats: dict) -> str:
    """Kurzer Bericht für das Protokoll der GitHub Action (Statistik + Beispiel-Übersetzungen)."""
    since = iso(utcnow() - timedelta(hours=RECENT_HOURS))
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT summary_json, source_count, coverage, trust_score, first_seen, last_updated FROM stories "
            "WHERE last_updated >= ?", (since,)).fetchall()]
    both = pending = 0
    samples: dict[str, list[tuple[float, str, str]]] = {"de": [], "en": []}
    now = utcnow()
    for r in rows:
        summary = json.loads(r["summary_json"] or "{}")
        de, en = summary.get("de") or {}, summary.get("en") or {}
        if de.get("available") and en.get("available"):
            both += 1
        if summary.get("translation_pending"):
            pending += 1
        for target, part, other in (("en", en, de), ("de", de, en)):
            if part.get("machine_translated"):
                samples[target].append((stories.importance(r, now), other.get("title", ""), part.get("title", "")))
    lines = [
        "=== Weitblick – Bericht ===",
        f"Feeds: {result.get('fetch')}",
        f"Zusammenfassungen/Übersetzung: {result.get('summaries')}",
        f"Zusammengeführte Meldungen: {result.get('merged')}",
        f"Export: {stats}",
        f"Meldungen (48 Std.): {len(rows)}, davon zweisprachig: {both}, Übersetzung ausstehend: {pending}",
        f"Übersetzung: {'aktiv' if translator.available else 'nicht verfügbar'}"
        + (f" – Modelle: {', '.join(translator.loaded_models())}" if hasattr(translator, "loaded_models") else ""),
    ]
    for target, label in (("en", "DE → EN"), ("de", "EN → DE")):
        top = sorted(samples[target], reverse=True)[:5]
        if top:
            lines.append(f"Beispiele {label}:")
            lines.extend(f"  • {src}  →  {dst}" for _, src, dst in top)
    if result.get("error"):
        lines.append(f"FEHLER im Durchlauf: {result['error']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Statischen Export für GitHub Pages erzeugen")
    parser.add_argument("--out", required=True, help="Zielverzeichnis für die JSON-Dateien")
    parser.add_argument("--skip-cycle", action="store_true", help="Keinen Abruf durchführen, nur exportieren")
    parser.add_argument("--compact-db", action="store_true", help="Datenbank danach verkleinern")
    parser.add_argument("--report", help="Kurzbericht in diese Datei schreiben")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = Settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    translator = Translator(db, enabled=settings.translation_enabled)
    log.info("Übersetzung: %s", "aktiv (OPUS-MT)" if translator.available else "nicht verfügbar")
    pipeline = Pipeline(settings, db, translator)
    result: dict = {}
    if not args.skip_cycle:
        result = pipeline.run_cycle()
        log.info("Durchlauf: %s", result)
    stats = export(db, pipeline.sources, translator.info(), settings, Path(args.out))
    log.info("Export abgeschlossen: %s", stats)
    if args.report:
        Path(args.report).write_text(run_report(db, result, translator, stats) + "\n", encoding="utf-8")
    if args.compact_db:
        compact_database(db, settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
