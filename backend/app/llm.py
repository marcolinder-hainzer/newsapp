"""Anbindung an Claude (Anthropic API) für Zusammenfassungen, Einordnung und Briefings."""

from __future__ import annotations

import json
import logging
import threading

import anthropic

from .config import Settings

log = logging.getLogger(__name__)

# Modelle, die serverseitige Fallbacks bei Ablehnungen (refusals) unterstützen
_FALLBACK_PREFIXES = ("claude-opus-5", "claude-sonnet-5-5", "claude-fable-5", "claude-mythos-5")


class LLMClient:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None):
        self.settings = settings
        self._client = client
        self._lock = threading.Lock()
        self._usage_lock = threading.Lock()
        self.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "errors": 0, "refusals": 0}

    @property
    def enabled(self) -> bool:
        return self._client is not None or self.settings.llm_enabled

    @property
    def model(self) -> str:
        return self.settings.llm_model

    def _get_client(self) -> anthropic.Anthropic:
        with self._lock:
            if self._client is None:
                self._client = anthropic.Anthropic(max_retries=3, timeout=300)
            return self._client

    def _count(self, key: str, amount: int = 1) -> None:
        with self._usage_lock:
            self.usage[key] += amount

    def generate_json(self, system: str, prompt: str, schema: dict, max_tokens: int = 16000) -> dict | None:
        """Ein Aufruf mit strukturierter Ausgabe (JSON-Schema). Gibt None zurück, wenn kein Ergebnis vorliegt."""
        if not self.enabled:
            return None
        params: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            # Stabiler System-Prompt zuerst, damit er gecacht werden kann
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        if self.settings.llm_effort:
            params["output_config"]["effort"] = self.settings.llm_effort

        client = self._get_client()
        try:
            if self.model.startswith(_FALLBACK_PREFIXES):
                response = client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
                )
            else:
                response = client.messages.create(**params)
        except anthropic.AuthenticationError:
            log.error("Anthropic-API: Authentifizierung fehlgeschlagen – ANTHROPIC_API_KEY prüfen")
            self._count("errors")
            return None
        except anthropic.BadRequestError as exc:
            log.error("Anthropic-API: ungültige Anfrage: %s", exc.message)
            self._count("errors")
            return None
        except anthropic.RateLimitError:
            log.warning("Anthropic-API: Rate-Limit erreicht – wird im nächsten Durchlauf erneut versucht")
            self._count("errors")
            return None
        except anthropic.APIStatusError as exc:
            log.warning("Anthropic-API-Fehler %s: %s", exc.status_code, exc.message)
            self._count("errors")
            return None
        except anthropic.APIConnectionError as exc:
            log.warning("Anthropic-API nicht erreichbar: %s", exc)
            self._count("errors")
            return None

        self._count("requests")
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._count("input_tokens", (getattr(usage, "input_tokens", 0) or 0)
                        + (getattr(usage, "cache_read_input_tokens", 0) or 0)
                        + (getattr(usage, "cache_creation_input_tokens", 0) or 0))
            self._count("output_tokens", getattr(usage, "output_tokens", 0) or 0)

        if response.stop_reason == "refusal":
            self._count("refusals")
            log.warning("Anfrage wurde vom Modell abgelehnt (refusal)")
            return None
        if response.stop_reason == "max_tokens":
            log.warning("Antwort wurde wegen max_tokens abgeschnitten")
            return None
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning("Antwort war kein gültiges JSON")
            return None
