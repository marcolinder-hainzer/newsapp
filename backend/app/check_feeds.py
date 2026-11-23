"""Prüft alle Feeds der Quellenliste: `python -m app.check_feeds`."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

from .config import settings
from .db import utcnow
from .ingest import fetch_feed, make_client
from .sources import load_sources_file


def main() -> int:
    sources = load_sources_file(settings.sources_file)
    jobs = [(s, f) for s in sources for f in s["feeds"]]
    now = utcnow()
    with make_client(settings.feed_timeout_seconds) as client, ThreadPoolExecutor(12) as pool:
        results = list(pool.map(lambda job: (job, fetch_feed(client, dict(job[1]), job[0], now, 24 * 14)), jobs))
    failures = 0
    for (src, feed), res in results:
        ok = res["status"] != "error" and (res["articles"] or res["status"] == "not_modified")
        failures += 0 if ok else 1
        mark = "OK  " if ok else "FAIL"
        info = f"{len(res['articles'])} Einträge" if ok else (res["error"] or "keine Einträge")
        print(f"{mark} {src['id']:<14} {feed['url']:<75} {info}")
    print(f"\n{len(results) - failures}/{len(results)} Feeds funktionieren.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
