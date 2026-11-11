#!/usr/bin/env python3
"""Phase 1 collector (SPEC.md section 9.1): reads a local watchlist.json,
queries Travelpayouts per enabled route, writes a dated snapshot per route,
then regenerates data/index.json and data/history/<route_id>.json from
whatever snapshots exist on disk.

Only Python standard library is used.

Usage:
  python3 collect.py --dry-run                 # fake data, no network/token
  TP_TOKEN=xxx python3 collect.py               # real Travelpayouts query

Env vars:
  TP_TOKEN   Travelpayouts API token (required unless --dry-run)
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from aggregate import (aggregate_entries, month_range, regenerate_history,
                        regenerate_index, write_snapshot)
from fake_data import fake_entries_for_route
from tp_client import TravelpayoutsClient, TravelpayoutsError

DEFAULT_WATCHLIST = Path(__file__).with_name("watchlist.json")
DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"


def load_watchlist(path):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--dry-run", action="store_true",
                         help="use fake data, no network calls or token needed")
    args = parser.parse_args()

    watchlist = load_watchlist(args.watchlist)
    today = date.today().isoformat()

    token = os.getenv("TP_TOKEN")
    if not args.dry_run and not token:
        print("TP_TOKEN missing and --dry-run not set; nothing to do.")
        return 1
    client = None if args.dry_run else TravelpayoutsClient(token)

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

    regenerate_index(args.data_dir, watchlist)
    for route in watchlist:
        regenerate_history(args.data_dir, route["id"])
    print(f"done, {len(touched_routes)}/{len(watchlist)} route(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
