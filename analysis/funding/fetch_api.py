"""Fetch xyz:SP500 hourly funding history and 1h candles from the Hyperliquid public info API.

Writes sp500_funding_api.json and candles.json next to this file.
Run: python3 analysis/funding/fetch_api.py
"""
import json
import time
import urllib.request
from pathlib import Path

HERE = Path("data/derived/funding"); HERE.mkdir(parents=True, exist_ok=True)
URL = "https://api.hyperliquid.xyz/info"
COIN = "xyz:SP500"
START_MS = 1773000000000  # before the first available funding print


def post(body):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20))


def fetch_funding():
    out, t = [], START_MS
    while True:
        rows = post({"type": "fundingHistory", "coin": COIN, "startTime": t})
        if not rows:
            break
        out += rows
        nxt = rows[-1]["time"] + 1
        if nxt <= t or len(rows) < 2:
            break
        t = nxt
        time.sleep(0.3)
    return out


def fetch_candles():
    # the API serves only the most recent ~5000 bars; page boundaries can repeat a bar (deduplicated downstream)
    out, t, end = [], START_MS, int(time.time() * 1000)
    while t < end:
        rows = post({"type": "candleSnapshot", "req": {"coin": COIN, "interval": "1h", "startTime": t, "endTime": end}})
        if not rows:
            break
        out += rows
        nxt = rows[-1]["t"] + 1
        if nxt <= t:
            break
        t = nxt
        time.sleep(0.3)
    return out


if __name__ == "__main__":
    f = fetch_funding()
    json.dump(f, open(HERE / "sp500_funding_api.json", "w"))
    c = fetch_candles()
    json.dump(c, open(HERE / "candles.json", "w"))
    print(f"funding rows {len(f)}, candle rows {len(c)}")
