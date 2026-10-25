"""Per-minute book features for regime clustering, xyz:SP500, every day of the run window (scripts/window.py).
depth: replayed notional within 10 bps of mid (offhours_depth_minutes.parquet, last block of minute).
From replayed L1 (ofi/l1): time-weighted spread (bps), time-weighted |L1 size imbalance|,
realized vol = sqrt(sum of squared 5s log mid returns within the minute), annualized.
Plain numpy arrays and per-minute bincounts keep memory to a few GB over long windows."""
import duckdb
import numpy as np
import pandas as pd

R = "data/derived"
# each day file ends with an empty-book sentinel row (NaN prices, zero sizes) at ~23:59:59; dropped here
L = duckdb.sql(f"""SELECT t_ns, bid_px, ask_px, bid_sz, ask_sz FROM read_parquet('{R}/ofi/l1/*.parquet')
                   WHERE bid_px IS NOT NULL AND ask_px IS NOT NULL AND NOT isnan(bid_px) AND NOT isnan(ask_px)
                   ORDER BY t_ns, block""").fetchnumpy()
t = L["t_ns"].astype(np.int64)
MIN = 60_000_000_000
nxt = np.r_[t[1:], t[-1]]
dur = (np.minimum(nxt, (t // MIN + 1) * MIN) - t).astype(float)  # clip at minute edge (remainder after last state dropped)
mid = (L["ask_px"] + L["bid_px"]) / 2
spr = (L["ask_px"] - L["bid_px"]) / mid * 1e4
tot = L["bid_sz"] + L["ask_sz"]
simb = np.where(tot > 0, (L["bid_sz"] - L["ask_sz"]) / np.where(tot > 0, tot, 1), np.nan)
k = dur > 0
mn = t[k] // MIN; m0 = mn.min(); mi = mn - m0; nm = int(mi.max()) + 1
w = dur[k]
B = lambda v: np.bincount(mi, np.nan_to_num(v), nm)   # per-minute sums; NaN terms count as 0 (as in a pandas sum)
ws, cnt = B(w), np.bincount(mi, minlength=nm)
have = cnt > 0
agg = pd.DataFrame({
    "spread_bps": B(spr[k] * w)[have] / ws[have],
    "abs_imb": B(np.abs(simb[k]) * w)[have] / ws[have],
    "signed_imb": B(simb[k] * w)[have] / ws[have],
    "n_states": cnt[have],
}, index=pd.Index(np.arange(nm)[have] + m0, name="mn"))
del L, dur, spr, tot, simb, k, mn, mi, w
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
