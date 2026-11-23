"""Optionaler Volltext-Abruf für bessere Zusammenfassungen (der Text wird nur intern verwendet)."""

from __future__ import annotations

import logging

import httpx

from .ingest import USER_AGENT

log = logging.getLogger(__name__)

try:  # trafilatura ist optional – ohne wird mit den Feed-Texten gearbeitet
    import trafilatura
except ImportError:  # pragma: no cover
    trafilatura = None


def fetch_fulltext(url: str, timeout: int = 15, max_chars: int = 6000) -> str:
    if trafilatura is None:
        return ""
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True,
                             headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        response.raise_for_status()
        text = trafilatura.extract(response.text, include_comments=False, include_tables=False,
                                   favor_precision=True) or ""
    except (httpx.HTTPError, ValueError) as exc:
        log.debug("Volltext für %s nicht verfügbar: %s", url, exc)
        return ""
    except Exception as exc:  # trafilatura kann bei kaputtem HTML vielfältige Fehler werfen
        log.debug("Volltext-Extraktion fehlgeschlagen für %s: %s", url, exc)
        return ""
    return text.strip()[:max_chars]
