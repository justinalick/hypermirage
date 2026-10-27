"""Does execution shape change what a metaorder costs, once size, length, timing and the trader are held fixed?

Metaorders with 4+ child orders and their k=3 shape labels come from analysis/metaorder_shapes/ (label 0 front-loaded,
1 spread out, 2 back-loaded); the largest taker is left out. Two costs per metaorder, in bps, signed so that + is
paid by the trader: shortfall (volume-weighted fill price vs the mid just before the first fill) and impact (mid
0.25 s after the last fill vs the same mid). Two comparisons of spread out against each other shape:
  strata  coarsened exact matching on size / day's volume, child-order count, duration, CME session and the
          prior-minute trend; per-stratum mean differences averaged with the spread-out stratum counts as weights
  account the same comparison within each account (account fixed effects) plus the same covariates, by OLS
95% CIs: block bootstrap over UTC days. Writes shape_cost.json."""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN

S = "data/derived/metaorder_shapes"
O = "data/derived/shape_cost"
os.makedirs(O, exist_ok=True)
NAMES = {0: "front-loaded", 1: "spread out", 2: "back-loaded"}

# volume-weighted fill price per metaorder: rebuild the metaorder ids exactly as metaorder_shapes/build.py does
o = pd.read_parquet("data/derived/impact/orders.parquet", columns=["a", "order_id", "t0", "t1", "q", "sz", "liq", "s"])
o = o[~o.liq].sort_values(["a", "t0", "order_id"], kind="mergesort").reset_index(drop=True)
o["mo"] = ((o.a != o.a.shift()) | (o.s != o.s.shift()) | ((o.t0 - o.t1.shift()) > 300e9)).cumsum()
V = o.groupby("mo").agg(qq=("q", "sum"), sz=("sz", "sum"))
del o
M = pd.read_parquet(f"{S}/metaorders_shape.parquet")                     # indexed by metaorder id (mo)
L = pd.read_parquet(f"{S}/labels.parquet")
M = M.join(V).join(L[["k3"]], how="inner")
assert np.allclose(M.q, M.qq, rtol=1e-9), "metaorder ids do not match metaorder_shapes/build.py"
M = M[~M.top].copy()
M["shape"] = M.k3.map(NAMES)
M["shortfall"] = M.s * (M.q / M.sz - M.m0) / M.m0 * 1e4
M["impact"] = M.i0
M["t"] = pd.to_datetime(M.t0)
M["sess"] = WIN.session(M.t)
M = M.dropna(subset=["shortfall", "impact", "dur_s"])

# strata
M["b_x"] = pd.qcut(np.log(M.q / M.V), 10, labels=False, duplicates="drop")
M["b_n"] = pd.cut(M.n, [3, 5, 8, 15, 40, np.inf], labels=False)
M["b_d"] = pd.qcut(np.log1p(M.dur_s), 8, labels=False, duplicates="drop")
M["b_p"] = pd.cut(M.pre60.fillna(0), [-np.inf, -0.5, 0.5, np.inf], labels=False)
M["stratum"] = M.groupby(["b_x", "b_n", "b_d", "sess", "b_p"], observed=True).ngroup()

days = np.array(sorted(M.day.unique())); di = {d: i for i, d in enumerate(days)}
M["di"] = M.day.map(di)
rng = np.random.default_rng(17)
DRAWS = [np.bincount(rng.integers(0, len(days), len(days)), minlength=len(days)) for _ in range(500)]


def strata_diff(D, y, other):
    """Spread out minus `other`, matched within strata; `w` = per-row day weights for the bootstrap."""
    g = D[D["shape"].isin(["spread out", other])]
    s = g.assign(yw=g[y] * g.w).groupby(["stratum", "shape"])[["yw", "w"]].sum().unstack("shape")
    s = s[(s[("w", "spread out")] > 0) & (s[("w", other)] > 0)]
    d = s[("yw", "spread out")] / s[("w", "spread out")] - s[("yw", other)] / s[("w", other)]
    return float(np.average(d, weights=s[("w", "spread out")])), float(s[("w", "spread out")].sum())


def fe_diff(D, y, other):
    """Weighted least squares of y on shape dummies and covariates, all demeaned within account (account fixed
    effects) with the same weights."""
    g = D[D["shape"].isin(["spread out", other])].copy()
    X = pd.DataFrame({"sp": (g["shape"] == "spread out").astype(float), "lx": np.log(g.q / g.V), "ln": np.log(g.n),
                      "ld": np.log1p(g.dur_s), "pre": g.pre60.fillna(0)})
    for c in g.sess.unique():
        X[f"s_{c}"] = (g.sess == c).astype(float)
    w = g.w.values
    keep = w > 0
    X, yy, ac, w = X[keep], g[y].values[keep], g.acct.values[keep], w[keep]
    # weighted within-account means, so a day drawn twice in the bootstrap counts twice in the fixed effects too
    sw_a = pd.Series(w).groupby(ac).transform("sum").values
    Xd = X - (X.mul(w, axis=0).groupby(ac).transform("sum").values / sw_a[:, None])
    yd = yy - pd.Series(yy * w).groupby(ac).transform("sum").values / sw_a
    sw = np.sqrt(w)
    beta = np.linalg.lstsq(Xd.values * sw[:, None], yd * sw, rcond=None)[0]
    return float(beta[0])


res = {"window": WIN.span(), "n": {}, "raw": {}, "strata": {}, "account": {}}
for k, v in M["shape"].value_counts().items():
    res["n"][k] = int(v)
M["w"] = 1.0
for y in ["shortfall", "impact"]:
    res["raw"][y] = {k: float(v) for k, v in M.groupby("shape")[y].mean().items()}
    for other in ["front-loaded", "back-loaded"]:
        est, ns = strata_diff(M, y, other)
        fe = fe_diff(M, y, other)
        bs, bf = [], []
        for c in DRAWS:
            D = M.assign(w=c[M.di.values].astype(float))
            bs.append(strata_diff(D, y, other)[0]); bf.append(fe_diff(D, y, other))
        res["strata"][f"{y}: spread out - {other}"] = [est, *np.nanpercentile(bs, [2.5, 97.5]).tolist(), ns]
        res["account"][f"{y}: spread out - {other}"] = [fe, *np.nanpercentile(bf, [2.5, 97.5]).tolist()]
        print(f"{y:9s} spread out - {other:12s} strata {est:+.3f} [{np.nanpercentile(bs, 2.5):+.3f}, {np.nanpercentile(bs, 97.5):+.3f}]"
              f"  within-account {fe:+.3f} [{np.nanpercentile(bf, 2.5):+.3f}, {np.nanpercentile(bf, 97.5):+.3f}] bps", flush=True)
res["median_q_usd"] = {k: float(v) for k, v in M.groupby("shape").q.median().items()}
json.dump(res, open(f"{O}/shape_cost.json", "w"), indent=1)
print("n", res["n"], "raw", json.dumps(res["raw"]))
