"""Mechanical impact from the displayed top-20 L2 (Reservoir 1m): for a market order of $Q,
mid shift if consumed levels are not refilled, and depth within k bps of mid, every day of the run window (scripts/window.py)."""
import duckdb, numpy as np, pandas as pd, json
import sys
sys.path.insert(0, "scripts")
import window as WIN
R = "."; O = f"{R}/data/derived/impact"
con = duckdb.connect()
Q = np.logspace(3, 7, 25)
rows = []; dep = []; cens = np.zeros(len(Q)); tot = 0
for iso in WIN.ISO:
    df = con.execute(f"select block_time_ms, bids, asks from '{R}/data/raw/xyz/book_1m/SP500/{iso}.parquet'").fetchall()
    for t, bids, asks in df:
        if not bids or not asks: continue
        bp = np.array([float(x['px']) for x in bids]); bs = np.array([float(x['sz']) for x in bids])
        ap = np.array([float(x['px']) for x in asks]); az = np.array([float(x['sz']) for x in asks])
        mid = (bp[0] + ap[0]) / 2
        for side, p, s, opp in [(1, ap, az, bp[0]), (-1, bp, bs, ap[0])]:
            cum = np.cumsum(p * s); tot += 1
            k = np.searchsorted(cum, Q, 'right')   # first level not fully consumed
            ok = k < len(p); cens += ~ok
            newbest = np.where(ok, p[np.minimum(k, len(p) - 1)], np.nan)
            shift = side * ((newbest + opp) / 2 - mid) / mid * 1e4
            rows.append(shift)
            dist = side * (p - mid) / mid * 1e4
            dep.append([cum[dist <= x][-1] if (dist <= x).any() else 0 for x in (0.5, 1, 2, 3)] + [dist[-1]])
S = np.array(rows); D = np.array(dep)
res = dict(Q=Q.tolist(), shift_med=np.nanmedian(S, 0).tolist(), shift_mean=np.nanmean(S, 0).tolist(),
           shift_p25=np.nanpercentile(S, 25, 0).tolist(), shift_p75=np.nanpercentile(S, 75, 0).tolist(),
           censored_frac=(cens / tot).tolist(), n_side_snaps=int(tot),
           depth_med_usd={k: float(np.median(D[:, i])) for i, k in enumerate(['0.5', '1', '2', '3'])},
           depth_mean_usd={k: float(np.mean(D[:, i])) for i, k in enumerate(['0.5', '1', '2', '3'])},
           top20_reach_bps_med=float(np.median(D[:, 4])))
json.dump(res, open(f"{O}/bookwalk.json", 'w'), indent=1)
for i in range(0, 25, 2): print(f"Q ${Q[i]:>12,.0f}  med {res['shift_med'][i]:.3f}  mean {res['shift_mean'][i]:.3f}  cens {res['censored_frac'][i]:.3f}")
print(res['depth_med_usd'], res['depth_mean_usd'], res['top20_reach_bps_med'], tot)
