"""Independent per-order table for xyz:SP500 from raw node order statuses (+ Reservoir fills for
reduce-only fill sizes), with my own book replay for the touch at placement.
Writes data/checks/cancels/work/orders_<day>.parquet (user hashed, no addresses).
Usage: python -P orders.py 20261008 [...]"""
import sys, os, heapq, time
from datetime import datetime, timezone
import duckdb, numpy as np, pandas as pd

ROOT = "."
W = f"{ROOT}/data/checks/cancels/work"; os.makedirs(W, exist_ok=True)
TICK = 0.1

def replay(s, e, side, px):
    """Book state at end of each block: order rests at end of block b iff s <= b < e.
    Per-level counters with lazy heaps. Returns arrays (block, best_bid, best_ask) at each change."""
    tk = np.round(px / TICK).astype(np.int64)
    # events: at block s add, at block e remove (remove and add in same block both apply before snapshot)
    blk = np.concatenate([s, e]); d = np.concatenate([np.ones(len(s), np.int8), -np.ones(len(e), np.int8)])
    sd = np.concatenate([side, side]); tt = np.concatenate([tk, tk])
    o = np.argsort(blk, kind="stable"); blk, d, sd, tt = blk[o], d[o], sd[o], tt[o]
    cnt = {True: {}, False: {}}   # isbid -> tick -> count
    hb, ha = [], []
    ob, obid, oask = [], [], []
    lb = la = None
    n = len(blk); i = 0
    while i < n:
        b = blk[i]
        while i < n and blk[i] == b:
            isb = bool(sd[i]); t = int(tt[i]); c = cnt[isb]
            v = c.get(t, 0) + int(d[i]); c[t] = v
            if d[i] > 0 and v == 1:
                heapq.heappush(hb if isb else ha, -t if isb else t)
            i += 1
        while hb and cnt[True].get(-hb[0], 0) <= 0: heapq.heappop(hb)
        while ha and cnt[False].get(ha[0], 0) <= 0: heapq.heappop(ha)
        bb = -hb[0] if hb else None; ba = ha[0] if ha else None
        if bb != lb or ba != la:
            ob.append(int(b)); obid.append(np.nan if bb is None else bb * TICK); oask.append(np.nan if ba is None else ba * TICK)
            lb, la = bb, ba
    return pd.DataFrame({"block": ob, "bb": obid, "ba": oask})

for d in sys.argv[1:]:
    t0 = time.time()
    iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    day_ms = int(datetime.strptime(d, "%Y%m%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=2")
    con.execute(f"""CREATE TABLE fo AS SELECT order_id::BIGINT oid, sum(size::DOUBLE) fsz
        FROM '{ROOT}/data/raw/xyz/fills/{iso}.parquet' WHERE coin='xyz:SP500' GROUP BY 1""")
    # per-order rollup; ordering key within block: open first
    con.execute(f"""CREATE TABLE o AS
      WITH ev AS (SELECT oid, user, side, limit_px, sz, orig_sz, status, block_number b, event_time, order_ts_ms,
                     reduce_only, is_trigger, (status<>'open')::INT r
                  FROM '{ROOT}/data/l4/order_statuses/xyz_SP500/{d}/*.parquet' WHERE coin='xyz:SP500')
      SELECT oid, hash(any_value(user)) uh, any_value(side) side, bool_or(reduce_only) ro, bool_or(is_trigger) trig,
        max(orig_sz) osz, arg_min(limit_px, b*2+r) px, min(order_ts_ms) placed_ms,
        min(b) FILTER (WHERE status='open') b_open, min(b) b_first, max(b) b_last,
        arg_min(status, b*2+r) st0, arg_max(status, b*2+r) st1, arg_max(sz, b*2+r) lsz,
        arg_max(event_time, b*2+r) let
      FROM ev GROUP BY oid""")
    b0, b1, mpb = con.execute(f"""SELECT min(block_number), max(block_number),
        (max(epoch_ms(substr(event_time,1,23)::TIMESTAMP)) - min(epoch_ms(substr(event_time,1,23)::TIMESTAMP)))/(max(block_number)-min(block_number))
        FROM '{ROOT}/data/l4/order_statuses/xyz_SP500/{d}/*.parquet'""").fetchone()
    con.execute(f"""CREATE TABLE o2 AS SELECT o.*,
        (st1 LIKE '%anceled' OR st1='scheduledCancel') canc,
        CASE WHEN ro THEN coalesce(f.fsz,0) ELSE greatest(osz-coalesce(lsz,0),0) END fsz
      FROM o LEFT JOIN fo f USING (oid)""")
    con.execute(f"""CREATE TABLE o3 AS SELECT *,
      CASE WHEN trig OR st0='triggered' THEN 'trigger'
           WHEN st0 LIKE '%Rejected' AND st1 LIKE '%Rejected' THEN 'rejected'
           WHEN b_open IS NULL AND placed_ms < {day_ms} THEN 'pre'
           WHEN st1='filled' THEN 'filled'
           WHEN st1='open' THEN 'open_end'
           WHEN canc AND b_open=b_last THEN 'samebk'
           WHEN canc AND fsz>1e-12 THEN 'partial'
           WHEN canc THEN 'pulled' ELSE 'other' END cls
      FROM o2""")
    # resting intervals for the book
    r = con.execute(f"""SELECT CASE WHEN cls='pre' THEN {b0} ELSE b_open END s,
          CASE WHEN cls='open_end' THEN {b1}+1 ELSE b_last END e, side='B' isb, px
        FROM o3 WHERE cls IN ('pulled','partial','filled','open_end','pre') AND px IS NOT NULL""").df()
    r = r[(r.s.notna()) & (r.e > r.s)]
    bbo = replay(r.s.to_numpy(np.int64), r.e.to_numpy(np.int64), r.isb.to_numpy(), r.px.to_numpy())
    con.register("bbo_df", bbo)
    con.execute(f"""COPY (
      SELECT x.oid, x.uh, x.side, x.px, x.osz, x.placed_ms, x.b_open, x.b_first, x.b_last, x.cls, x.st1, x.let,
        {mpb} mpb, (x.b_last-x.b_open) brest,
        CASE WHEN x.cls<>'trigger' THEN x.px*x.osz END ntl, CASE WHEN x.cls<>'trigger' THEN x.px*x.fsz END fusd,
        k.bb, k.ba,
        CASE WHEN x.side='B' THEN (k.bb-x.px)/((k.bb+k.ba)/2)*1e4 ELSE (x.px-k.ba)/((k.bb+k.ba)/2)*1e4 END dist
      FROM o3 x ASOF LEFT JOIN bbo_df k ON k.block < coalesce(x.b_open, x.b_first)
    ) TO '{W}/orders_{d}.parquet' (FORMAT parquet)""")
    print(d, con.execute(f"SELECT count(*) FROM '{W}/orders_{d}.parquet'").fetchone(), len(bbo), f"{time.time()-t0:.0f}s", flush=True)
    bbo.to_parquet(f"{W}/bbo_{d}.parquet")
