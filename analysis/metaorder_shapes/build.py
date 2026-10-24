"""Per-metaorder execution-shape features, xyz:SP500 2026-10-08..21.
Rebuilds metaorders from data/derived/impact/orders.parquet with the same rule (same account, same side, gap <= 300 s,
liquidations excluded as in plot.py) and keeps the child-order sequence of each one."""
import numpy as np, pandas as pd
R = "."; O = f"{R}/data/derived/metaorder_shapes"
o = pd.read_parquet(f"{R}/data/derived/impact/orders.parquet"); o = o[~o.liq]
top = o.groupby('a').q.sum().idxmax()
o = o.sort_values(['a', 't0']).reset_index(drop=True)
o['mo'] = ((o.a != o.a.shift()) | (o.s != o.s.shift()) | ((o.t0 - o.t1.shift()) > 300e9)).cumsum()
g = o.groupby('mo')
M = g.agg(a=('a', 'first'), s=('s', 'first'), t0=('t0', 'min'), t1=('t1', 'max'), q=('q', 'sum'), n=('order_id', 'size'),
          nf=('nf', 'sum'), twap=('twap', lambda x: (x > 0).mean()), m0=('m0', 'first'), pre60=('pre60', 'first'),
          sig=('sig_d_bps', 'first'), V=('V_d', 'first'), day=('day', 'first'), qmax=('q', 'max'))
last = o.loc[g.t1.idxmax().values].set_index('mo')
for h in ['i0', 'i10', 'i60', 'i300']:   # mid h after last fill vs mid before first fill, signed, bps
    M[h] = M.s * (last.m0 * (1 + last.s * last[h] / 1e4) - M.m0) / M.m0 * 1e4
M['dur_s'] = (M.t1 - M.t0) / 1e9
M['top'] = M.a == top
# child-order shape: cumulative notional fraction on a normalized time grid (21 points), regularity stats
K = 21; grid = np.linspace(0, 1, K)
multi = M.index[M.n >= 4]
oo = o[o.mo.isin(multi)]
curves = {}; feats = []
for mo, d in oo.groupby('mo', sort=True):
    t = d.t0.values.astype(float); q = d.q.values; T = t[-1] - t[0]
    u = (t - t[0]) / T if T > 0 else np.zeros_like(t)
    cf = np.cumsum(q) / q.sum()
    curves[mo] = cf[np.searchsorted(u, grid, 'right') - 1]
    dt = np.diff(t) / 1e9
    feats.append((mo, q.std() / q.mean(), dt.std() / dt.mean() if dt.mean() > 0 else np.nan, np.median(dt),
                  (np.abs(q / np.median(q) - 1) < 0.02).mean()))
F = pd.DataFrame(feats, columns=['mo', 'size_cv', 'gap_cv', 'gap_med_s', 'same_clip_share']).set_index('mo')
M = M.join(F)
C = pd.DataFrame.from_dict(curves, orient='index', columns=[f'c{i}' for i in range(K)])
M.drop(columns=['a']).assign(acct=pd.factorize(M.a)[0]).to_parquet(f"{O}/metaorders_shape.parquet")
C.to_parquet(f"{O}/curves.parquet")
print(len(M), 'metaorders;', (M.n > 1).sum(), '>1 order;', len(multi), '>=4 orders;', int(M[M.n >= 4].top.sum()), 'of those from largest taker')
print(M[M.n >= 4][['n', 'dur_s', 'q', 'size_cv', 'gap_cv', 'gap_med_s', 'same_clip_share', 'twap']].describe().round(3).to_string())
print('notional share n>=4:', M[M.n >= 4].q.sum() / M.q.sum(), ' n==1:', M[M.n == 1].q.sum() / M.q.sum())
