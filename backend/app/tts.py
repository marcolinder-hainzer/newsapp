"""Sprachausgabe (Text-to-Speech) mit hochwertigen neuronalen Stimmen.

Unterstützte Anbieter (jeweils mit eigenem API-Schlüssel):
* Azure AI Speech  – sehr natürliche Stimmen, großzügiges Gratiskontingent (empfohlen)
* OpenAI           – gpt-4o-mini-tts
* ElevenLabs       – multilinguale Premium-Stimmen

Ist kein Anbieter konfiguriert, liest die App im Browser mit den Systemstimmen vor.
Erzeugte Audiodateien werden auf der Festplatte zwischengespeichert.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from xml.sax.saxutils import escape

import httpx

from .config import Settings
from .textutil import split_sentences

log = logging.getLogger(__name__)

GENDERS = ("female", "male")


class TTSError(RuntimeError):
    pass


def chunk_text(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for sentence in split_sentences(text) or [text]:
        while len(sentence) > max_chars:  # extrem lange Sätze hart teilen
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:cut])
            sentence = sentence[cut:].strip()
        if len(current) + len(sentence) + 1 > max_chars and current:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


class Provider:
    name = "base"
    label = ""
    max_chars = 3000

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return False

    def voice(self, lang: str, gender: str) -> str:
        raise NotImplementedError

    def voice_names(self) -> dict:
        return {lang: {g: self.voice(lang, g) for g in GENDERS} for lang in ("de", "en")}

    def synthesize_chunk(self, client: httpx.Client, text: str, lang: str, gender: str) -> bytes:
        raise NotImplementedError


class AzureProvider(Provider):
    name = "azure"
    label = "Azure AI Speech"
    max_chars = 3500
    DEFAULTS = {
        ("de", "female"): "de-DE-SeraphinaMultilingualNeural",
        ("de", "male"): "de-DE-FlorianMultilingualNeural",
        ("en", "female"): "en-US-AvaMultilingualNeural",
        ("en", "male"): "en-US-AndrewMultilingualNeural",
    }

    @property
    def configured(self) -> bool:
        return bool(self.settings.azure_speech_key)

    def voice(self, lang: str, gender: str) -> str:
        return os.getenv(f"AZURE_VOICE_{lang.upper()}_{gender.upper()}") or self.DEFAULTS[(lang, gender)]

    def synthesize_chunk(self, client, text, lang, gender):
        voice = self.voice(lang, gender)
        locale = "-".join(voice.split("-")[:2])
        ssml = (
            f"<speak version='1.0' xml:lang='{locale}' xmlns='http://www.w3.org/2001/10/synthesis'>"
            f"<voice name='{voice}'>{escape(text)}</voice></speak>"
        )
        response = client.post(
            f"https://{self.settings.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={
                "Ocp-Apim-Subscription-Key": self.settings.azure_speech_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
            },
            content=ssml.encode("utf-8"),
        )
        response.raise_for_status()
        return response.content


class OpenAIProvider(Provider):
    name = "openai"
    label = "OpenAI"
    max_chars = 3800
    DEFAULTS = {"female": "nova", "male": "onyx"}
    INSTRUCTIONS = {
        "de": "Sprich ruhig, warm und deutlich wie eine professionelle Nachrichtensprecherin bzw. ein "
              "professioneller Nachrichtensprecher. Sprache: Deutsch.",
        "en": "Speak in a calm, warm and clear tone like a professional news presenter. Language: English.",
    }

    @property
    def configured(self) -> bool:
        return bool(self.settings.openai_api_key)

    def voice(self, lang: str, gender: str) -> str:
        return os.getenv(f"OPENAI_VOICE_{gender.upper()}") or self.DEFAULTS[gender]

    def synthesize_chunk(self, client, text, lang, gender):
        payload = {
            "model": self.settings.openai_tts_model,
            "voice": self.voice(lang, gender),
            "input": text,
            "response_format": "mp3",
        }
        if "gpt-4o" in self.settings.openai_tts_model:
            payload["instructions"] = self.INSTRUCTIONS[lang]
        response = client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json=payload,
        )
        response.raise_for_status()
        return response.content


class ElevenLabsProvider(Provider):
    name = "elevenlabs"
    label = "ElevenLabs"
    max_chars = 2500
    DEFAULTS = {"female": "21m00Tcm4TlvDq8ikWAM", "male": "pNInz6obpgDQGcFmaJgB"}

    @property
    def configured(self) -> bool:
        return bool(self.settings.elevenlabs_api_key)

    def voice(self, lang: str, gender: str) -> str:
        return os.getenv(f"ELEVENLABS_VOICE_{gender.upper()}") or self.DEFAULTS[gender]

    def synthesize_chunk(self, client, text, lang, gender):
        response = client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice(lang, gender)}",
            headers={"xi-api-key": self.settings.elevenlabs_api_key, "Accept": "audio/mpeg"},
            params={"output_format": "mp3_44100_128"},
            json={"text": text, "model_id": os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")},
        )
        response.raise_for_status()
        return response.content


PROVIDERS = {"azure": AzureProvider, "openai": OpenAIProvider, "elevenlabs": ElevenLabsProvider}


class TTSService:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport
        self.provider = self._select_provider()

    def _select_provider(self) -> Provider | None:
        choice = self.settings.tts_provider
        if choice in ("browser", "none", "off"):
            return None
        if choice in PROVIDERS:
            provider = PROVIDERS[choice](self.settings)
            if not provider.configured:
                log.warning("TTS-Anbieter %s gewählt, aber kein API-Schlüssel gesetzt", choice)
                return None
            return provider
        for cls in PROVIDERS.values():  # auto: erster konfigurierter Anbieter
            provider = cls(self.settings)
            if provider.configured:
                return provider
        return None

    @property
    def available(self) -> bool:
        return self.provider is not None

    def info(self) -> dict:
        if not self.provider:
            return {"server": False, "provider": None, "label": None, "voices": None}
        return {"server": True, "provider": self.provider.name, "label": self.provider.label,
                "voices": self.provider.voice_names()}

    def cache_path(self, text: str, lang: str, gender: str) -> Path:
        assert self.provider is not None
        key = "|".join([self.provider.name, self.provider.voice(lang, gender), lang, text])
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
        return self.settings.tts_cache_dir / f"{digest}.mp3"

    def synthesize(self, text: str, lang: str, gender: str) -> Path:
        if not self.provider:
            raise TTSError("Kein Sprachausgabe-Anbieter konfiguriert")
        if lang not in ("de", "en") or gender not in GENDERS:
            raise TTSError("Ungültige Sprache oder Stimme")
        path = self.cache_path(text, lang, gender)
        if path.exists() and path.stat().st_size > 0:
            return path
        audio = bytearray()
        try:
            with httpx.Client(timeout=90, transport=self.transport) as client:
                for chunk in chunk_text(text, self.provider.max_chars):
                    audio.extend(self.provider.synthesize_chunk(client, chunk, lang, gender))
        except httpx.HTTPStatusError as exc:
            raise TTSError(f"{self.provider.label}: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise TTSError(f"{self.provider.label} nicht erreichbar: {exc}") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(bytes(audio))
        tmp.replace(path)
        return path

    def prune_cache(self, max_files: int = 2000) -> None:
        files = sorted(self.settings.tts_cache_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        for p in files[:-max_files] if len(files) > max_files else []:
            p.unlink(missing_ok=True)
