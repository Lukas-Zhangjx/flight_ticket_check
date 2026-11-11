// Mirrors collector/aggregate.py's month_range/aggregate_entries so the
// Worker's live /prices response has the exact same `dates` shape as a
// committed snapshot (SPEC.md 4.2) - the frontend doesn't need to care
// which one it got.

export function monthRange(dateFrom, dateTo) {
  const [y0, m0] = dateFrom.split("-").map(Number);
  const [y1, m1] = dateTo.split("-").map(Number);
  const months = [];
  let y = y0, m = m0;
  while (y < y1 || (y === y1 && m <= m1)) {
    months.push(`${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}`);
    m += 1;
    if (m > 12) { m = 1; y += 1; }
  }
  return months;
}

export function aggregateEntries(rawEntries, dateFrom, dateTo) {
  const byDate = {};
  for (const e of rawEntries) {
    const dep = (e.departure_at || "").slice(0, 10);
    const airline = e.airline;
    const price = e.price;
    if (!dep || airline == null || price == null) continue;
    if (!(dateFrom <= dep && dep <= dateTo)) continue;
    const day = byDate[dep] || (byDate[dep] = {});
    const existing = day[airline];
    if (!existing || price < existing.price) {
      day[airline] = {
        price,
        flight_number: e.flight_number,
        transfers: e.transfers,
        link: e.link,
      };
    }
  }

  const dates = {};
  for (const [dep, byAirlineFull] of Object.entries(byDate)) {
    let bestAirline = null, best = null;
    for (const [airline, info] of Object.entries(byAirlineFull)) {
      if (!best || info.price < best.price) { best = info; bestAirline = airline; }
    }
    dates[dep] = {
      min: {
        price: best.price,
        airline: bestAirline,
        flight_number: best.flight_number,
        transfers: best.transfers,
        link: best.link,
      },
      by_airline: Object.fromEntries(
        Object.entries(byAirlineFull).map(([airline, v]) => [
          airline,
          { price: v.price, flight_number: v.flight_number, transfers: v.transfers },
        ])
      ),
    };
  }
  return dates;
}
