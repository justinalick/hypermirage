"""Independent cancel/replace classification, xyz:SP500. Plain 'canceled' events of non-trigger orders are
paired 1:1 with 'open' events of the same account, side and block by price rank (pandas cumcount, not SQL
window join). Writes work/amv_<day>.parquet (no addresses: per-cancel rows keyed by oid only).
Also: identical re-placements at the own-side touch (my replayed book) for each day.
Usage: python -P amends_v.py 20261008 [...]"""
import sys, duckdb, numpy as np, pandas as pd
ROOT = "."; W = f"{ROOT}/data/checks/cancels/work"
for d in sys.argv[1:]:
    con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=2")
    e = con.execute(f"""SELECT hash(user) uh, side, block_number b, status='canceled' isc, oid, limit_px px, sz, orig_sz
      FROM '{ROOT}/data/l4/order_statuses/xyz_SP500/{d}/*.parquet'
      WHERE coin='xyz:SP500' AND status IN ('open','canceled') AND NOT coalesce(is_trigger,false)""").df()
    e = e.sort_values(["uh", "side", "b", "isc", "px", "oid"], kind="mergesort")
    e["rk"] = e.groupby(["uh", "side", "b", "isc"], sort=False).cumcount()
    c = e[e.isc].drop(columns="isc"); o = e[~e.isc][["uh", "side", "b", "rk", "oid", "px", "orig_sz"]]
    o = o.rename(columns={"oid": "new_oid", "px": "new_px", "orig_sz": "new_sz"})
    m = c.merge(o, on=["uh", "side", "b", "rk"], how="left")
    del e, c, o
    eq_px = m.new_px == m.px; eq_sz = (m.new_sz - m.sz).abs() < 1e-9
    m["kind"] = np.select([m.new_oid.isna(), eq_px & eq_sz, eq_px, eq_sz],
                          ["pure cancel", "identical", "size only", "price only"], "price and size")
    up = m.new_px > m.px
    m["dir"] = np.where(m.new_oid.isna() | eq_px, None, np.where((m.side == "B") == up, "toward", "away"))
    m["ticks"] = np.round((m.new_px - m.px).abs() / 0.1)
    con.register("m", m[["oid", "b", "side", "px", "new_oid", "new_px", "kind", "dir", "ticks"]])
    con.execute(f"""COPY (SELECT m.*, CASE WHEN x.cls='pre' THEN '0 pre' WHEN x.dist IS NULL THEN 'unknown'
          WHEN x.dist<0 THEN '1 improves' WHEN x.dist=0 THEN '2 at' WHEN x.dist<=1 THEN '3 lt1' WHEN x.dist<=5 THEN '4 1-5'
          WHEN x.dist<=25 THEN '5 5-25' ELSE '6 gt25' END db
        FROM m LEFT JOIN '{W}/orders_{d}.parquet' x USING (oid)) TO '{W}/amv_{d}.parquet' (FORMAT parquet)""")
    # identical re-placements: is the new price the own-side best? (a) end of previous block, (b) end of same block
    r = con.execute(f"""WITH i AS (SELECT * FROM '{W}/amv_{d}.parquet' WHERE kind='identical'),
        k AS (SELECT * FROM '{W}/bbo_{d}.parquet')
      SELECT count(*) n,
        count(*) FILTER (WHERE (side='B' AND new_px=p.bb) OR (side='A' AND new_px=p.ba)) at_prev,
        count(*) FILTER (WHERE (side='B' AND new_px=q.bb) OR (side='A' AND new_px=q.ba)) at_same
      FROM i ASOF LEFT JOIN k p ON p.block < i.b ASOF LEFT JOIN k q ON q.block <= i.b""").fetchone()
    print(d, len(m), r, flush=True)
