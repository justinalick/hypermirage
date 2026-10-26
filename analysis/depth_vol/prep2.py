"""Depth vs realized volatility: hourly medians (left panel of charts/depth_vol.py) and, within a day,
depth by decile of 15-minute realized vol (right panel). Sessions and day keys come from the
scripts/window.py clock: a futures closure (weekend or holiday) is one day key. Depth is taken relative
to the median for the same UTC hour of day (closed hours separate) and then to the same day key.
Cash and overnight deciles get 90% bootstrap bands over day keys. Futures-closed minutes get bands too
when the window has at least 8 closures; otherwise (the two-week atlas) each closure is shown on its own."""
import sys
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN
S = 'data/derived/depth_vol/'
D = 'data/derived/offhours/offhours_depth_minutes.parquet'
df = duckdb.sql(f"select * from '{D}' order by t").df()
df['r'] = np.log(df.mid).diff() * 1e4
df['rv'] = df.r.rolling(15, min_periods=12).std() * np.sqrt(365 * 1440) / 100
flat = df.r.rolling(15, min_periods=12).max() == df.r.rolling(15, min_periods=12).min()
df.loc[flat, 'rv'] = 0.0                 # equal returns: rolling std leaves float residue instead of 0
h = df.t.dt.hour
s_ = WIN.session(df.t)
wk = s_ == 'closed'
df['g'] = np.where(wk, 'weekend', s_)        # labels: cash, overnight, break, weekend (= futures closed)
df['hod'] = h.astype(str) + np.where(wk, 'w', 'd')
df['rel'] = np.log(df.d10) - df.groupby('hod').d10.transform(lambda s: np.log(s).median())
df['blk'] = WIN.block(df.t)
d = df.dropna(subset=['rv']).copy()
d = d[d.g != 'break']
d['rel2'] = d.rel - d.groupby(['g', 'blk']).rel.transform('median')
print(d[d.g == 'weekend'].groupby('blk').size())
# hourly (left), session at minute 30 of each hour
hr = df.dropna(subset=['rv']).assign(hr=df.t.dt.floor('h'))
mid30 = df[df.t.dt.minute == 30].set_index(df.t[df.t.dt.minute == 30].dt.floor('h')).g.rename('g')
hr = hr.groupby('hr').agg(d10=('d10', 'median'), rv=('rv', 'median')).join(mid30).reset_index()
hr['g'] = hr.g.replace({'weekend': 'closed', 'break': 'closed'}); hr = hr[hr.rv > 0]
print('hours', len(hr), 'rho', np.corrcoef(np.log(hr.d10), np.log(hr.rv))[0, 1].round(3)); hr.to_parquet(S + 'hourly2.parquet')
rng = np.random.default_rng(7); out = []


def dec(gg, key):
    q = pd.qcut(gg.rv.rank(method='first'), 10, labels=False)
    b = gg.assign(q=q).groupby('q').agg(rv=('rv', 'median'), rel=('rel2', 'median')).reset_index(); b['k'] = key; return b, q


n_closed = d[d.g == 'weekend'].blk.nunique()
pooled = ['cash', 'overnight'] + (['weekend'] if n_closed >= 8 else [])
for g in pooled:
    gg = d[d.g == g]; b, q = dec(gg, g if g != 'weekend' else 'closed'); gg = gg.assign(q=q.values)
    days = gg.blk.unique(); by = {x: v for x, v in gg.groupby('blk')}; gs = []; B = []
    for _ in range(1000):
        s = pd.concat([by[x] for x in rng.choice(days, len(days))]); m = s.groupby('q').rel2.median(); B.append(m); gs.append(m[9] - m[0])
    B = pd.concat(B, axis=1); b['lo'] = B.quantile(.05, axis=1).values; b['hi'] = B.quantile(.95, axis=1).values
    print(g, len(gg), len(days), 'gap', round(np.expm1(b.rel[9] - b.rel[0]) * 100, 1), 'CI', np.round(np.expm1(np.quantile(gs, [.05, .95])) * 100, 1))
    out.append(b)
if n_closed < 8:   # the atlas: two weekends, one line each
    for k, gg in d[d.g == 'weekend'].groupby('blk'):
        k = 'W' + k[1:]   # day key of a closure, named as before (W + Friday's MMDD)
        b, _ = dec(gg, k); b['lo'] = np.nan; b['hi'] = np.nan; out.append(b); print(k, len(gg), 'gap', round(np.expm1(b.rel[9] - b.rel[0]) * 100, 1))
pd.concat(out).to_parquet(S + 'deciles2.parquet')
