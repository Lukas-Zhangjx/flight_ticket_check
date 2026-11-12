"""data/alert_state.json (SPEC.md 4.4): per route+departure-date historical
low, plus RSS guids already pushed (kept to the most recent 500)."""

import json
from pathlib import Path

MAX_SEEN_RSS = 500


def state_path(data_dir):
    return Path(data_dir) / "alert_state.json"


def load_alert_state(data_dir):
    path = state_path(data_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"best_price": {}, "seen_rss": []}


def save_alert_state(data_dir, state):
    state["seen_rss"] = state["seen_rss"][-MAX_SEEN_RSS:]
    path = state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                     encoding="utf-8")


def compute_route_alerts(state, route_id, max_price, dates_dict):
    """Price alert rule (SPEC.md section 0): below max_price AND a new low
    for that specific departure date. max_price=None means no cap - alert on
    every new low. Updates state['best_price'] in place."""
    best_for_route = state["best_price"].setdefault(route_id, {})
    alerts = []
    for dep, day in sorted(dates_dict.items()):
        info = day["min"]
        price = info["price"]
        prev_best = best_for_route.get(dep)
        under_cap = max_price is None or price <= max_price
        if under_cap and (prev_best is None or price < prev_best):
            alerts.append({
                "departure_at": dep,
                "price": price,
                "airline": info["airline"],
                "flight_number": info["flight_number"],
                "transfers": info["transfers"],
                "link": info["link"],
            })
        if prev_best is None or price < prev_best:
            best_for_route[dep] = price
    return alerts
