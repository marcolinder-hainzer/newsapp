"""Kostenlose maschinelle Übersetzung Deutsch ↔ Englisch.

Verwendet die frei verfügbaren Open-Source-Modelle OPUS-MT der Universität Helsinki
(Lizenz CC-BY 4.0). Sie laufen lokal – in der GitHub Action oder auf dem eigenen Rechner –
und benötigen weder Konto noch API-Schlüssel. Übersetzungen werden in der Datenbank
zwischengespeichert, so dass jeder Text nur einmal übersetzt wird.

Benötigt die optionalen Pakete aus requirements-translate.txt (torch, transformers,
sentencepiece). Fehlen sie, zeigt die App Inhalte in der Originalsprache.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
import threading
import time

from .db import Database, iso, utcnow

log = logging.getLogger(__name__)

# Je Richtung das bevorzugte Modell zuerst; schlägt das Laden fehl, wird das nächste verwendet.
# Für Englisch → Deutsch liefert das größere "tc-big"-Modell deutlich natürlichere Überschriften.
MODELS = {
    ("de", "en"): [os.getenv("TRANSLATION_MODEL_DE_EN") or "Helsinki-NLP/opus-mt-de-en"],
    ("en", "de"): [os.getenv("TRANSLATION_MODEL_EN_DE") or "Helsinki-NLP/opus-mt-tc-big-en-de",
                   "Helsinki-NLP/opus-mt-en-de"],
}
ENGINE_LABEL = "OPUS-MT (Helsinki-NLP)"


def dependencies_installed() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "transformers", "sentencepiece"))


def _key(text: str, src: str, tgt: str) -> str:
    # Das bevorzugte Modell ist Teil des Schlüssels: ein Modellwechsel übersetzt neue Texte neu
    model = MODELS.get((src, tgt), ["?"])[0]
    return hashlib.sha1(f"{model}|{src}>{tgt}|{text}".encode("utf-8")).hexdigest()


class Translator:
    """Übersetzt Textlisten stapelweise und hält sich an ein Zeitbudget pro Durchlauf."""

    batch_size = 16

    def __init__(self, db: Database, enabled: bool = True):
        self.db = db
        self.enabled = enabled and dependencies_installed()
        self._models: dict[tuple[str, str], tuple] = {}
        self._lock = threading.Lock()
        self._deadline: float | None = None
        self.stats = {"translated": 0, "cached": 0, "seconds": 0.0}

    @property
    def available(self) -> bool:
        return self.enabled

    def info(self) -> dict:
        return {"enabled": self.available, "engine": ENGINE_LABEL if self.available else None}

    # --- Zeitbudget ---------------------------------------------------------
    def start_budget(self, seconds: int) -> None:
        self._deadline = time.monotonic() + max(0, seconds)
        self.stats = {"translated": 0, "cached": 0, "seconds": 0.0}

    def time_left(self) -> bool:
        return self._deadline is None or time.monotonic() < self._deadline

    # --- Modelle ------------------------------------------------------------
    def _model(self, src: str, tgt: str):
        with self._lock:
            if (src, tgt) not in self._models:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

                torch.set_num_threads(max(1, os.cpu_count() or 1))
                last_error: Exception | None = None
                for name in MODELS[(src, tgt)]:
                    started = time.monotonic()
                    try:
                        tokenizer = AutoTokenizer.from_pretrained(name)
                        model = AutoModelForSeq2SeqLM.from_pretrained(name)
                    except Exception as exc:  # z. B. Modell nicht verfügbar → nächstes versuchen
                        log.warning("Übersetzungsmodell %s nicht verfügbar: %s", name, exc)
                        last_error = exc
                        continue
                    model.eval()
                    self._models[(src, tgt)] = (tokenizer, model)
                    log.info("Übersetzungsmodell %s geladen (%.1f s)", name, time.monotonic() - started)
                    break
                else:
                    raise RuntimeError(f"Kein Übersetzungsmodell für {src}→{tgt} verfügbar") from last_error
            return self._models[(src, tgt)]

    def loaded_models(self) -> list[str]:
        return [getattr(m, "name_or_path", "?") for _, m in self._models.values()]

    def _translate_batch(self, texts: list[str], src: str, tgt: str) -> list[str]:
        import torch

        tokenizer, model = self._model(src, tgt)
        encoded = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=400)
        max_new = min(512, int(encoded["input_ids"].shape[1] * 1.6) + 16)
        with torch.inference_mode():
            generated = model.generate(**encoded, num_beams=2, max_new_tokens=max_new)
        return [t.strip() for t in tokenizer.batch_decode(generated, skip_special_tokens=True)]

    # --- Öffentliche Schnittstelle -----------------------------------------
    def cached(self, texts: list[str], src: str, tgt: str) -> dict[str, str]:
        keys = {_key(t, src, tgt): t for t in texts}
        found: dict[str, str] = {}
        if not keys:
            return found
        with self.db.connect() as conn:
            items = list(keys)
            for start in range(0, len(items), 500):
                chunk = items[start:start + 500]
                rows = conn.execute(
                    f"SELECT key, text FROM translations WHERE key IN ({','.join('?' * len(chunk))})", chunk
                ).fetchall()
                for r in rows:
                    found[keys[r["key"]]] = r["text"]
        return found

    def translate(self, texts: list[str], src: str, tgt: str) -> list[str | None]:
        """Übersetzt Texte; liefert None für Texte, die im Zeitbudget nicht mehr übersetzt wurden."""
        if src == tgt:
            return list(texts)
        clean = [t.strip() for t in texts]
        known = self.cached([t for t in clean if t], src, tgt)
        self.stats["cached"] += sum(1 for t in clean if t in known)
        todo = sorted({t for t in clean if t and t not in known}, key=len)
        if todo and self.available and (src, tgt) in MODELS:
            started = time.monotonic()
            for start in range(0, len(todo), self.batch_size):
                if not self.time_left():
                    break
                batch = todo[start:start + self.batch_size]
                try:
                    out = self._translate_batch(batch, src, tgt)
                except Exception:  # Modellfehler dürfen den Durchlauf nicht abbrechen
                    log.exception("Übersetzung fehlgeschlagen – Übersetzung wird für diesen Durchlauf deaktiviert")
                    self.enabled = False
                    break
                now = iso(utcnow())
                with self.db.write() as conn:
                    conn.executemany(
                        "INSERT OR REPLACE INTO translations(key, text, created) VALUES(?,?,?)",
                        [(_key(s, src, tgt), t, now) for s, t in zip(batch, out)],
                    )
                known.update(zip(batch, out))
                self.stats["translated"] += len(batch)
            self.stats["seconds"] += time.monotonic() - started
        return [known.get(t) if t else "" for t in clean]
