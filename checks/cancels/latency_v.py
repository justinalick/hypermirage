"""Independent pull-latency recompute, xyz:SP500. Same event definition and the same random draws as the
original (numpy default_rng(7), consumed day by day in the same order, drawn as vectors), but exposure is
found with a binned equi-join in DuckDB on my own order tables (not the sweep line), and the 30% move
sample can be switched off (--all) to check that the rates do not depend on the sample.
Writes work/lat_<mode>.parquet with (day, ev, mv, k, n); k NULL = not pulled within 100 blocks.
Usage: python -P latency_v.py [--all] 20261008 ..."""
import sys, duckdb, numpy as np, pandas as pd
ROOT = "."; W = f"{ROOT}/data/checks/cancels/work"; TICK = 0.1; BIN = 2000
args = sys.argv[1:]; ALL = "--all" in args; days = [a for a in args if a != "--all"]
rng = np.random.default_rng(7)
con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=2")
out = []
for d in days:
    l1 = con.execute(f"SELECT block, bid_px, ask_px FROM '{ROOT}/data/derived/ofi/l1/{d}.parquet' ORDER BY block").df()
    ch = ((l1.bid_px.diff() != 0) | (l1.ask_px.diff() != 0)).to_numpy()
    px = l1[ch].reset_index(drop=True)
    blk = px.block.to_numpy(); bid = px.bid_px.to_numpy(); ask = px.ask_px.to_numpy()
    pb = np.r_[np.nan, bid[:-1]]; pa = np.r_[np.nan, ask[:-1]]
    gap = np.r_[np.nan, np.diff(blk)]
    cand = np.where(gap > 5)[0]
    u = rng.random(len(cand))
    if not ALL: cand = cand[u <= 0.3]
    E = []
    a = cand[ask[cand] != pa[cand]]
    E.append(pd.DataFrame({"t": blk[a], "side": "B", "ev": np.where(ask[a] < pa[a], "adverse", "favorable"),
                           "dmv": np.abs(ask[a] - pa[a]), "best": pb[a]}))
    b = cand[bid[cand] != pb[cand]]
    E.append(pd.DataFrame({"t": blk[b], "side": "A", "ev": np.where(bid[b] > pb[b], "adverse", "favorable"),
                           "dmv": np.abs(bid[b] - pb[b]), "best": pa[b]}))
    ct = rng.integers(int(blk[1]), int(blk[-1]), 60000)
    j = np.searchsorted(blk, ct, side="right") - 1
    ok = (ct - blk[j]) > 5
    sb = rng.random(int(ok.sum())) < 0.5
    E.append(pd.DataFrame({"t": ct[ok], "side": np.where(sb, "B", "A"), "ev": "control", "dmv": 0.0,
                           "best": np.where(sb, bid[j[ok]], ask[j[ok]])}))
    E = pd.concat(E, ignore_index=True)
    E = E[np.isfinite(E.best) & np.isfinite(E.dmv)].copy()
    E["mv"] = np.minimum(np.round(E.dmv / TICK), 3).astype(int)
    E["bt"] = np.round(E.best / TICK).astype(np.int64); E["w"] = np.ceil(E.best * 1e-4 / TICK).astype(np.int64)
    E["lo"] = np.where(E.side == "B", E.bt - E.w, E.bt); E["hi"] = np.where(E.side == "B", E.bt, E.bt + E.w)
    E["eid"] = np.arange(len(E))
    # expand events over the tick window (small), orders over time bins; equi-join on (side, tick, bin)
    con.register("E", E[["eid", "t", "side", "ev", "mv", "lo", "hi"]])
    r = con.execute(f"""
      WITH o AS (SELECT side, round(px/{TICK})::BIGINT tk, b_open, b_last, cls IN ('pulled','partial') pulled
                 FROM '{W}/orders_{d}.parquet' WHERE cls IN ('pulled','partial','filled') AND brest>0),
      ob AS (SELECT *, unnest(range(b_open//{BIN}, b_last//{BIN}+1)) bn FROM o),
      eb AS (SELECT eid, t, side, ev, mv, unnest(range(lo, hi+1)) tk, t//{BIN} bn FROM E),
      p AS (SELECT eb.ev, eb.mv, CASE WHEN ob.pulled AND ob.b_last-eb.t<=100 THEN ob.b_last-eb.t END k
            FROM eb JOIN ob ON ob.side=eb.side AND ob.tk=eb.tk AND ob.bn=eb.bn
            WHERE ob.b_open<=eb.t-1 AND ob.b_last>eb.t)
      SELECT '{d}' AS day, ev, mv, k, count(*) n FROM p GROUP BY ALL""").df()
    out.append(r)
    print(d, len(E), int(r.n.sum()), flush=True)
pd.concat(out).to_parquet(f"{W}/lat_{'all' if ALL else 's30'}.parquet")
