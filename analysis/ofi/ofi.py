"""Cont-Kukanov-Stoikov OFI on xyz:SP500, 2026-10-08..21.
Event OFI e_n from consecutive top-of-book states (l1/*.parquet), summed into fixed UTC bins of
length h. Mid return over a bin = 1e4 * log change of the mid at bin edges (mid at edge T = last
book state with t < T; OFI of a bin uses only states with t in [T-h, T)).
Contemporaneous: r_k on OFI_k. Predictive: r_{k+1} on OFI_k (and r_k), walk-forward by day:
fit on all earlier days, score the next day, OOS R2 vs a zero forecast.
Normalization: OFI_k / D_k, D_k = mean L1 depth (bid+ask)/2 over the previous 30 minutes (trailing).
"""
import glob, json, numpy as np, duckdb
ROOT = "."; OUT = f"{ROOT}/data/derived/ofi"
con = duckdb.connect()
L = con.execute(f"""select block, t_ns, bid_px, bid_sz, ask_px, ask_sz, regexp_extract(filename,'(\\d{{8}})',1) d
  from read_parquet('{OUT}/l1/*.parquet', filename=true) order by block""").fetchnumpy()
t = L["t_ns"].astype(np.int64); bp, bs, ap, as_ = L["bid_px"], L["bid_sz"], L["ask_px"], L["ask_sz"]
d = L["d"]
ok = bp < ap
t, bp, bs, ap, as_, d = t[ok], bp[ok], bs[ok], ap[ok], as_[ok], d[ok]
newday = np.r_[True, d[1:] != d[:-1]]
e = np.zeros(len(t))
pb, qb, pa, qa = bp[:-1], bs[:-1], ap[:-1], as_[:-1]
e[1:] = (bp[1:] >= pb) * bs[1:] - (bp[1:] <= pb) * qb - (ap[1:] <= pa) * as_[1:] + (ap[1:] >= pa) * qa
e[newday] = 0.0
lmid = np.log((bp + ap) / 2)
dep = (bs + as_) / 2
spr_bps = (ap - bp) / ((ap + bp) / 2) * 1e4
cume = np.r_[0, np.cumsum(e)]
# signed taker volume (trade imbalance), contracts
F = con.execute(f"""select epoch_ns(timestamp::timestamp) fn, case when side='buy' then 1 else -1 end * size::double s
  from read_parquet('{ROOT}/data/raw/xyz/fills/2026-10-*.parquet') where coin='xyz:SP500' and crossed
  and timestamp >= '2026-10-08' and timestamp < '2026-10-22' order by fn""").fetchnumpy()
fn, fs = F["fn"].astype(np.int64), F["s"]; cumf = np.r_[0, np.cumsum(fs)]
DAY = 86400 * 10**9
t0 = (t[0] // DAY) * DAY; t1 = t0 + 14 * DAY
HZ = [1, 5, 10, 30, 60, 300]
# trailing 30-min depth: time-weighted mean of dep over [T-30m, T)
dt = np.diff(np.r_[t, t[-1]]); cumdep = np.r_[0, np.cumsum(dep * dt)]; cumt = np.r_[0, np.cumsum(dt)]
def edge_state(T):
    return np.searchsorted(t, T, "left") - 1   # last state with t < T
def ols(X, y):
    b, *_ = np.linalg.lstsq(X, y, rcond=None); return b
def r2(y, yh, base=None):
    base = np.zeros_like(y) if base is None else base
    return 1 - ((y - yh) ** 2).sum() / ((y - base) ** 2).sum()
res = {"n_l1_states": int(len(t)), "n_taker_fills": int(len(fn)), "h": {}}
for h in HZ:
    H = h * 10**9
    E = np.arange(t0, t1 + 1, H)                       # bin edges
    i = edge_state(E)
    good_edge = i >= 0
    m = np.where(good_edge, lmid[np.clip(i, 0, None)], np.nan)
    j = np.searchsorted(t, E, "left")                 # states with t < E -> cume[j]
    ofi = np.diff(cume[j]); r = np.diff(m) * 1e4
    jf = np.searchsorted(fn, E, "left"); ti = np.diff(cumf[jf])
    # trailing depth at the start edge of each bin (uses only data before the bin starts)
    W = 1800 * 10**9; a0 = np.searchsorted(t, E[:-1] - W, "left"); a1 = np.searchsorted(t, E[:-1], "left")
    D = np.where(a1 > a0, (cumdep[a1] - cumdep[a0]) / np.maximum(cumt[a1] - cumt[a0], 1), np.nan)
    sp = np.where(i[:-1] >= 0, spr_bps[np.clip(i[:-1], 0, None)], np.nan)
    day = ((E[:-1] - t0) // DAY).astype(int)
    hr = ((E[:-1] % DAY) // (3600 * 10**9)).astype(int)
    wd = ((E[:-1] // DAY + 3) % 7)                     # 0=Mon (1970-01-01 was a Thursday)
    rth = (wd < 5) & (E[:-1] % DAY >= 13.5 * 3600e9) & (E[:-1] % DAY < 20 * 3600e9)
    v = np.isfinite(r) & np.isfinite(D) & (D > 0)
    x = ofi / np.where(D > 0, D, np.nan)
    o = {"n_bins": int(v.sum())}
    # contemporaneous, pooled
    for nm, X in (("ofi", x), ("ti", ti / np.where(D > 0, D, np.nan))):
        Xm = np.c_[np.ones(v.sum()), X[v]]; b = ols(Xm, r[v])
        o[f"cont_{nm}_r2"] = float(r2(r[v], Xm @ b, np.full(v.sum(), r[v].mean()))); o[f"cont_{nm}_beta"] = float(b[1])
    Xm = np.c_[np.ones(v.sum()), x[v], (ti / D)[v]]; b = ols(Xm, r[v]); o["cont_both_r2"] = float(r2(r[v], Xm @ b, np.full(v.sum(), r[v].mean())))
    for nm, msk in (("rth", rth), ("off", ~rth)):
        w = v & msk; Xm = np.c_[np.ones(w.sum()), x[w]]; b = ols(Xm, r[w])
        o[f"cont_ofi_r2_{nm}"] = float(r2(r[w], Xm @ b, np.full(w.sum(), r[w].mean()))); o[f"n_{nm}"] = int(w.sum())
    # CKS-style: per half-hour window OLS on raw OFI, median R2 (windows with >= 20 bins)
    if h <= 60:
        win = (E[:-1] - t0) // (1800 * 10**9); rs = []
        for wv in np.unique(win[v]):
            w = v & (win == wv)
            if w.sum() >= 20 and ofi[w].std() > 0 and r[w].std() > 0:
                rs.append(np.corrcoef(ofi[w], r[w])[0, 1] ** 2)
        o["cont_halfhour_r2_median"] = float(np.median(rs)); o["cont_halfhour_r2_iqr"] = [float(np.percentile(rs, 25)), float(np.percentile(rs, 75))]; o["n_halfhours"] = len(rs)
    # predictive: y = r_{k+1}; features at k: x_k, r_k
    y = r[1:]; xk = x[:-1]; rk = r[:-1]; vv = v[1:] & v[:-1]; dk = day[1:]
    oos = {"ofi": [], "lagret": [], "both": []}; per = {k: [] for k in oos}; yall = {k: [] for k in oos}
    hit = []; pred_mag = []
    for td in range(1, 14):
        tr, te = vv & (dk < td), vv & (dk == td)
        if te.sum() < 10: continue
        for k, cols in (("ofi", [xk]), ("lagret", [rk]), ("both", [xk, rk])):
            Xtr = np.c_[np.ones(tr.sum()), *[c[tr] for c in cols]]; b = ols(Xtr, y[tr])
            Xte = np.c_[np.ones(te.sum()), *[c[te] for c in cols]]; yh = Xte @ b
            per[k].append(float(r2(y[te], yh))); oos[k].append(yh); yall[k].append(y[te])
            if k == "ofi":
                nz = y[te] != 0; hit.append(np.sign(yh[nz]) == np.sign(y[te][nz])); pred_mag.append(np.abs(yh))
    for k in oos:
        yy, yh = np.concatenate(yall[k]), np.concatenate(oos[k])
        o[f"oos_{k}_r2"] = float(r2(yy, yh)); o[f"oos_{k}_r2_days"] = per[k]
    o["oos_ofi_days_positive"] = int(sum(p > 0 for p in per["ofi"])); o["oos_days"] = len(per["ofi"])
    o["oos_ofi_hit"] = float(np.mean(np.concatenate(hit)))  # pooled, bins with a non-zero move; o["oos_n"] = int(len(np.concatenate(yall["ofi"])))
    pm = np.concatenate(pred_mag); o["oos_ofi_pred_abs_med_bps"] = float(np.median(pm)); o["oos_ofi_pred_abs_p99_bps"] = float(np.percentile(pm, 99))
    # full-sample in-sample predictive beta and t (HAC-free; bins non-overlapping)
    Xm = np.c_[np.ones(vv.sum()), xk[vv], rk[vv]]; b = ols(Xm, y[vv]); res_ = y[vv] - Xm @ b
    cov = np.linalg.inv(Xm.T @ Xm) * res_.var(); o["is_pred_beta_ofi"] = float(b[1]); o["is_pred_t_ofi"] = float(b[1] / np.sqrt(cov[1, 1]))
    o["is_pred_beta_lagret"] = float(b[2]); o["is_pred_t_lagret"] = float(b[2] / np.sqrt(cov[2, 2]))
    # lookahead check: same pipeline but OFI from the SAME bin as the target (should look "great")
    o["leak_check_r2_same_bin"] = o["cont_ofi_r2"]
    # placebo: OFI from bin k+1 shifted by a day (should be ~0)
    o["med_spread_bps"] = float(np.nanmedian(sp)); o["frac_zero_ret"] = float(np.mean(r[v] == 0)); o["sd_ret_bps"] = float(r[v].std())
    res["h"][h] = o
    print(h, {k: (round(val, 4) if isinstance(val, float) else val) for k, val in o.items() if not k.endswith("_days")}, flush=True)
json.dump(res, open(f"{OUT}/ofi_res.json", "w"), indent=1)
