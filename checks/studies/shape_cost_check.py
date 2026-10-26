"""Independent recompute of analysis/shape_cost/shape_cost.py: shortfall and impact per shape, and the matched
(strata) differences, in SQL. Metaorder volume-weighted prices come from orders.parquet grouped by the ids that
metaorder_shapes/build.py writes (metaorders_shape.parquet index), strata from DuckDB quantiles with the same edges
as pandas.qcut (linear interpolation, right-closed bins). Exit code 1 on a mismatch above 1e-6 bps."""
import json, sys
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/shape_cost/shape_cost.json"))
con = duckdb.connect(); con.execute("SET memory_limit='4GB'; SET threads=4")
con.execute("""CREATE TABLE o AS
  WITH o AS (SELECT * FROM 'data/derived/impact/orders.parquet' WHERE NOT liq),
  s AS (SELECT *, CASE WHEN lag(a) OVER w IS DISTINCT FROM a OR lag(s) OVER w IS DISTINCT FROM s
                         OR t0 - lag(t1) OVER w > 300e9 THEN 1 ELSE 0 END AS new FROM o WINDOW w AS (ORDER BY a, t0, order_id))
  SELECT sum(new) OVER (ORDER BY a, t0, order_id ROWS UNBOUNDED PRECEDING) mo, q, sz FROM s""")
con.execute("CREATE TABLE v AS SELECT mo, sum(q) qq, sum(sz) ssz FROM o GROUP BY mo")
M = pd.read_parquet("data/derived/metaorder_shapes/metaorders_shape.parquet").join(
    pd.read_parquet("data/derived/metaorder_shapes/labels.parquet")[["k3"]], how="inner")
M = M[~M.top].reset_index().rename(columns={"index": "mo"}) if "mo" not in M.columns else M[~M.top]
con.register("m", M[["mo", "k3", "s", "m0", "i0", "q", "V", "n", "dur_s", "pre60", "t0", "day", "acct"]])
d = con.sql("""SELECT m.*, m.s * (v.qq / v.ssz - m.m0) / m.m0 * 1e4 shortfall, m.i0 impact
               FROM m JOIN v ON v.mo = m.mo""").df()
d["sess"] = WIN.session(pd.to_datetime(d.t0))
d = d.dropna(subset=["shortfall", "impact", "dur_s"])
NAMES = {0: "front-loaded", 1: "spread out", 2: "back-loaded"}
ok = True
for y in ("shortfall", "impact"):
    for k, name in NAMES.items():
        got = float(d[d.k3 == k][y].mean()); want = R["raw"][y][name]
        good = abs(got - want) < 1e-6; ok &= good
        print(f"{'OK  ' if good else 'FAIL'} raw {y:9s} {name:12s} recompute {got:+.6f}  shape_cost.json {want:+.6f}")
con.register("d", d)
lx = np.log(d.q / d.V).to_numpy(); ld = np.log1p(d.dur_s).to_numpy()
ex = con.sql("SELECT quantile_cont(lx, [0.1*i for i in range(11)]) FROM (SELECT ln(q / \"V\") lx FROM d)").fetchall()[0][0]
ed = con.sql("SELECT quantile_cont(ld, [i/8 for i in range(9)]) FROM (SELECT ln(1 + dur_s) ld FROM d)").fetchall()[0][0]
d["b_x"] = np.clip(np.searchsorted(np.unique(ex), lx, side="left") - 1, 0, None)
d["b_d"] = np.clip(np.searchsorted(np.unique(ed), ld, side="left") - 1, 0, None)
d["b_n"] = np.searchsorted([3, 5, 8, 15, 40], d.n.to_numpy(), side="left") - 1
p = d.pre60.fillna(0).to_numpy(); d["b_p"] = np.where(p <= -0.5, 0, np.where(p <= 0.5, 1, 2))
d["shape"] = d.k3.map(NAMES)
for y in ("shortfall", "impact"):
    for other in ("front-loaded", "back-loaded"):
        g = d[d["shape"].isin(["spread out", other])].groupby(["b_x", "b_n", "b_d", "sess", "b_p", "shape"])[y].agg(["mean", "size"]).unstack("shape").dropna()
        diff = g[("mean", "spread out")] - g[("mean", other)]
        got = float(np.average(diff, weights=g[("size", "spread out")])); want = R["strata"][f"{y}: spread out - {other}"][0]
        good = abs(got - want) < 1e-6; ok &= good
        print(f"{'OK  ' if good else 'FAIL'} strata {y:9s} spread out - {other:12s} recompute {got:+.6f}  shape_cost.json {want:+.6f}")
print("ALL OK" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)
