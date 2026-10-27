"""Impact by shape cluster: Y in I/sigma = Y sqrt(Q/V) (exponent fixed at 0.5, LS through origin), hour-block bootstrap."""
import json, numpy as np, pandas as pd
O = "data/derived/metaorder_shapes"
M = pd.read_parquet(f"{O}/metaorders_shape.parquet"); L = pd.read_parquet(f"{O}/labels.parquet")
M = M.join(L)
names = {0: 'front-loaded', 1: 'spread out', 2: 'back-loaded'}
M['grp'] = np.select([M.n == 1, M.n < 4], ['single order', '2-3 orders'], default='')
M.loc[M.k3.notna(), 'grp'] = M.loc[M.k3.notna(), 'k3'].map(names)
M['x'] = M.q / M.V
M['hr'] = M.t0 // (3600 * 10**9)
rng = np.random.default_rng(11)
def Y(d, h='i0', B=1000):
    d = d[(d.x >= 1e-5) & d[h].notna()]
    hr = pd.factorize(d.hr)[0]; nh = hr.max() + 1
    num = np.bincount(hr, (d[h] / d.sig * np.sqrt(d.x)).values, nh); den = np.bincount(hr, d.x.values, nh)
    bs = [(num[i].sum() / den[i].sum()) for i in rng.integers(0, nh, (B, nh))]
    return dict(n=len(d), Y=float(num.sum() / den.sum()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)))
def binned(d, h='i0'):   # mean I/sigma in Q/V bins, for matched-size comparison
    e = np.logspace(-5, -2, 7); b = np.digitize(d.x, e) - 1; out = []
    for i in range(len(e) - 1):
        s = d[(b == i) & d[h].notna()]
        out.append(dict(x=float(s.x.mean()) if len(s) else None, n=len(s), y=float((s[h] / s.sig).mean()) if len(s) >= 30 else None))
    return out
res = {}
order = ['single order', '2-3 orders', 'front-loaded', 'spread out', 'back-loaded']
for sub, tag in [(M, 'all'), (M[~M.top], 'ex_top'), (M[M.top], 'top_only')]:
    res[tag] = {}
    for gname in order:
        d = sub[sub.grp == gname]
        res[tag][gname] = dict(Y_i0=Y(d), Y_i300=Y(d, 'i300'), Y_pre60=Y(d, 'pre60'), bins=binned(d),
                               n_mo=len(d), notional_M=float(d.q.sum() / 1e6), med_dur_s=float(d.dur_s.median()), med_q=float(d.q.median()))
# urgency inside shape clusters: short (< 10 s) vs long (>= 60 s)
res['by_duration'] = {}
for gname in ['front-loaded', 'spread out', 'back-loaded']:
    for lab, m in [('<10s', M.dur_s < 10), ('10-60s', (M.dur_s >= 10) & (M.dur_s < 60)), ('>=60s', M.dur_s >= 60)]:
        res['by_duration'][f'{gname} {lab}'] = Y(M[(M.grp == gname) & m & ~M.top], B=500)
# native TWAP and constant-clip (iceberg-like) subsets
res['native_twap_ex_top'] = Y(M[(M.twap > 0.5) & ~M.top]); res['native_twap_all'] = Y(M[M.twap > 0.5])
res['const_clip_ex_top'] = Y(M[(M.same_clip_share >= 0.8) & (M.n >= 4) & ~M.top]); res['const_clip_n'] = int(((M.same_clip_share >= 0.8) & (M.n >= 4)).sum())
json.dump(res, open(f"{O}/impact.json", "w"), indent=1)
for tag in ['all', 'ex_top', 'top_only']:
    print(tag)
    for g in order:
        r = res[tag][g]; f = lambda z: f"{z['Y']:.2f} [{z['lo']:.2f},{z['hi']:.2f}] n={z['n']}"
        print(f"  {g:13s} mo={r['n_mo']:6d} ${r['notional_M']:7.0f}M  i0 {f(r['Y_i0'])}  i300 {f(r['Y_i300'])}  pre60 {f(r['Y_pre60'])}")
for k, v in res['by_duration'].items(): print(k, round(v['Y'], 2), [round(v['lo'], 2), round(v['hi'], 2)], v['n'])
for k in ['native_twap_ex_top', 'native_twap_all', 'const_clip_ex_top', 'const_clip_n']: print(k, res[k])
tw = M[(M.twap > 0.5) & M.k3.notna()]
res['native_twap_shape_share'] = {names[int(k)]: float(v) for k, v in tw.k3.value_counts(normalize=True).items()}
print('native TWAPs (4+ child orders) by shape:', {k: round(v, 3) for k, v in res['native_twap_shape_share'].items()}, len(tw))
json.dump(res, open(f"{O}/impact.json", "w"), indent=1)
