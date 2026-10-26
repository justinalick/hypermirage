"""Cancel-replace ("amend") pairs, xyz:SP500. A cancel of oid X and an open of a new oid Y by the
same account on the same side in the same block. Pairs are matched 1:1 within (user, side, block)
by price rank. Native modify and separate cancel+place cannot be told apart in these data."""
import sys, duckdb
ROOT = "."
days = sys.argv[1:]
con = duckdb.connect(); con.execute("SET threads=4; SET memory_limit='4GB'")
for d in days:
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE e AS SELECT user, oid, side, block_number b, status, limit_px px, sz, orig_sz
      FROM '{ROOT}/data/l4/order_statuses/xyz_SP500/{d}/*.parquet'
      WHERE status IN ('open','canceled') AND NOT coalesce(is_trigger,false);
    CREATE OR REPLACE TEMP TABLE c AS SELECT *, row_number() OVER (PARTITION BY user, side, b ORDER BY px, oid) r,
      count(*) OVER (PARTITION BY user, side, b) n FROM e WHERE status='canceled';
    CREATE OR REPLACE TEMP TABLE o AS SELECT *, row_number() OVER (PARTITION BY user, side, b ORDER BY px, oid) r,
      count(*) OVER (PARTITION BY user, side, b) n FROM e WHERE status='open';
    COPY (
      SELECT '{d}' AS day, c.user, c.side, c.b, c.oid old_oid, c.px old_px, c.sz old_sz, c.orig_sz old_orig,
             o.oid new_oid, o.px new_px, o.orig_sz new_sz, c.n nc, o.n no
      FROM c LEFT JOIN o ON c.user=o.user AND c.side=o.side AND c.b=o.b AND c.r=o.r
    ) TO '{ROOT}/data/derived/cancels/amends_{d}.parquet'""")
    print(d, con.execute(f"SELECT count(*), count(new_oid) FROM '{ROOT}/data/derived/cancels/amends_{d}.parquet'").fetchone(), flush=True)
