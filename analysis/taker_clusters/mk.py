"""Taker markouts at 1/10/60s by taker cluster (sub-accounts under master) and by ES session."""
import duckdb, numpy as np, pandas as pd, json
import sys
sys.path.insert(0, "scripts")
import window as WIN
D = "data/derived/taker_clusters"
B = "data/derived/markout/bbo_t.parquet"
R = "data/raw/xyz/fills"
con = duckdb.connect()
b = con.execute(f"select epoch_ns(t)::bigint, (best_bid+best_ask)/2 from '{B}' where t is not null order by t").fetchnumpy()
bt, bmid = [b[k] for k in b]; bt = bt.astype(np.int64)
f = con.execute(f"""
 with t as (select epoch_ns(timestamp::timestamp)::bigint ft, price::double px, size::double sz,
        case when side='B' or side='buy' then 1 else -1 end s, order_id, trade_id, address
   from read_parquet('{R}/*.parquet')
   where coin='xyz:SP500' and crossed and timestamp >= '{WIN.T0}' and timestamp < '{WIN.T1}'),
 cm as (select * from read_csv('{D}/cluster_map.csv')),
 mk as (select trade_id, any_value(address) maddr from read_parquet('{R}/*.parquet')
   where coin='xyz:SP500' and not crossed and timestamp >= '{WIN.T0}' and timestamp < '{WIN.T1}' group by 1)
 select ft, px, sz, s, t.cluster c, coalesce(m2.cluster, mk.maddr) mc, extract(dow from to_timestamp(ft/1e9) at time zone 'UTC') dow,
   extract(hour from to_timestamp(ft/1e9) at time zone 'UTC')*60+extract(minute from to_timestamp(ft/1e9) at time zone 'UTC') mod
 from (t join cm using(address)) t left join mk using(trade_id) left join cm m2 on m2.address=mk.maddr order by ft""").fetchnumpy()
ft = f['ft'].astype(np.int64); px, sz, s = f['px'], f['sz'], f['s'].astype(float); nt = px*sz
c = f['c'].astype(str); mc = f['mc'].astype(str); dow = f['dow'].astype(int); mod = f['mod'].astype(int)
print("side check", np.unique(s, return_counts=True))
# ES session from the scripts/window.py clock (CME Globex in Chicago time, NYSE hours, holidays):
# ES closed = weekends, holiday closures and the daily halt; Cash hours = NYSE session
wk = (dow >= 1) & (dow <= 5)
_s = WIN.session(pd.to_datetime(ft, unit="ns", utc=True))
sess = np.where(np.isin(_s, ["closed", "break"]), "ES closed", np.where(_s == "cash", "Cash hours", "ES overnight"))
i0 = np.searchsorted(bt, ft, 'left') - 1; ok = i0 >= 0; end = bt[-1]
H = [0, 1, 10, 60]; X = {}
for h in H:
    if h == 0: m, v = bmid[i0], ok
    else:
        ih = np.searchsorted(bt, ft + int(h*1e9), 'right') - 1; m, v = bmid[ih], ok & (ft + int(h*1e9) <= end)
    X[h] = (np.nan_to_num(s*(m-px)/px*1e4), v)
hour = ft // (3600*10**9); uh, hidx = np.unique(hour, return_inverse=True)
rng = np.random.default_rng(7); draws = rng.integers(0, len(uh), (2000, len(uh)))
def est(mask):
    o = {"n": int(mask.sum()), "notional": float(nt[mask].sum())}
    for h in H:
        x, v = X[h]; w = nt*(v & mask)
        sw = np.bincount(hidx, w, len(uh)); sx = np.bincount(hidx, x*w, len(uh))
        bs = sx[draws].sum(1)/np.maximum(sw[draws].sum(1), 1e-9)
        o[h] = [float(sx.sum()/sw.sum()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
    return o
tot = {}
for k in np.unique(c): tot[k] = nt[c == k].sum()
rank = sorted(tot, key=lambda k: -tot[k]); lab = {k: f"T{i+1}" for i, k in enumerate(rank[:10])}
res = {"clusters": {}, "sessions": {}, "makers_vs_T1": {}, "meta": {}}
T1 = c == rank[0]
for k in rank[:10]: res["clusters"][lab[k]] = est(c == k)
res["clusters"]["T11+ (rest)"] = est(~np.isin(c, rank[:10]))
res["clusters"]["All except T1"] = est(~T1)
res["clusters"]["All"] = est(np.ones(len(c), bool))
for ss in ["Cash hours", "ES overnight", "ES closed"]:
    sm = sess == ss
    res["sessions"][ss] = {"T1": est(T1 & sm), "Others": est(~T1 & sm),
        "hours": int(len(np.unique(hour[sm]))), "T1_share": float(nt[T1 & sm].sum()/nt[sm].sum()),
        "T1_notional_share_of_T1": float(nt[T1 & sm].sum()/nt[T1].sum()), "all_share_of_all": float(nt[sm].sum()/nt.sum())}
# makers T1 hits: top 5 maker clusters by notional vs T1
mt = {}
for k in np.unique(mc[T1]): mt[k] = nt[T1 & (mc == k)].sum()
mr = sorted(mt, key=lambda k: -mt[k])[:5]
for i, k in enumerate(mr):
    e = est(T1 & (mc == k)); e["share_of_T1"] = float(mt[k]/nt[T1].sum()); res["makers_vs_T1"][f"M{i+1}"] = e
res["meta"] = {"hours": int(len(uh)), "n": int(len(ft)), "notional": float(nt.sum()), "T1_share": float(nt[T1].sum()/nt.sum())}
# hours with zero T1 activity per session; T1 hourly notional by hour-of-week
hw = ((dow*24 + mod//60)).astype(int)
res["T1_by_utc_hour_weekday"] = [float(nt[T1 & wk & (mod//60 == hh)].sum()) for hh in range(24)]
res["oth_by_utc_hour_weekday"] = [float(nt[~T1 & wk & (mod//60 == hh)].sum()) for hh in range(24)]
json.dump(res, open(f"{D}/mk_res.json", "w"), indent=1)
json.dump({lab[k]: k for k in lab}, open(f"{D}/labels_local.json", "w"))
def p(n, e): print(f"{n:16s} n={e['n']:7d} ${e['notional']/1e6:7.0f}M " + " ".join(f"{h}s {e[h][0]:+.2f}[{e[h][1]:+.2f},{e[h][2]:+.2f}]" for h in H))
for k, e in res["clusters"].items(): p(k, e)
for ss, d in res["sessions"].items():
    print(ss, "hours", d["hours"], "T1 share", round(d["T1_share"], 3), "T1 frac", round(d["T1_notional_share_of_T1"], 3), "all frac", round(d["all_share_of_all"], 3))
    p(" T1", d["T1"]); p(" Others", d["Others"])
for k, e in res["makers_vs_T1"].items(): print(k, round(e["share_of_T1"], 3)); p(" vsT1", e)
