"""Robustness: normalized fits on x>=1e-5, metaorder gap sensitivity, TWAPs, $-binned vs book walk."""
import numpy as np, pandas as pd, json
O = "data/derived/impact"
rng = np.random.default_rng(5)
o = pd.read_parquet(f"{O}/orders.parquet"); o = o[~o.liq]
def meta(o, G):
    o = o.sort_values(['a', 't0', 'order_id'], kind='mergesort').reset_index(drop=True)
    new = (o.a != o.a.shift()) | (o.s != o.s.shift()) | ((o.t0 - o.t1.shift()) > G * 1e9)
    o['mo'] = new.cumsum()
    # peak impact: mid just after last fill vs mid before first fill, recomputed from order-level mids
    g = o.groupby('mo')
    M = g.agg(q=('q', 'sum'), n=('q', 'size'), m0=('m0', 'first'), s=('s', 'first'), t0=('t0', 'min'),
              sig=('sig_d_bps', 'first'), V=('V_d', 'first'), pre60=('pre60', 'first'))
    last = o.loc[g.t1.idxmax().values]
    # i0 of last order is relative to its own m0; convert to mid level then to metaorder start
    m_end = last.m0.values * (1 + last.s.values * last.i0.values / 1e4)
    M['i0'] = M.s * (m_end - M.m0) / M.m0 * 1e4
    return M
def fitnorm(M, col='i0', lo=1e-5, hi=1e-2, B=1000):
    M = M.dropna(subset=[col]); x = M.q / M.V
    M = M[(x >= lo) & (x < hi)]; x = M.q / M.V
    e = np.logspace(np.log10(lo), np.log10(hi), 10); b = np.digitize(x, e) - 1
    hr = (M.t0 // (3600 * 10**9)).values; uh, hi_ = np.unique(hr, return_inverse=True)
    y = (M[col] / M.sig).values
    S = np.zeros((len(uh), 9)); C = np.zeros_like(S); X = np.zeros_like(S)
    np.add.at(S, (hi_, b), y); np.add.at(C, (hi_, b), 1); np.add.at(X, (hi_, b), x.values)
    def f(Sx, Cx, Xx):
        I = Sx / Cx; xx = Xx / Cx; g = (Cx >= 30) & (I > 0)
        if g.sum() < 3: return np.nan, np.nan
        sl, ic = np.polyfit(np.log(xx[g]), np.log(I[g]), 1)
        Y = np.sum(Sx[g]) / np.sum(Cx[g] * np.sqrt(xx[g]))   # sqrt-law prefactor: mean(I/sig) / sqrt(x)
        return sl, Y
    d0, Y0 = f(S.sum(0), C.sum(0), X.sum(0))
    bs = [f(*(A[k].sum(0) for A in (S, C, X))) for k in rng.integers(0, len(uh), (B, len(uh)))]
    bs = np.array(bs)
    return dict(n=int(len(M)), delta=round(d0, 3), delta_ci=np.nanpercentile(bs[:, 0], [2.5, 97.5]).round(3).tolist(),
                Y=round(Y0, 3), Y_ci=np.nanpercentile(bs[:, 1], [2.5, 97.5]).round(3).tolist())
out = {}
out['orders_i0'] = fitnorm(o.rename(columns={'sig_d_bps': 'sig', 'V_d': 'V'}))
for G in [10, 60, 300, 1800]:
    M = meta(o, G)
    out[f'meta_G{G}'] = fitnorm(M)
    out[f'meta_G{G}_pretrend_small'] = fitnorm(M, 'pre60')
    print(G, out[f'meta_G{G}'], 'pre60 fit', out[f'meta_G{G}_pretrend_small'])
print('orders', out['orders_i0'])
# multi-order metaorders only, and TWAP-tagged orders grouped by twap id
M = meta(o, 300); out['meta_G300_multi'] = fitnorm(M[M.n > 1]); print('multi', out['meta_G300_multi'])
tw = o[o.twap > 0].copy(); tw['a'] = tw.twap.astype(str)
Mt = meta(tw, 1e9); out['twap'] = fitnorm(Mt, lo=1e-6); out['twap']['n_twaps'] = int(len(Mt)); print('twap', out['twap'])
# $-binned single orders vs book walk
bw = json.load(open(f"{O}/bookwalk.json")); Q = np.array(bw['Q'])
e = np.sqrt(Q[:-1] * Q[1:]); e = np.r_[Q[0] / 1.2, e, Q[-1] * 1.2]
o['qb'] = np.digitize(o.q, e) - 1
t = o.groupby('qb').agg(n=('i0', 'size'), i0=('i0', 'mean'), q=('q', 'median'))
M['qb'] = np.digitize(M.q, e) - 1
tm = M.groupby('qb').agg(n=('i0', 'size'), i0=('i0', 'mean'))
cmp = pd.DataFrame({'Q': Q, 'book_mean': bw['shift_mean'], 'book_med': bw['shift_med'], 'cens': bw['censored_frac']})
cmp = cmp.join(t[['n', 'i0']].rename(columns={'n': 'n_ord', 'i0': 'obs_order_i0'})).join(tm.rename(columns={'n': 'n_meta', 'i0': 'obs_meta_i0'}))
print(cmp.to_string(float_format=lambda v: f'{v:.3g}'))
out['dollar_cmp'] = cmp.to_dict('list')
json.dump(out, open(f"{O}/robust.json", 'w'), indent=1, default=float)
# concentration check: drop the largest taker account (by notional) and refit
top = o.groupby('a').q.sum().sort_values(ascending=False)
print('top taker share', round(top.iloc[0] / top.sum(), 3), 'top5', round(top.iloc[:5].sum() / top.sum(), 3))
M2 = meta(o[o.a != top.index[0]], 300); out['meta_G300_ex_top1'] = fitnorm(M2); print('ex top1', out['meta_G300_ex_top1'])
M3 = meta(o[~o.a.isin(top.index[:5])], 300); out['meta_G300_ex_top5'] = fitnorm(M3); print('ex top5', out['meta_G300_ex_top5'])
Mt1 = meta(o[o.a == top.index[0]], 300); out['meta_G300_top1_only'] = fitnorm(Mt1); print('top1 only', out['meta_G300_top1_only'])
json.dump(out, open(f"{O}/robust.json", 'w'), indent=1, default=float)
