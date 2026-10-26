"""Predictive OOS R2 with a gap g between the end of the OFI bin and the start of the target window.
Signal: OFI over [T-h, T) / trailing depth. Target: mid return over [T+g, T+g+h). Walk-forward by day:
fit y = b0 + b1 x on all earlier days, score the next day. The fits use per-day sums (n, sum x, sum y,
sum xx, sum xy, sum yy), which give the same least-squares coefficients and squared errors as refitting
on the stacked rows, in one pass and flat memory."""
import numpy as np, duckdb, json
import sys
sys.path.insert(0, "scripts")
import window as WIN
OUT = "data/derived/ofi"
con = duckdb.connect()
L = con.execute(f"""select t_ns, bid_px, bid_sz, ask_px, ask_sz, cast(regexp_extract(filename,'(\\d{{8}})',1) as integer) d
                    from read_parquet('{OUT}/l1/*.parquet', filename=true) order by block""").fetchnumpy()
t = L["t_ns"].astype(np.int64); bp, bs, ap, as_, d = L["bid_px"], L["bid_sz"], L["ask_px"], L["ask_sz"], L["d"]
del L
ok = bp < ap; t, bp, bs, ap, as_, d = t[ok], bp[ok], bs[ok], ap[ok], as_[ok], d[ok]
e = np.zeros(len(t)); pb, qb, pa, qa = bp[:-1], bs[:-1], ap[:-1], as_[:-1]
e[1:] = (bp[1:] >= pb) * bs[1:] - (bp[1:] <= pb) * qb - (ap[1:] <= pa) * as_[1:] + (ap[1:] >= pa) * qa
e[np.r_[True, d[1:] != d[:-1]]] = 0
del pb, qb, pa, qa, d
lmid = np.log((bp + ap) / 2); dep = (bs + as_) / 2
del bp, bs, ap, as_
cume = np.r_[0, np.cumsum(e)]; dt = np.diff(np.r_[t, t[-1]]); cumdep = np.r_[0, np.cumsum(dep * dt)]; cumt = np.r_[0, np.cumsum(dt)]
del e, dep, dt
DAY = 86400 * 10**9; t0 = (t[0] // DAY) * DAY
ND = WIN.N_DAYS
def mid_at(T):
    i = np.searchsorted(t, T, "left") - 1; return np.where(i >= 0, lmid[np.clip(i, 0, None)], np.nan)
out = {}
for h in (1, 5, 10):
    H = h * 10**9; T = np.arange(t0 + 1800 * 10**9, t0 + ND * DAY - 2 * H - 10**9, H)
    j0, j1 = np.searchsorted(t, T - H, "left"), np.searchsorted(t, T, "left")
    a0 = np.searchsorted(t, T - 1800 * 10**9, "left")
    with np.errstate(invalid="ignore", divide="ignore"):
        D = (cumdep[j1] - cumdep[a0]) / np.maximum(cumt[j1] - cumt[a0], 1)
        x = (cume[j1] - cume[j0]) / D
    day = ((T - t0) // DAY).astype(int)
    del j0, j1, a0, D
    for g_ms in (0, 70, 140, 250, 500, 1000):
        g = g_ms * 10**6; y = (mid_at(T + g + H) - mid_at(T + g)) * 1e4
        v = np.isfinite(x) & np.isfinite(y)
        dv, xv, yv = day[v], x[v], y[v]
        S = {k: np.bincount(dv, w, ND) for k, w in (("n", np.ones_like(xv)), ("x", xv), ("y", yv), ("xx", xv * xv),
                                                    ("xy", xv * yv), ("yy", yv * yv))}
        C = {k: np.cumsum(s) - s for k, s in S.items()}       # sums over days before each day
        sse = tss = 0.0
        for td in range(1, ND):
            n, sx, sy, sxx, sxy = C["n"][td], C["x"][td], C["y"][td], C["xx"][td], C["xy"][td]
            b1 = (n * sxy - sx * sy) / (n * sxx - sx * sx); b0 = (sy - b1 * sx) / n
            m, tx, ty, txx, txy, tyy = S["n"][td], S["x"][td], S["y"][td], S["xx"][td], S["xy"][td], S["yy"][td]
            sse += tyy - 2 * b0 * ty - 2 * b1 * txy + m * b0 * b0 + 2 * b0 * b1 * tx + b1 * b1 * txx
            tss += tyy
        out[f"{h}s_gap{g_ms}ms"] = float(1 - sse / tss)
        print(h, g_ms, round(out[f"{h}s_gap{g_ms}ms"], 4), flush=True)
json.dump(out, open(f"{OUT}/gap_res.json", "w"), indent=1)
