"""Top-of-book with sizes per block for xyz:SP500, from lifecycles + order_statuses + maker fills.

Resting intervals follow scripts/touch.py (rest from b_open to b_last; pre_existing from day_b0;
still_open to day_b1+1). Resting size: open-event sz, minus maker fills (Reservoir, crossed=false)
at the block they print in; pre_existing orders start at (in-window maker fills + remaining at their
last event). Reduce-only shrink without a fill is ignored.
Output: data/derived/ofi/l1/<day>.parquet with block, t_ns, bid_px, bid_sz, ask_px, ask_sz at every
change of any of the four.
Usage: python l1.py 20261014 [more days]
"""
import heapq, os, sys, time
import duckdb, numpy as np, pyarrow as pa, pyarrow.parquet as pq

ROOT = "."
OUT = f"{ROOT}/data/derived/ofi/l1"


def day(d):
    t0 = time.time()
    iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    con = duckdb.connect(); con.execute("SET threads=2")
    con.execute(f"CREATE TABLE lc AS SELECT * FROM '{ROOT}/data/derived/lifecycle/xyz_SP500/{d}.parquet'")
    con.execute(f"""CREATE TABLE st AS SELECT block_number b, epoch_ns(block_time::timestamp) tn, oid, status, sz
                    FROM read_parquet('{ROOT}/data/l4/order_statuses/xyz_SP500/{d}/*.parquet')""")
    con.execute("CREATE TABLE bt AS SELECT b, min(tn) tn FROM st GROUP BY b ORDER BY b")
    con.execute(f"""CREATE TABLE mf AS SELECT order_id::BIGINT oid, epoch_ns(timestamp::timestamp) fn, size::DOUBLE fsz
                    FROM '{ROOT}/data/raw/xyz/fills/{iso}.parquet' WHERE coin='xyz:SP500' AND NOT crossed""")
    con.execute("CREATE TABLE mfb AS SELECT m.oid, m.fsz, x.b FROM mf m ASOF JOIN bt x ON x.tn >= m.fn")
    con.execute("""
      CREATE TABLE r AS
      SELECT l.oid, l.side, l.limit_px px,
             CASE WHEN class='pre_existing' THEN day_b0 ELSE b_open END s,
             CASE WHEN class='still_open' THEN day_b1+1 ELSE b_last END e,
             CASE WHEN class='pre_existing' THEN coalesce(f.fs,0) + coalesce(l.last_sz,0) ELSE o.sz END sz0
      FROM lc l
      LEFT JOIN (SELECT oid, max(sz) sz FROM st WHERE status='open' GROUP BY oid) o USING(oid)
      LEFT JOIN (SELECT oid, sum(fsz) fs FROM mfb GROUP BY oid) f USING(oid)
      WHERE class IN ('displayed_pulled','displayed_partial','filled','still_open','pre_existing')
        AND displayed_blocks > 0 AND limit_px IS NOT NULL""")
    ev = con.execute("""
      SELECT blk, kind, oid, side='B' isb, px, dsz FROM (
        SELECT s blk, 0 kind, oid, side, px, sz0 dsz FROM r
        UNION ALL
        SELECT m.b, 1, m.oid, r.side, r.px, -m.fsz FROM mfb m JOIN r USING(oid) WHERE m.b > r.s AND m.b < r.e
        UNION ALL
        SELECT e, 2, oid, side, px, 0 FROM r
      ) ORDER BY blk, kind""").fetchnumpy()
    nmiss = con.execute("SELECT count(*) FROM r WHERE sz0 IS NULL").fetchone()[0]
    bt = con.execute("SELECT b, tn FROM bt").fetchnumpy()
    blk = ev["blk"].astype(np.int64); kind = ev["kind"]; oid = ev["oid"]; isb = ev["isb"]
    px = ev["px"].astype(np.float64); dsz = np.nan_to_num(ev["dsz"].astype(np.float64))
    rem = {}              # oid -> remaining size
    lvl = ({}, {})        # bid/ask px -> size
    heaps = ([], [])      # bid: -px, ask: px
    ob, obp, obs, oap, oas = [], [], [], [], []
    last = None
    def top(k):
        h, L = heaps[k], lvl[k]
        while h:
            p = -h[0] if k == 0 else h[0]
            if L.get(p, 0) > 1e-9: return p, L[p]
            heapq.heappop(h); L.pop(p, None)
        return np.nan, 0.0
    i, n = 0, len(blk)
    while i < n:
        b = blk[i]
        while i < n and blk[i] == b:
            k = 0 if isb[i] else 1; p = px[i]; o = oid[i]; L = lvl[k]
            if kind[i] == 0:
                rem[o] = dsz[i]
                if p not in L or L[p] <= 1e-9: heapq.heappush(heaps[k], -p if k == 0 else p)
                L[p] = L.get(p, 0.0) + dsz[i]
            elif kind[i] == 1:
                if o in rem:
                    d_ = max(dsz[i], -rem[o]); rem[o] += d_; L[p] = L.get(p, 0.0) + d_
            else:
                r_ = rem.pop(o, 0.0); L[p] = L.get(p, 0.0) - r_
            i += 1
        bp, bs = top(0); ap, as_ = top(1)
        cur = (bp, round(bs, 6), ap, round(as_, 6))
        if cur != last:
            ob.append(b); obp.append(bp); obs.append(bs); oap.append(ap); oas.append(as_); last = cur
    ob = np.array(ob, np.int64)
    j = np.searchsorted(bt["b"], ob); j = np.clip(j, 0, len(bt["b"]) - 1)
    tn = np.where(bt["b"][j] == ob, bt["tn"][j], -1)  # blocks w/o status events (close at e) -> fill below
    # end blocks come from status events, so nearly all match; forward-fill from the previous known block otherwise
    tn = np.maximum.accumulate(np.where(tn < 0, 0, tn))
    os.makedirs(OUT, exist_ok=True)
    pq.write_table(pa.table({"block": ob, "t_ns": tn, "bid_px": obp, "bid_sz": obs, "ask_px": oap, "ask_sz": oas}),
                   f"{OUT}/{d}.parquet", compression="zstd")
    print(d, f"orders={con.execute('select count(*) from r').fetchone()[0]:,} missing_sz0={nmiss} rows={len(ob):,} {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    for d in sys.argv[1:]: day(d)
