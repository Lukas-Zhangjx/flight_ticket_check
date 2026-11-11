// SPEC.md 2.3: look up each code's country via Travelpayouts' public static
// data, different country => international. cities.json covers the city
// codes this project mostly deals with (e.g. SHA); airports.json is the
// fallback for airport-only codes. Both are public, no token needed.
// Cached in the edge Cache API for a day since this is large and near-static.

const CITIES_URL = "https://api.travelpayouts.com/data/en/cities.json";
const AIRPORTS_URL = "https://api.travelpayouts.com/data/en/airports.json";
const CACHE_TTL_SECONDS = 86400;

async function fetchJsonCached(url) {
  const cache = caches.default;
  const cacheKey = new Request(url, { method: "GET" });
  let resp = await cache.match(cacheKey);
  if (!resp) {
    resp = await fetch(url, { headers: { "User-Agent": "flight-ticket-check-worker/1.0" } });
    if (!resp.ok) throw new Error(`failed to fetch ${url}: ${resp.status}`);
    resp = new Response(resp.body, resp);
    resp.headers.set("Cache-Control", `public, max-age=${CACHE_TTL_SECONDS}`);
    await cache.put(cacheKey, resp.clone());
  }
  return resp.json();
}

async function buildCodeToCountryMap(url) {
  const rows = await fetchJsonCached(url);
  const map = new Map();
  for (const row of rows) {
    if (row.code && row.country_code) map.set(row.code, row.country_code);
  }
  return map;
}

let citiesMapPromise = null;
let airportsMapPromise = null;

export async function countryCodeFor(code) {
  if (!citiesMapPromise) citiesMapPromise = buildCodeToCountryMap(CITIES_URL);
  const cities = await citiesMapPromise;
  if (cities.has(code)) return cities.get(code);

  if (!airportsMapPromise) airportsMapPromise = buildCodeToCountryMap(AIRPORTS_URL);
  const airports = await airportsMapPromise;
  return airports.get(code) || null;
}

// Returns null if international (ok), or a user-facing error string if not.
export async function checkInternational(origin, destination) {
  const [originCountry, destCountry] = await Promise.all([
    countryCodeFor(origin),
    countryCodeFor(destination),
  ]);
  if (!originCountry) return `无法识别的出发地代码: ${origin}`;
  if (!destCountry) return `无法识别的目的地代码: ${destination}`;
  if (originCountry === destCountry) return "仅支持国际航线（出发地和目的地在同一个国家）";
  return null;
}
