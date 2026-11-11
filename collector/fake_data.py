"""Deterministic fake data for --dry-run, so the pipeline can be exercised
without a TP_TOKEN or any network access. Seeded by route+date so re-running
dry-run on the same day is stable; some dates are intentionally skipped to
exercise the "gap, no interpolation" behaviour from SPEC.md 4.2.
"""

import random
from datetime import date, timedelta

AIRLINES = ["MU", "CA", "LH", "AF", "KL"]


def _daterange(date_from, date_to):
    start = date(*map(int, date_from.split("-")))
    end = date(*map(int, date_to.split("-")))
    d = start
    while d <= end:
        yield d.isoformat()
        d += timedelta(days=1)


def fake_entries_for_route(route_id, date_from, date_to):
    """Returns raw entries shaped like the real API's 'data' list."""
    entries = []
    for dep in _daterange(date_from, date_to):
        rng = random.Random(f"{route_id}:{dep}")
        if rng.random() < 0.15:
            continue  # simulate a day with no cached fare at all
        base = rng.randint(380, 900)
        n_airlines = rng.randint(1, len(AIRLINES))
        for airline in rng.sample(AIRLINES, n_airlines):
            entries.append({
                "price": base + rng.randint(-30, 120),
                "airline": airline,
                "flight_number": str(rng.randint(100, 999)),
                "departure_at": dep,
                "transfers": rng.choice([0, 0, 1]),
                "duration": rng.randint(600, 1400),
                "link": f"/search/{route_id}{dep.replace('-', '')}1",
            })
    return entries
