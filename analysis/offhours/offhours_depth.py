"""Per-minute resting depth within 5/10/25 bps of mid from the replayed book, by session; and
median distinct makers per hour. 2026-10-08..21."""
import duckdb

R = "."
T = "data/derived/offhours"; import os; os.makedirs(T, exist_ok=True)
SESSION = """
  CASE
    WHEN (dayofweek({t}) = 5 AND hour({t}) >= 21) OR dayofweek({t}) = 6
         OR (dayofweek({t}) = 0 AND hour({t}) < 22)                            THEN 'weekend'
    WHEN dayofweek({t}) BETWEEN 1 AND 5
         AND (hour({t}) * 60 + minute({t})) BETWEEN 810 AND 1199                THEN 'cash'
    WHEN dayofweek({t}) BETWEEN 1 AND 4 AND hour({t}) = 21                      THEN 'break'
    ELSE 'overnight' END"""
S = lambda t: SESSION.format(t=t)
con = duckdb.connect()
con.execute("SET TimeZone='UTC'; SET threads=6; SET memory_limit='9GB'")
con.execute("CREATE TABLE snaps (t TIMESTAMP, mid DOUBLE, d5 DOUBLE, d10 DOUBLE, d25 DOUBLE, d_all DOUBLE)")
for d in range(8, 22):
    day = f"202610{d:02d}"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE clock AS SELECT block_number blk, min(epoch_ms(block_time::TIMESTAMP)) ms
        FROM read_parquet('{R}/data/l4/order_statuses/xyz_SP500/{day}/*.parquet') GROUP BY 1""")
    # one sample block per minute: the last block of each minute, with the replayed mid there
    con.execute(f"""CREATE OR REPLACE TEMP TABLE smp AS
        WITH m AS (SELECT ms // 60000 AS mn, max(blk) blk FROM clock GROUP BY 1)
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
con.execute(f"COPY snaps TO '{T}/offhours_depth_minutes.parquet' (FORMAT parquet)")
print(con.sql(f"""
  SELECT {S('t')} session, count(*) n_minutes,
         round(median(d5) / 1e6, 2) depth5_musd, round(median(d10) / 1e6, 2) depth10_musd,
         round(median(d25) / 1e6, 2) depth25_musd, round(median(d_all) / 1e6, 1) depth_all_musd,
         round(quantile_cont(d10, 0.1) / 1e6, 2) depth10_p10_musd
  FROM snaps GROUP BY 1
  ORDER BY CASE session WHEN 'cash' THEN 1 WHEN 'overnight' THEN 2 WHEN 'break' THEN 3 ELSE 4 END"""))
fills = [f"{R}/data/raw/xyz/fills/2026-10-{d:02d}.parquet" for d in range(8, 22)]
print(con.sql(f"""
  WITH h AS (SELECT date_trunc('hour', timestamp) hr, count(DISTINCT address) FILTER (WHERE NOT crossed) makers,
                    count(DISTINCT address) FILTER (WHERE crossed) takers
             FROM read_parquet({fills}) WHERE coin = 'xyz:SP500' GROUP BY 1)
  SELECT {S('hr')} session, median(makers) med_makers_per_h, median(takers) med_takers_per_h, count(*) hours_with_fills
  FROM h GROUP BY 1
  ORDER BY CASE session WHEN 'cash' THEN 1 WHEN 'overnight' THEN 2 WHEN 'break' THEN 3 ELSE 4 END"""))
