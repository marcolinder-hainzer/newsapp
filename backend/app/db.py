"""SQLite-Datenbank: Schema und Hilfsfunktionen."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    homepage TEXT,
    country TEXT,
    language TEXT,
    bias TEXT,
    reliability INTEGER,
    ownership TEXT,
    type TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS feeds (
    url TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    category TEXT,
    etag TEXT,
    last_modified TEXT,
    last_fetch TEXT,
    last_status TEXT,
    last_error TEXT,
    new_items INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    content TEXT,
    image_url TEXT,
    language TEXT,
    category TEXT,
    category_conf INTEGER DEFAULT 0,
    is_opinion INTEGER DEFAULT 0,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    story_id INTEGER,
    content_fetched INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_articles_story ON articles(story_id);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source_title ON articles(source_id, title);

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    headline TEXT,
    headline_lang TEXT,
    image_url TEXT,
    first_seen TEXT,
    last_updated TEXT,
    article_count INTEGER DEFAULT 0,
    source_count INTEGER DEFAULT 0,
    languages TEXT DEFAULT '[]',
    countries TEXT DEFAULT '[]',
    bias_left INTEGER DEFAULT 0,
    bias_center INTEGER DEFAULT 0,
    bias_right INTEGER DEFAULT 0,
    trust_score INTEGER,
    trust_json TEXT,
    coverage REAL DEFAULT 0,
    summary_json TEXT,
    summary_status TEXT DEFAULT 'none',
    summary_article_count INTEGER DEFAULT 0,
    summary_updated TEXT,
    dirty INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_stories_updated ON stories(last_updated);
CREATE INDEX IF NOT EXISTS idx_stories_category ON stories(category);

CREATE TABLE IF NOT EXISTS digests (
    scope TEXT PRIMARY KEY,
    content_json TEXT,
    story_ids TEXT,
    generated_by TEXT,
    generated_at TEXT
);

CREATE TABLE IF NOT EXISTS translations (
    key TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    created TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None


class Database:
    """Dünne Hülle um sqlite3 – eine Verbindung pro Aufruf, WAL-Modus für parallele Leser."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        self._write_lock = threading.RLock()
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock, self.connect() as conn:
            yield conn

    # --- Meta-Werte -------------------------------------------------------
    def get_meta(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return row["value"]

    def set_meta(self, key: str, value: Any) -> None:
        with self.write() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
