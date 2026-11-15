"""RSS deal-feed check, ported from prototype/flight_watch.py: download ->
parse <item> -> dedup by guid -> keyword filter -> return new matches."""

import urllib.request
import xml.etree.ElementTree as ET

UA = {
    "User-Agent": "personal-flight-watch/1.0",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.5",
}


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check_rss(state, feeds, keywords_re):
    """Marks every item seen (so a later run won't re-alert on it). The first
    time a given feed URL is ever fetched it is only seeded, never alerted
    on (SPEC.md section 6 step 5) - tracked per feed rather than per run, so
    adding a feed later doesn't dump its whole backlog as "new" deals."""
    alerts = []
    seen = set(state["seen_rss"])
    seen_feeds = state.setdefault("seen_feeds", [])
    for feed in feeds:
        first_time = feed not in seen_feeds
        try:
            raw = http_get(feed)
            # A dead/blocked feed URL often answers with an HTML page; say so
            # instead of surfacing an opaque XML parse error.
            if raw.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
                print(f"rss failed {feed}: not an RSS feed (got an HTML page)")
                continue
            root = ET.fromstring(raw)
        except Exception as e:
            print(f"rss failed {feed}: {e}")
            continue
        new_items = 0
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            key = item.findtext("guid") or link or title
            if key in seen:
                continue
            seen.add(key)
            state["seen_rss"].append(key)
            new_items += 1
            if not first_time and keywords_re.search(
                    title + " " + (item.findtext("description") or "")):
                alerts.append({"title": title, "link": link})
        if first_time:
            seen_feeds.append(feed)
            print(f"rss {feed}: first fetch, seeded {new_items} item(s) without alerting")
    return alerts
