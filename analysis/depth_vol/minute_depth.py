"""Step 1: per-minute resting depth of xyz:SP500 from the order-level book replay.

For each UTC minute, take the last block of that minute, the replayed mid there, and sum the
notional (limit_px * orig_sz) of every order resting at that block within 5/10/25 bps of mid
(both sides). Inputs are per-day lifecycle_touch and bbo tables built by scripts/lifecycle.py
and scripts/touch.py. Same logic as the off-hours depth step, written as a standalone script.

Usage: .venv/bin/python minute_depth.py OUT.parquet [--exclude-filled]
  --exclude-filled  drop orders that ended filled or partly filled (their size is not netted for
                    partial fills before the snapshot); used as a robustness check.
"""
import sys
import duckdb
sys.path.insert(0, "scripts")
import window as WIN

R = "."
out = sys.argv[1]
classes = ["displayed_pulled", "still_open", "pre_existing"]
if "--exclude-filled" not in sys.argv:
    classes += ["filled", "displayed_partial"]
cls = ", ".join(f"'{c}'" for c in classes)

con = duckdb.connect()
con.execute("SET TimeZone='UTC'; SET threads=6; SET memory_limit='9GB'")
con.execute("CREATE TABLE snaps (t TIMESTAMP, mid DOUBLE, d5 DOUBLE, d10 DOUBLE, d25 DOUBLE, d_all DOUBLE)")
for day in WIN.DAYS:
    # block -> time, from the day's order-status extract
    con.execute(f"""CREATE OR REPLACE TEMP TABLE clock AS
        SELECT block_number blk, min(epoch_ms(block_time::TIMESTAMP)) ms
        FROM read_parquet('{R}/data/l4/order_statuses/xyz_SP500/{day}/*.parquet') GROUP BY 1""")
    # last block of each minute and the replayed mid at that block
    con.execute(f"""CREATE OR REPLACE TEMP TABLE smp AS
        WITH m AS (SELECT ms // 60000 AS mn, max(blk) blk FROM clock GROUP BY 1)
        SELECT m.mn, m.blk, (b.best_bid + b.best_ask) / 2 mid
        FROM m ASOF JOIN read_parquet('{R}/data/derived/bbo/xyz_SP500/{day}.parquet') b ON b.block <= m.blk
        WHERE b.best_bid IS NOT NULL AND b.best_ask IS NOT NULL""")
    # resting interval [s, e) of every displayed order
    con.execute(f"""CREATE OR REPLACE TEMP TABLE rest AS
        SELECT limit_px px, notional_usd usd,
               CASE WHEN class = 'pre_existing' THEN day_b0 ELSE b_open END s,
               CASE WHEN class = 'still_open' THEN day_b1 + 1 ELSE b_last END e
        FROM '{R}/data/derived/lifecycle_touch/xyz_SP500/{day}.parquet'
        WHERE class IN ({cls}) AND displayed_blocks > 0 AND limit_px IS NOT NULL""")
    con.execute("""INSERT INTO snaps
        SELECT make_timestamp(smp.mn * 60000000) t, smp.mid,
               sum(r.usd) FILTER (WHERE abs(r.px - smp.mid) / smp.mid * 1e4 <= 5),
               sum(r.usd) FILTER (WHERE abs(r.px - smp.mid) / smp.mid * 1e4 <= 10),
               sum(r.usd) FILTER (WHERE abs(r.px - smp.mid) / smp.mid * 1e4 <= 25),
               sum(r.usd)
        FROM smp JOIN rest r ON r.s <= smp.blk AND r.e > smp.blk
        GROUP BY smp.mn, smp.mid""")
    print(day, flush=True)
con.execute(f"COPY (SELECT * FROM snaps ORDER BY t) TO '{out}' (FORMAT parquet)")
