"""Binned impact curves, power-law fits, square-root prefactor Y, hour-block bootstrap."""
import numpy as np, pandas as pd, json
O = "data/derived/impact"
rng = np.random.default_rng(11)
def curve(df, col, edges, B=1000):
    df = df.dropna(subset=[col]).copy()
    df['x'] = df.q / df.V_d
    df['b'] = np.digitize(df.x, edges) - 1
    df = df[(df.b >= 0) & (df.b < len(edges) - 1)]
    df['hr'] = df.t0 // (3600 * 10**9)
    hrs = df.hr.unique(); hi = pd.Series(np.arange(len(hrs)), hrs)
    df['h'] = hi[df.hr].values
    nb, nh = len(edges) - 1, len(hrs)
    S = np.zeros((nh, nb)); C = np.zeros((nh, nb)); X = np.zeros((nh, nb)); Z = np.zeros((nh, nb))
    np.add.at(S, (df.h, df.b), df[col]); np.add.at(C, (df.h, df.b), 1); np.add.at(X, (df.h, df.b), df.x)
    np.add.at(Z, (df.h, df.b), df[col] / (df.sig_d_bps * np.sqrt(df.x)))
    d = rng.integers(0, nh, (B, nh))
    bs = S[d].sum(1) / C[d].sum(1)
    res = pd.DataFrame({'n': C.sum(0), 'x': X.sum(0) / C.sum(0), 'I': S.sum(0) / C.sum(0),
                        'lo': np.nanpercentile(bs, 2.5, 0), 'hi': np.nanpercentile(bs, 97.5, 0),
                        'Y': Z.sum(0) / C.sum(0)})
    # power-law fit over bins with n>=30, bootstrap the exponent
    ok = (res.n >= 30).values
    def fit(I, x):
        g = ok & (I > 0)
        return np.polyfit(np.log(x[g]), np.log(I[g]), 1)[0] if g.sum() >= 3 else np.nan
    xs = res.x.values
    dl = [fit(bs[k], xs) for k in range(B)]
    return res, fit(res.I.values, xs), np.nanpercentile(dl, [2.5, 97.5]).tolist(), int(len(df))
o = pd.read_parquet(f"{O}/orders.parquet"); M = pd.read_parquet(f"{O}/metaorders.parquet")
out = {}
E = np.logspace(-8, -2, 19)
for nm, df in [('orders', o[~o.liq]), ('meta', M[M.n >= 1])]:
    for col in ['i0', 'i10', 'i60', 'i300', 'pre60']:
        r, d, ci, n = curve(df, col, E)
        out[f'{nm}_{col}'] = dict(delta=d, ci=ci, n=n, bins=r.round(4).to_dict('list'))
        print(nm, col, 'n', n, 'delta', round(d, 3), [round(c, 2) for c in ci])
        print(r[r.n >= 30][['n', 'x', 'I', 'lo', 'hi', 'Y']].to_string(float_format=lambda v: f'{v:.3g}'))
json.dump(out, open(f"{O}/fit.json", 'w'), indent=1, default=float)
