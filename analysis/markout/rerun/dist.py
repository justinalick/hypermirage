import duckdb, numpy as np, json
S = "data/derived/markout/rerun"
R = "data/raw/xyz/fills"
con = duckdb.connect()
b = con.execute(f"select epoch_ns(t)::bigint, (best_bid+best_ask)/2 from 'data/derived/markout/bbo_t.parquet' where t is not null order by t").fetchnumpy()
bt, bmid = [b[k] for k in b]; bt = bt.astype(np.int64)
f = con.execute(f"""
 with t as (select epoch_ns(timestamp::timestamp)::bigint ft, price::double px, size::double sz,
        case when side='buy' then 1 else -1 end s, order_id
   from read_parquet('{R}/2026-10-*.parquet')
   where coin='xyz:SP500' and crossed and timestamp >= '2026-10-08' and timestamp < '2026-10-22'),
 o as (select order_id, sum(px*sz) onot from t group by 1)
 select ft, px, sz, s, onot from t join o using(order_id) order by ft""").fetchnumpy()
ft = f['ft'].astype(np.int64); px, sz, s, onot = f['px'], f['sz'], f['s'].astype(float), f['onot']
nt = px*sz; end = bt[-1]
hour = ft // (3600*10**9); uh, hidx = np.unique(hour, return_inverse=True)
buckets = {"lt10k": onot < 1e4, "10k_100k": (onot >= 1e4) & (onot < 1e5), "ge100k": onot >= 1e5}
out = {"hours": int(len(uh))}
for h in [1, 10, 60]:
    ih = np.searchsorted(bt, ft + int(h*1e9), 'right') - 1
    v = ft + int(h*1e9) <= end
    x = s*(bmid[ih]-px)/px*1e4
    print(h, "per-trade pctl", np.round(np.percentile(x[v], [1,5,25,50,75,95,99]),2), "share exactly 0:", np.mean(np.abs(x[v])<1e-9).round(3))
    for k, m in buckets.items():
        mm = m & v; w = nt*mm
        sw = np.bincount(hidx, w, len(uh)); sx = np.bincount(hidx, np.nan_to_num(x)*w, len(uh))
        cnt = np.bincount(hidx, mm.astype(float), len(uh))
        keep = cnt >= 5
        hm = sx[keep]/sw[keep]
        out[f"{k}_{h}"] = hm.tolist()
        print(" ", k, "hours", keep.sum(), "hourly pctl", np.round(np.percentile(hm,[5,25,50,75,95]),2))
json.dump(out, open(f"{S}/hourly.json","w"))
