"""Step 1: attach block times to the replayed best bid/ask (output of scripts/touch.py), one day at a time.
Mid at t = last top-of-book change at or before t. Block time comes from node order statuses.
Writes data/derived/markout/bbo_t.parquet (block, t, best_bid, best_ask), ordered by block."""
import os, duckdb
con = duckdb.connect(); con.execute("SET memory_limit='1500MB'; SET threads=2")
con.execute("CREATE TABLE out (block BIGINT, t TIMESTAMP, best_bid DOUBLE, best_ask DOUBLE)")
for d in sorted(os.listdir("data/l4/order_statuses/xyz_SP500")):
    con.execute(f"""INSERT INTO out
        WITH bt AS (SELECT block_number block, min(block_time::TIMESTAMP) t
                    FROM read_parquet('data/l4/order_statuses/xyz_SP500/{d}/*.parquet') GROUP BY 1)
        SELECT b.block, bt.t, b.best_bid, b.best_ask
        FROM 'data/derived/bbo/xyz_SP500/{d}.parquet' b LEFT JOIN bt USING (block)""")
con.execute("COPY (SELECT * FROM out ORDER BY block) TO 'data/derived/markout/bbo_t.parquet'")
print(con.execute("SELECT count(*), count(t), min(t), max(t) FROM out").fetchall())
