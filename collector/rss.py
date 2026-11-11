"""RSS deal-feed check, ported from prototype/flight_watch.py: download ->
parse <item> -> dedup by guid -> keyword filter -> return new matches."""

import urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "personal-flight-watch/1.0"}


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check_rss(state, feeds, keywords_re, first_run):
    """Marks every item seen (so a later run won't re-alert on it), but only
    returns matches when first_run is False (SPEC.md section 6 step 5:
    the first run just seeds 'seen', it must not spam on day one)."""
    alerts = []
    seen = set(state["seen_rss"])
    for feed in feeds:
        try:
            root = ET.fromstring(http_get(feed))
        except Exception as e:
            print(f"rss failed {feed}: {e}")
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            key = item.findtext("guid") or link or title
            if key in seen:
                continue
            seen.add(key)
            state["seen_rss"].append(key)
            if not first_run and keywords_re.search(
                    title + " " + (item.findtext("description") or "")):
                alerts.append({"title": title, "link": link})
    return alerts
