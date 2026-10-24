#!/usr/bin/env python3
"""Filter one hour of Hyperliquid node output down to a single coin and write parquet.

Reads decompressed node output (one JSON object per line, one line per block) from stdin:
    {"local_time": ..., "block_time": ..., "block_number": ..., "events": [ ... ]}

Works for the per-block datasets the node writes (order statuses, raw book diffs, fills,
twap statuses, misc events). Events are matched on their coin, wherever it lives:
    {"coin": ...}                      book diffs, twap statuses
    {"order": {"coin": ...}}           order statuses
    [user, {"coin": ...}]              fills

Order statuses are flattened into typed columns. Every other dataset keeps the matching
event as a JSON string next to the block columns, so nothing is lost before the format
has been checked.

Usage:
    zstd -dc 14.zst | python scripts/node_extract.py --coin xyz:SP500 \
        --dataset order_statuses --out out/14.parquet

Speed: lines that do not contain the coin string are skipped without JSON parsing. Only
blocks that mention the coin are parsed. A one-line JSON summary goes to stderr.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter

try:
    import orjson

    loads = orjson.loads

    def dumps(obj) -> str:
        return orjson.dumps(obj).decode()
except ImportError:  # pragma: no cover - slower fallback
    loads = json.loads

    def dumps(obj) -> str:
        return json.dumps(obj, separators=(",", ":"))

import pyarrow as pa
import pyarrow.parquet as pq

BATCH_ROWS = 50_000

ORDER_STATUS_SCHEMA = pa.schema(
    [
        ("block_number", pa.int64()),
        ("block_time", pa.string()),
        ("local_time", pa.string()),
        ("event_time", pa.string()),
        ("user", pa.string()),
        ("status", pa.string()),
        ("hash", pa.string()),
        ("builder", pa.string()),
        ("builder_fee", pa.float64()),
        ("coin", pa.string()),
        ("side", pa.string()),
        ("limit_px", pa.float64()),
        ("sz", pa.float64()),
        ("orig_sz", pa.float64()),
        ("oid", pa.int64()),
        ("order_ts_ms", pa.int64()),
        ("order_type", pa.string()),
        ("tif", pa.string()),
        ("reduce_only", pa.bool_()),
        ("is_trigger", pa.bool_()),
        ("trigger_condition", pa.string()),
        ("trigger_px", pa.float64()),
        ("is_position_tpsl", pa.bool_()),
        ("n_children", pa.int32()),
        ("cloid", pa.string()),
    ]
)

GENERIC_SCHEMA = pa.schema(
    [
        ("block_number", pa.int64()),
        ("block_time", pa.string()),
        ("local_time", pa.string()),
        ("user", pa.string()),
        ("coin", pa.string()),
        ("event_json", pa.string()),
    ]
)


def _f(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _i(x):
    if x is None or x == "":
        return None
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def event_coin_and_user(ev):
    """Return (coin, user, payload) for any known event shape."""
    if isinstance(ev, list) and len(ev) == 2 and isinstance(ev[1], dict):
        return ev[1].get("coin"), ev[0] if isinstance(ev[0], str) else None, ev[1]
    if isinstance(ev, dict):
        if "coin" in ev:
            return ev.get("coin"), ev.get("user"), ev
        order = ev.get("order")
        if isinstance(order, dict):
            return order.get("coin"), ev.get("user"), ev
    return None, None, ev


def order_status_row(block, ev):
    order = ev.get("order") or {}
    builder = ev.get("builder") or {}
    children = order.get("children")
    return {
        "block_number": _i(block.get("block_number")),
        "block_time": block.get("block_time"),
        "local_time": block.get("local_time"),
        "event_time": ev.get("time"),
        "user": ev.get("user"),
        "status": ev.get("status"),
        "hash": ev.get("hash"),
        "builder": builder.get("b") if isinstance(builder, dict) else None,
        "builder_fee": _f(builder.get("f")) if isinstance(builder, dict) else None,
        "coin": order.get("coin"),
        "side": order.get("side"),
        "limit_px": _f(order.get("limitPx")),
        "sz": _f(order.get("sz")),
        "orig_sz": _f(order.get("origSz")),
        "oid": _i(order.get("oid")),
        "order_ts_ms": _i(order.get("timestamp")),
        "order_type": order.get("orderType"),
        "tif": order.get("tif"),
        "reduce_only": order.get("reduceOnly"),
        "is_trigger": order.get("isTrigger"),
        "trigger_condition": order.get("triggerCondition"),
        "trigger_px": _f(order.get("triggerPx")),
        "is_position_tpsl": order.get("isPositionTpsl"),
        "n_children": len(children) if isinstance(children, list) else None,
        "cloid": order.get("cloid"),
    }


def generic_row(block, coin, user, ev):
    return {
        "block_number": _i(block.get("block_number")),
        "block_time": block.get("block_time"),
        "local_time": block.get("local_time"),
        "user": user,
        "coin": coin,
        "event_json": dumps(ev),
    }


EV_START = b'{"time":"'
EVENTS_KEY = b'"events":['
HDR_RE = {
    "block_number": re.compile(rb'"block_number":\s*(\d+)'),
    "block_time": re.compile(rb'"block_time":\s*"([^"]*)"'),
    "local_time": re.compile(rb'"local_time":\s*"([^"]*)"'),
}


def fast_events(line: bytes, needle: bytes):
    """Order-status fast path: parse only the events that mention the coin.

    In node order-status output every event object starts with {"time":" and no nested
    object uses a "time" key, so events can be cut at those boundaries without parsing the
    whole block. Returns (block_header_dict, [event, ...]) or None if the layout is not the
    expected one (the caller then parses the full block).
    """
    i = line.find(EVENTS_KEY)
    if i < 0:
        return None
    head = line[:i]
    block = {}
    for k, rx in HDR_RE.items():
        m = rx.search(head)
        block[k] = (int(m.group(1)) if k == "block_number" else m.group(1).decode()) if m else None
    body = line[i + len(EVENTS_KEY):]
    starts_done = set()
    events = []
    pos = body.find(needle)
    while pos >= 0:
        s = body.rfind(EV_START, 0, pos)
        if s < 0:
            return None
        if s not in starts_done:
            starts_done.add(s)
            e = body.find(EV_START, pos)
            seg = body[s:] if e < 0 else body[s:e]
            seg = seg.rstrip()
            if e < 0:
                if not seg.endswith(b"]}"):
                    return None
                seg = seg[:-2]
            else:
                seg = seg.rstrip(b",")
            try:
                events.append(loads(seg))
            except Exception:
                return None
            pos = body.find(needle, len(body) if e < 0 else e)
        else:
            pos = body.find(needle, pos + 1)
    return block, events


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coin", required=True, help="exact coin string, e.g. xyz:SP500")
    ap.add_argument("--dataset", default="generic", help="order_statuses flattens columns; anything else keeps JSON")
    ap.add_argument("--out", required=True, help="output parquet path (written atomically)")
    ap.add_argument("--label", default="", help="free text echoed in the stderr summary (e.g. date/hour)")
    ap.add_argument("--parse", choices=["auto", "fast", "full"], default="auto",
                    help="fast: parse only events that mention the coin (order statuses layout); "
                         "full: parse whole blocks; auto: fast for order_statuses, full otherwise")
    args = ap.parse_args()

    flat = args.dataset == "order_statuses"
    schema = ORDER_STATUS_SCHEMA if flat else GENERIC_SCHEMA
    needle = ('"' + args.coin + '"').encode()
    coin_tag = b'"coin":'

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".tmp"
    writer = pq.ParquetWriter(tmp, schema, compression="zstd")

    t0 = time.time()
    n_lines = n_bytes = n_hit_lines = n_coin_tags = n_rows = n_bad = 0
    first_block = last_block = None
    status_counts: Counter = Counter()
    batch: list[dict] = []

    def flush():
        nonlocal batch
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
            batch = []

    fast = args.parse == "fast" or (args.parse == "auto" and flat)
    n_fallback = 0

    for line in sys.stdin.buffer:
        n_lines += 1
        n_bytes += len(line)
        n_coin_tags += line.count(coin_tag)
        if needle not in line:
            continue
        n_hit_lines += 1

        events = None
        if fast:
            got = fast_events(line, needle)
            if got is None:
                n_fallback += 1
            else:
                block, events = got
        if events is None:
            try:
                block = loads(line)
            except Exception:
                n_bad += 1
                continue
            events = block.get("events") or []

        bn = _i(block.get("block_number"))
        if bn is not None:
            first_block = bn if first_block is None else min(first_block, bn)
            last_block = bn if last_block is None else max(last_block, bn)
        for ev in events:
            coin, user, payload = event_coin_and_user(ev)
            if coin != args.coin:
                continue
            if flat:
                row = order_status_row(block, payload)
                status_counts[row["status"]] += 1
            else:
                row = generic_row(block, coin, user, ev)
            batch.append(row)
            n_rows += 1
            if len(batch) >= BATCH_ROWS:
                flush()

    flush()
    writer.close()
    os.replace(tmp, args.out)

    secs = time.time() - t0
    summary = {
        "label": args.label,
        "dataset": args.dataset,
        "coin": args.coin,
        "lines": n_lines,
        "gb_in": round(n_bytes / 1e9, 3),
        "lines_with_coin": n_hit_lines,
        "events_all_coins_approx": n_coin_tags,
        "rows_out": n_rows,
        "share_of_events_pct": round(100 * n_rows / n_coin_tags, 3) if n_coin_tags else None,
        "bad_lines": n_bad,
        "parse": "fast" if fast else "full",
        "fast_fallbacks": n_fallback,
        "first_block": first_block,
        "last_block": last_block,
        "seconds": round(secs, 1),
        "mb_per_s": round(n_bytes / 1e6 / secs, 1) if secs else None,
    }
    if flat:
        summary["status_counts"] = dict(status_counts.most_common())
    print(json.dumps(summary), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
