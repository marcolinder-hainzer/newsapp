# Weitblick – Nachrichten mit Überblick

Weitblick ist eine Nachrichten-App nach dem Vorbild von Ground News. Sie sammelt laufend die neuesten
Meldungen aus über 50 Medien (Deutschland, Österreich, Schweiz und international), fasst Berichte
über dasselbe Ereignis zu **einer Meldung** zusammen und zeigt, **wer wie darüber berichtet**.

| Startseite | Meldung | Mobil (dunkel) |
|---|---|---|
| ![Startseite](docs/startseite.png) | ![Meldung](docs/meldung.png) | ![Mobil](docs/mobil-dunkel.png) |

<sub>Screenshots mit fiktiven Testdaten.</sub>

## Funktionen

- **Immer aktuell** – alle 15 Minuten werden 115 RSS-Feeds abgerufen (konfigurierbar). Neue Meldungen
  erscheinen sofort, die App weist auf neue Inhalte hin.
- **Kategorien & Filter** – Politik, International, Wirtschaft, Technologie, Wissenschaft, Gesundheit,
  Klima & Umwelt, Sport, Kultur, Panorama. Filter nach Zeitraum, Sprache und Land der Quellen,
  politischer Perspektive (ausgewogen, überwiegend links/rechts, „Blindspots“), Mindest-Vertrauen,
  Mindestanzahl an Quellen sowie Volltextsuche und Sortierung (Relevanz, neueste, meiste Quellen, Vertrauen).
- **Zusammenfassung jeder Meldung auf Deutsch und Englisch** – Titel, Kurzfassung, die wichtigsten
  Punkte und „Warum das wichtig ist“, erstellt von Claude ausschließlich auf Basis der verlinkten Artikel.
- **Zusammenfassung je Kategorie** – „Das Wichtigste: Politik“ usw.
- **Übergreifende Briefings** – Top-Meldungen **des Tages** und **der Woche**.
- **Vorlesen** – jede Meldung und jedes Briefing kann angehört werden, wahlweise mit **Damen- oder
  Herrenstimme**, einstellbarem Tempo, Warteschlange („Alle anhören“) und Steuerung über den Sperrbildschirm.
- **Vertrauens-Score (0–100)** für jede Meldung – mit nachvollziehbarer Aufschlüsselung.
- **Ausrichtung der Berichterstattung** – Balken links/Mitte/rechts und Liste aller Originalartikel.
- **Installierbar als App** (PWA) auf iPhone, Android und Desktop; heller und dunkler Modus.

## Schnellstart

### Mit Docker (empfohlen)

```bash
cp .env.example .env        # Schlüssel eintragen (siehe unten)
docker compose up -d --build
```

Danach ist die App unter <http://localhost:8000> erreichbar. Der erste Abruf dauert etwa eine Minute.

### Ohne Docker

Voraussetzungen: Python ≥ 3.11 und Node.js ≥ 20.

```bash
# Frontend bauen
cd frontend && npm ci && npm run build && cd ..

# Backend starten
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env && set -a && source .env && set +a
cd backend && uvicorn app.server:app --port 8000
```

### Als App aufs Handy

Öffne die Adresse im Browser des Handys und wähle **„Zum Home-Bildschirm“** (iOS: Teilen-Menü,
Android: Menü ⋮). Damit das Handy den Server erreicht, muss er im selben Netz laufen oder im Internet
erreichbar sein (z. B. auf einem kleinen Server oder Raspberry Pi).

## Konfiguration

Alle Einstellungen erfolgen über Umgebungsvariablen – siehe [`.env.example`](.env.example).

### KI-Zusammenfassungen (Claude)

| Variable | Bedeutung |
|---|---|
| `ANTHROPIC_API_KEY` | API-Schlüssel von <https://console.anthropic.com>. Ohne Schlüssel zeigt die App automatische Auszüge in der Originalsprache (keine Übersetzung). |
| `LLM_MODEL` | Standard `claude-opus-5-5`. Günstiger: `claude-sonnet-5-5` oder `claude-haiku-5-5`. |
| `LLM_EFFORT` | Denktiefe `low` / `medium` / `high` (Standard `medium`). |
| `SUMMARIES_PER_CYCLE` | Wie viele Meldungen pro Durchlauf per KI zusammengefasst werden – die wichtigsten zuerst (Standard 20). Öffnet man eine Meldung ohne KI-Fassung, wird sie bei Bedarf sofort erstellt. |
| `DIGEST_INTERVAL_MINUTES` | Wie oft Tages- und Kategorie-Briefings neu geschrieben werden (Standard 60). |

**Kosten:** Pro Meldung fällt ein Aufruf an, pro Briefing ebenfalls einer. Die Kosten hängen stark vom
gewählten Modell ab – mit `SUMMARIES_PER_CYCLE`, `REFRESH_INTERVAL_MINUTES` und `LLM_MODEL` lässt
sich das gut steuern. Den Verbrauch zeigt `GET /api/status` (`llm_usage`).

### Sprachausgabe

Ohne weitere Konfiguration liest die App mit den **Stimmen des Geräts** vor und wählt automatisch die
natürlichste verfügbare Damen- bzw. Herrenstimme (z. B. „Katja/Conrad (Natural)“ in Edge,
„Anna/Markus“ auf Apple-Geräten). In den Einstellungen lässt sich jede Stimme auch manuell wählen.

Für durchgehend **hochwertige, natürliche Stimmen** auf allen Geräten kann ein Anbieter hinterlegt
werden – die Audiodateien werden auf dem Server zwischengespeichert:

| Anbieter | Variablen | Standardstimmen (Damen / Herren) |
|---|---|---|
| **Azure AI Speech** (empfohlen, Gratiskontingent 0,5 Mio. Zeichen/Monat) | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | DE: Seraphina / Florian · EN: Ava / Andrew |
| OpenAI | `OPENAI_API_KEY` | nova / onyx (gpt-4o-mini-tts) |
| ElevenLabs | `ELEVENLABS_API_KEY` | Rachel / Adam (multilingual v2) |

`TTS_PROVIDER=auto` nimmt den ersten konfigurierten Anbieter. Stimmen lassen sich per Variable ändern
(siehe `.env.example`).

## So funktioniert es

```
RSS-Feeds ──► Abruf & Normalisierung ──► Gruppierung zu Meldungen ──► Kennzahlen & Vertrauens-Score
                                                                         │
     Briefings (Tag, Woche, Kategorien) ◄── Zusammenfassungen DE/EN ◄────┘
```

1. **Abruf** (`backend/app/ingest.py`): alle Feeds parallel, mit ETag/Last-Modified, Kategorie aus
   Feed, URL-Pfad oder Schlüsselwörtern.
2. **Gruppierung** (`cluster.py`): Artikel werden per TF-IDF-Ähnlichkeit von Titel und Teaser derselben
   Meldung zugeordnet. Meldungen mit KI-Zusammenfassung erhalten deutsche und englische „Anker“, so dass
   auch deutsch- und englischsprachige Berichte zusammenfinden; zusätzlich werden sehr ähnliche Meldungen
   zusammengeführt.
3. **Kennzahlen** (`stories.py`): Anzahl Quellen, Länder, Verteilung links/Mitte/rechts, Blindspots,
   Relevanz (Abdeckung × Aktualität × Vertrauen).
4. **Zusammenfassungen** (`summarize.py`): Claude erhält bis zu 8 möglichst unterschiedliche Artikel
   (je Lager die zuverlässigste Quelle zuerst, bei Bedarf mit Volltext) und liefert strukturiert
   Deutsch + Englisch, Kategorie und eine inhaltliche Einschätzung.
5. **Briefings** (`digests.py`): Tages-, Wochen- und Kategorie-Überblicke aus den relevantesten Meldungen.

### Vertrauens-Score

| Faktor | Gewicht | Grundlage |
|---|---|---|
| Zuverlässigkeit der Quellen | 45 % | Faktentreue der berichtenden Medien |
| Unabhängige Bestätigung | 25 % | Anzahl unabhängiger Medien |
| Vielfalt der Perspektiven | 10 % | Politische Lager und Länder |
| Inhaltliche Qualität | 20 % | Mit KI: belegte Aussagen, Widersprüche, Tonalität, Nachricht vs. Meinung. Ohne KI: Heuristik (reißerische Überschriften, Meinungsbeiträge) |

Einstufung: ab 80 „sehr hoch“, ab 65 „hoch“, ab 50 „mittel“, darunter „niedrig“. Die App zeigt zu jeder
Meldung die Teilwerte und Hinweise (z. B. „Bisher berichtet nur eine Quelle“).

### Quellen anpassen

Die Quellenliste liegt in [`backend/app/data/sources.json`](backend/app/data/sources.json). Für jedes Medium
sind Land, Sprache, politische Ausrichtung (`left`, `lean_left`, `center`, `lean_right`, `right`),
Zuverlässigkeit (0–100) und die Feeds hinterlegt. Die Einordnungen sind **Näherungswerte**, angelehnt an
öffentliche Medienbewertungen (u. a. AllSides, Media Bias/Fact Check, Ad Fontes Media), und können frei
angepasst werden. Mit `SOURCES_FILE=/pfad/zu/eigene.json` lässt sich eine eigene Liste verwenden.

Feeds prüfen (zeigt, welche URLs funktionieren):

```bash
cd backend && python -m app.check_feeds
```

## API

| Endpunkt | Beschreibung |
|---|---|
| `GET /api/stories` | Meldungen; Parameter `category`, `q`, `lang`, `country`, `source`, `perspective` (`all`/`balanced`/`left`/`right`/`blindspot`), `min_trust`, `min_sources`, `hours`, `sort` (`relevance`/`latest`/`sources`/`trust`), `limit`, `offset` |
| `GET /api/stories/{id}` | Meldung mit Zusammenfassung (DE/EN), Vertrauens-Aufschlüsselung, allen Artikeln |
| `POST /api/stories/{id}/summarize` | KI-Zusammenfassung bei Bedarf erstellen (rate-limitiert) |
| `GET /api/digest?scope=top:day` | Briefing (`top:day`, `top:week`, `category:<slug>`) |
| `GET /api/briefing` | Tages-, Wochen- und alle Kategorie-Briefings |
| `GET /api/sources` | Quellen mit Ausrichtung, Zuverlässigkeit und Feed-Status |
| `GET /api/tts/story/{id}?lang=de&voice=female` | Meldung als MP3 (Server-Stimme) |
| `GET /api/tts/digest?scope=top:day&lang=de&voice=male` | Briefing als MP3 |
| `GET /api/meta`, `GET /api/status` | Konfiguration, Statistik, Feed-Status, KI-Verbrauch |
| `POST /api/admin/refresh` | Sofortigen Abruf auslösen (mit `ADMIN_TOKEN` über Header `X-Admin-Token`) |

## Entwicklung

```bash
# Backend-Tests (nutzen fiktive Feeds und eine simulierte KI – keine echten API-Aufrufe)
cd backend && pip install -r requirements-dev.txt && python -m pytest

# Frontend mit Hot-Reload (leitet /api an localhost:8000 weiter)
cd frontend && npm run dev
```

Aufbau:

```
backend/app/     FastAPI, Abruf, Gruppierung, Score, Claude-Anbindung, Sprachausgabe (SQLite)
frontend/src/    React + TypeScript (Vite), PWA
```

## Hinweise

- Weitblick zeigt nur Überschriften, kurze Teaser und eigene Zusammenfassungen – die Originalartikel sind
  stets verlinkt. Volltexte werden nur intern für die Zusammenfassung verwendet und nach 4 Tagen gelöscht.
- KI-Zusammenfassungen können Fehler enthalten; im Zweifel gilt der verlinkte Originalartikel.
