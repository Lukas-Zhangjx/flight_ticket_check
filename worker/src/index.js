import { aggregateEntries, monthRange } from "./aggregate.js";
import { checkInternational } from "./countries.js";
import { fetchPricesForMonth } from "./travelpayouts.js";

function corsHeaders(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "GET, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Access-Key",
  };
}

function json(data, status, env) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders(env) },
  });
}

function checkAccessKey(request, env) {
  const key = request.headers.get("X-Access-Key");
  return key && env.ACCESS_KEY && key === env.ACCESS_KEY;
}

async function handlePrices(request, env, ctx) {
  const url = new URL(request.url);
  const origin = url.searchParams.get("origin");
  const destination = url.searchParams.get("destination");
  const from = url.searchParams.get("from");
  const to = url.searchParams.get("to");
  if (!origin || !destination || !from || !to) {
    return json({ error: "origin, destination, from, to 都是必填参数" }, 400, env);
  }

  const intlError = await checkInternational(origin, destination);
  if (intlError) return json({ error: intlError }, 400, env);

  // Cache the expensive part (Travelpayouts + aggregation) at the edge for an
  // hour, keyed by the request URL - shared across every caller asking the
  // same question, access-key check above still gates who gets an answer.
  const cache = caches.default;
  const cacheKey = new Request(url.toString(), { method: "GET" });
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  let rawEntries = [];
  for (const yearMonth of monthRange(from, to)) {
    rawEntries = rawEntries.concat(
      await fetchPricesForMonth(env.TP_TOKEN, origin, destination, yearMonth)
    );
  }
  const dates = aggregateEntries(rawEntries, from, to);

  const body = {
    origin, destination,
    currency: "EUR",
    source: "travelpayouts-live",
    fetched_at: new Date().toISOString(),
    dates,
  };
  const response = json(body, 200, env);
  response.headers.set("Cache-Control", "public, max-age=3600");
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

async function handleGetWatchlist(env) {
  const raw = await env.WATCHLIST_KV.get("watchlist");
  return json(raw ? JSON.parse(raw) : [], 200, env);
}

async function handlePutWatchlist(request, env) {
  let routes;
  try {
    routes = await request.json();
  } catch {
    return json({ error: "请求体不是合法 JSON" }, 400, env);
  }
  if (!Array.isArray(routes)) return json({ error: "请求体必须是航线数组" }, 400, env);

  for (const route of routes) {
    if (!route.id || !route.origin || !route.destination
        || !route.date_from || !route.date_to) {
      return json({ error: `航线记录缺字段: ${JSON.stringify(route)}` }, 400, env);
    }
    const intlError = await checkInternational(route.origin, route.destination);
    if (intlError) return json({ error: `${route.id}: ${intlError}` }, 400, env);
  }

  await env.WATCHLIST_KV.put("watchlist", JSON.stringify(routes));
  return json({ ok: true, count: routes.length }, 200, env);
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(env) });
    }

    const url = new URL(request.url);
    if (!checkAccessKey(request, env)) {
      return json({ error: "缺少或错误的 X-Access-Key" }, 401, env);
    }

    try {
      if (url.pathname === "/prices" && request.method === "GET") {
        return await handlePrices(request, env, ctx);
      }
      if (url.pathname === "/watchlist" && request.method === "GET") {
        return await handleGetWatchlist(env);
      }
      if (url.pathname === "/watchlist" && request.method === "PUT") {
        return await handlePutWatchlist(request, env);
      }
      return json({ error: "not found" }, 404, env);
    } catch (err) {
      return json({ error: String(err && err.message || err) }, 500, env);
    }
  },
};
