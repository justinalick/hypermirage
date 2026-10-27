import sys, os; sys.path.insert(0, "analysis/heatmap")
import duckdb as _d
_c = _d.connect
def _conn(*a, **k):
    c = _c(*a, **k); c.execute("SET memory_limit='3GB'; SET threads=2"); return c
_d.connect = _conn
try: _d.default_connection().execute("SET memory_limit='3GB'; SET threads=2")
except Exception: pass
"""Recompute per-minute resting depth for xyz:SP500 with partial fills netted out, and validate the
book replay against Reservoir's 1m L2 snapshots (top 20 levels per side), every day of the run window (scripts/window.py).

Resting size of an order at block B (fills are maker legs from Reservoir, matched on order_id):
  order ended with a terminal event:  remaining at that event (last_sz, 0 if filled) + fills after B
  order still open at the day's end:  orig_sz - fills at or before B
Outputs (to argv[1]):
  depth_minutes_v2.parquet  t, mid, d5/d10/d25 (orig_sz, as in the first chart) and *_net (net of fills)
  l2_check.parquet          per L2 snapshot and side: L2 notional vs replay notional, same price band
"""
import sys
import duckdb
sys.path.insert(0, "scripts")
import window as WIN

R = "."
OUT = "data/checks/spotcheck/heatmap_out"
import os; os.makedirs(OUT, exist_ok=True)
con = duckdb.connect()
con.execute("SET TimeZone='UTC'; SET threads=2; SET memory_limit='3GB'; SET preserve_insertion_order=false")
con.execute("""CREATE TABLE mins (t TIMESTAMP, mid DOUBLE, d5 DOUBLE, d10 DOUBLE, d25 DOUBLE,
               d5_net DOUBLE, d10_net DOUBLE, d25_net DOUBLE)""")
con.execute("""CREATE TABLE l2chk (day VARCHAR, blk BIGINT, side VARCHAR, n_lvls INT, l2_usd DOUBLE,
               rep_usd DOUBLE, rep_net_usd DOUBLE)""")

for day, iso in zip(WIN.DAYS, WIN.ISO):
    con.execute(f"""CREATE OR REPLACE TEMP TABLE clock AS
        SELECT block_number blk, min(epoch_ms(block_time::TIMESTAMP)) ms
        FROM read_parquet('{R}/data/l4/order_statuses/xyz_SP500/{day}/*.parquet') GROUP BY 1""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE rest AS
        SELECT oid, side, limit_px px, orig_sz,
               CASE WHEN class = 'pre_existing' THEN day_b0 ELSE b_open END s,
               CASE WHEN class = 'still_open' THEN day_b1 + 1 ELSE b_last END e,
               last_status <> 'open' AS ended,
               CASE WHEN last_status = 'filled' THEN 0 ELSE last_sz END AS end_sz
        FROM '{R}/data/derived/lifecycle_touch/xyz_SP500/{day}.parquet'
        WHERE class IN ('displayed_pulled','displayed_partial','filled','still_open','pre_existing')
          AND displayed_blocks > 0 AND limit_px IS NOT NULL""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE mf AS
        SELECT order_id oid, epoch_ms(timestamp) ms, CAST(size AS DOUBLE) sz
        FROM '{R}/data/raw/xyz/fills/{iso}.parquet'
        WHERE coin = 'xyz:SP500' AND NOT crossed AND order_id IN (SELECT oid FROM rest)""")
    # sample blocks: last block of each minute (as in the chart) and every L2 snapshot block
    con.execute(f"""CREATE OR REPLACE TEMP TABLE smp AS
        WITH m AS (SELECT ms // 60000 AS mn, max(blk) blk FROM clock
                   WHERE ms >= epoch_ms(TIMESTAMP '{iso}')                  -- this UTC day only: the last hourly
                     AND ms < epoch_ms(TIMESTAMP '{iso}') + 86400000        -- order-status file can reach past midnight
                   GROUP BY 1)
        SELECT 'min' kind, m.mn, m.blk, (b.best_bid + b.best_ask) / 2 mid, NULL::DOUBLE lo, NULL::DOUBLE hi
        FROM m ASOF JOIN '{R}/data/derived/bbo/xyz_SP500/{day}.parquet' b ON b.block <= m.blk
        WHERE b.best_bid IS NOT NULL AND b.best_ask IS NOT NULL
        UNION ALL
        SELECT 'l2', NULL, block_number::BIGINT, NULL,
               CAST(bids[len(bids)].px AS DOUBLE), CAST(asks[len(asks)].px AS DOUBLE)
        FROM '{R}/data/raw/xyz/book_1m/SP500/{iso}.parquet'""")
    con.execute("""CREATE OR REPLACE TEMP TABLE smp_t AS
        SELECT s.*, c.ms bms FROM smp s ASOF JOIN clock c ON c.blk <= s.blk""")
    con.execute("""CREATE OR REPLACE TEMP TABLE j AS
        WITH g AS (
          SELECT s.kind, s.mn, s.blk, s.mid, s.lo, s.hi, r.oid, r.side, r.px, r.orig_sz, r.ended, r.end_sz,
                 coalesce(sum(f.sz) FILTER (WHERE f.ms > s.bms), 0) f_after,
                 coalesce(sum(f.sz) FILTER (WHERE f.ms <= s.bms), 0) f_before
          FROM smp_t s JOIN rest r ON r.s <= s.blk AND r.e > s.blk
               AND ((s.kind = 'min' AND abs(r.px - s.mid) / s.mid * 1e4 <= 25.001)
                    OR (s.kind = 'l2' AND r.px BETWEEN s.lo AND s.hi))
          LEFT JOIN mf f ON f.oid = r.oid
          GROUP BY ALL)
        SELECT kind, mn, blk, mid, lo, hi, oid, side, px, orig_sz,
               CASE WHEN ended THEN end_sz + f_after ELSE orig_sz - f_before END net_sz
        FROM g""")
    con.execute("""INSERT INTO mins
        SELECT make_timestamp(mn * 60000000), mid,
          sum(px * orig_sz) FILTER (WHERE abs(px - mid) / mid * 1e4 <= 5),
          sum(px * orig_sz) FILTER (WHERE abs(px - mid) / mid * 1e4 <= 10),
          sum(px * orig_sz) FILTER (WHERE abs(px - mid) / mid * 1e4 <= 25),
          sum(px * greatest(net_sz, 0)) FILTER (WHERE abs(px - mid) / mid * 1e4 <= 5),
          sum(px * greatest(net_sz, 0)) FILTER (WHERE abs(px - mid) / mid * 1e4 <= 10),
          sum(px * greatest(net_sz, 0)) FILTER (WHERE abs(px - mid) / mid * 1e4 <= 25)
        FROM j WHERE kind = 'min' GROUP BY mn, mid""")
    con.execute(f"""INSERT INTO l2chk
        WITH l2 AS (
          SELECT block_number::BIGINT blk, 'B' side, len(bids) n, list_sum(list_transform(bids, lambda x: CAST(x.px AS DOUBLE) * CAST(x.sz AS DOUBLE))) usd FROM '{R}/data/raw/xyz/book_1m/SP500/{iso}.parquet'
          UNION ALL
          SELECT block_number::BIGINT, 'A', len(asks), list_sum(list_transform(asks, lambda x: CAST(x.px AS DOUBLE) * CAST(x.sz AS DOUBLE))) FROM '{R}/data/raw/xyz/book_1m/SP500/{iso}.parquet'),
        rp AS (
          SELECT blk, side, sum(px * orig_sz) usd, sum(px * greatest(net_sz, 0)) net_usd FROM j
          WHERE kind = 'l2' AND ((side = 'B' AND px >= lo) OR (side = 'A' AND px <= hi))
          GROUP BY 1, 2)
        SELECT '{day}', l2.blk, l2.side, l2.n, l2.usd, coalesce(rp.usd, 0), coalesce(rp.net_usd, 0)
        FROM l2 LEFT JOIN rp USING (blk, side)""")
    print(day, flush=True)

con.execute(f"COPY mins TO '{OUT}/depth_minutes_v2.parquet' (FORMAT parquet)")
con.execute(f"COPY l2chk TO '{OUT}/l2_check.parquet' (FORMAT parquet)")
