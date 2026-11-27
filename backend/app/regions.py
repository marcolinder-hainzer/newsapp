"""Regionale Einordnung von Meldungen – derzeit: Themen aus Österreich.

Eine Meldung gilt als österreichisches Thema, wenn
* sie aus einem regionalen Österreich-Feed stammt (z. B. ORF Tirol), oder
* mindestens zwei Hinweise zusammenkommen: ein Bericht eines österreichischen Mediums und/oder
  Berichte, die eindeutig österreichische Begriffe enthalten (Orte, Bundesländer, Parteien,
  Institutionen, Politikerinnen und Politiker).
"""

from __future__ import annotations

import re

AT = "AT"

# Eindeutige Begriffe; "*" am Ende erlaubt Endungen (Wiener, Tirols, österreichische …)
_AT_TERMS = [
    "österreich*", "austria*", "wien*", "vienna*", "viennese", "graz*", "linz*", "salzburg*", "innsbruck*",
    "klagenfurt*", "bregenz*", "eisenstadt*", "st. pölten*", "sankt pölten*", "villach*", "wels", "dornbirn*",
    "tirol*", "tyrol*", "vorarlberg*", "kärnten*", "carinthia*", "steiermark*", "steirisch*", "styria*",
    "burgenland*", "niederösterreich*", "oberösterreich*", "arlberg*", "zillertal*", "kitzbühel*", "ischgl*",
    "hallstatt*", "wachau*", "osttirol*",
    "övp", "spö", "fpö", "neos", "kickl*", "babler*", "meinl-reisinger*", "van der bellen", "mikl-leitner*",
    "edtstadler*", "doskozil*", "mattle*", "nationalrat*", "bundesheer*", "orf", "öbb", "asfinag", "wko",
    "ögb", "vfgh", "öfb", "ams-chef*",
]


def _pattern(term: str) -> str:
    word = re.escape(term.rstrip("*"))
    suffix = r"[\wäöüß-]*" if term.endswith("*") else ""
    return rf"(?<![\wäöüß]){word}{suffix}(?![\wäöüß])"


_AT_RE = re.compile("|".join(_pattern(t) for t in _AT_TERMS), re.IGNORECASE)


def austria_hits(text: str) -> int:
    """Anzahl verschiedener Österreich-Begriffe im Text."""
    return len({m.group(0).lower() for m in _AT_RE.finditer(text or "")})


def story_regions(articles: list[dict], sources: dict[str, dict]) -> list[str]:
    regional_feed = any((a.get("region") or "").upper().startswith(AT) for a in articles)
    at_source = any(sources.get(a["source_id"], {}).get("country") == AT for a in articles)
    hits = [austria_hits(f"{a.get('title') or ''} {a.get('description') or ''}") for a in articles]
    score = sum(1 for h in hits if h) + (1 if at_source else 0)
    if regional_feed or score >= 2 or (hits and max(hits) >= 2):
        return [AT]
    return []
