"""Active-account universe: accounts with quoting activity (open, cancel, post-only reject or scheduled
cancel events) in >= 200 distinct blocks in the window. Counted day by day (a block belongs to one day,
so the per-day distinct counts add up) to keep memory flat over long windows.
Writes data/derived/concentration/universe.csv (u, nb, n)."""
import glob, os, duckdb
con = duckdb.connect(); con.execute("SET memory_limit='3GB'; SET threads=4")
con.execute("CREATE TABLE a (u VARCHAR, nb BIGINT, n BIGINT)")
for d in sorted(os.listdir("data/l4/order_statuses/xyz_SP500")):
    con.execute(f"""INSERT INTO a SELECT "user", count(DISTINCT block_number), count(*)
        FROM read_parquet('data/l4/order_statuses/xyz_SP500/{d}/*.parquet')
        WHERE status IN ('open','canceled','badAloPxRejected','scheduledCancel') GROUP BY 1""")
con.execute("""COPY (SELECT u, sum(nb) nb, sum(n) n FROM a GROUP BY 1 HAVING sum(nb) >= 200 ORDER BY nb DESC, u)
               TO 'data/derived/concentration/universe.csv'""")
print(con.execute("SELECT count(*) FROM read_csv('data/derived/concentration/universe.csv')").fetchone()[0], "accounts")
