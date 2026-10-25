"""Price impact vs signed size, xyz:SP500, every day of the run window (scripts/window.py). Builds taker-order and metaorder tables
with pre/post mids from the replayed BBO (data/derived/markout/bbo_t.parquet)."""
import duckdb, numpy as np, pandas as pd
import sys
sys.path.insert(0, "scripts")
import window as WIN
R = "."
O = f"{R}/data/derived/impact"
con = duckdb.connect()
b = con.execute(f"select epoch_ns(t)::bigint t, (best_bid+best_ask)/2 m, best_ask-best_bid sp from '{R}/data/derived/markout/bbo_t.parquet' "
                "where t is not null and best_bid is not null and best_ask is not null and best_ask>best_bid order by t").fetchnumpy()
bt, bm = b['t'].astype(np.int64), b['m']
# taker orders
o = con.execute(f"""
 select address a, order_id, any_value(side) side, min(epoch_ns(timestamp::timestamp))::bigint t0,
        max(epoch_ns(timestamp::timestamp))::bigint t1, sum(price::double*size::double) q,
        sum(size::double) sz, count(*) nf, bool_or(is_liquidation) liq, max(coalesce(twap_id,0)) twap
 from read_parquet('{R}/data/raw/xyz/fills/*.parquet')
 where coin='xyz:SP500' and crossed and timestamp >= '{WIN.T0}' and timestamp < '{WIN.T1}'
 group by 1,2 order by t0""").df()
o['s'] = np.where(o.side == 'buy', 1, -1)
def mid_before(t):  # last change strictly before t
    i = np.searchsorted(bt, t, 'left') - 1; return np.where(i >= 0, bm[np.maximum(i, 0)], np.nan)
def mid_at(t):      # last change <= t
    i = np.searchsorted(bt, t, 'right') - 1; return np.where(i >= 0, bm[np.maximum(i, 0)], np.nan)
END = bt[-1]
def add(df, t0, t1, s):
    m0 = mid_before(t0); df['m0'] = m0
    df['pre60'] = s * (m0 - mid_before(t0 - 60_000_000_000)) / m0 * 1e4   # pre-trend
    for name, h in [('i0', 0.25), ('i10', 10), ('i60', 60), ('i300', 300)]:
        th = t1 + int(h * 1e9)
        df[name] = np.where(th <= END, s * (mid_at(th) - m0) / m0 * 1e4, np.nan)
add(o, o.t0.values, o.t1.values, o.s.values)
o['day'] = pd.to_datetime(o.t0).dt.strftime('%Y%m%d')
# daily volume (one leg) and daily vol of 1-min mid log returns
mm = pd.Series(bm, index=pd.to_datetime(bt)).resample('1min').last().ffill()
r = np.log(mm).diff().dropna()
sig = (r.groupby(r.index.strftime('%Y%m%d')).std() * np.sqrt(1440) * 1e4).rename('sig_d_bps')
V = o.groupby('day').q.sum().rename('V_d')
o = o.join(sig, on='day').join(V, on='day')
o.drop(columns=['side']).to_parquet(f"{O}/orders.parquet")
# metaorders: same account, same sign, consecutive taker orders with gap <= G; sign flip or gap ends it
G = 300e9
o = o.sort_values(['a', 't0', 'order_id'], kind='mergesort').reset_index(drop=True)
new = (o.a != o.a.shift()) | (o.s != o.s.shift()) | ((o.t0 - o.t1.shift()) > G)
o['mo'] = new.cumsum()
M = o.groupby('mo').agg(a=('a', 'first'), s=('s', 'first'), t0=('t0', 'min'), t1=('t1', 'max'), q=('q', 'sum'),
                        n=('order_id', 'size'), twap=('twap', 'max'), day=('day', 'first'), sig_d_bps=('sig_d_bps', 'first'), V_d=('V_d', 'first'))
add(M, M.t0.values, M.t1.values, M.s.values)
M['dur_s'] = (M.t1 - M.t0) / 1e9
# market share of volume during metaorder (participation)
M.drop(columns=['a']).assign(acct=pd.factorize(M.a)[0]).to_parquet(f"{O}/metaorders.parquet")
print(len(o), 'orders;', len(M), 'metaorders;', (M.n > 1).sum(), 'with >1 order')
print(sig.round(1).to_dict()); print((V / 1e6).round(0).to_dict())
