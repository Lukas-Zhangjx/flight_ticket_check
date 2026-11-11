"""Travelpayouts (Aviasales) Data API client.

Docs (per SPEC.md 2.1, verify against official docs when wiring a real token):
  GET https://api.travelpayouts.com/aviasales/v3/prices_for_dates
  params: origin, destination, departure_at (YYYY-MM or YYYY-MM-DD),
          one_way, unique, sorting, currency, limit, page, token

Returns *cached* search results, not live prices. Throttled to <=1 req/sec
and retried up to MAX_RETRIES times per SPEC.md's "统一节流/失败重试" rule.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
UA = {"User-Agent": "personal-flight-watch-collector/1.0"}

MIN_INTERVAL_SECONDS = 1.0
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 2.0
PAGE_SIZE = 1000
MAX_PAGES = 3


class TravelpayoutsError(Exception):
    pass


class TravelpayoutsClient:
    def __init__(self, token, min_interval=MIN_INTERVAL_SECONDS,
                 max_retries=MAX_RETRIES, timeout=30):
        self.token = token
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_call = 0.0

    def _throttle(self):
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

    def _request(self, params):
        url = API_BASE + "?" + urllib.parse.urlencode(params)
        last_err = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            self._last_call = time.monotonic()
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read())
            except (urllib.error.URLError, json.JSONDecodeError) as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        raise TravelpayoutsError(f"request failed after retries: {last_err}")

    def get_prices_for_month(self, origin, destination, year_month,
                              currency="eur"):
        """Fetch cached one-way fares for a whole month, paging until exhausted."""
        entries = []
        for page in range(1, MAX_PAGES + 1):
            params = {
                "origin": origin,
                "destination": destination,
                "departure_at": year_month,
                "one_way": "true",
                "unique": "false",
                "sorting": "price",
                "currency": currency,
                "limit": str(PAGE_SIZE),
                "page": str(page),
                "token": self.token,
            }
            payload = self._request(params)
            page_data = payload.get("data") or []
            entries.extend(page_data)
            if len(page_data) < PAGE_SIZE:
                break
        return entries
