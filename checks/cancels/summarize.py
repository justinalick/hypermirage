"""Summaries of my recomputed outputs: amend mix, amend ticks, latency curves. Prints aggregate numbers only."""
import duckdb, json, numpy as np, pandas as pd
W = "data/checks/cancels/work"
con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=2")
# ---- amends ----
a = con.execute(f"""SELECT kind, dir, CASE WHEN x.cls='pre' THEN '0 pre' WHEN x.dist IS NULL THEN 'unknown'
      WHEN round(x.dist,9)<0 THEN '1 improves' WHEN round(x.dist,9)=0 THEN '2 at' WHEN round(x.dist,9)<=1 THEN '3 lt1'
      WHEN round(x.dist,9)<=5 THEN '4 1-5' WHEN round(x.dist,9)<=25 THEN '5 5-25' ELSE '6 gt25' END db,
    least(ticks,20) ticks, count(*) n
  FROM '{W}/amv_*.parquet' a LEFT JOIN (SELECT oid, cls, dist FROM '{W}/orders_*.parquet') x USING (oid) GROUP BY ALL""").df()
tot = a.n.sum(); print("cancels", tot)
mix = a.groupby("kind").n.sum() / tot; print((100 * mix).round(3).to_dict())
po = a[a.kind == "price only"].groupby("dir").n.sum() / tot; print("price only by dir %", (100 * po).round(2).to_dict())
byd = a.groupby(["db", "kind"]).n.sum().unstack().fillna(0); print("replaced share by dist %", (100 * (1 - byd["pure cancel"] / byd.sum(1))).round(2).to_dict())
for d in ["toward", "away"]:
    s = a[(a.kind == "price only") & (a.dir == d)].groupby("ticks").n.sum()
    print(d, "1-3 ticks %", round(100 * s.loc[1:3].sum() / s.sum(), 2), "by tick", (100 * s / s.sum()).round(1).loc[[1, 2, 3, 4, 20]].to_dict())
# ---- latency ----
for mode in ["s30", "all"]:
    try: L = pd.read_parquet(f"{W}/lat_{mode}.parquet")
    except Exception: continue
    L["grp"] = np.where(L.ev == "control", "control", L.ev + np.where(L.mv >= 2, " 2+", " 1"))
    out = {}
    for g, s in L.groupby("grp"):
        n = s.n.sum(); c = s.dropna(subset=["k"]).groupby("k").n.sum().reindex(range(1, 101), fill_value=0).cumsum() / n
        out[g] = dict(n=int(n), b1=round(100 * c.loc[1], 2), b5=round(100 * c.loc[5], 2), b14=round(100 * c.loc[14], 2), b100=round(100 * c.loc[100], 2))
    print(mode, json.dumps(out, indent=0))
    print(mode, "adverse n", out["adverse 1"]["n"] + out["adverse 2+"]["n"], "favorable n", out["favorable 1"]["n"] + out["favorable 2+"]["n"])
