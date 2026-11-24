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
    feed_timeout_seconds: int = field(default_factory=lambda: _int("FEED_TIMEOUT_SECONDS", 20))

    # Kostenlose maschinelle Übersetzung (Open-Source-Modelle OPUS-MT, laufen lokal)
    translation_enabled: bool = field(default_factory=lambda: _bool("TRANSLATION_ENABLED", True))
    # Höchstens so viele Sekunden pro Durchlauf übersetzen – der Rest folgt im nächsten Durchlauf
    translation_time_budget_seconds: int = field(
        default_factory=lambda: _int("TRANSLATION_TIME_BUDGET_SECONDS", 300)
    )

    # Optional: schützt den manuellen Refresh-Endpunkt des eigenen Servers
    admin_token: str = field(default_factory=lambda: os.getenv("ADMIN_TOKEN", ""))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "news.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
