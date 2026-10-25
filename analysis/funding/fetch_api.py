"""Fetch xyz:SP500 hourly funding history and 1h candles from the Hyperliquid public info API.

Writes sp500_funding_api.json and candles.json to data/derived/funding. The candle endpoint serves only
the most recent ~5000 bars, so each pull is merged into the saved files instead of replacing them: older
hours that have rolled out of the API stay, and an hour present in both takes the new copy (the later
copy of a bar is the completed one). Requests go through analysis/hl_api.py (throttled per IP).
Run: python3 analysis/funding/fetch_api.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "analysis")
from hl_api import post

HERE = Path("data/derived/funding"); HERE.mkdir(parents=True, exist_ok=True)
COIN = "xyz:SP500"
START_MS = 1773000000000  # before the first available funding print


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
    return out


def fetch_candles():
    # page boundaries can repeat a bar (deduplicated in merge, later copy kept)
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
    return out


def merge(path, new, key):
    """Union of the saved rows and a new pull, one row per hour (key: ms field floored to the hour)."""
    old = json.load(open(path)) if path.exists() else []
    rows = {}
    for r in old + new:          # new rows last, so they win
        rows[r[key] // 3_600_000] = r
    out = [rows[k] for k in sorted(rows)]
    tmp = path.with_suffix(".tmp")
    json.dump(out, open(tmp, "w")); tmp.replace(path)
    return len(old), len(new), len(out)


if __name__ == "__main__":
    a = merge(HERE / "sp500_funding_api.json", fetch_funding(), "time")
    b = merge(HERE / "candles.json", fetch_candles(), "t")
    print(f"funding rows saved/pulled/merged {a}, candle rows {b}")
