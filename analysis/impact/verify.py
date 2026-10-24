"""Independent re-derivation (DuckDB ASOF joins, plain loops) of the numbers in build/robust/bookwalk."""
import duckdb, numpy as np, pandas as pd, json
R = "."; O = f"{R}/data/derived/impact"
con = duckdb.connect(); con.execute("SET TimeZone='UTC'")
o = pd.read_parquet(f"{O}/orders.parquet")
# 1) single-order impact via ASOF join, on all orders
v = con.execute(f"""
 with f as (select order_id, any_value(side) side, min(timestamp::timestamp) t0, max(timestamp::timestamp) t1
            from read_parquet('{R}/data/raw/xyz/fills/2026-10-*.parquet')
            where coin='xyz:SP500' and crossed and timestamp>='2026-10-08' and timestamp<'2026-10-22' group by 1),
 b as (select t, (best_bid+best_ask)/2 m from '{R}/data/derived/markout/bbo_t.parquet'
       where t is not null and best_bid is not null and best_ask is not null and best_ask>best_bid),
 pre as (select f.*, b.m m0 from f asof join b on b.t < f.t0),
 post as (select pre.*, b.m m1 from pre asof join b on b.t <= pre.t1 + interval 250 millisecond)
 select order_id, case when side='buy' then 1 else -1 end*(m1-m0)/m0*1e4 i0_chk from post""").df()
j = o.merge(v, on='order_id')
d = (j.i0 - j.i0_chk).abs()
print('1) order i0: n', len(j), 'max abs diff', d.max(), 'n diff>1e-9', int((d > 1e-9).sum()), 'mean i0', j.i0.mean(), j.i0_chk.mean())
# 2) daily sigma and V
s2 = con.execute(f"""with b as (select time_bucket(interval 1 minute, t) mn, arg_max((best_bid+best_ask)/2, t) m
     from '{R}/data/derived/markout/bbo_t.parquet' where t is not null and best_ask>best_bid group by 1),
     r as (select mn, ln(m) - ln(lag(m) over (order by mn)) r from b)
     select strftime(mn, '%Y%m%d') d, stddev_samp(r)*sqrt(1440)*1e4 sig, count(*) from r where r is not null group by 1 order by 1""").df()
print('2) sigma check (gap minutes not ffilled here):'); print(pd.concat([s2.set_index('d').sig.round(1), o.groupby('day').sig_d_bps.first().round(1)], axis=1).T.to_string())
V2 = con.execute(f"""select strftime(timestamp::timestamp,'%Y%m%d') d, sum(price::double*size::double)/1e6 from read_parquet('{R}/data/raw/xyz/fills/2026-10-*.parquet')
     where coin='xyz:SP500' and crossed and timestamp>='2026-10-08' and timestamp<'2026-10-22' group by 1 order by 1""").fetchall()
print('   V diff max ($M):', max(abs(x - o[o.day == dd].V_d.iloc[0] / 1e6) for dd, x in V2))
# 3) metaorders by explicit loop (G=300s, ex liquidations): compare count and peak impact with robust.meta
exec(open(f"{O}/robust.py").read().split("out = {}")[0])  # loads meta(), fitnorm()
ol = o[~o.liq].sort_values(['a', 't0'])
b = con.execute(f"select epoch_ns(t)::bigint, (best_bid+best_ask)/2 from '{R}/data/derived/markout/bbo_t.parquet' where t is not null and best_ask>best_bid order by t").fetchnumpy()
bt, bm = [b[k] for k in b]
recs = []
for a, g in ol.groupby('a', sort=False):
    cur = None
    for r in g.itertuples():
        if cur and r.s == cur['s'] and r.t0 - cur['t1'] <= 300e9:
            cur['t1'] = max(cur['t1'], r.t1); cur['q'] += r.q
        else:
            if cur: recs.append(cur)
            cur = dict(s=r.s, t0=r.t0, t1=r.t1, q=r.q)
    recs.append(cur)
L = pd.DataFrame(recs)
i = np.searchsorted(bt, L.t0.values, 'left') - 1; m0 = bm[i]
k = np.searchsorted(bt, L.t1.values + 250_000_000, 'right') - 1; m1 = bm[k]
L['i0'] = L.s * (m1 - m0) / m0 * 1e4
L.loc[L.t1 + 250_000_000 > bt[-1], 'i0'] = np.nan
M = meta(o[~o.liq], 300)
print('3) metaorders loop', len(L), 'vs meta()', len(M), '| mean i0', round(L.i0.mean(), 5), round(M.i0.mean(), 5),
      '| q-weighted', round(np.nansum(L.i0 * L.q) / L.q[L.i0.notna()].sum(), 5), round((M.i0 * M.q).sum() / M.q.sum(), 5))
# 4) book walk on one snapshot by hand
row = con.execute(f"select asks, bids from '{R}/data/raw/xyz/book_1m/SP500/2026-10-15.parquet' limit 1 offset 700").fetchone()
ap = [(float(x['px']), float(x['sz'])) for x in row[0]]; bb = float(row[1][0]['px']); mid = (ap[0][0] + bb) / 2
for Q in (1e4, 1e5, 4.6e5):
    left = Q; j_ = 0
    while j_ < len(ap) and left >= ap[j_][0] * ap[j_][1]: left -= ap[j_][0] * ap[j_][1]; j_ += 1
    print(f'4) Q ${Q:,.0f}: walk reaches level {j_}, mid shift {((ap[j_][0] + bb) / 2 - mid) / mid * 1e4 if j_ < len(ap) else float("nan"):.3f} bps')
