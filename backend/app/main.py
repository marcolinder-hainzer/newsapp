"""FastAPI-Anwendung: REST-API und Auslieferung des Web-Frontends."""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import categories, digests, stories, summarize
from .config import Settings, settings as default_settings
from .db import Database, iso, loads, utcnow
from .llm import LLMClient
from .pipeline import Pipeline
from .tts import TTSError, TTSService

log = logging.getLogger(__name__)

APP_NAME = "Weitblick"
APP_VERSION = "1.0.0"


class RateLimiter:
    """Einfaches gleitendes Fenster – schützt kostenpflichtige Aktionen vor Missbrauch."""

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


def create_app(settings: Settings | None = None, llm: LLMClient | None = None,
               transport: httpx.BaseTransport | None = None, tts_transport: httpx.BaseTransport | None = None,
               start_scheduler: bool | None = None) -> FastAPI:
    settings = settings or default_settings
    settings.ensure_dirs()
    db = Database(settings.db_path)
    llm = llm or LLMClient(settings)
    tts = TTSService(settings, transport=tts_transport)
    pipeline = Pipeline(settings, db, llm, tts, transport=transport)
    run_scheduler = settings.scheduler_enabled if start_scheduler is None else start_scheduler

    summary_limiter = RateLimiter(max_events=40, per_seconds=3600)
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
    app.state.llm = llm
    app.state.tts = tts

    # ------------------------------------------------------------------
    # Allgemein
    # ------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta():
        since = iso(utcnow() - timedelta(hours=24))
        with db.connect() as conn:
            story_count = conn.execute("SELECT COUNT(*) FROM stories WHERE last_updated >= ?", (since,)).fetchone()[0]
            article_count = conn.execute("SELECT COUNT(*) FROM articles WHERE published_at >= ?", (since,)).fetchone()[0]
        countries = sorted({s.get("country") for s in pipeline.sources.values() if s.get("country")})
        return {
            "app": {"name": APP_NAME, "version": APP_VERSION},
            "categories": categories.CATEGORIES,
            "countries": countries,
            "llm": {"enabled": llm.enabled, "model": llm.model if llm.enabled else None},
            "tts": tts.info(),
            "last_update": db.get_meta("last_update"),
            "cycle_running": pipeline.running,
            "refresh_interval_minutes": settings.refresh_interval_minutes,
            "stats": {"stories_24h": story_count, "articles_24h": article_count,
                      "sources": len(pipeline.sources)},
        }

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
            "llm_usage": llm.usage,
            "feeds": feeds,
        }

    # ------------------------------------------------------------------
    # Meldungen
    # ------------------------------------------------------------------
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

    def _story_detail(story_id: int) -> dict:
        story = stories.get_story(db, story_id)
        if not story:
            raise HTTPException(404, "Meldung nicht gefunden")
        item = stories.serialize_many(db, [story], pipeline.sources)[0]
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
            "articles": stories.story_articles(db, story_id, pipeline.sources),
            "speech": {lang: dict(zip(("text", "lang"), stories.story_speech(story, lang))) for lang in ("de", "en")},
            "can_generate_summary": llm.enabled and summarize.is_stale(story),
        })
        return item

    @app.get("/api/stories/{story_id}")
    def story_detail(story_id: int):
        return _story_detail(story_id)

    @app.post("/api/stories/{story_id}/summarize")
    def story_summarize(story_id: int):
        story = stories.get_story(db, story_id)
        if not story:
            raise HTTPException(404, "Meldung nicht gefunden")
        if not llm.enabled:
            raise HTTPException(409, "KI-Zusammenfassungen sind nicht konfiguriert (ANTHROPIC_API_KEY fehlt)")
        if summarize.is_stale(story):
            if not summary_limiter.allow():
                raise HTTPException(429, "Zu viele Anfragen – bitte später erneut versuchen")
            summarize.summarize_story(db, story_id, pipeline.sources, llm, settings, use_llm=True)
            stories.recompute_stories(db, pipeline.sources, {story_id})
        return _story_detail(story_id)

    # ------------------------------------------------------------------
    # Briefings
    # ------------------------------------------------------------------
    def _digest_or_404(scope: str) -> dict:
        if scope not in digests.all_scopes():
            raise HTTPException(404, "Unbekannter Bereich")
        digest = digests.get_digest(db, scope, pipeline.sources)
        if digest is None:
            digests.generate_digest(db, scope, llm, use_llm=False)
            digest = digests.get_digest(db, scope, pipeline.sources)
        digest["speech"] = {lang: digests.digest_speech(digest, lang) for lang in ("de", "en")}
        return digest

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

    # ------------------------------------------------------------------
    # Quellen
    # ------------------------------------------------------------------
    @app.get("/api/sources")
    def list_sources():
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
        for src in sorted(pipeline.sources.values(), key=lambda s: (s.get("language") != "de", s["name"].lower())):
            item = stories.public_source(src)
            item["articles_24h"] = counts.get(src["id"], 0)
            item.update(feed_status.get(src["id"], {"feeds": 0, "errors": 0}))
            out.append(item)
        return {"items": out}

    # ------------------------------------------------------------------
    # Sprachausgabe
    # ------------------------------------------------------------------
    def _audio(text: str, lang: str, voice: str):
        if not tts.available:
            raise HTTPException(404, "Keine Server-Sprachausgabe konfiguriert")
        if not text.strip():
            raise HTTPException(404, "Kein Text zum Vorlesen")
        try:
            path = tts.synthesize(text, lang, voice)
        except TTSError as exc:
            raise HTTPException(502, str(exc)) from exc
        return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/api/tts/story/{story_id}")
    def tts_story(story_id: int, lang: str = "de", voice: str = "female"):
        story = stories.get_story(db, story_id)
        if not story:
            raise HTTPException(404, "Meldung nicht gefunden")
        text, actual_lang = stories.story_speech(story, lang if lang in ("de", "en") else "de")
        return _audio(text, actual_lang, voice)

    preview_texts = {
        "de": "Guten Tag. Das ist eine Hörprobe für die Nachrichten von Weitblick.",
        "en": "Hello. This is a voice preview for the Weitblick news.",
    }

    @app.get("/api/tts/preview")
    def tts_preview(lang: str = "de", voice: str = "female"):
        lang = lang if lang in preview_texts else "de"
        return _audio(preview_texts[lang], lang, voice)

    @app.get("/api/tts/digest")
    def tts_digest(scope: str = "top:day", lang: str = "de", voice: str = "female"):
        digest = _digest_or_404(scope)
        return _audio(digest["speech"][lang if lang in ("de", "en") else "de"], lang, voice)

    # ------------------------------------------------------------------
    # Verwaltung
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Frontend (gebaute React-App)
    # ------------------------------------------------------------------
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

