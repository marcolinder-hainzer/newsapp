"""Vertrauens-Score (0–100) für eine Meldung.

Der Score setzt sich transparent aus vier Komponenten zusammen:

* Quellen-Zuverlässigkeit (45 %): Ø der Zuverlässigkeitswerte aller berichtenden Medien.
* Bestätigung (25 %): Wie viele unabhängige Medien berichten über dasselbe Ereignis?
* Vielfalt (10 %): Berichten Medien aus verschiedenen politischen Lagern und Ländern?
* Inhaltsqualität (20 %): KI-Prüfung (belegte Aussagen, Widersprüche, Tonalität) bzw. ohne KI
  eine Heuristik (reißerische Überschriften, Meinungsbeiträge).
"""

from __future__ import annotations

from .sources import BIAS_BUCKET
from .textutil import clickbait_hits

WEIGHTS = {"reliability": 0.45, "corroboration": 0.25, "diversity": 0.10, "content": 0.20}


def trust_label(score: int) -> str:
    if score >= 80:
        return "very_high"
    if score >= 65:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def compute_trust(articles: list[dict], sources: dict[str, dict], llm_assessment: dict | None = None) -> dict:
    """articles: Liste mit mindestens source_id, title, is_opinion."""
    source_ids = sorted({a["source_id"] for a in articles if a["source_id"] in sources})
    if not source_ids:
        return {"score": 0, "label": "low", "components": {}, "notes": {"de": [], "en": []}}

    reliabilities = [int(sources[s].get("reliability") or 60) for s in source_ids]
    # Die besten Quellen zählen etwas stärker (eine seriöse Quelle wird durch Boulevard nicht entwertet)
    reliabilities.sort(reverse=True)
    weights = [1.0 / (1 + 0.15 * i) for i in range(len(reliabilities))]
    reliability = sum(r * w for r, w in zip(reliabilities, weights)) / sum(weights)

    n = len(source_ids)
    corroboration = 100 * (1 - 0.6 ** n)

    buckets = {BIAS_BUCKET.get(sources[s].get("bias"), "center") for s in source_ids}
    countries = {sources[s].get("country") for s in source_ids if sources[s].get("country")}
    diversity = (len(buckets) - 1) / 2 * 70 + min(len(countries) - 1, 2) / 2 * 30 if n > 1 else 0

    notes_de: list[str] = []
    notes_en: list[str] = []
    if llm_assessment and isinstance(llm_assessment.get("score"), (int, float)):
        content = max(0, min(100, float(llm_assessment["score"])))
        notes_de.extend(llm_assessment.get("notes_de") or [])
        notes_en.extend(llm_assessment.get("notes_en") or [])
        content_method = "ai"
    else:
        content = 72.0  # ohne KI-Prüfung bleibt eine Unsicherheit
        titles = [a.get("title") or "" for a in articles]
        bait = sum(1 for t in titles if clickbait_hits(t) > 0)
        if titles and bait / len(titles) >= 0.5:
            content -= 25
            notes_de.append("Überschriften enthalten auffällig reißerische Formulierungen.")
            notes_en.append("Headlines contain noticeably sensational wording.")
        elif bait:
            content -= 8
        opinion = sum(1 for a in articles if a.get("is_opinion"))
        if articles and opinion == len(articles):
            content -= 25
            notes_de.append("Es handelt sich ausschließlich um Meinungsbeiträge.")
            notes_en.append("Coverage consists only of opinion pieces.")
        content_method = "heuristic"

    if n == 1:
        notes_de.insert(0, "Bisher berichtet nur eine Quelle – noch nicht unabhängig bestätigt.")
        notes_en.insert(0, "Only one outlet has reported this so far – not yet independently confirmed.")
    elif n >= 5:
        notes_de.insert(0, f"Von {n} unabhängigen Medien aus {len(countries)} Ländern berichtet.")
        notes_en.insert(0, f"Reported by {n} independent outlets from {len(countries)} countries.")
    if n > 1 and len(buckets) == 3:
        notes_de.append("Berichterstattung aus dem gesamten politischen Spektrum.")
        notes_en.append("Covered across the entire political spectrum.")
    elif n >= 3 and len(buckets) == 1:
        side = next(iter(buckets))
        side_de = {"left": "aus dem linken Spektrum", "center": "aus der Mitte",
                   "right": "aus dem rechten Spektrum"}[side]
        side_en = {"left": "left-leaning", "center": "centrist", "right": "right-leaning"}[side]
        notes_de.append(f"Bisher berichten nur Medien {side_de}.")
        notes_en.append(f"So far only {side_en} outlets are covering this.")
    low_sources = [sources[s]["name"] for s in source_ids if int(sources[s].get("reliability") or 60) < 50]
    if low_sources and len(low_sources) == n:
        notes_de.append("Berichtet wird nur von Medien mit gemischter Faktentreue.")
        notes_en.append("Only outlets with a mixed factual record are reporting this.")

    components = {
        "reliability": round(reliability),
        "corroboration": round(corroboration),
        "diversity": round(diversity),
        "content": round(content),
    }
    score = round(sum(components[k] * w for k, w in WEIGHTS.items()))
    return {
        "score": score,
        "label": trust_label(score),
        "components": components,
        "weights": WEIGHTS,
        "content_method": content_method,
        "notes": {"de": notes_de[:6], "en": notes_en[:6]},
    }
