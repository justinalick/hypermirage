"""Depth robustness for the regime split. Two alternative per-minute depth measures:
 (a) fill-adjusted replay: same replay as offhours/offhours_depth.py but each order counts (notional - filled) for its
     whole life, a lower bound (fills treated as if they happened at placement); the original counts full notional, an upper bound.
 (b) Reservoir 1m L2 snapshots (independent source): notional summed over the 20 published levels per side.
     The snapshot at the start of minute m+1 is used as the end-of-minute book for minute m.
Writes depth_alt.parquet (t, d10_net, l2_20lvl)."""
import duckdb

R = "."
O = f"{R}/data/derived/regimes/verify"
con = duckdb.connect()
con.execute("SET TimeZone='UTC'; SET threads=3; SET memory_limit='4GB'; SET preserve_insertion_order=false")
con.execute("CREATE TABLE net (t TIMESTAMP, d10_net DOUBLE)")
for d in range(8, 22):
    day = f"202610{d:02d}"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE clock AS SELECT block_number blk, min(epoch_ms(block_time::TIMESTAMP)) ms
        FROM read_parquet('{R}/data/l4/order_statuses/xyz_SP500/{day}/*.parquet') GROUP BY 1""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE smp AS
        WITH m AS (SELECT ms // 60000 AS mn, max(blk) blk FROM clock GROUP BY 1)
        SELECT m.mn, m.blk, (b.best_bid + b.best_ask) / 2 mid
        FROM m ASOF JOIN read_parquet('{R}/data/derived/bbo/xyz_SP500/{day}.parquet') b ON b.block <= m.blk
        WHERE b.best_bid IS NOT NULL AND b.best_ask IS NOT NULL""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE rest AS
        SELECT limit_px px, greatest(notional_usd - coalesce(filled_usd, 0), 0) usd,
               CASE WHEN class = 'pre_existing' THEN day_b0 ELSE b_open END s,
               CASE WHEN class = 'still_open' THEN day_b1 + 1 ELSE b_last END e
        FROM '{R}/data/derived/lifecycle_touch/xyz_SP500/{day}.parquet'
        WHERE class IN ('displayed_pulled','displayed_partial','filled','still_open','pre_existing')
          AND displayed_blocks > 0 AND limit_px IS NOT NULL""")
    con.execute("""INSERT INTO net
        SELECT make_timestamp(smp.mn * 60000000) t,
               coalesce(sum(r.usd) FILTER (WHERE abs(r.px - smp.mid) / smp.mid * 1e4 <= 10), 0)
        FROM smp JOIN rest r ON r.s <= smp.blk AND r.e > smp.blk GROUP BY smp.mn""")
    print(day, flush=True)
books = [f"{R}/data/raw/xyz/book_1m/SP500/2026-10-{d:02d}.parquet" for d in range(8, 23) if d < 22]
con.execute(f"""CREATE TABLE l2 AS
    SELECT make_timestamp((block_time_ms // 60000 - 1) * 60000000) t,
           (SELECT sum(x.px::DOUBLE * x.sz::DOUBLE) FROM unnest(bids) AS u(x)) + (SELECT sum(x.px::DOUBLE * x.sz::DOUBLE) FROM unnest(asks) AS u(x)) l2_20lvl
    FROM read_parquet({books})""")
con.execute(f"""COPY (SELECT n.t, n.d10_net, l2.l2_20lvl FROM net n LEFT JOIN (SELECT t, avg(l2_20lvl) l2_20lvl FROM l2 GROUP BY t) l2 USING (t) ORDER BY t)
    TO '{O}/depth_alt.parquet' (FORMAT parquet)""")
print(con.sql(f"SELECT count(*), count(l2_20lvl), median(d10_net), median(l2_20lvl) FROM '{O}/depth_alt.parquet'"))
