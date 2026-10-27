"""When do takers lead the price, and do the same takers lead every month? xyz:SP500, every day of the run window.
Taker markouts (mid h seconds after the fill vs the fill price, bps, notional-weighted) as in
analysis/taker_clusters/mk.py, by hour of the week in New York time, all takers and all but the largest taker
cluster (T1); and by month for the ten largest taker clusters (sub-accounts under one master, labeled T1.. by
notional). Writes data/derived/taker_hours/hours.json; no address is written."""
import json, os, sys
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN

D = "data/derived/taker_clusters"
O = "data/derived/taker_hours"
os.makedirs(O, exist_ok=True)
con = duckdb.connect(); con.execute("SET memory_limit='3GB'; SET threads=2")
b = con.execute("select epoch_ns(t)::bigint, (best_bid+best_ask)/2 from 'data/derived/markout/bbo_t.parquet' where t is not null order by t").fetchnumpy()
bt, bmid = [b[k] for k in b]; bt = bt.astype(np.int64)
FILES = [f"data/raw/xyz/fills/{d}.parquet" for d in WIN.ISO]
f = con.execute(f"""
 with t as (select epoch_ns(timestamp::timestamp)::bigint ft, price::double px, size::double sz,
        case when side='B' or side='buy' then 1 else -1 end s, address
   from read_parquet({FILES}) where coin='xyz:SP500' and crossed and timestamp >= '{WIN.T0}' and timestamp < '{WIN.T1}')
 select ft, px, sz, s, cm.cluster c from t join read_csv('{D}/cluster_map.csv') cm using(address) order by ft""").fetchnumpy()
ft = f["ft"].astype(np.int64); px, s = f["px"], f["s"].astype(float); nt = px * f["sz"]; c = f["c"].astype(str)
del f
tot = pd.Series(nt).groupby(c).sum().sort_values(ascending=False)
lab = {k: f"T{i + 1}" for i, k in enumerate(tot.index[:10])}
T1 = c == tot.index[0]
i0 = np.searchsorted(bt, ft, "left") - 1; ok = i0 >= 0; end = bt[-1]
X = {}
for h in (10, 60):
    ih = np.searchsorted(bt, ft + h * 10**9, "right") - 1
    x = s * (bmid[ih] - px) / px * 1e4                              # a fill with no mid is left out, not counted as 0
    X[h] = (np.nan_to_num(x), ok & (ft + h * 10**9 <= end) & np.isfinite(x))
ts = pd.to_datetime(ft, unit="ns", utc=True).tz_convert("America/New_York")
how = (ts.dayofweek * 24 + ts.hour).to_numpy()                       # hour of week, Monday 00:00 New York = 0
mon = ts.strftime("%Y-%m").to_numpy()
res = {"window": WIN.span(), "tz": "America/New_York", "n_fills": int(len(ft)), "T1_share": float(nt[T1].sum() / nt.sum()),
       "how": {}, "months": sorted(set(mon)), "clusters": {}}
for name, m in (("all", np.ones(len(ft), bool)), ("ex_T1", ~T1)):
    g = {}
    for h in (10, 60):
        x, v = X[h]; w = nt * (v & m)
        g[f"mk{h}"] = (np.bincount(how, x * w, 168) / np.maximum(np.bincount(how, w, 168), 1e-9)).tolist()
    g["notional"] = np.bincount(how, nt * m, 168).tolist()
    res["how"][name] = g
x, v = X[60]
for k, L in lab.items():
    m = (c == k) & v
    res["clusters"][L] = {"notional": float(tot[k]),
                          "mk60_by_month": [float((x * nt)[m & (mon == mm)].sum() / max(nt[m & (mon == mm)].sum(), 1e-9))
                                            if (m & (mon == mm)).sum() >= 200 else None for mm in res["months"]],
                          "notional_by_month": [float(nt[(c == k) & (mon == mm)].sum()) for mm in res["months"]]}
json.dump(res, open(f"{O}/hours.json", "w"), indent=1)
a = np.array(res["how"]["all"]["mk60"]); n = np.array(res["how"]["all"]["notional"])
print(f"{len(ft):,} taker fills; T1 share {res['T1_share']:.1%}")
print("hour-of-week 60s markout: min", round(a[n > 0].min(), 2), "max", round(a[n > 0].max(), 2))
for L, r in res["clusters"].items():
    print(L, [None if v_ is None else round(v_, 2) for v_ in r["mk60_by_month"]])
