#!/usr/bin/env python3
"""Daily collector (SPEC.md sections 9.1-9.2): reads a local watchlist.json,
queries Travelpayouts per enabled route, writes a dated snapshot per route,
regenerates data/index.json and data/history/<route_id>.json, then checks
for price alerts and RSS deals and pushes any to ntfy.

Only Python standard library is used.

Usage:
  python3 collect.py --dry-run                 # fake data, no network/token
  TP_TOKEN=xxx NTFY_TOPIC=xxx python3 collect.py

Env vars:
  TP_TOKEN     Travelpayouts API token (required unless --dry-run)
  NTFY_TOPIC   ntfy topic to push alerts to (optional; no topic = print only)
  NTFY_SERVER  optional, default https://ntfy.sh
  RSS_FEEDS    comma-separated RSS URLs (optional, has a default)
  KEYWORDS     regex for RSS filtering (optional, has a default)
  WORKER_URL   Cloudflare Worker base URL (optional; with ACCESS_KEY, reads
               the watchlist from the Worker's KV instead of --watchlist)
  ACCESS_KEY   access key for WORKER_URL (SPEC.md section 5/6)
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from aggregate import (aggregate_entries, month_range, regenerate_history,
                        regenerate_index, write_snapshot)
from alert_state import compute_route_alerts, load_alert_state, save_alert_state, state_path
from fake_data import fake_entries_for_route
from notify import notify
from rss import check_rss
from tp_client import TravelpayoutsClient, TravelpayoutsError
from worker_client import get_watchlist

DEFAULT_WATCHLIST = Path(__file__).with_name("watchlist.json")
DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"

DEFAULT_RSS_FEEDS = "https://www.secretflying.com/feed/,https://www.urlaubspiraten.de/feed"
DEFAULT_KEYWORDS = r"shanghai|schanghai|china|上海|PVG"


def load_watchlist(path):
    worker_url = os.getenv("WORKER_URL")
    access_key = os.getenv("ACCESS_KEY")
    if worker_url and access_key:
        print(f"loading watchlist from Worker ({worker_url})")
        return get_watchlist(worker_url, access_key)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_route_dates(client, route, dry_run):
    """Returns (dates_dict, ok). ok=False means every request for this
    route failed, so the caller must NOT write a snapshot (SPEC.md 10:
    a failed run must not write an empty snapshot or clobber good data)."""
    if dry_run:
        raw = fake_entries_for_route(route["id"], route["date_from"],
                                      route["date_to"])
        return aggregate_entries(raw, route["date_from"], route["date_to"]), True

    raw_entries = []
    any_success = False
    for year_month in month_range(route["date_from"], route["date_to"]):
        try:
            raw_entries.extend(client.get_prices_for_month(
                route["origin"], route["destination"], year_month))
            any_success = True
        except TravelpayoutsError as e:
            print(f"  {route['id']} {year_month}: fetch failed: {e}")
    if not any_success:
        return {}, False
    return aggregate_entries(raw_entries, route["date_from"], route["date_to"]), True


def format_price_alert(route, alerts):
    lines = [f"✈️ {route['origin']}→{route['destination']} "
             f"发现 {len(alerts)} 个新低价"]
    for a in sorted(alerts, key=lambda x: x["departure_at"]):
        lines.append(
            f"去 {a['departure_at']}  {a['price']:.0f}€  "
            f"{a['airline']}{a['flight_number'] or ''}  "
            f"转机{a['transfers']}次\n"
            f"https://www.aviasales.com{a['link']}")
    lines.append("(缓存价，下单前请在官网/"
                  "Google Flights确认)")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--dry-run", action="store_true",
                         help="use fake data, no network calls or token needed")
    parser.add_argument("--skip-rss", action="store_true",
                         help="skip the RSS deal-feed check")
    args = parser.parse_args()

    watchlist = load_watchlist(args.watchlist)
    today = date.today().isoformat()

    token = os.getenv("TP_TOKEN")
    if not args.dry_run and not token:
        print("TP_TOKEN missing and --dry-run not set; nothing to do.")
        return 1
    client = None if args.dry_run else TravelpayoutsClient(token)

    first_rss_run = not state_path(args.data_dir).exists()
    state = load_alert_state(args.data_dir)

    touched_routes = []
    for route in watchlist:
        if not route.get("enabled", True):
            print(f"{route['id']}: disabled, skipping")
            continue
        print(f"{route['id']}: fetching {route['date_from']}..{route['date_to']}"
              f"{' (dry-run)' if args.dry_run else ''}")
        dates_dict, ok = fetch_route_dates(client, route, args.dry_run)
        if not ok:
            print(f"{route['id']}: all requests failed, keeping prior data as-is")
            continue
        path = write_snapshot(args.data_dir, route["id"], today, dates_dict)
        print(f"{route['id']}: wrote {path} ({len(dates_dict)} date(s) with data)")
        touched_routes.append(route["id"])

        alerts = compute_route_alerts(state, route["id"], route.get("max_price"),
                                       dates_dict)
        if alerts:
            cheapest = min(alerts, key=lambda a: a["price"])
            notify(f"✈️ {route['origin']}⇄{route['destination']} "
                   f"{cheapest['price']:.0f}€",
                   format_price_alert(route, alerts),
                   click_url=f"https://www.aviasales.com{cheapest['link']}")

    regenerate_index(args.data_dir, watchlist)
    for route in watchlist:
        regenerate_history(args.data_dir, route["id"])

    if not args.skip_rss:
        feeds = [u.strip() for u in
                 os.getenv("RSS_FEEDS", DEFAULT_RSS_FEEDS).split(",") if u.strip()]
        keywords = re.compile(os.getenv("KEYWORDS", DEFAULT_KEYWORDS), re.I)
        for item in check_rss(state, feeds, keywords, first_rss_run):
            notify(f"\U0001f525 特价情报: {item['title'][:50]}",
                   f"{item['title']}\n{item['link']}", click_url=item["link"])

    save_alert_state(args.data_dir, state)
    print(f"done, {len(touched_routes)}/{len(watchlist)} route(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
