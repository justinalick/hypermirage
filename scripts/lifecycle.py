#!/usr/bin/env python3
"""Build one row per order from extracted order-status events, and classify it.

Input:  data/l4/order_statuses/<coin_slug>/<YYYYMMDD>/*.parquet  (from node_extract)
Output: data/derived/lifecycle/<coin_slug>/<YYYYMMDD>.parquet
        plus a printed summary by class.

Classes (per order id):
  trigger             trigger / TP-SL orders; their limit price and size can be placeholders, so
                      they are excluded from notional and depth
  rejected            never rested: first and last event is a *Rejected status
  never_displayed     opened and cancelled in the same block, so it never appeared in any book
  displayed_pulled    rested >= 1 block, cancelled with nothing filled
  displayed_partial   rested >= 1 block, cancelled after a partial fill (filled_sz > 0)
  filled              ended fully filled (including orders that filled on arrival, which have
                      no "open" event because they never rested)
  still_open          no terminal event in the window (right-censored)
  pre_existing        no "open" event in the window and placed before the day started
  other               anything else; inspect before using

Cancel statuses: any status ending in "Canceled", plus "scheduledCancel" (orders removed when the
account's scheduled cancel-all fires; see the exchange API's scheduleCancel action).

Depth: displayed_blocks = blocks the order rested in the book (0 if never displayed; censored at
the day's last block for still_open; from the day's first block for pre_existing). Time-weighted
average displayed depth = sum(notional * displayed_blocks) / blocks in the day. This measures
depth that existed, unlike "placed notional", which counts every re-quote again. Size is taken at
placement (orig_sz), so depth is overstated slightly for orders that partly filled while resting.

Sizes: every event carries the order's remaining size (sz) and original size (orig_sz), so
filled_sz = orig_sz - remaining size at the last event. Exception: a reduce-only order's remaining
size also shrinks when the position shrinks, with no fill, so that difference is not a fill. For
reduce-only orders filled_sz comes from Reservoir fills for the same day (--fills; default
data/raw/<dex>/fills/<YYYY-MM-DD>.parquet). Those fills cover the day only, so fills of a
pre_existing reduce-only order before the day are not counted. filled_src records the source:
'status', 'fills', or 'status_unverified' (reduce-only with no fills file: an upper bound).

Usage:
  .venv/bin/python scripts/lifecycle.py --day 20261020 [--coin xyz:SP500] [--in-glob GLOB] [--fills PATH]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import duckdb

SQL = """
WITH ev AS (
  SELECT *,
         CASE WHEN status = 'open' THEN 0 ELSE 1 END AS rank_in_block
  FROM read_parquet($glob)
  WHERE coin = $coin
),
bounds AS (
  SELECT min(block_number) AS day_b0, max(block_number) AS day_b1,
         (max(epoch_ms(CAST(substr(event_time,1,23) AS TIMESTAMP)))
          - min(epoch_ms(CAST(substr(event_time,1,23) AS TIMESTAMP))))
         / greatest(max(block_number) - min(block_number), 1) AS ms_per_block
  FROM ev
),
agg AS (
  SELECT
    oid,
    any_value("user")                                   AS "user",
    any_value(side)                                     AS side,
    any_value(tif)                                      AS tif,
    any_value(order_type)                               AS order_type,
    bool_or(reduce_only)                                AS reduce_only,
    bool_or(is_trigger)                                 AS is_trigger,
    max(orig_sz)                                        AS orig_sz,
    arg_min(limit_px, (block_number, rank_in_block))    AS limit_px,
    min(order_ts_ms)                                    AS placed_ms,
    min(block_number) FILTER (WHERE status = 'open')    AS b_open,
    min(block_number)                                   AS b_first,
    max(block_number)                                   AS b_last,
    arg_min(status, (block_number, rank_in_block))      AS first_status,
    arg_max(status, (block_number, rank_in_block))      AS last_status,
    arg_max(sz,     (block_number, rank_in_block))      AS last_sz,
    arg_max(event_time, (block_number, rank_in_block))  AS last_event_time,
    count(*)                                            AS n_events
  FROM ev
  GROUP BY oid
),
sized AS (
SELECT
  agg.*,
  CASE WHEN reduce_only AND $have_fills THEN coalesce(fo.fill_sz, 0)
       ELSE greatest(orig_sz - coalesce(last_sz, 0), 0) END   AS filled_sz,
  CASE WHEN NOT reduce_only THEN 'status'
       WHEN $have_fills     THEN 'fills'
       ELSE 'status_unverified' END                           AS filled_src,
  last_status LIKE '%anceled' OR last_status = 'scheduledCancel' AS is_cancel
FROM agg LEFT JOIN fo ON fo.order_id = agg.oid
),
classed AS (
SELECT
  sized.*, bounds.day_b0, bounds.day_b1, bounds.ms_per_block,
  CASE WHEN b_open IS NOT NULL THEN b_last - b_open END AS blocks_rested,
  CASE
    WHEN is_trigger OR first_status = 'triggered'                                  THEN 'trigger'
    WHEN first_status LIKE '%Rejected' AND last_status LIKE '%Rejected'           THEN 'rejected'
    WHEN b_open IS NULL AND placed_ms < $day_start_ms                              THEN 'pre_existing'
    WHEN last_status = 'filled'                                                    THEN 'filled'
    WHEN last_status = 'open'                                                      THEN 'still_open'
    WHEN is_cancel AND b_open = b_last                                             THEN 'never_displayed'
    WHEN is_cancel AND filled_sz > 1e-12                                           THEN 'displayed_partial'
    WHEN is_cancel                                                                 THEN 'displayed_pulled'
    ELSE 'other'
  END AS class
FROM sized CROSS JOIN bounds
)
SELECT
  *,
  CASE WHEN class = 'trigger' THEN NULL ELSE limit_px * orig_sz END       AS notional_usd,
  CASE WHEN class = 'trigger' THEN NULL ELSE limit_px * filled_sz END     AS filled_usd,
  CASE
    WHEN class IN ('displayed_pulled', 'displayed_partial')                THEN b_last - b_open
    WHEN class = 'filled' AND b_open IS NOT NULL                           THEN b_last - b_open
    WHEN class = 'still_open'                                              THEN day_b1 - b_open
    WHEN class = 'pre_existing'                                            THEN b_last - day_b0
    ELSE 0
  END                                                                      AS displayed_blocks
FROM classed
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", required=True, help="YYYYMMDD")
    ap.add_argument("--coin", default="xyz:SP500")
    ap.add_argument("--in-glob", help="override input glob (default: data/l4/order_statuses/<slug>/<day>/*.parquet)")
    ap.add_argument("--out", help="override output path")
    ap.add_argument("--fills", help="Reservoir fills parquet for the day, for reduce-only filled size "
                                    "(default: data/raw/<dex>/fills/<YYYY-MM-DD>.parquet)")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    slug = args.coin.replace(":", "_")
    glob = args.in_glob or os.path.join(root, "data/l4/order_statuses", slug, args.day, "*.parquet")
    out = args.out or os.path.join(root, "data/derived/lifecycle", slug, f"{args.day}.parquet")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    day = datetime.strptime(args.day, "%Y%m%d").replace(tzinfo=timezone.utc)
    day_start_ms = int(day.timestamp() * 1000)
    fills = args.fills
    if fills is None and ":" in args.coin:
        fills = os.path.join(root, "data/raw", args.coin.split(":")[0], "fills", f"{day:%Y-%m-%d}.parquet")
    have_fills = bool(fills) and os.path.exists(fills)

    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'")   # spills to disk beyond this; keeps a day within a shared 16 GB machine
    if have_fills:
        con.execute("""CREATE TABLE fo AS SELECT order_id, sum(CAST(size AS DOUBLE)) AS fill_sz
                       FROM read_parquet(?) WHERE coin = ? GROUP BY order_id""", [fills, args.coin]).fetchall()
    else:
        con.execute("CREATE TABLE fo (order_id UBIGINT, fill_sz DOUBLE)").fetchall()
        print(f"WARNING: no fills file ({fills or 'pass --fills'}); reduce-only filled sizes come from "
              "remaining-size changes and overstate fills (filled_src = 'status_unverified')\n", file=sys.stderr)
    con.execute(f"CREATE TABLE lc AS {SQL}",
                {"glob": glob, "coin": args.coin, "day_start_ms": day_start_ms,
                 "have_fills": have_fills}).fetchall()
    con.execute("COPY lc TO '" + out.replace("'", "''") + "' (FORMAT parquet, COMPRESSION zstd)").fetchall()

    n = con.execute("SELECT count(*) FROM lc").fetchall()[0][0]
    print(f"{args.coin} {args.day}: {n:,} orders -> {out}\n")

    day_blocks, ms_per_block = con.execute(
        "SELECT any_value(day_b1 - day_b0), any_value(ms_per_block) FROM lc").fetchall()[0]
    print(f"blocks in window: {day_blocks:,}  (~{ms_per_block:.0f} ms per block)\n")

    print("By class (placed = message notional, counts every re-quote; depth = time-weighted):")
    print(con.sql(f"""
        SELECT class,
               count(*)                                              AS orders,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1)     AS pct_orders,
               round(sum(notional_usd) / 1e6, 1)                     AS placed_musd,
               round(sum(filled_usd) / 1e6, 1)                       AS filled_musd,
               round(sum(notional_usd * displayed_blocks) / {day_blocks} / 1e6, 2) AS avg_depth_musd,
               median(displayed_blocks) FILTER (WHERE displayed_blocks > 0) AS med_blocks_shown
        FROM lc GROUP BY class ORDER BY orders DESC
    """))

    return 0


if __name__ == "__main__":
    sys.exit(main())
