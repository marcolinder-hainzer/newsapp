"""Zentrale Konfiguration – alles über Umgebungsvariablen steuerbar."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "ja"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "./data")).resolve())
    sources_file: Path = field(
        default_factory=lambda: Path(
            os.getenv("SOURCES_FILE", str(Path(__file__).parent / "data" / "sources.json"))
        )
    )

    # Abruf & Verarbeitung
    refresh_interval_minutes: int = field(default_factory=lambda: _int("REFRESH_INTERVAL_MINUTES", 15))
    scheduler_enabled: bool = field(default_factory=lambda: _bool("SCHEDULER_ENABLED", True))
    max_article_age_hours: int = field(default_factory=lambda: _int("MAX_ARTICLE_AGE_HOURS", 96))
    retention_days: int = field(default_factory=lambda: _int("RETENTION_DAYS", 30))
    fetch_fulltext: bool = field(default_factory=lambda: _bool("FETCH_FULLTEXT", True))
    feed_timeout_seconds: int = field(default_factory=lambda: _int("FEED_TIMEOUT_SECONDS", 20))

    # KI-Zusammenfassungen (Claude)
    llm_enabled_flag: bool = field(default_factory=lambda: _bool("LLM_ENABLED", True))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-opus-5-5"))
    llm_effort: str = field(default_factory=lambda: os.getenv("LLM_EFFORT", "medium"))
    summaries_per_cycle: int = field(default_factory=lambda: _int("SUMMARIES_PER_CYCLE", 20))
    llm_concurrency: int = field(default_factory=lambda: _int("LLM_CONCURRENCY", 4))
    digest_interval_minutes: int = field(default_factory=lambda: _int("DIGEST_INTERVAL_MINUTES", 60))
    weekly_digest_interval_minutes: int = field(
        default_factory=lambda: _int("WEEKLY_DIGEST_INTERVAL_MINUTES", 360)
    )

    # Sprachausgabe
    tts_provider: str = field(default_factory=lambda: os.getenv("TTS_PROVIDER", "auto").lower())
    azure_speech_key: str = field(default_factory=lambda: os.getenv("AZURE_SPEECH_KEY", ""))
    azure_speech_region: str = field(default_factory=lambda: os.getenv("AZURE_SPEECH_REGION", "westeurope"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_tts_model: str = field(default_factory=lambda: os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"))
    elevenlabs_api_key: str = field(default_factory=lambda: os.getenv("ELEVENLABS_API_KEY", ""))

    # Optional: schützt den manuellen Refresh-Endpunkt
    admin_token: str = field(default_factory=lambda: os.getenv("ADMIN_TOKEN", ""))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "news.db"

    @property
    def tts_cache_dir(self) -> Path:
        return self.data_dir / "tts-cache"

    @property
    def llm_enabled(self) -> bool:
        has_credentials = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
        return self.llm_enabled_flag and has_credentials

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tts_cache_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
