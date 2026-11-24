"""Verarbeitungs-Pipeline: Abruf → Gruppierung → Kennzahlen → Zusammenfassungen → Briefings."""

from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

import httpx

from . import cluster, digests, ingest, stories, summarize
from .config import Settings
from .db import Database, iso, utcnow
from .sources import source_map, sync_sources
from .translate import Translator

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, settings: Settings, db: Database, translator: Translator,
                 transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.db = db
        self.translator = translator
        self.transport = transport
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.sources: dict[str, dict] = {}
        self.reload_sources()

    def reload_sources(self) -> None:
        sync_sources(self.db, self.settings.sources_file)
        self.sources = source_map(self.db)

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def run_cycle(self, fetch: bool = True) -> dict:
        """Ein kompletter Verarbeitungsdurchlauf. Läuft nie parallel zu sich selbst."""
        if not self._lock.acquire(blocking=False):
            return {"skipped": True}
        started = time.monotonic()
        result: dict = {"started_at": iso(utcnow())}
        try:
            self.db.set_meta("cycle_running", True)
            if fetch:
                result["fetch"] = ingest.fetch_all(
                    self.db, self.sources, max_age_hours=self.settings.max_article_age_hours,
                    timeout=self.settings.feed_timeout_seconds, transport=self.transport,
                )
            touched = cluster.assign_articles(self.db, window_hours=self.settings.max_article_age_hours)
            stories.recompute_stories(self.db, self.sources, touched)
            if touched:  # neue Meldungen sofort sichtbar machen, Zusammenfassungen folgen
                self.db.set_meta("last_update", iso(utcnow()))
            result["summaries"] = summarize.summarize_pending(self.db, self.sources, self.translator, self.settings)
            stories.recompute_stories(self.db, self.sources)
            merged = cluster.merge_similar_stories(self.db)
            if merged:
                stories.recompute_stories(self.db, self.sources, merged)
                for story_id in merged:  # zusammengeführte Meldungen gleich neu zusammenfassen
                    summarize.summarize_story(self.db, story_id, self.sources, self.translator)
            result["merged"] = len(merged)
            result["digests"] = digests.refresh_digests(self.db)
            self.prune()
            result["duration_s"] = round(time.monotonic() - started, 1)
            self.db.set_meta("last_cycle", result)
            self.db.set_meta("last_update", iso(utcnow()))
            self.db.set_meta("last_error", None)
            log.info("Durchlauf abgeschlossen: %s", result)
        except Exception as exc:  # Hintergrundprozess darf nicht abbrechen
            log.exception("Durchlauf fehlgeschlagen")
            self.db.set_meta("last_error", f"{type(exc).__name__}: {exc}")
            result["error"] = str(exc)
        finally:
            self.db.set_meta("cycle_running", False)
            self._lock.release()
        return result

    def prune(self) -> None:
        cutoff = iso(utcnow() - timedelta(days=self.settings.retention_days))
        with self.db.write() as conn:
            conn.execute("DELETE FROM articles WHERE published_at < ?", (cutoff,))
            conn.execute("DELETE FROM stories WHERE last_updated < ?", (cutoff,))
            conn.execute("DELETE FROM translations WHERE created < ?", (cutoff,))

    # --- Hintergrund-Thread -------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="news-pipeline", daemon=True)
        self._thread.start()

    def trigger(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _loop(self) -> None:
        interval = max(1, self.settings.refresh_interval_minutes) * 60
        while not self._stop.is_set():
            self.run_cycle()
            self._wake.wait(timeout=interval)
            self._wake.clear()
