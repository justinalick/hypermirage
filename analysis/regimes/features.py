"""Per-minute book features for regime clustering, xyz:SP500 2026-10-08..21.
depth: replayed notional within 10 bps of mid (offhours_depth_minutes.parquet, last block of minute).
From replayed L1 (ofi/l1): time-weighted spread (bps), time-weighted |L1 size imbalance|,
realized vol = sqrt(sum of squared 5s log mid returns within the minute), annualized."""
import glob
import numpy as np
import pandas as pd

R = "data/derived"
l1 = pd.concat([pd.read_parquet(p) for p in sorted(glob.glob(f"{R}/ofi/l1/*.parquet"))]).sort_values(["t_ns", "block"])
# each day file ends with an empty-book sentinel row (NaN prices, zero sizes) at ~23:59:59; drop it
l1 = l1[l1.bid_px.notna() & l1.ask_px.notna()].reset_index(drop=True)
t = l1.t_ns.to_numpy()
MIN = 60_000_000_000
nxt = np.r_[t[1:], t[-1]]
dur = np.minimum(nxt, (t // MIN + 1) * MIN) - t  # clip at minute edge (remainder of minute after last state is dropped)
mid = (l1.ask_px + l1.bid_px).to_numpy() / 2
spr = (l1.ask_px - l1.bid_px).to_numpy() / mid * 1e4
tot = (l1.bid_sz + l1.ask_sz).to_numpy()
simb = np.where(tot > 0, (l1.bid_sz - l1.ask_sz).to_numpy() / np.where(tot > 0, tot, 1), np.nan)
df = pd.DataFrame(dict(mn=t // MIN, dur=dur.astype(float), spr=spr, simb=simb, aimb=np.abs(simb)))
df = df[df.dur > 0]
w = df.dur
agg = pd.DataFrame({
    "spread_bps": (df.spr * w).groupby(df.mn).sum() / w.groupby(df.mn).sum(),
    "abs_imb": (df.aimb * w).groupby(df.mn).sum() / w.groupby(df.mn).sum(),
    "signed_imb": (df.simb * w).groupby(df.mn).sum() / w.groupby(df.mn).sum(),
    "n_states": df.groupby("mn").size(),
})
# 5s grid: last mid strictly before each edge
S5 = 5_000_000_000
edges = np.arange((t[0] // S5 + 1) * S5, t[-1] + 1, S5)
idx = np.searchsorted(t, edges, side="left") - 1
gm = mid[idx]
ret = np.log(gm[1:] / gm[:-1])
rmn = (edges[1:] - 1) // MIN
rv = pd.Series(ret ** 2).groupby(rmn).agg(["sum", "size"])
agg["rv_ann"] = np.sqrt(rv["sum"]) * np.sqrt(365 * 1440)
agg["n_ret"] = rv["size"]
d = pd.read_parquet(f"{R}/offhours/offhours_depth_minutes.parquet").sort_values("t")
d["mn"] = (d.t.values.astype("datetime64[ns]").astype("int64")) // MIN
out = d.merge(agg, left_on="mn", right_index=True, how="left").drop(columns="mn")
out.to_parquet(f"{R}/regimes/features.parquet", index=False)
print(len(out), out.spread_bps.notna().sum(), out.rv_ann.notna().sum())
print(out[["d10", "spread_bps", "abs_imb", "signed_imb", "rv_ann", "n_states", "n_ret"]].describe().T.round(3))
print("rv==0 minutes:", (out.rv_ann == 0).sum())
