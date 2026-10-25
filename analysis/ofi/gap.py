"""Predictive OOS R2 with a gap g between the end of the OFI bin and the start of the target window.
Signal: OFI over [T-h, T) / trailing depth. Target: mid return over [T+g, T+g+h). Walk-forward by day."""
import numpy as np, duckdb, json
import sys
sys.path.insert(0, "scripts")
import window as WIN
OUT = "data/derived/ofi"
con = duckdb.connect()
L = con.execute(f"select t_ns, bid_px, bid_sz, ask_px, ask_sz, regexp_extract(filename,'(\\d{{8}})',1) d from read_parquet('{OUT}/l1/*.parquet', filename=true) order by block").fetchnumpy()
t = L["t_ns"].astype(np.int64); bp, bs, ap, as_, d = L["bid_px"], L["bid_sz"], L["ask_px"], L["ask_sz"], L["d"]
ok = bp < ap; t, bp, bs, ap, as_, d = t[ok], bp[ok], bs[ok], ap[ok], as_[ok], d[ok]
e = np.zeros(len(t)); pb, qb, pa, qa = bp[:-1], bs[:-1], ap[:-1], as_[:-1]
e[1:] = (bp[1:] >= pb) * bs[1:] - (bp[1:] <= pb) * qb - (ap[1:] <= pa) * as_[1:] + (ap[1:] >= pa) * qa
e[np.r_[True, d[1:] != d[:-1]]] = 0
lmid = np.log((bp + ap) / 2); dep = (bs + as_) / 2
cume = np.r_[0, np.cumsum(e)]; dt = np.diff(np.r_[t, t[-1]]); cumdep = np.r_[0, np.cumsum(dep * dt)]; cumt = np.r_[0, np.cumsum(dt)]
DAY = 86400 * 10**9; t0 = (t[0] // DAY) * DAY
def mid_at(T):
    i = np.searchsorted(t, T, "left") - 1; return np.where(i >= 0, lmid[np.clip(i, 0, None)], np.nan)
out = {}
for h in (1, 5, 10):
    H = h * 10**9; T = np.arange(t0 + 1800 * 10**9, t0 + WIN.N_DAYS * DAY - 2 * H - 10**9, H)
    j0, j1 = np.searchsorted(t, T - H, "left"), np.searchsorted(t, T, "left")
    a0 = np.searchsorted(t, T - 1800 * 10**9, "left")
    D = (cumdep[j1] - cumdep[a0]) / np.maximum(cumt[j1] - cumt[a0], 1)
    x = (cume[j1] - cume[j0]) / D; day = ((T - t0) // DAY).astype(int)
    for g_ms in (0, 70, 140, 250, 500, 1000):
        g = g_ms * 10**6; y = (mid_at(T + g + H) - mid_at(T + g)) * 1e4
        v = np.isfinite(x) & np.isfinite(y); yy, yh = [], []
        for td in range(1, WIN.N_DAYS):
            tr, te = v & (day < td), v & (day == td)
            b = np.linalg.lstsq(np.c_[np.ones(tr.sum()), x[tr]], y[tr], rcond=None)[0]
            yy.append(y[te]); yh.append(b[0] + b[1] * x[te])
        yy, yh = np.concatenate(yy), np.concatenate(yh)
        out[f"{h}s_gap{g_ms}ms"] = float(1 - ((yy - yh) ** 2).sum() / (yy ** 2).sum())
        print(h, g_ms, round(out[f"{h}s_gap{g_ms}ms"], 4), flush=True)
json.dump(out, open(f"{OUT}/gap_res.json", "w"), indent=1)
