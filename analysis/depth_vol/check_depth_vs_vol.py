"""Independent check of the depth_vs_vol.py numbers, written in DuckDB SQL from the same minute table.

Recomputes returns, trailing vol, sessions, the hour and day normalization, decile gaps and the
left-panel correlation without pandas, then cross-checks the inputs against the Reservoir 1m L2
book (mid alignment). Prints each number next to the expected one and fails loudly on a mismatch.

Usage: .venv/bin/python check_depth_vs_vol.py MINUTES.parquet
"""
import sys
import glob
import duckdb

src = sys.argv[1]
L2 = "data/raw/xyz/book_1m/SP500/*.parquet"
EXPECT = {"cash": -3.8, "overnight": 4.8, "W1009": -9.0, "W1016": -35.2}
con = duckdb.connect()
con.execute("SET TimeZone='UTC'; SET memory_limit='4GB'")

con.execute(f"""
CREATE TABLE m AS
WITH a AS (SELECT t, mid, d10, 1e4 * ln(mid / lag(mid) OVER (ORDER BY t)) r FROM '{src}'),
b AS (SELECT *, stddev_samp(r) OVER w * sqrt(365 * 1440) / 100 rv0, count(r) OVER w nr
      FROM a WINDOW w AS (ORDER BY t ROWS BETWEEN 14 PRECEDING AND CURRENT ROW)),
c AS (SELECT t, d10, CASE WHEN nr >= 12 THEN rv0 END rv,
        isodow(t) dw, hour(t) h, hour(t) * 60 + minute(t) mm FROM b),
s AS (SELECT *,
        (dw = 5 AND h >= 21) OR dw = 6 OR (dw = 7 AND h < 22) wk,
        CASE WHEN dw <= 5 AND mm BETWEEN 810 AND 1199 THEN 'cash'
             WHEN (dw = 5 AND h >= 21) OR dw = 6 OR (dw = 7 AND h < 22) THEN 'weekend'
             WHEN dw <= 4 AND h = 21 THEN 'break' ELSE 'overnight' END g
      FROM c)
SELECT *, h::VARCHAR || CASE WHEN wk THEN 'w' ELSE 'd' END hod,
       CASE WHEN wk THEN 'W' || strftime(t - INTERVAL (((dw - 5 + 7) % 7)) DAY, '%m%d')
            ELSE strftime(t, '%m%d') END blk,
       ln(d10) lnd
FROM s""")

ok = True
def check(name, got, want, tol):
    global ok
    good = abs(got - want) <= tol
    ok &= good
    print(f"{'OK  ' if good else 'FAIL'} {name:34s} got {got:+.2f}  expected {want:+.2f}")

n, gaps = con.sql("SELECT count(*), count(*) FILTER (WHERE rv IS NULL) FROM m").fetchall()[0]
check("minutes", n, 20160, 0)
check("minutes without vol (warm-up)", gaps, 12, 0)

rows = con.sql("""
WITH n1 AS (SELECT *, lnd - median(lnd) OVER (PARTITION BY hod) rel FROM m),
n2 AS (SELECT *, rel - median(rel) OVER (PARTITION BY g, blk) rel2 FROM n1
       WHERE rv IS NOT NULL AND g <> 'break'),
k AS (SELECT *, CASE WHEN g = 'weekend' THEN blk ELSE g END key FROM n2),
q AS (SELECT *, ntile(10) OVER (PARTITION BY key ORDER BY rv, t) - 1 dec FROM k)
SELECT key, count(*) n,
       100 * (exp(median(rel2) FILTER (WHERE dec = 9) - median(rel2) FILTER (WHERE dec = 0)) - 1) gap
FROM q GROUP BY key ORDER BY key""").fetchall()
for key, n, gap in rows:
    check(f"gap {key} (n={n})", gap, EXPECT[key], 0.5)

hours, rho = con.sql("""
WITH hr AS (SELECT date_trunc('hour', t) hr, median(d10) dep, median(rv) rv FROM m
            WHERE rv IS NOT NULL GROUP BY 1)
SELECT count(*), corr(ln(rv), ln(dep)) FROM hr WHERE rv > 0""").fetchall()[0]
check("left panel hours", hours, 336, 0)
check("left panel rho", rho, 0.63, 0.005)

# inputs: replayed mid at the last block of minute t should equal the Reservoir L2 mid at the
# first block of minute t+1 (the L2 is sampled just after each minute starts)
diff, matched = con.sql(f"""
WITH l2 AS (SELECT make_timestamp(block_time_ms * 1000) ts,
                   (bids[1].px::DOUBLE + asks[1].px::DOUBLE) / 2 mid FROM read_parquet('{L2}'))
SELECT median(abs(m.mid / l2.mid - 1) * 1e4), count(*)
FROM '{src}' m JOIN l2 ON date_trunc('minute', l2.ts) = m.t + INTERVAL 1 MINUTE""").fetchall()[0]
check("median |replay mid - L2 mid| bps", diff, 0.0, 0.05)
check("minutes matched to L2", matched, 20159, 0)

print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
