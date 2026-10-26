"""How much of a metaorder's impact stays: the mid 0.25 s, 10 s, 60 s and 300 s after its last fill, against the mid
just before its first fill, by metaorder size. Metaorders as in analysis/impact/robust.py (5-minute gap, liquidations
excluded), rebuilt from data/derived/impact/orders.parquet. A metaorder counts as clean when its account sends no
taker order of either side within 300 s after it ends, so the later mids are not moved by the same account.
Means are equal-weighted per metaorder; 95% CIs are a block bootstrap over UTC days. Writes decay.json."""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN

I = "data/derived/impact"
O = "data/derived/impact_decay"
os.makedirs(O, exist_ok=True)
H = ["i0", "i10", "i60", "i300"]
o = pd.read_parquet(f"{I}/orders.parquet", columns=["a", "order_id", "t0", "t1", "q", "liq", "s", "m0", "pre60", "day"] + H)
o = o[~o.liq].sort_values(["a", "t0", "order_id"], kind="mergesort").reset_index(drop=True)
new = (o.a != o.a.shift()) | (o.s != o.s.shift()) | ((o.t0 - o.t1.shift()) > 300e9)
o["mo"] = new.cumsum()
g = o.groupby("mo")
M = g.agg(a=("a", "first"), q=("q", "sum"), n=("q", "size"), m0=("m0", "first"), s=("s", "first"),
          t0=("t0", "min"), t1=("t1", "max"), pre60=("pre60", "first"), day=("day", "first"))
last = o.loc[g.t1.idxmax().values]
for h in H:   # each order's mids are relative to its own start: convert to a mid level, then to the metaorder start
    m_h = last[h].values / 1e4 * last.s.values * last.m0.values + last.m0.values
    M[h] = M.s * (m_h - M.m0) / M.m0 * 1e4
# next taker order by the same account, either side
# the account's next taker order is the first order of its next metaorder (metaorder ids follow account, then time)
nxt_t0 = M.t0.shift(-1).where(M.a.shift(-1) == M.a)
M["gap_next_s"] = (nxt_t0 - M.t1) / 1e9
M["clean"] = ~(M.gap_next_s <= 300)
M = M.dropna(subset=H)
top = o.groupby("a").q.sum().idxmax()
M["top"] = M.a == top
del o, g, last                                     # the order table is no longer needed; free it before the book
BK = [(1e3, 1e4, "$1k to $10k"), (1e4, 1e5, "$10k to $100k"), (1e5, 1e6, "$100k to $1M"), (1e6, np.inf, "$1M+")]
days = np.array(sorted(M.day.unique())); di = {d: i for i, d in enumerate(days)}
rng = np.random.default_rng(11)
DRAW = rng.integers(0, len(days), (1000, len(days)))


def stats(S):
    """Mean of each horizon and of the share kept at 300 s, with day-bootstrap CIs (from per-day sums)."""
    k = S.day.map(di).values
    out = {"n": int(len(S)), "notional_usd": float(S.q.sum())}
    bs = {}
    for h in [c for c in H + ["pre60"] + H_EX if S[c].notna().any()]:   # pre60 is missing when the window starts under 60 s before the metaorder
        ok = S[h].notna().values
        c_ = np.bincount(k[ok], minlength=len(days)).astype(float)
        s_ = np.bincount(k[ok], S[h].values[ok], len(days))
        bs[h] = s_[DRAW].sum(1) / c_[DRAW].sum(1)
        out[h] = [float(s_.sum() / c_.sum()), *np.nanpercentile(bs[h], [2.5, 97.5]).tolist()]
    for h in H[1:]:                                       # share of the end-of-metaorder impact still there at h
        out[f"kept_{h[1:]}"] = [out[h][0] / out["i0"][0], *np.nanpercentile(bs[h] / bs["i0"], [2.5, 97.5]).tolist()]
    return out


# Momentum control. Each clean metaorder gets a placebo: the same time of day 1 to 7 days earlier or later, with a
# random side and a look-back equal to its own duration. The placebo's continuation (mid move over the next h
# seconds, in its side's direction) is averaged within bins of its look-back move, and each metaorder's expected
# continuation is read off the bin of its own move (i0). Excess = observed continuation minus that expectation.
b = pd.read_parquet("data/derived/markout/bbo_t.parquet", columns=["t", "best_bid", "best_ask"])
b = b[(b.best_ask > b.best_bid)].dropna()
bt = b.t.values.astype("datetime64[ns]").astype(np.int64); bm = ((b.best_bid + b.best_ask) / 2).values
del b
def mid_at(t):
    i = np.searchsorted(bt, t, "right") - 1
    return np.where(i >= 0, bm[np.maximum(i, 0)], np.nan)
C = M[M.clean].copy()
rng_p = np.random.default_rng(13)
k = rng_p.choice(np.r_[-7:0, 1:8], len(C)) * 86400 * 10**9
tp = C.t1.values + k
lb = np.maximum(C.t1.values - C.t0.values, 250_000_000)                       # look-back, at least 0.25 s
sp = rng_p.choice([-1, 1], len(C))
inside = (tp - lb > bt[0]) & (tp + 300 * 10**9 < bt[-1])
m_now = mid_at(tp); back = sp * (m_now - mid_at(tp - lb)) / m_now * 1e4
HS = {"i10": 10, "i60": 60, "i300": 300}
fut = {h: sp * (mid_at(tp + s_ * 10**9) - m_now) / m_now * 1e4 for h, s_ in HS.items()}
pre = sp * (mid_at(tp - lb) - mid_at(tp - lb - 60 * 10**9)) / m_now * 1e4          # the minute before, as pre60
def bins(x, ref, n):
    e = np.unique(np.nanquantile(ref, np.linspace(0, 1, n + 1)))
    return np.where(np.isfinite(x), np.clip(np.digitize(x, e) - 1, 0, len(e) - 2), len(e) - 1), len(e)
b1p, n1 = bins(back, C.i0, 20); b1c, _ = bins(C.i0.values, C.i0, 20)            # the move itself
b2p, n2 = bins(pre, C.pre60, 5); b2c, _ = bins(C.pre60.values, C.pre60, 5)      # and the trend before it
kp, kc = b1p * (n2 + 1) + b2p, b1c * (n2 + 1) + b2c
for h in HS:
    ok = inside & np.isfinite(back) & np.isfinite(fut[h])
    e = pd.Series(fut[h][ok]).groupby(kp[ok]).agg(["mean", "size"])
    e = e["mean"].where(e["size"] >= 100)                                       # thin cells give no expectation
    C[f"exp_{h}"] = e.reindex(kc).values
    C[f"ex_{h}"] = (C[h] - C.i0) - C[f"exp_{h}"]
M = M.join(C[[c for c in C if c.startswith(("exp_", "ex_"))]])
H_EX = [f"ex_{h}" for h in HS] + [f"exp_{h}" for h in HS]

res = {"window": WIN.span(), "n_metaorders": int(len(M)), "clean_share": float(M.clean.mean()), "groups": {}}
for gname, sel in [("all", M.clean), ("ex_top", M.clean & ~M.top), ("top", M.clean & M.top),
                   ("all_incl_unclean", M.clean | ~M.clean)]:
    res["groups"][gname] = {}
    for lo, hi, lab in BK:
        S = M[sel & (M.q >= lo) & (M.q < hi)]
        if len(S) >= 200:
            res["groups"][gname][lab] = stats(S)
for gname, sel in [("single", M.clean & (M.n == 1)), ("multi", M.clean & (M.n > 1))]:
    S = M[sel & (M.q >= 1e5)]
    res["groups"][f"{gname}_100k+"] = stats(S)
json.dump(res, open(f"{O}/decay.json", "w"), indent=1)
print(f"{len(M):,} metaorders, {M.clean.mean():.0%} clean")
for gname, G in res["groups"].items():
    for lab, r in (G.items() if "_100k+" not in gname else [("$100k+", G)]):
        print(f"{gname:16s} {lab:14s} n={r['n']:>8,}  " + "  ".join(f"{h}={r[h][0]:+.2f}" for h in H)
              + "".join(f"  {h}={r[h][0]:+.2f}" for h in ("pre60", "exp_i300", "ex_i300") if h in r) + f"  kept300={r['kept_300'][0]:.2f} [{r['kept_300'][1]:.2f}, {r['kept_300'][2]:.2f}]")
