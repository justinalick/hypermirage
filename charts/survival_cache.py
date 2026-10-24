"""Cache the Kaplan-Meier curves of analysis/survival_viz.py to a small json (same query, count weights).
DuckDB capped at 2 GB / 2 threads per the brief."""
import json, os, duckdb, numpy as np
ROOT = "."
LT = f"{ROOT}/data/derived/lifecycle_touch/xyz_SP500/*.parquet"
GROUP = """CASE WHEN dist_bucket IN ('1 improves touch', '2 at touch') THEN 'a'
                 WHEN dist_bucket = '3 within 1 bp' THEN 'b'
                 WHEN dist_bucket = '4 1-5 bps' THEN 'c' ELSE 'd' END"""
WHERE = """displayed_blocks > 0 AND dist_bps IS NOT NULL
          AND class IN ('displayed_pulled','displayed_partial','filled','still_open')"""
con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=2")
df = con.execute(f"""
    SELECT {GROUP} b, displayed_blocks * ms_per_block t,
           sum(CASE WHEN class IN ('displayed_pulled','displayed_partial') THEN 1 ELSE 0 END) ev, count(*) w
    FROM read_parquet('{LT}') WHERE {WHERE} GROUP BY 1, 2 ORDER BY 1, 2""").df()
meta = con.execute(f"""SELECT count(*) n, count(DISTINCT user) accts, min(placed_ms) p0, max(placed_ms) p1
    FROM read_parquet('{LT}') WHERE {WHERE}""").df().iloc[0]
grid = np.geomspace(0.03, 3600, 4000) * 1000
out = {"meta": {k: int(meta[k]) for k in ("n", "accts", "p0", "p1")}, "grid_s": (grid / 1000).tolist(), "curves": {}}
for b, g in df.groupby("b"):
    g = g.sort_values("t"); t = g.t.to_numpy(float)
    at_risk = g.w[::-1].cumsum()[::-1].to_numpy()
    s = np.cumprod(1 - g.ev.to_numpy() / at_risk)
    i = np.searchsorted(t, grid, side="right") - 1
    sg = np.where(i < 0, 1.0, s[np.clip(i, 0, None)])
    j = np.searchsorted(t, 1000, side="right") - 1
    out["curves"][b] = {"n": int(g.w.sum()), "s": sg.round(6).tolist(), "cancel_1s": float(1 - s[j]),
                        "t_first_s": float(t[0] / 1000)}
    print(b, out["curves"][b]["n"], round(out["curves"][b]["cancel_1s"], 4), len(t))
print(out["meta"])
json.dump(out, open(f"{ROOT}/data/derived/chart_cache/survival.json", "w"))
