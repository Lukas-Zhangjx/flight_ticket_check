"""Talks to the Cloudflare Worker's /watchlist endpoint (SPEC.md section 5),
so the collector can read its route list from Worker KV instead of a local
file once that's configured (Phase 5+)."""

import json
import urllib.request

UA = {"User-Agent": "flight-ticket-check-collector/1.0"}


def get_watchlist(worker_url, access_key, timeout=30):
    req = urllib.request.Request(
        worker_url.rstrip("/") + "/watchlist",
        headers={**UA, "X-Access-Key": access_key},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())
