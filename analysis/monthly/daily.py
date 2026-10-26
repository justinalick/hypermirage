"""Per-day building blocks for the month-by-month view, xyz:SP500, every day of the run window (scripts/window.py).
One day at a time (DuckDB 1 GB / 2 threads), so memory stays flat. Writes data/derived/monthly/:
  km.parquet, kn.parquet: Kaplan-Meier inputs up to 1 s (as charts/survival_cache.py: distance group,
      displayed time, cancels, orders) plus each group's order count, so any set of days gives the exact KM at 1 s
  fill.parquet: displayed notional and filled notional of rested orders (as analysis/cancels/rates.sql)
  amends.parquet: cancels by kind (as analysis/cancels/amends_sum.py) and price-amend ticks by direction"""
import os, sys
import duckdb
sys.path.insert(0, "scripts")
import window as WIN

LT = "data/derived/lifecycle_touch/xyz_SP500"
O = "data/derived/monthly"
os.makedirs(O, exist_ok=True)
GROUP = """CASE WHEN dist_bucket IN ('1 improves touch', '2 at touch') THEN 'a' WHEN dist_bucket = '3 within 1 bp' THEN 'b'
                WHEN dist_bucket = '4 1-5 bps' THEN 'c' ELSE 'd' END"""
WHERE = """displayed_blocks > 0 AND dist_bps IS NOT NULL AND class IN ('displayed_pulled','displayed_partial','filled','still_open')"""
KIND = """CASE WHEN new_oid IS NULL THEN 'pure cancel' WHEN new_px=old_px AND abs(new_sz-old_sz)<1e-9 THEN 'refresh'
       WHEN new_px=old_px THEN 'size only' WHEN abs(new_sz-old_sz)<1e-9 THEN 'price only' ELSE 'price and size' END"""
DIR = """CASE WHEN new_oid IS NULL OR new_px=old_px THEN NULL WHEN (side='B') = (new_px>old_px) THEN 'toward' ELSE 'away' END"""
con = duckdb.connect(); con.execute("SET memory_limit='1GB'; SET threads=2")
con.execute("CREATE TABLE km (day VARCHAR, b VARCHAR, t DOUBLE, ev BIGINT, w BIGINT)")
con.execute("CREATE TABLE kn (day VARCHAR, b VARCHAR, n BIGINT)")
con.execute("CREATE TABLE fill (day VARCHAR, placed_usd DOUBLE, filled_usd DOUBLE, n BIGINT)")
con.execute("CREATE TABLE am (day VARCHAR, kind VARCHAR, dir VARCHAR, ticks DOUBLE, n BIGINT)")
for d in WIN.DAYS:
    f = f"{LT}/{d}.parquet"
    con.execute(f"""INSERT INTO km SELECT '{d}', {GROUP}, displayed_blocks * ms_per_block t,
        sum(CASE WHEN class IN ('displayed_pulled','displayed_partial') THEN 1 ELSE 0 END), count(*)
        FROM '{f}' WHERE {WHERE} AND displayed_blocks * ms_per_block <= 1000 GROUP BY 2, 3""")
    con.execute(f"INSERT INTO kn SELECT '{d}', {GROUP}, count(*) FROM '{f}' WHERE {WHERE} GROUP BY 2")
    con.execute(f"""INSERT INTO fill SELECT '{d}', sum(notional_usd), sum(least(coalesce(filled_usd, 0), notional_usd)), count(*)
        FROM '{f}' WHERE class IN ('displayed_pulled','displayed_partial','filled') AND displayed_blocks > 0
        AND dist_bucket NOT IN ('unknown','0 placed before window')""")
    a = f"data/derived/cancels/amends_{d}.parquet"
    if os.path.exists(a):
        con.execute(f"""INSERT INTO am SELECT '{d}', {KIND}, {DIR}, round(abs(new_px-old_px)/0.1), count(*)
            FROM '{a}' GROUP BY ALL""")
for t in ("km", "kn", "fill", "am"):
    con.execute(f"COPY {t} TO '{O}/{t}.parquet'")
print(con.sql("SELECT count(DISTINCT day) n_days, sum(n) n_orders FROM kn"))
