"""Per-minute resting depth within 5/10/25 bps of mid from the replayed book, by session; and
median distinct makers per hour, every day of the run window (scripts/window.py)."""
import duckdb
import sys
sys.path.insert(0, "scripts")
import window as WIN

import pandas as pd

R = "."
T = "data/derived/offhours"; import os; os.makedirs(T, exist_ok=True)
ORDER = "ORDER BY CASE session WHEN 'cash' THEN 1 WHEN 'overnight' THEN 2 WHEN 'break' THEN 3 ELSE 4 END"


def with_session(con, table, col):
    """Register <table>_s = distinct <col> with its session label from the scripts/window.py clock
    (closed = futures closed: weekends and holiday closures)."""
    ts = con.execute(f"SELECT DISTINCT {col} FROM {table}").df()[col]
    con.register(f"{table}_s", pd.DataFrame({col: ts, "session": WIN.session(ts)}))


con = duckdb.connect()
con.execute("SET TimeZone='UTC'; SET threads=4; SET memory_limit='6GB'")   # one day at a time; leaves room for a second lane
con.execute("CREATE TABLE snaps (t TIMESTAMP, mid DOUBLE, d5 DOUBLE, d10 DOUBLE, d25 DOUBLE, d_all DOUBLE)")
for day in WIN.DAYS:
    con.execute(f"""CREATE OR REPLACE TEMP TABLE clock AS SELECT block_number blk, min(epoch_ms(block_time::TIMESTAMP)) ms
        FROM read_parquet('{R}/data/l4/order_statuses/xyz_SP500/{day}/*.parquet') GROUP BY 1""")
    # one sample block per minute: the last block of each minute, with the replayed mid there
    con.execute(f"""CREATE OR REPLACE TEMP TABLE smp AS
        WITH m AS (SELECT ms // 60000 AS mn, max(blk) blk FROM clock
                   WHERE ms >= epoch_ms(TIMESTAMP '{day[:4]}-{day[4:6]}-{day[6:]}')          -- this UTC day only: the last hour
                     AND ms < epoch_ms(TIMESTAMP '{day[:4]}-{day[4:6]}-{day[6:]}') + 86400000  -- file can reach past midnight
                   GROUP BY 1)
        SELECT m.mn, m.blk, (b.best_bid + b.best_ask) / 2 mid
        FROM m ASOF JOIN read_parquet('{R}/data/derived/bbo/xyz_SP500/{day}.parquet') b ON b.block <= m.blk
        WHERE b.best_bid IS NOT NULL AND b.best_ask IS NOT NULL""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE rest AS
        SELECT limit_px px, notional_usd usd,
               CASE WHEN class = 'pre_existing' THEN day_b0 ELSE b_open END s,
               CASE WHEN class = 'still_open' THEN day_b1 + 1 ELSE b_last END e
        FROM '{R}/data/derived/lifecycle_touch/xyz_SP500/{day}.parquet'
        WHERE class IN ('displayed_pulled','displayed_partial','filled','still_open','pre_existing')
          AND displayed_blocks > 0 AND limit_px IS NOT NULL""")
    con.execute(f"""INSERT INTO snaps
        SELECT make_timestamp(smp.mn * 60000000) t, smp.mid,
               sum(r.usd) FILTER (WHERE abs(r.px - smp.mid) / smp.mid * 1e4 <= 5),
               sum(r.usd) FILTER (WHERE abs(r.px - smp.mid) / smp.mid * 1e4 <= 10),
               sum(r.usd) FILTER (WHERE abs(r.px - smp.mid) / smp.mid * 1e4 <= 25),
               sum(r.usd)
        FROM smp JOIN rest r ON r.s <= smp.blk AND r.e > smp.blk
        GROUP BY smp.mn, smp.mid""")
    print(day, flush=True)
con.execute(f"COPY (SELECT * FROM snaps ORDER BY t) TO '{T}/offhours_depth_minutes.parquet' (FORMAT parquet)")
with_session(con, "snaps", "t")
print(con.sql(f"""
  SELECT session, count(*) n_minutes,
         round(median(d5) / 1e6, 2) depth5_musd, round(median(d10) / 1e6, 2) depth10_musd,
         round(median(d25) / 1e6, 2) depth25_musd, round(median(d_all) / 1e6, 1) depth_all_musd,
         round(quantile_cont(d10, 0.1) / 1e6, 2) depth10_p10_musd
  FROM snaps JOIN snaps_s USING (t) GROUP BY 1 {ORDER}"""))
fills = [f"{R}/data/raw/xyz/fills/{d}.parquet" for d in WIN.ISO]
con.execute(f"""CREATE TABLE h AS SELECT date_trunc('hour', timestamp)::TIMESTAMP hr,
                    count(DISTINCT address) FILTER (WHERE NOT crossed) makers,
                    count(DISTINCT address) FILTER (WHERE crossed) takers
             FROM read_parquet({fills}) WHERE coin = 'xyz:SP500' GROUP BY 1""")
with_session(con, "h", "hr")
print(con.sql(f"""
  SELECT session, median(makers) med_makers_per_h, median(takers) med_takers_per_h, count(*) hours_with_fills
  FROM h JOIN h_s USING (hr) GROUP BY 1 {ORDER}"""))
