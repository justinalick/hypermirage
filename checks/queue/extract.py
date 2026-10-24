"""Heavy extraction (run under flock): SP500 maker fills from Reservoir, and oid->account map for opens."""
import duckdb, os
D = "data"; W = "data/checks/queue/work"
c = duckdb.connect(); c.execute("SET memory_limit='2GB'; SET threads=2")
if not os.path.exists(f"{W}/maker_fills.parquet"):
    c.execute(f"""COPY (SELECT order_id AS oid, CAST(size AS DOUBLE) sz, CAST(price AS DOUBLE) px,
        epoch_ms(timestamp) t_ms, trade_id, crossed, twap_id
        FROM read_parquet('{D}/raw/xyz/fills/2026-10-*.parquet') WHERE coin='xyz:SP500')
        TO '{W}/sp_fills.parquet' (FORMAT parquet)""")
    c.execute(f"COPY (SELECT * FROM '{W}/sp_fills.parquet' WHERE NOT crossed) TO '{W}/maker_fills.parquet' (FORMAT parquet)")
if not os.path.exists(f"{W}/oid_user.parquet"):
    c.execute(f"""COPY (SELECT DISTINCT oid, "user" AS acct FROM read_parquet('{D}/l4/order_statuses/xyz_SP500/*/*.parquet')
        WHERE status='open' AND coin='xyz:SP500') TO '{W}/oid_user.parquet' (FORMAT parquet)""")
print("done")
