"""Kategorien und regelbasierte Einordnung von Artikeln."""

from __future__ import annotations

import re
from urllib.parse import urlparse

CATEGORIES: list[dict] = [
    {"slug": "politik", "de": "Politik", "en": "Politics", "icon": "landmark"},
    {"slug": "international", "de": "International", "en": "World", "icon": "globe"},
    {"slug": "wirtschaft", "de": "Wirtschaft", "en": "Business", "icon": "trending-up"},
    {"slug": "technologie", "de": "Technologie", "en": "Technology", "icon": "cpu"},
    {"slug": "wissenschaft", "de": "Wissenschaft", "en": "Science", "icon": "flask"},
    {"slug": "gesundheit", "de": "Gesundheit", "en": "Health", "icon": "heart-pulse"},
    {"slug": "klima", "de": "Klima & Umwelt", "en": "Climate & Environment", "icon": "leaf"},
    {"slug": "sport", "de": "Sport", "en": "Sports", "icon": "trophy"},
    {"slug": "kultur", "de": "Kultur & Unterhaltung", "en": "Culture & Entertainment", "icon": "palette"},
    {"slug": "panorama", "de": "Panorama", "en": "Society & More", "icon": "newspaper"},
]

SLUGS = [c["slug"] for c in CATEGORIES]
DEFAULT_CATEGORY = "panorama"

# Pfadsegmente in Artikel-URLs, die eindeutig auf ein Ressort hinweisen.
URL_SEGMENTS: dict[str, set[str]] = {
    "politik": {"politik", "politics", "inland", "deutschland", "us-news", "uk-news", "election",
                "elections", "wahl", "wahlen", "bundestagswahl", "innenpolitik", "us-politics"},
    "international": {"ausland", "international", "world", "welt", "europe", "europa", "middle-east",
                      "nahost", "africa", "afrika", "asia", "asien", "americas", "amerika", "ukraine",
                      "israel", "aussenpolitik", "world-news", "worldnews"},
    "wirtschaft": {"wirtschaft", "business", "economy", "finanzen", "finance", "markets", "money",
                   "boerse", "unternehmen", "konjunktur", "geldanlage", "economics", "maerkte"},
    "technologie": {"technology", "tech", "digital", "netzwelt", "technik", "internet", "gadgets",
                    "ki", "ai", "software", "security", "it"},
    "wissenschaft": {"wissen", "wissenschaft", "science", "forschung", "space", "weltraum", "research"},
    "gesundheit": {"gesundheit", "health", "medizin", "wellbeing", "medicine", "coronavirus"},
    "klima": {"klima", "climate", "environment", "umwelt", "climate-crisis", "klimawandel", "energy",
              "energie", "energiewende"},
    "sport": {"sport", "sports", "fussball", "football", "soccer", "tennis", "formel1", "formula1",
              "bundesliga", "olympia", "nba", "nfl", "wintersport", "golf", "cricket", "rugby"},
    "kultur": {"kultur", "culture", "arts", "entertainment", "feuilleton", "film", "music", "musik",
               "books", "buecher", "kino", "tv-and-radio", "stage", "fernsehen", "serien", "medien",
               "entertainment-and-arts", "stars", "lifestyle", "leute", "promis"},
    "panorama": {"panorama", "vermischtes", "gesellschaft", "society", "crime", "justiz", "kriminalitaet",
                 "unglueck", "wetter", "weather", "regional", "reise", "travel"},
}

# Schlüsselwörter (Wortanfänge) für die Einordnung allgemeiner Feeds.
KEYWORDS: dict[str, list[str]] = {
    "politik": [
        "bundestag", "bundesrat", "regierung", "kanzler", "minister", "partei", "koalition", "wahl",
        "abgeordnete", "opposition", "cdu", "csu", "spd", "grüne", "fdp", "afd", "bsw", "linke",
        "parlament", "parliament", "gesetz", "mps ", "senat", "congress", "senate", "president", "präsident", "governor",
        "election", "vote", "democrat", "republican", "labour", "tory", "conservative", "white house",
        "weißes haus", "nationalrat", "bundesrat", "landtag", "haushalt", "budget", "policy",
    ],
    "international": [
        "krieg", "war ", "ukraine", "russland", "russia", "gaza", "israel", "iran", "china", "nato",
        "un ", "vereinte nationen", "united nations", "diplomat", "botschaft", "ceasefire",
        "waffenruhe", "militär", "military", "invasion", "sanktion", "sanction", "eu-gipfel",
        "summit", "gipfel", "flüchtling", "refugee", "taiwan", "syrien", "syria", "putin", "selenskyj",
        "zelensky", "netanjahu", "netanyahu", "hamas", "hisbollah", "hezbollah",
    ],
    "wirtschaft": [
        "wirtschaft", "economy", "inflation", "zins", "interest rate", "ezb", "ecb", "federal reserve",
        "fed ", "börse", "stock", "dax", "aktie", "shares", "unternehmen", "konzern", "company",
        "umsatz", "revenue", "gewinn", "profit", "arbeitsmarkt", "jobs", "unemployment",
        "arbeitslos", "insolvenz", "bankrupt", "zoll", "tariff", "handel", "trade", "bank",
        "investor", "rezession", "recession", "bip", "gdp", "streik", "strike", "merger", "übernahme",
    ],
    "technologie": [
        "künstliche intelligenz", "artificial intelligence", " ki ", " ai ", "software", "apple",
        "google", "microsoft", "meta ", "openai", "smartphone", "iphone", "android", "chip",
        "nvidia", "cyber", "hacker", "datenschutz", "app ", "internet", "startup", "robot",
        "tesla", "algorithm", "algorithmus", "cloud", "quanten", "quantum", "tiktok", "social media",
    ],
    "wissenschaft": [
        "forscher", "researcher", "studie", "study", "wissenschaft", "scientist", "nasa", "esa",
        "weltraum", "space", "astronom", "rakete", "rocket", "physik", "physics", "archäolog",
        "archaeolog", "fossil", "genom", "genome", "teleskop", "telescope", "planet", "mond", "moon",
    ],
    "gesundheit": [
        "gesundheit", "health", "krankenhaus", "hospital", "patient", "arzt", "doctor", "virus",
        "impf", "vaccin", "krebs", "cancer", "medikament", "drug", "pandemie", "pandemic", "who ",
        "krankheit", "disease", "pflege", "therapie", "therapy", "krankenkasse", "infektion",
    ],
    "klima": [
        "klima", "climate", "umwelt", "environment", "co2", "emission", "erderwärmung",
        "global warming", "hitzewelle", "heatwave", "dürre", "drought", "hochwasser", "flood",
        "waldbrand", "wildfire", "erneuerbar", "renewable", "solar", "windkraft", "wind power",
        "artensterben", "biodiversity", "biodiversität", "cop3", "klimaschutz",
    ],
    "sport": [
        "bundesliga", "fußball", "football", "soccer", "champions league", "tor ", "goal",
        "trainer", "coach", "tennis", "formel 1", "formula one", "olympi", "weltmeister",
        "world cup", "wm ", " em ", "nba", "nfl", "spieltag", "match", "turnier", "tournament",
        "fc ", "bayern", "dortmund", "premier league", "transfer",
    ],
    "kultur": [
        "film", "kino", "cinema", "musik", "music", "album", "konzert", "concert", "museum",
        "ausstellung", "exhibition", "buch", "book", "roman", "novel", "theater", "theatre",
        "oscar", "grammy", "festival", "serie", "netflix", "schauspieler", "actor", "actress",
        "sänger", "singer", "künstler", "artist", "streaming",
    ],
    "panorama": [
        "polizei", "police", "unfall", "accident", "festnahme", "arrest", "gericht", "court",
        "prozess", "trial", "mord", "murder", "feuer", "fire", "unwetter", "storm", "erdbeben",
        "earthquake", "royal", "könig", "king", "prinz", "prince", "wetter", "weather",
    ],
}


def category_from_url(url: str) -> str | None:
    """Leitet die Kategorie aus den Pfadsegmenten einer Artikel-URL ab."""
    try:
        path = urlparse(url).path.lower()
    except ValueError:
        return None
    segments = [s for s in re.split(r"[/_.]", path) if s][:4]
    for segment in segments:
        for slug, hints in URL_SEGMENTS.items():
            if segment in hints:
                return slug
    return None


def category_from_tags(tags: list[str]) -> str | None:
    for tag in tags:
        tag_norm = tag.strip().lower().replace(" ", "-")
        for slug, hints in URL_SEGMENTS.items():
            if tag_norm in hints:
                return slug
    return None


def category_from_keywords(text: str) -> str | None:
    haystack = f" {text.lower()} "
    best_slug, best_score = None, 0
    for slug, words in KEYWORDS.items():
        score = sum(1 for w in words if w in haystack)
        if score > best_score:
            best_slug, best_score = slug, score
    return best_slug if best_score > 0 else None


def label(slug: str, lang: str = "de") -> str:
    for c in CATEGORIES:
        if c["slug"] == slug:
            return c[lang]
    return slug
