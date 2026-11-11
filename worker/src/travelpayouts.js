// Same endpoint as collector/tp_client.py (SPEC.md 2.1). No per-call
// throttle here: unlike the collector's daily bulk job, this runs once per
// incoming request and relies on the Worker's own edge cache (see index.js)
// to keep real request volume to Travelpayouts low.
const API_BASE = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates";
const PAGE_SIZE = 1000;
const MAX_PAGES = 3;

export async function fetchPricesForMonth(token, origin, destination, yearMonth) {
  const entries = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const url = new URL(API_BASE);
    url.searchParams.set("origin", origin);
    url.searchParams.set("destination", destination);
    url.searchParams.set("departure_at", yearMonth);
    url.searchParams.set("one_way", "true");
    url.searchParams.set("unique", "false");
    url.searchParams.set("sorting", "price");
    url.searchParams.set("currency", "eur");
    url.searchParams.set("limit", String(PAGE_SIZE));
    url.searchParams.set("page", String(page));
    url.searchParams.set("token", token);

    const resp = await fetch(url.toString(), {
      headers: { "User-Agent": "flight-ticket-check-worker/1.0" },
    });
    if (!resp.ok) {
      throw new Error(`travelpayouts ${resp.status} for ${yearMonth} page ${page}`);
    }
    const json = await resp.json();
    const pageData = json.data || [];
    entries.push(...pageData);
    if (pageData.length < PAGE_SIZE) break;
  }
  return entries;
}
