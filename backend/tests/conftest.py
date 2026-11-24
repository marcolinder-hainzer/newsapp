"""Testumgebung: fiktive Quellen und Feeds, ausgeliefert über einen httpx-MockTransport."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from app.config import Settings

NOW = datetime.now(timezone.utc)


def _rfc822(minutes_ago: int) -> str:
    return format_datetime(NOW - timedelta(minutes=minutes_ago))


# Alle Meldungen sind frei erfunden und dienen nur Testzwecken.
FEED_ITEMS: dict[str, list[dict]] = {
    "tagesschau": [
        {"title": "Bundestag beschließt Reform der Bahnfinanzierung",
         "link": "https://test.tagesschau.example/inland/bahnreform-bundestag-101.html",
         "desc": "Der Bundestag hat die Reform der Bahnfinanzierung beschlossen. Künftig soll ein Infrastrukturfonds "
                 "die Sanierung des Schienennetzes über zehn Jahre absichern. Die Opposition kritisiert die Finanzierung.",
         "ago": 60},
        {"title": "Sturm Elara trifft Portugals Küste – Tausende ohne Strom",
         "link": "https://test.tagesschau.example/ausland/sturm-elara-portugal-100.html",
         "desc": "Der Sturm Elara hat an der Küste Portugals schwere Schäden angerichtet. Tausende Haushalte sind ohne Strom, "
                 "Behörden warnen vor Überschwemmungen.",
         "ago": 120},
    ],
    "spiegel": [
        {"title": "Bahnreform: Bundestag stimmt für neuen Infrastrukturfonds der Bahn",
         "link": "https://test.spiegel.example/politik/deutschland/bahnreform-bundestag-a-1.html",
         "desc": "Mit den Stimmen der Koalition hat der Bundestag die Bahnreform beschlossen. Ein Infrastrukturfonds soll die "
                 "Sanierung des maroden Schienennetzes finanzieren.",
         "ago": 50},
        {"title": "FC Musterstadt gewinnt das Pokalfinale gegen Beispielhausen",
         "link": "https://test.spiegel.example/sport/fussball/pokalfinale-musterstadt-a-2.html",
         "desc": "Der FC Musterstadt hat das Pokalfinale gegen Beispielhausen mit 2:1 gewonnen. Das Siegtor fiel in der Nachspielzeit.",
         "ago": 30},
    ],
    "welt": [
        {"title": "Bundestag beschließt Bahnreform – Kritik an Finanzierung des Infrastrukturfonds",
         "link": "https://test.welt.example/politik/deutschland/article1/bahnreform.html",
         "desc": "Der Bundestag hat die Reform der Bahnfinanzierung beschlossen. Kritiker bemängeln, dass der Infrastrukturfonds "
                 "die Sanierung des Schienennetzes nicht dauerhaft absichere.",
         "ago": 70},
    ],
    "bbc": [
        {"title": "German parliament approves rail funding reform",
         "link": "https://test.bbc.example/news/world-europe-1",
         "desc": "Germany's parliament has approved a reform of rail funding, creating an infrastructure fund to renovate "
                 "the rail network over ten years.",
         "ago": 40},
        {"title": "Storm Elara batters Portugal coast leaving thousands without power",
         "link": "https://test.bbc.example/news/world-europe-2",
         "desc": "Storm Elara has caused severe damage along Portugal's coast, leaving thousands of homes without power "
                 "as authorities warn of flooding.",
         "ago": 90},
    ],
    "guardian": [
        {"title": "Storm Elara: thousands without power as storm hits Portugal coast",
         "link": "https://test.guardian.example/world/2026/storm-elara-portugal",
         "desc": "Thousands of homes in Portugal are without power after Storm Elara hit the coast, with authorities "
                 "warning of further flooding.",
         "ago": 80},
    ],
    "heise": [
        {"title": "Neues Open-Source-Werkzeug prüft Router auf Sicherheitslücken",
         "link": "https://test.heise.example/news/router-werkzeug-1.html",
         "desc": "Ein neues quelloffenes Werkzeug soll Heimrouter automatisch auf bekannte Sicherheitslücken prüfen.",
         "ago": 200},
    ],
    "kicker": [
        {"title": "Pokalfinale: Musterstadt besiegt Beispielhausen in der Nachspielzeit",
         "link": "https://test.kicker.example/pokalfinale-musterstadt",
         "desc": "Der FC Musterstadt gewinnt das Pokalfinale gegen Beispielhausen mit 2:1. Das entscheidende Tor fiel in der Nachspielzeit.",
         "ago": 25},
    ],
    "boulevard": [
        {"title": "SCHOCK-Sturm Elara! Portugal versinkt im Chaos",
         "link": "https://test.boulevard.example/news/sturm-elara-schock",
         "desc": "Unglaubliche Bilder aus Portugal: Sturm Elara wütet an der Küste.",
         "ago": 85},
    ],
}

SOURCES = [
    {"id": "tagesschau", "name": "Rundfunk Aktuell (fiktiv)", "country": "DE", "language": "de", "bias": "center",
     "reliability": 90, "ownership": "public", "type": "broadcaster", "feeds": [{"url": "https://feeds.test/tagesschau.xml", "category": None}]},
    {"id": "spiegel", "name": "Das Wochenmagazin (fiktiv)", "country": "DE", "language": "de", "bias": "lean_left",
     "reliability": 85, "ownership": "private", "type": "news", "feeds": [{"url": "https://feeds.test/spiegel.xml", "category": None}]},
    {"id": "welt", "name": "Morgenzeitung (fiktiv)", "country": "DE", "language": "de", "bias": "lean_right",
     "reliability": 78, "ownership": "private", "type": "news", "feeds": [{"url": "https://feeds.test/welt.xml", "category": None}]},
    {"id": "bbc", "name": "Global Broadcast (fictional)", "country": "GB", "language": "en", "bias": "center",
     "reliability": 90, "ownership": "public", "type": "broadcaster", "feeds": [{"url": "https://feeds.test/bbc.xml", "category": None}]},
    {"id": "guardian", "name": "Morning Ledger (fictional)", "country": "GB", "language": "en", "bias": "lean_left",
     "reliability": 83, "ownership": "trust", "type": "news", "feeds": [{"url": "https://feeds.test/guardian.xml", "category": None}]},
    {"id": "heise", "name": "Tech-Kurier (fiktiv)", "country": "DE", "language": "de", "bias": "center",
     "reliability": 88, "ownership": "private", "type": "specialist", "feeds": [{"url": "https://feeds.test/heise.xml", "category": "technologie"}]},
    {"id": "kicker", "name": "Sportblatt (fiktiv)", "country": "DE", "language": "de", "bias": "center",
     "reliability": 82, "ownership": "private", "type": "specialist", "feeds": [{"url": "https://feeds.test/kicker.xml", "category": "sport"}]},
    {"id": "boulevard", "name": "Blitz-Boulevard (fiktiv)", "country": "DE", "language": "de", "bias": "right",
     "reliability": 45, "ownership": "private", "type": "tabloid", "feeds": [{"url": "https://feeds.test/boulevard.xml", "category": None}]},
]


def build_feed(source_id: str) -> bytes:
    items = []
    for item in FEED_ITEMS.get(source_id, []):
        items.append(
            f"""<item><title><![CDATA[{item['title']}]]></title><link>{item['link']}</link>
            <description><![CDATA[<p>{item['desc']}</p>]]></description>
            <pubDate>{_rfc822(item['ago'])}</pubDate>
            <enclosure url="https://img.test/{source_id}.jpg" type="image/jpeg" length="1000"/></item>"""
        )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{source_id}</title>
    <link>https://{source_id}.example</link><description>Test</description>{''.join(items)}</channel></rss>"""
    return xml.encode("utf-8")


def feed_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "feeds.test":
        source_id = request.url.path.strip("/").removesuffix(".xml")
        if source_id in FEED_ITEMS:
            return httpx.Response(200, content=build_feed(source_id), headers={"Content-Type": "application/rss+xml"})
    return httpx.Response(404)


@pytest.fixture
def test_settings(tmp_path: Path, monkeypatch) -> Settings:
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path / "no-frontend"))
    sources_file = tmp_path / "sources.json"
    sources_file.write_text(json.dumps({"sources": SOURCES}), encoding="utf-8")
    settings = Settings()
    settings.data_dir = tmp_path / "data"
    settings.sources_file = sources_file
    settings.scheduler_enabled = False
    settings.translation_enabled = False
    settings.ensure_dirs()
    return settings


@pytest.fixture
def feed_transport() -> httpx.MockTransport:
    return httpx.MockTransport(feed_handler)


class FakeTranslator:
    """Simulierte Übersetzung für Tests: kennt ein paar feste Sätze, sonst wird markiert übersetzt."""

    KNOWN = {
        "Bundestag beschließt Reform der Bahnfinanzierung": "German parliament approves rail funding reform",
        "Sturm Elara trifft Portugals Küste – Tausende ohne Strom":
            "Storm Elara hits Portugal's coast leaving thousands without power",
        "Der Bundestag hat die Reform der Bahnfinanzierung beschlossen.":
            "The Bundestag has approved the reform of rail funding.",
        "Künftig soll ein Infrastrukturfonds die Sanierung des Schienennetzes über zehn Jahre absichern.":
            "In future, an infrastructure fund is to secure the renovation of the rail network over ten years.",
        "Mit den Stimmen der Koalition hat der Bundestag die Bahnreform beschlossen.":
            "With the votes of the coalition, the Bundestag passed the rail reform.",
        "Ein Infrastrukturfonds soll die Sanierung des maroden Schienennetzes finanzieren.":
            "An infrastructure fund is to finance the renovation of the dilapidated rail network.",
        "Kritiker bemängeln, dass der Infrastrukturfonds die Sanierung des Schienennetzes nicht dauerhaft absichere.":
            "Critics complain that the infrastructure fund does not permanently secure the renovation of the rail network.",
        "Die Opposition kritisiert die Finanzierung.": "The opposition criticises the funding.",
        "Bundestag beschließt Bahnreform – Kritik an Finanzierung des Infrastrukturfonds":
            "Bundestag passes rail reform – criticism of infrastructure fund financing",
        "Bahnreform: Bundestag stimmt für neuen Infrastrukturfonds der Bahn":
            "Rail reform: Bundestag votes for new rail infrastructure fund",
    }

    def __init__(self, budget_segments: int | None = None):
        self.calls = 0
        self.budget = budget_segments
        self.stats = {"translated": 0, "cached": 0, "seconds": 0.0}
        self.available = True

    def info(self):
        return {"enabled": True, "engine": "Fake"}

    def start_budget(self, seconds):
        self.stats = {"translated": 0, "cached": 0, "seconds": 0.0}

    def translate(self, texts, src, tgt):
        out = []
        for t in texts:
            if self.budget is not None and self.budget <= 0:
                out.append(None)
                continue
            if self.budget is not None:
                self.budget -= 1
            self.calls += 1
            out.append(self.KNOWN.get(t, f"[{tgt}] {t}"))
        return out
