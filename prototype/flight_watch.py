#!/usr/bin/env python3
"""
MUC <-> Shanghai cheap-fare watcher (legal, free).

Data sources (all official / public):
  1. Travelpayouts (Aviasales) Data API  - official, free with a partner token
  2. Public RSS feeds of deal sites       - published for subscription

Notifications (any combination, set only the ones you use):
  WeChat via PushPlus or Server酱, and/or Telegram.
Only Python standard library is used.

Env vars (set as GitHub Actions secrets):
  TP_TOKEN        Travelpayouts API token
  NTFY_TOPIC      ntfy topic name - use a long random string, topics are public
  NTFY_SERVER     optional, default https://ntfy.sh
  PUSHPLUS_TOKEN  PushPlus token        (WeChat)
  SERVERCHAN_KEY  Server酱 SendKey       (WeChat)
  TG_TOKEN        Telegram bot token    (optional)
  TG_CHAT_ID      Telegram chat id      (optional)
Optional:
  ORIGIN        default MUC
  DEST          default SHA   (city code: covers PVG + SHA)
  MONTHS        departure/return month pairs, e.g. "2027-01:2027-02,2027-09:2027-10"
  MAX_PRICE     alert threshold in EUR, default 650
  RSS_FEEDS     comma-separated RSS URLs
  KEYWORDS      regex for RSS filtering
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(__file__).with_name("state.json")

ORIGIN = os.getenv("ORIGIN", "MUC")
DEST = os.getenv("DEST", "SHA")
MONTHS = os.getenv("MONTHS", "2027-01:2027-02")
MAX_PRICE = float(os.getenv("MAX_PRICE", "650"))
RSS_FEEDS = [u.strip() for u in os.getenv(
    "RSS_FEEDS",
    "https://www.secretflying.com/feed/,https://www.urlaubspiraten.de/feed",
).split(",") if u.strip()]
KEYWORDS = re.compile(os.getenv(
    "KEYWORDS", r"shanghai|schanghai|china|上海|PVG"), re.I)

UA = {"User-Agent": "personal-flight-watch/1.0"}


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"best": {}, "seen_rss": [], "history": []}


def save_state(state):
    state["seen_rss"] = state["seen_rss"][-500:]
    state["history"] = state["history"][-1000:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def _post(url, data, json_body=False):
    if json_body:
        body = json.dumps(data).encode()
        headers = {**UA, "Content-Type": "application/json"}
    else:
        body = urllib.parse.urlencode(data).encode()
        headers = UA
    req = urllib.request.Request(url, body, headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def notify(text):
    """Send to every channel that is configured; WeChat first."""
    title = text.splitlines()[0][:60]
    sent = False

    # ntfy  (https://ntfy.sh) - JSON publish so Chinese/emoji titles work
    if os.getenv("NTFY_TOPIC"):
        try:
            server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
            msg = {"topic": os.getenv("NTFY_TOPIC"),
                   "title": title, "message": text, "tags": ["airplane"]}
            m = re.search(r"https?://\S+", text)
            if m:
                msg["click"] = m.group(0)     # tap notification -> open link
            print("ntfy:", _post(server, msg, json_body=True)[:120])
            sent = True
        except Exception as e:
            print("ntfy failed:", e)

    # WeChat via PushPlus  (https://www.pushplus.plus)
    if os.getenv("PUSHPLUS_TOKEN"):
        try:
            print("pushplus:", _post("https://www.pushplus.plus/send", {
                "token": os.getenv("PUSHPLUS_TOKEN"),
                "title": title, "content": text, "template": "txt",
            }, json_body=True))
            sent = True
        except Exception as e:
            print("pushplus failed:", e)

    # WeChat via ServerChan / Server酱  (https://sct.ftqq.com)
    if os.getenv("SERVERCHAN_KEY"):
        try:
            key = os.getenv("SERVERCHAN_KEY")
            print("serverchan:", _post(f"https://sctapi.ftqq.com/{key}.send",
                                       {"title": title, "desp": text}))
            sent = True
        except Exception as e:
            print("serverchan failed:", e)

    # Telegram (optional)
    token, chat = os.getenv("TG_TOKEN"), os.getenv("TG_CHAT_ID")
    if token and chat:
        try:
            _post(f"https://api.telegram.org/bot{token}/sendMessage", {
                "chat_id": chat, "text": text,
                "disable_web_page_preview": "true",
            })
            sent = True
        except Exception as e:
            print("telegram failed:", e)

    if not sent:
        print("[no notification channel configured]\n" + text)


# ---------- 1. Travelpayouts ----------

def check_fares(state):
    token = os.getenv("TP_TOKEN")
    if not token:
        print("TP_TOKEN missing, skipping fares")
        return []
    alerts = []
    for pair in MONTHS.split(","):
        dep, ret = pair.strip().split(":")
        params = {
            "origin": ORIGIN, "destination": DEST,
            "departure_at": dep, "return_at": ret,
            "one_way": "false", "currency": "eur",
            "sorting": "price", "unique": "false",
            "limit": "10", "token": token,
        }
        url = ("https://api.travelpayouts.com/aviasales/v3/prices_for_dates?"
               + urllib.parse.urlencode(params))
        try:
            data = json.loads(http_get(url)).get("data", [])
        except Exception as e:
            print(f"fare request failed for {pair}: {e}")
            continue
        if not data:
            print(f"{pair}: no cached data")
            continue

        cheapest = min(data, key=lambda x: x["price"])
        price = cheapest["price"]
        state["history"].append({
            "t": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "months": pair, "price": price,
            "airline": cheapest.get("airline"),
        })
        prev_best = state["best"].get(pair)
        print(f"{pair}: cheapest {price} EUR (prev best {prev_best})")

        if price <= MAX_PRICE and (prev_best is None or price < prev_best):
            link = cheapest.get("link", "")
            alerts.append(
                f"✈️ {ORIGIN}⇄{DEST} 往返 {price:.0f} €\n"
                f"去 {cheapest.get('departure_at', '')[:10]} / "
                f"回 {cheapest.get('return_at', '')[:10]}\n"
                f"航司 {cheapest.get('airline')}  转机 {cheapest.get('transfers')} 次\n"
                f"https://www.aviasales.com{link}\n"
                f"(缓存价，下单前去 Google Flights / 官网确认)"
            )
        if prev_best is None or price < prev_best:
            state["best"][pair] = price
    return alerts


# ---------- 2. RSS deal feeds ----------

def check_rss(state):
    alerts = []
    seen = set(state["seen_rss"])
    for feed in RSS_FEEDS:
        try:
            root = ET.fromstring(http_get(feed))
        except Exception as e:
            print(f"rss failed {feed}: {e}")
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            key = item.findtext("guid") or link or title
            if key in seen:
                continue
            seen.add(key)
            state["seen_rss"].append(key)
            if KEYWORDS.search(title + " " + (item.findtext("description") or "")):
                alerts.append(f"🔥 特价情报: {title}\n{link}")
    return alerts


def main():
    first_run = not STATE_FILE.exists()
    state = load_state()
    alerts = check_fares(state)
    rss_alerts = check_rss(state)
    if not first_run:          # first run only fills "seen" list, no spam
        alerts += rss_alerts
    save_state(state)
    for a in alerts:
        notify(a)
    print(f"done, {len(alerts)} alert(s)")


if __name__ == "__main__":
    sys.exit(main())
