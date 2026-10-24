"""Kaplan-Meier fill probability (%) by queue bucket, from table r of queue.duckdb (analysis/queue_fill.sql).
Event = first fill (secs_to_fill); orders that end unfilled are censored at secs_alive; orders still open at
the end of the data are left out. Writes data/derived/queue/km.json for charts/queue_fill.py."""
import json, sys, duckdb, numpy as np

DB = sys.argv[1] if len(sys.argv) > 1 else "data/derived/queue/queue.duckdb"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/derived/queue/km.json"
GRID = [0.1, 0.5, 1, 5, 30, 300]
con = duckdb.connect(DB, read_only=True); con.execute("SET memory_limit='2GB'; SET threads=2")
km = {}
for (qb,) in con.execute("SELECT DISTINCT qb FROM r ORDER BY 1").fetchall():
    d = con.execute("""SELECT CASE WHEN any_fill AND secs_to_fill >= 0 THEN secs_to_fill ELSE secs_alive END tt,
                              any_fill AND secs_to_fill >= 0 ev
                       FROM r WHERE qb = ? AND ((any_fill AND secs_to_fill >= 0) OR secs_alive >= 0)""", [qb]).fetchnumpy()
    tt, ev = d["tt"].astype(float), d["ev"].astype(bool)
    o = np.argsort(tt, kind="stable"); tt, ev = tt[o], ev[o]
    ut, idx = np.unique(tt, return_index=True)
    S = np.cumprod(1 - np.add.reduceat(ev.astype(int), idx) / (len(tt) - idx))
    km[qb] = [float(100 * (1 - (S[np.searchsorted(ut, g, side="right") - 1] if g >= ut[0] else 1.0))) for g in GRID]
    print(qb, len(tt), " ".join(f"{v:.1f}" for v in km[qb]))
json.dump({"grid": GRID, "km": km}, open(OUT, "w"))
