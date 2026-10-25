"""Independent checks of build/cluster/impact outputs (recomputed from raw fills and the replayed BBO where possible)."""
import duckdb, numpy as np, pandas as pd, json
import sys
sys.path.insert(0, "scripts")
import window as WIN
R = "."; O = f"{R}/data/derived/metaorder_shapes"
M = pd.read_parquet(f"{O}/metaorders_shape.parquet"); C = pd.read_parquet(f"{O}/curves.parquet"); L = pd.read_parquet(f"{O}/labels.parquet")
o = pd.read_parquet(f"{R}/data/derived/impact/orders.parquet")
ok = lambda name, cond: print(('PASS ' if cond else 'FAIL ') + name)
# 1. metaorder count with liquidations included must equal the impact thread's (metaorders.parquet; 141,552 in the atlas)
oa = o.sort_values(['a', 't0', 'order_id'], kind='mergesort').reset_index(drop=True)
n_all = ((oa.a != oa.a.shift()) | (oa.s != oa.s.shift()) | ((oa.t0 - oa.t1.shift()) > 300e9)).sum()
n_imp = len(pd.read_parquet(f"{R}/data/derived/impact/metaorders.parquet"))
ok(f"metaorders incl. liquidations = {n_all} (impact thread {n_imp})", n_all == n_imp)
WIN.expect("metaorders incl. liquidations", int(n_all), 141552)
ol = o[~o.liq]
ok("notional conserved", abs(M.q.sum() - ol.q.sum()) < 1e-3 * ol.q.sum())
ok("child-order count conserved", M.n.sum() == len(ol))
# 2. impact recomputed from the BBO directly (mid before first fill, mid 0.25 s after last), random 2,000
con = duckdb.connect(); con.execute("set memory_limit='3GB'; set threads=2")
b = con.execute(f"select epoch_ns(t)::bigint t, (best_bid+best_ask)/2 m from '{R}/data/derived/markout/bbo_t.parquet' "
                "where t is not null and best_bid is not null and best_ask is not null and best_ask>best_bid order by t").fetchnumpy()
bt, bm = b['t'], b['m']
s = M.sample(2000, random_state=1)
m0 = bm[np.searchsorted(bt, s.t0.values, 'left') - 1]; th = s.t1.values + 250_000_000
m1 = bm[np.searchsorted(bt, th, 'right') - 1]
i0 = s.s.values * (m1 - m0) / m0 * 1e4; g = th <= bt[-1]
ok(f"i0 matches direct BBO recompute (max abs diff {np.nanmax(np.abs(i0[g] - s.i0.values[g])):.2e} bps)", np.allclose(i0[g], s.i0.values[g], atol=1e-6, equal_nan=True))
ok("pre60 matches", np.allclose(s.s.values * (m0 - bm[np.searchsorted(bt, s.t0.values - 60_000_000_000, 'left') - 1]) / m0 * 1e4, s.pre60.values, atol=1e-6))
# 3. curves: recompute 300 random metaorders from raw fills (first-fill time per order, notional = sum px*sz)
print('checks 1-2 done', flush=True)
fills = con.execute(f"""select address a, order_id, min(epoch_ns(timestamp::timestamp))::bigint t, sum(price::double*size::double) q
  from read_parquet('{R}/data/raw/xyz/fills/*.parquet') where coin='xyz:SP500' and crossed
  and timestamp >= '{WIN.T0}' and timestamp < '{WIN.T1}' group by 1,2""").df()
olm = ol.sort_values(['a', 't0', 'order_id'], kind='mergesort').reset_index(drop=True)
olm['mo'] = ((olm.a != olm.a.shift()) | (olm.s != olm.s.shift()) | ((olm.t0 - olm.t1.shift()) > 300e9)).cumsum()
olm = olm.merge(fills, on=['a', 'order_id'])
ok("raw-fill notional per order matches orders.parquet", np.allclose(olm.q_x, olm.q_y))
grid = np.linspace(0, 1, 21); bad = 0
for mo in C.sample(300, random_state=2).index:
    d = olm[olm.mo == mo].sort_values('t'); t = d.t.values.astype(float); T = t[-1] - t[0]
    cf = np.cumsum(d.q_y.values) / d.q_y.sum()
    ref = np.array([cf[t <= t[0] + gg * T].max() if T > 0 else 1.0 for gg in grid])
    bad += not np.allclose(ref, C.loc[mo].values)
ok(f"curves match raw-fill recompute ({300 - bad}/300)", bad == 0)
# 4. DTW: textbook full-matrix DP with band vs vectorized version
src = open("analysis/metaorder_shapes/cluster.py").read(); ns = {'np': np, 'K': 21}
exec(src[src.index('def dtw'):src.index('def pdist')], ns)   # the exact dtw() used for clustering
def dtw_ref(a, b, w):
    n = len(a); D = np.full((n + 1, n + 1), np.inf); D[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(max(1, i - w), min(n, i + w) + 1):
            D[i, j] = abs(a[i - 1] - b[j - 1]) + min(D[i - 1, j - 1], D[i - 1, j], D[i, j - 1])
    return D[n, n]
X = C.values; rng = np.random.default_rng(0); A = X[rng.integers(0, len(X), 200)]; B = X[rng.integers(0, len(X), 200)]
ok("banded DTW matches reference DP", np.allclose(ns['dtw'](A, B, 2), [dtw_ref(a, b, 2) for a, b in zip(A, B)]))
ok("unconstrained DTW matches reference DP", np.allclose(ns['dtw'](A, B, 21), [dtw_ref(a, b, 21) for a, b in zip(A, B)]))
# 5. labels are nearest-medoid assignments
med = np.load(f"{O}/medoid_curves.npy", allow_pickle=True)[1]
Dm = np.stack([[dtw_ref(x, m, 2) for m in med] for x in X[:500]])
ok("k=3 labels = nearest medoid (first 500)", (Dm.argmin(1) == L.k3.values[:500]).all())
# 6. Y recomputed in a different way (weighted regression through origin of I/sigma on sqrt(x))
I = json.load(open(f"{O}/impact.json")); M = M.join(L)
names = {0: 'front-loaded', 1: 'spread out', 2: 'back-loaded'}
for c, nm in names.items():
    d = M[(M.k3 == c) & ~M.top & (M.q / M.V >= 1e-5) & M.i0.notna()]
    xs = np.sqrt(d.q / d.V); y = d.i0 / d.sig; Yr = np.linalg.lstsq(xs.values[:, None], y.values, rcond=None)[0][0]
    ok(f"Y {nm} ex-top lstsq {Yr:.4f} vs reported {I['ex_top'][nm]['Y_i0']['Y']:.4f}, n {len(d)}", abs(Yr - I['ex_top'][nm]['Y_i0']['Y']) < 1e-9 and len(d) == I['ex_top'][nm]['Y_i0']['n'])
# 7. degenerate curves: zero-duration metaorders (all child orders in one ms) get a flat curve of 1
z = M.loc[C.index]; print('zero-duration 4+ metaorders:', int((z.dur_s == 0).sum()), 'cluster:', z[z.dur_s == 0].k3.value_counts().to_dict())
print('largest taker share in each cluster:', z.groupby('k3').top.mean().round(3).to_dict())
