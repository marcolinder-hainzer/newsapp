"""FastAPI-Anwendung für den Betrieb auf dem eigenen Rechner (z. B. zur Entwicklung).

Für die Veröffentlichung über GitHub Pages wird stattdessen app.static_export verwendet.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import categories, digests, stories, views
from .config import Settings, settings as default_settings
from .db import Database
from .pipeline import Pipeline
from .translate import Translator
from .views import APP_NAME, APP_VERSION

log = logging.getLogger(__name__)


class RateLimiter:
    """Einfaches gleitendes Fenster – verhindert zu häufiges manuelles Aktualisieren."""

    def __init__(self, max_events: int, per_seconds: int):
        self.max_events = max_events
        self.per_seconds = per_seconds
        self._events: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._events = [t for t in self._events if now - t < self.per_seconds]
            if len(self._events) >= self.max_events:
                return False
            self._events.append(now)
            return True


def create_app(settings: Settings | None = None, translator: Translator | None = None,
               transport: httpx.BaseTransport | None = None, start_scheduler: bool | None = None) -> FastAPI:
    settings = settings or default_settings
    settings.ensure_dirs()
    db = Database(settings.db_path)
    translator = translator or Translator(db, enabled=settings.translation_enabled)
    pipeline = Pipeline(settings, db, translator, transport=transport)
    run_scheduler = settings.scheduler_enabled if start_scheduler is None else start_scheduler
    refresh_limiter = RateLimiter(max_events=1, per_seconds=120)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if run_scheduler:
            pipeline.start()
        yield
        pipeline.stop()

    app = FastAPI(title=f"{APP_NAME} API", version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.state.settings = settings
    app.state.db = db
    app.state.pipeline = pipeline
    app.state.translator = translator

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta():
        return views.meta_payload(db, pipeline.sources, translator.info(), settings.refresh_interval_minutes,
                                  running=pipeline.running)

    @app.get("/api/status")
    def status():
        with db.connect() as conn:
            feeds = [dict(r) for r in conn.execute(
                "SELECT url, source_id, category, last_fetch, last_status, last_error, new_items FROM feeds "
                "ORDER BY source_id").fetchall()]
        return {
            "last_cycle": db.get_meta("last_cycle"),
            "last_error": db.get_meta("last_error"),
            "last_update": db.get_meta("last_update"),
            "cycle_running": pipeline.running,
            "feeds": feeds,
        }

    @app.get("/api/stories")
    def list_stories(
        category: str | None = None,
        q: str | None = Query(None, max_length=120),
        lang: str | None = None,
        country: str | None = None,
        source: str | None = None,
        perspective: str = "all",
        min_trust: int = Query(0, ge=0, le=100),
        min_sources: int = Query(1, ge=1, le=50),
        hours: int = Query(48, ge=0, le=24 * 30),
        sort: str = "relevance",
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        cats = [c for c in (category or "").split(",") if c in categories.SLUGS] or None
        rows, total = stories.query_stories(
            db, categories_filter=cats, q=q, lang=lang, country=country, source=source,
            perspective=perspective if perspective in stories.PERSPECTIVES else "all",
            min_trust=min_trust, min_sources=min_sources, hours=hours or None,
            sort=sort if sort in stories.SORTS else "relevance", limit=limit, offset=offset,
        )
        return {"total": total, "offset": offset, "limit": limit,
                "items": stories.serialize_many(db, rows, pipeline.sources)}

    @app.get("/api/stories/{story_id}")
    def story_detail(story_id: int):
        story = stories.get_story(db, story_id)
        if not story:
            raise HTTPException(404, "Meldung nicht gefunden")
        return views.story_detail_payload(db, story, pipeline.sources)

    def _digest_or_404(scope: str) -> dict:
        if scope not in digests.all_scopes():
            raise HTTPException(404, "Unbekannter Bereich")
        return views.digest_payload(db, scope, pipeline.sources)

    @app.get("/api/digest")
    def digest(scope: str = "top:day"):
        return _digest_or_404(scope)

    @app.get("/api/briefing")
    def briefing():
        return {
            "day": _digest_or_404("top:day"),
            "week": _digest_or_404("top:week"),
            "categories": [_digest_or_404(f"category:{c}") for c in categories.SLUGS],
        }

    @app.get("/api/sources")
    def list_sources():
        return views.sources_payload(db, pipeline.sources)

    @app.post("/api/admin/refresh")
    def refresh(x_admin_token: str | None = Header(None)):
        if settings.admin_token:
            if x_admin_token != settings.admin_token:
                raise HTTPException(401, "Ungültiges Admin-Token")
        elif not refresh_limiter.allow():
            raise HTTPException(429, "Aktualisierung läuft bereits oder wurde gerade erst ausgelöst")
        if run_scheduler:
            pipeline.trigger()
        else:
            threading.Thread(target=pipeline.run_cycle, daemon=True).start()
        return {"status": "triggered"}

    # Gebautes Frontend ausliefern (falls vorhanden)
    dist = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
    if dist.is_dir():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str, request: Request):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app
