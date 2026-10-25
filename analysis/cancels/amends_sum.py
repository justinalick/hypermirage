"""Cancel-replace ("amend") mix by distance from the touch and size of price amends, from the per-day pair
tables of amends.py joined to that day's lifecycles. One day at a time (pairs and lifecycles share the day),
so memory stays flat over long windows; every output is a sum over days.
Writes data/derived/cancels/amend_kinds.parquet and amend_ticks.parquet and prints the summaries."""
import glob, os, re, duckdb
con = duckdb.connect(); con.execute("SET threads=4; SET memory_limit='6GB'")
KIND = """CASE WHEN new_oid IS NULL THEN 'pure cancel'
       WHEN new_px=old_px AND abs(new_sz-old_sz)<1e-9 THEN 'refresh (same px, same size)'
       WHEN new_px=old_px THEN 'size only'
       WHEN abs(new_sz-old_sz)<1e-9 THEN 'price only'
       ELSE 'price and size' END"""
DIR = """CASE WHEN new_oid IS NULL OR new_px=old_px THEN NULL
       WHEN (a.side='B') = (new_px>old_px) THEN 'toward touch' ELSE 'away from touch' END"""
con.execute("CREATE TABLE k (kind VARCHAR, dir VARCHAR, dist_bucket VARCHAR, n BIGINT, usd DOUBLE, no_lc BIGINT, up BIGINT)")
con.execute("CREATE TABLE t (kind VARCHAR, dir VARCHAR, ticks DOUBLE, n BIGINT)")
days = sorted(re.search(r"amends_(\d{8})", p).group(1) for p in glob.glob("data/derived/cancels/amends_*.parquet"))
for d in days:
    con.execute(f"""CREATE OR REPLACE TEMP TABLE a AS
        SELECT a.*, l.dist_bucket, l.class, l.notional_usd, {KIND} kind, {DIR} dir,
               round(abs(new_px-old_px)/0.1) ticks
        FROM 'data/derived/cancels/amends_{d}.parquet' a
        LEFT JOIN 'data/derived/lifecycle_touch/xyz_SP500/{d}.parquet' l ON l.oid=a.old_oid""")
    con.execute("""INSERT INTO k SELECT kind, dir, dist_bucket, count(*), sum(notional_usd),
                   count(*) FILTER (WHERE class IS NULL), count(*) FILTER (WHERE new_sz>old_sz) FROM a GROUP BY ALL""")
    con.execute("INSERT INTO t SELECT kind, dir, ticks, count(*) FROM a WHERE ticks IS NOT NULL GROUP BY ALL")
con.execute("""COPY (SELECT kind, dir, dist_bucket, sum(n) n, sum(usd) usd FROM k GROUP BY ALL)
               TO 'data/derived/cancels/amend_kinds.parquet'""")
con.execute("""COPY (SELECT kind, dir, least(ticks,20) ticks, sum(n) n FROM t GROUP BY ALL)
               TO 'data/derived/cancels/amend_ticks.parquet'""")
print(len(days), "days")
print(con.sql("""SELECT kind, sum(n) n, round(100*sum(n)/sum(sum(n)) over (),1) pct, round(100*sum(no_lc)/sum(n),2) no_lc
                 FROM k GROUP BY 1 ORDER BY 2 DESC"""))
# median ticks per direction, exact, from the per-tick counts
print(con.sql("""WITH c AS (SELECT dir, ticks, sum(n) n FROM t WHERE dir IS NOT NULL GROUP BY ALL),
                 r AS (SELECT dir, ticks, n, sum(n) OVER (PARTITION BY dir ORDER BY ticks) cum, sum(n) OVER (PARTITION BY dir) tot FROM c)
                 SELECT dir, any_value(tot) n,
                        (min(ticks) FILTER (WHERE cum >= floor((tot + 1) / 2.0))
                         + min(ticks) FILTER (WHERE cum >= ceil((tot + 1) / 2.0))) / 2 median_ticks
                 FROM r GROUP BY 1"""))
# same block size changes: grow or shrink
print(con.sql("""SELECT kind, round(100*sum(up)/sum(n),1) pct_up FROM k
                 WHERE kind IN ('size only','price and size') GROUP BY 1"""))
