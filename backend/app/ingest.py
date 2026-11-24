"""RSS/Atom-Abruf: holt alle Feeds, normalisiert Einträge und speichert neue Artikel."""

from __future__ import annotations

import calendar
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from . import categories
from .db import Database, iso, utcnow
from .textutil import canonical_url, clean_html, guess_language, looks_like_opinion

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; WeitblickNews/1.0; +RSS-Reader)"
_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)


def make_client(timeout: int = 20, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"},
        transport=transport,
    )


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
            except (OverflowError, ValueError, TypeError):
                continue
    return None


def _entry_image(entry) -> str | None:
    for media in entry.get("media_content", []) or []:
        url = media.get("url")
        medium = (media.get("medium") or media.get("type") or "image").lower()
        if url and ("image" in medium or re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I)):
            return url
    for thumb in entry.get("media_thumbnail", []) or []:
        if thumb.get("url"):
            return thumb["url"]
    for enc in entry.get("enclosures", []) or []:
        if (enc.get("type") or "").startswith("image") and enc.get("href"):
            return enc["href"]
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image"):
            return link.get("href")
    html_blob = (entry.get("summary") or "") + " ".join(c.get("value", "") for c in entry.get("content", []) or [])
    match = _IMG_RE.search(html_blob)
    if match and not match.group(1).startswith("data:"):
        return match.group(1)
    return None


def parse_entries(raw: bytes, source: dict, feed_category: str | None, now: datetime,
                  max_age_hours: int) -> list[dict]:
    parsed = feedparser.parse(raw)
    articles = []
    oldest = now - timedelta(hours=max_age_hours)
    for entry in parsed.entries:
        link = entry.get("link")
        title = clean_html(entry.get("title"), 400)
        if not link or not title:
            continue
        url = canonical_url(link)
        published = _entry_datetime(entry) or now
        if published > now + timedelta(hours=1):
            published = now
        if published < oldest:
            continue

        description = clean_html(entry.get("summary") or entry.get("description"), 1500)
        if description.lower() == title.lower():
            description = ""
        content = ""
        for block in entry.get("content", []) or []:
            text = clean_html(block.get("value"))
            if len(text) > len(content):
                content = text
        if len(content) < 400 or content[:200] == description[:200]:
            content = ""
        content = content[:6000]

        tags = [t.get("term", "") for t in entry.get("tags", []) or [] if t.get("term")]
        if feed_category:
            category, conf = feed_category, 3
        else:
            category = categories.category_from_url(url)
            conf = 2
            if not category:
                category = categories.category_from_tags(tags)
            if not category:
                category = categories.category_from_keywords(f"{title} {description}")
                conf = 1
            if not category:
                category, conf = categories.DEFAULT_CATEGORY, 0

        language = source.get("language") or guess_language(f"{title} {description}")
        articles.append({
            "source_id": source["id"],
            "url": url,
            "title": title,
            "description": description,
            "content": content,
            "image_url": _entry_image(entry),
            "language": language,
            "category": category,
            "category_conf": conf,
            "is_opinion": int(looks_like_opinion(title, url)),
            "published_at": iso(published),
        })
    return articles


def store_articles(db: Database, articles: list[dict], now: datetime) -> int:
    new_count = 0
    window = iso(now - timedelta(hours=48))
    with db.write() as conn:
        for a in articles:
            existing = conn.execute("SELECT id, category_conf FROM articles WHERE url = ?", (a["url"],)).fetchone()
            if existing:
                if a["category_conf"] > (existing["category_conf"] or 0):
                    conn.execute("UPDATE articles SET category = ?, category_conf = ? WHERE id = ?",
                                 (a["category"], a["category_conf"], existing["id"]))
                continue
            duplicate = conn.execute(
                "SELECT 1 FROM articles WHERE source_id = ? AND title = ? AND published_at >= ?",
                (a["source_id"], a["title"], window),
            ).fetchone()
            if duplicate:
                continue
            conn.execute(
                """INSERT INTO articles(source_id, url, title, description, content, image_url, language, category,
                       category_conf, is_opinion, published_at, fetched_at, content_fetched)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (a["source_id"], a["url"], a["title"], a["description"], a["content"], a["image_url"],
                 a["language"], a["category"], a["category_conf"], a["is_opinion"], a["published_at"],
                 iso(now), 1 if a["content"] else 0),
            )
            new_count += 1
    return new_count


def fetch_feed(client: httpx.Client, feed: dict, source: dict, now: datetime, max_age_hours: int) -> dict:
    headers = {}
    if feed.get("etag"):
        headers["If-None-Match"] = feed["etag"]
    if feed.get("last_modified"):
        headers["If-Modified-Since"] = feed["last_modified"]
    result = {"url": feed["url"], "status": "ok", "error": None, "articles": [], "etag": feed.get("etag"),
              "last_modified": feed.get("last_modified")}
    try:
        response = client.get(feed["url"], headers=headers)
        if response.status_code == 304:
            result["status"] = "not_modified"
            return result
        response.raise_for_status()
        result["etag"] = response.headers.get("ETag")
        result["last_modified"] = response.headers.get("Last-Modified")
        result["articles"] = parse_entries(response.content, source, feed.get("category"), now, max_age_hours)
        if not result["articles"] and b"<" not in response.content[:200]:
            result["status"] = "error"
            result["error"] = "Antwort ist kein Feed"
    except httpx.HTTPStatusError as exc:
        result["status"] = "error"
        result["error"] = f"HTTP {exc.response.status_code}"
    except (httpx.HTTPError, ValueError) as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return result


def fetch_all(db: Database, source_by_id: dict[str, dict], *, max_age_hours: int = 96, timeout: int = 20,
              transport: httpx.BaseTransport | None = None, workers: int = 12) -> dict:
    """Ruft alle Feeds parallel ab und speichert neue Artikel. Gibt eine kleine Statistik zurück."""
    now = utcnow()
    with db.connect() as conn:
        feeds = [dict(r) for r in conn.execute("SELECT * FROM feeds").fetchall()]
    feeds = [f for f in feeds if f["source_id"] in source_by_id]

    stats = {"feeds": len(feeds), "ok": 0, "not_modified": 0, "errors": 0, "new_articles": 0}
    with make_client(timeout, transport) as client, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_feed, client, f, source_by_id[f["source_id"]], now, max_age_hours)
                   for f in feeds]
        results = [f.result() for f in futures]

    for res in results:
        if res["status"] == "error":
            log.warning("Feed fehlgeschlagen: %s – %s", res["url"], res["error"])
        new_items = store_articles(db, res["articles"], now) if res["articles"] else 0
        stats["new_articles"] += new_items
        stats["errors" if res["status"] == "error" else res["status"]] += 1
        with db.write() as conn:
            conn.execute(
                """UPDATE feeds SET etag = ?, last_modified = ?, last_fetch = ?, last_status = ?, last_error = ?,
                       new_items = ? WHERE url = ?""",
                (res["etag"], res["last_modified"], iso(now), res["status"], res["error"], new_items, res["url"]),
            )
    log.info("Feeds abgerufen: %s", stats)
    return stats
