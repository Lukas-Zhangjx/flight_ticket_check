"""Turn raw Travelpayouts entries into the snapshot/index/history files
described in SPEC.md 4.2-4.3.
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path


def month_range(date_from, date_to):
    """List of 'YYYY-MM' strings covering [date_from, date_to] (inclusive)."""
    start = date(*map(int, date_from.split("-")))
    end = date(*map(int, date_to.split("-")))
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def aggregate_entries(raw_entries, date_from, date_to):
    """Keep only entries within [date_from, date_to]; one lowest price per
    (departure date, airline). Returns the 'dates' dict from SPEC.md 4.2."""
    by_date = {}
    for e in raw_entries:
        dep = (e.get("departure_at") or "")[:10]
        airline = e.get("airline")
        price = e.get("price")
        if not dep or airline is None or price is None:
            continue
        if not (date_from <= dep <= date_to):
            continue
        day = by_date.setdefault(dep, {})
        existing = day.get(airline)
        if existing is None or price < existing["price"]:
            day[airline] = {
                "price": price,
                "flight_number": e.get("flight_number"),
                "transfers": e.get("transfers"),
                "link": e.get("link"),
            }

    dates = {}
    for dep, by_airline_full in by_date.items():
        best_airline, best = min(by_airline_full.items(),
                                  key=lambda kv: kv[1]["price"])
        dates[dep] = {
            "min": {
                "price": best["price"],
                "airline": best_airline,
                "flight_number": best["flight_number"],
                "transfers": best["transfers"],
                "link": best["link"],
            },
            "by_airline": {
                airline: {
                    "price": v["price"],
                    "flight_number": v["flight_number"],
                    "transfers": v["transfers"],
                }
                for airline, v in by_airline_full.items()
            },
        }
    return dates


def snapshot_path(data_dir, route_id, query_date):
    return Path(data_dir) / "snapshots" / route_id / f"{query_date}.json"


def write_snapshot(data_dir, route_id, query_date, dates_dict, currency="EUR"):
    path = snapshot_path(data_dir, route_id, query_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "route_id": route_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "currency": currency,
        "source": "travelpayouts-cache",
        "dates": dates_dict,
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return path


def list_snapshot_dates(data_dir, route_id):
    route_dir = Path(data_dir) / "snapshots" / route_id
    if not route_dir.exists():
        return []
    return sorted(p.stem for p in route_dir.glob("*.json"))


def regenerate_index(data_dir, watchlist):
    """data/index.json: every watched route and which query dates have a
    snapshot on disk. Derived purely from what's already written, so a
    skipped/failed fetch this run never corrupts it."""
    routes = []
    for route in watchlist:
        routes.append({
            "id": route["id"],
            "origin": route["origin"],
            "destination": route["destination"],
            "date_from": route["date_from"],
            "date_to": route["date_to"],
            "max_price": route.get("max_price"),
            "enabled": route.get("enabled", True),
            "snapshot_dates": list_snapshot_dates(data_dir, route["id"]),
        })
    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "routes": routes,
    }
    path = Path(data_dir) / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return path


def regenerate_history(data_dir, route_id):
    """data/history/<route_id>.json: departure date -> query date -> airline
    -> price. Rebuilt from every snapshot file on disk for this route."""
    departures = {}
    for query_date in list_snapshot_dates(data_dir, route_id):
        snap_path = snapshot_path(data_dir, route_id, query_date)
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        for dep, day in snapshot.get("dates", {}).items():
            by_query = departures.setdefault(dep, {})
            by_query[query_date] = {
                airline: info["price"]
                for airline, info in day.get("by_airline", {}).items()
            }

    history = {
        "route_id": route_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "departures": departures,
    }
    path = Path(data_dir) / "history" / f"{route_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return path
