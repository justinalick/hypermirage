#!/usr/bin/env python3
"""Reconstruct best bid/ask per block from order lifecycles, then measure each order's distance
from the touch and how displayed depth splits by distance.

Input:  data/derived/lifecycle/<coin_slug>/<YYYYMMDD>.parquet   (from lifecycle.py)
Output: data/derived/bbo/<coin_slug>/<YYYYMMDD>.parquet          best bid/ask at every change
        data/derived/lifecycle_touch/<coin_slug>/<YYYYMMDD>.parquet  lifecycle + distance columns

Book replay: an order rests from the end of the block it opened in (b_open) until the block it
left (b_last). Orders still open at day end rest to the last block; orders placed before the day
rest from the first block. Never-displayed, rejected and filled-on-arrival orders never rest.
The best bid/ask recorded for block b is the state after all of block b's changes.

Distance at placement is measured against the touch at the END OF THE PREVIOUS BLOCK, so an
order does not count itself:
  bid: dist_bps = (best_bid - px) / mid * 1e4     ask: dist_bps = (px - best_ask) / mid * 1e4
  negative = improves the touch, 0 = joins it, positive = behind it.
pre_existing orders were placed before the window, so the touch at placement is unknown: their
dist_bps is NULL and they get their own bucket. (Their first in-window event is often the fill,
which would score them at the touch after resting far away for hours.)

Limits: orders resting since before the window that had NO event during the window are invisible
(they mostly sit far from the touch). Validate against an independent book with --check-book
(Reservoir 1-minute L2, fetched with scripts/fetch.sh xyz book:SP500 YYYY-MM-DD).

Usage:
  .venv/bin/python scripts/touch.py --day 20261020 [--coin xyz:SP500] [--check-book PATH]
"""
from __future__ import annotations

import argparse
import heapq
import os
import sys
import time

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

BUCKETS = """
  CASE
    WHEN class = 'pre_existing' THEN '0 placed before window'
    WHEN dist_bps IS NULL      THEN 'unknown'
    WHEN dist_bps < 0          THEN '1 improves touch'
    WHEN dist_bps = 0          THEN '2 at touch'
    WHEN dist_bps <= 1         THEN '3 within 1 bp'
    WHEN dist_bps <= 5         THEN '4 1-5 bps'
    WHEN dist_bps <= 25        THEN '5 5-25 bps'
    ELSE                            '6 over 25 bps'
  END
"""


def replay(con) -> pa.Table:
    """Sweep resting intervals block by block; return best bid/ask at every change."""
    ev = con.execute("""
        WITH r AS (
          SELECT row_number() OVER () - 1 AS idx, side, limit_px AS px,
                 CASE WHEN class = 'pre_existing' THEN day_b0 ELSE b_open END                AS s,
                 CASE WHEN class = 'still_open'   THEN day_b1 + 1 ELSE b_last END            AS e
          FROM lc
          WHERE class IN ('displayed_pulled','displayed_partial','filled','still_open','pre_existing')
            AND displayed_blocks > 0 AND limit_px IS NOT NULL
        )
        SELECT blk, kind, idx, side, px FROM (
          SELECT s AS blk, 0 AS kind, idx, side, px FROM r
          UNION ALL
          SELECT e AS blk, 1 AS kind, idx, side, px FROM r
        ) ORDER BY blk, kind
    """).fetchnumpy()
    blk, kind, idx = ev["blk"].astype(np.int64), ev["kind"], ev["idx"].astype(np.int64)
    side = ev["side"]
    px = ev["px"].astype(np.float64)
    n_orders = int(idx.max()) + 1 if len(idx) else 0
    alive = bytearray(n_orders)
    bids: list = []   # (-px, idx)
    asks: list = []   # (px, idx)
    out_b, out_bid, out_ask = [], [], []
    last_bid = last_ask = None

    def top(heap, sign):
        while heap and not alive[heap[0][1]]:
            heapq.heappop(heap)
        return (sign * heap[0][0]) if heap else None

    i, n = 0, len(blk)
    while i < n:
        b = blk[i]
        while i < n and blk[i] == b:
            k, j = idx[i], idx[i]
            if kind[i] == 0:
                alive[k] = 1
                if side[i] == "B":
                    heapq.heappush(bids, (-px[i], j))
                else:
                    heapq.heappush(asks, (px[i], j))
            else:
                alive[k] = 0
            i += 1
        bb, ba = top(bids, -1), top(asks, 1)
        if bb != last_bid or ba != last_ask:
            out_b.append(int(b)); out_bid.append(bb); out_ask.append(ba)
            last_bid, last_ask = bb, ba
    return pa.table({"block": pa.array(out_b, pa.int64()),
                     "best_bid": pa.array(out_bid, pa.float64()),
                     "best_ask": pa.array(out_ask, pa.float64())})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", required=True)
    ap.add_argument("--coin", default="xyz:SP500")
    ap.add_argument("--check-book", help="Reservoir 1m L2 parquet for the same day, to validate the replay")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    slug = args.coin.replace(":", "_")
    lc_path = os.path.join(root, "data/derived/lifecycle", slug, f"{args.day}.parquet")
    bbo_path = os.path.join(root, "data/derived/bbo", slug, f"{args.day}.parquet")
    out_path = os.path.join(root, "data/derived/lifecycle_touch", slug, f"{args.day}.parquet")
    for p in (bbo_path, out_path):
        os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.exists(lc_path):
        print(f"missing {lc_path}; run scripts/lifecycle.py --day {args.day} first", file=sys.stderr)
        return 1

    con = duckdb.connect()
    con.execute("CREATE TABLE lc AS SELECT * FROM read_parquet(?)", [lc_path]).fetchall()

    t0 = time.time()
    bbo = replay(con)
    pq.write_table(bbo, bbo_path, compression="zstd")
    con.register("bbo_arrow", bbo)
    con.execute("CREATE TABLE bbo AS SELECT * FROM bbo_arrow").fetchall()
    print(f"replayed book: {bbo.num_rows:,} best bid/ask changes in {time.time() - t0:.0f}s -> {bbo_path}")

    crossed = con.execute("SELECT count(*) FROM bbo WHERE best_bid >= best_ask").fetchall()[0][0]
    print(f"blocks with crossed/locked replayed book: {crossed:,} (should be ~0; if not, the replay is missing events)\n")

    con.execute(f"""
        CREATE TABLE lt AS
        SELECT l.*, b.best_bid, b.best_ask,
               (b.best_bid + b.best_ask) / 2 AS mid,
               CASE WHEN l.class = 'pre_existing' THEN NULL
                    WHEN l.side = 'B' THEN (b.best_bid - l.limit_px) / ((b.best_bid + b.best_ask) / 2) * 1e4
                    ELSE (l.limit_px - b.best_ask) / ((b.best_bid + b.best_ask) / 2) * 1e4 END AS dist_bps
        FROM lc l
        ASOF LEFT JOIN bbo b ON b.block < coalesce(l.b_open, l.b_first)
    """).fetchall()
    con.execute(f"CREATE TABLE lt2 AS SELECT *, {BUCKETS} AS dist_bucket FROM lt").fetchall()
    con.execute("COPY lt2 TO '" + out_path.replace("'", "''") + "' (FORMAT parquet, COMPRESSION zstd)").fetchall()
    day_blocks = con.execute("SELECT any_value(day_b1 - day_b0) FROM lt2").fetchall()[0][0]

    print("Time-weighted displayed depth by distance from the touch at placement:")
    print(con.sql(f"""
        SELECT dist_bucket,
               count(*) FILTER (WHERE displayed_blocks > 0)                               AS resting_orders,
               round(sum(notional_usd * displayed_blocks) / {day_blocks} / 1e6, 2)        AS avg_depth_musd,
               round(100.0 * sum(notional_usd * displayed_blocks)
                     / sum(sum(notional_usd * displayed_blocks)) OVER (), 1)              AS pct_depth,
               round(sum(filled_usd) / 1e6, 1)                                            AS filled_musd,
               median(displayed_blocks) FILTER (WHERE displayed_blocks > 0)              AS med_blocks_shown,
               round(median(notional_usd) FILTER (WHERE displayed_blocks > 0))            AS med_order_usd
        FROM lt2 WHERE class <> 'trigger' GROUP BY 1 ORDER BY 1
    """))

    if args.check_book:
        print("\nValidation against an independent book (Reservoir 1m L2, exact price match):")
        print(con.sql(f"""
            WITH r AS (
              SELECT block_number,
                     CAST(bids[1].px AS DOUBLE) AS r_bid, CAST(asks[1].px AS DOUBLE) AS r_ask
              FROM read_parquet('{args.check_book.replace("'", "''")}')
            ),
            j AS (SELECT r.*, b.best_bid, b.best_ask FROM r ASOF LEFT JOIN bbo b ON b.block <= r.block_number)
            SELECT count(*)                                                  AS snapshots,
                   round(100.0 * avg(CASE WHEN best_bid = r_bid THEN 1 ELSE 0 END), 1) AS pct_bid_match,
                   round(100.0 * avg(CASE WHEN best_ask = r_ask THEN 1 ELSE 0 END), 1) AS pct_ask_match,
                   round(median(abs(best_bid - r_bid)), 4)                   AS med_bid_diff,
                   round(median(abs(best_ask - r_ask)), 4)                   AS med_ask_diff
            FROM j
        """))
    return 0


if __name__ == "__main__":
    sys.exit(main())
