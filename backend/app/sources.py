"""Quellenverwaltung: Laden der kuratierten Quellenliste in die Datenbank."""

from __future__ import annotations

import json
from pathlib import Path

from .db import Database

BIAS_BUCKET = {
    "left": "left",
    "lean_left": "left",
    "center": "center",
    "lean_right": "right",
    "right": "right",
}

FACTUALITY_LABELS = [
    (85, "very_high"),
    (75, "high"),
    (60, "mostly"),
    (45, "mixed"),
    (0, "low"),
]


def factuality(reliability: int | None) -> str:
    value = reliability if reliability is not None else 60
    for threshold, label in FACTUALITY_LABELS:
        if value >= threshold:
            return label
    return "low"


def load_sources_file(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    sources = data["sources"] if isinstance(data, dict) else data
    for s in sources:
        if s.get("bias") not in BIAS_BUCKET:
            raise ValueError(f"Quelle {s.get('id')}: unbekannte Ausrichtung {s.get('bias')!r}")
    return sources


def sync_sources(db: Database, path: Path) -> list[dict]:
    """Schreibt Quellen und Feeds in die Datenbank (Feeds, die nicht mehr gelistet sind, werden entfernt)."""
    sources = load_sources_file(path)
    feed_urls = []
    with db.write() as conn:
        for s in sources:
            conn.execute(
                """INSERT INTO sources(id, name, homepage, country, language, bias, reliability, ownership, type, note)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, homepage=excluded.homepage,
                     country=excluded.country, language=excluded.language, bias=excluded.bias,
                     reliability=excluded.reliability, ownership=excluded.ownership, type=excluded.type,
                     note=excluded.note""",
                (s["id"], s["name"], s.get("homepage"), s.get("country"), s.get("language", "de"),
                 s["bias"], int(s.get("reliability", 60)), s.get("ownership"), s.get("type", "news"),
                 s.get("note", "")),
            )
            for f in s.get("feeds", []):
                feed_urls.append(f["url"])
                conn.execute(
                    """INSERT INTO feeds(url, source_id, category) VALUES(?,?,?)
                       ON CONFLICT(url) DO UPDATE SET source_id=excluded.source_id, category=excluded.category""",
                    (f["url"], s["id"], f.get("category")),
                )
        if feed_urls:
            placeholders = ",".join("?" * len(feed_urls))
            conn.execute(f"DELETE FROM feeds WHERE url NOT IN ({placeholders})", feed_urls)
    return sources


def source_map(db: Database) -> dict[str, dict]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM sources").fetchall()
    return {r["id"]: dict(r) for r in rows}
