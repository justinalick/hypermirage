"""Markout curves (role) and by taker order size; hour-block bootstrap 95% CIs. Writes results json."""
import duckdb, numpy as np, json
import sys
sys.path.insert(0, "scripts")
import window as WIN
S = "data/derived/markout/rerun"
R = "data/raw/xyz/fills"
con = duckdb.connect()
b = con.execute(f"select epoch_ns(t)::bigint, (best_bid+best_ask)/2 from 'data/derived/markout/bbo_t.parquet' where t is not null order by t").fetchnumpy()
bt, bmid = [b[k] for k in b]; bt = bt.astype(np.int64)
f = con.execute(f"""
 with t as (select epoch_ns(timestamp::timestamp)::bigint ft, price::double px, size::double sz,
        case when side='buy' then 1 else -1 end s, order_id
   from read_parquet('{R}/*.parquet')
   where coin='xyz:SP500' and crossed and timestamp >= '{WIN.T0}' and timestamp < '{WIN.T1}'),
 o as (select order_id, sum(px*sz) onot from t group by 1)
 select ft, px, sz, s, onot from t join o using(order_id) order by ft""").fetchnumpy()
ft = f['ft'].astype(np.int64); px, sz, s, onot = f['px'], f['sz'], f['s'].astype(float), f['onot']
nt = px*sz
i0 = np.searchsorted(bt, ft, 'left') - 1
ok = i0 >= 0
end = bt[-1]
H = [0, 0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300]
X = {}
for h in H:
    if h == 0:
        m, v = bmid[i0], ok
    else:
        ih = np.searchsorted(bt, ft + int(h*1e9), 'right') - 1
        m, v = bmid[ih], ok & (ft + int(h*1e9) <= end)
    X[h] = (np.nan_to_num(s*(m-px)/px*1e4), v)
hour = ft // (3600*10**9)
uh, hidx = np.unique(hour, return_inverse=True)
rng = np.random.default_rng(7); B = 4000
draws = rng.integers(0, len(uh), (B, len(uh)))
def est(mask):
    o = {}
    for h in H:
        x, v = X[h]; w = nt*(v & mask)
        sw = np.bincount(hidx, w, len(uh)); sx = np.bincount(hidx, x*w, len(uh))
        bs = sx[draws].sum(1)/sw[draws].sum(1)
        o[h] = [float(sx.sum()/sw.sum()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
    return o
allm = np.ones(len(ft), bool)
res = {"all": est(allm)}
buckets = {"< $10k": onot < 1e4, "$10k to $100k": (onot >= 1e4) & (onot < 1e5), ">= $100k": onot >= 1e5}
for k, m in buckets.items():
    res[k] = est(m)
    res[k + "_n_trades"] = int(m.sum()); res[k + "_n_orders"] = None
res["n_trades"] = int(len(ft)); res["notional"] = float(nt.sum()); res["hours"] = int(len(uh))
res["n_orders_by_bucket"] = {k: int(con.execute(f"select count(*) from (select order_id, sum(price::double*size::double) n from read_parquet('{R}/*.parquet') where coin='xyz:SP500' and crossed and timestamp >= '{WIN.T0}' and timestamp < '{WIN.T1}' group by 1) where {q}").fetchone()[0])
    for k, q in {"< $10k": "n<1e4", "$10k to $100k": "n>=1e4 and n<1e5", ">= $100k": "n>=1e5"}.items()}
for k in ["all", *buckets]:
    print(k, {h: [round(x, 3) for x in res[k][h]] for h in [0, 1, 10, 60]})
print(res["n_orders_by_bucket"], {k: res[k+"_n_trades"] for k in buckets})
# fees in bps of notional: taker legs (with and without builder fees), and taker legs by order-size bucket
fee = con.execute(f"""
 with t as (select order_id, crossed, price::double*size::double n, fee::double fee, coalesce(builder_fee::double, 0) bfee
   from read_parquet('{R}/*.parquet') where coin='xyz:SP500' and timestamp >= '{WIN.T0}' and timestamp < '{WIN.T1}'),
 o as (select order_id, sum(n) onot from t where crossed group by 1)
 select sum(fee) filter (where crossed) / sum(n) filter (where crossed) * 1e4,
        sum(fee - bfee) filter (where crossed) / sum(n) filter (where crossed) * 1e4,
        sum(t.fee) filter (where crossed and onot < 1e4) / sum(t.n) filter (where crossed and onot < 1e4) * 1e4
 from t left join o using (order_id)""").fetchone()
res["fees_bps"] = {"taker": fee[0], "taker_ex_builder": fee[1], "taker_lt10k": fee[2]}
print("fees bps", res["fees_bps"])
json.dump(res, open(f"{S}/markout_res.json", "w"), indent=1)
