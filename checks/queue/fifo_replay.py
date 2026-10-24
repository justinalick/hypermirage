"""Independent FIFO head-hit check. Own book (per-level dict of oid->remaining, priority = lowest oid),
own fill sequencing (fill -> block by ms timestamp; inside the block, just before the taker's first status
row, else at block start). Also records entry position/queue-ahead for touch opens to cross-check buckets.
Usage: fifo_replay.py WARMUP_DAY... -- CHECK_DAY...
"""
import sys, json, duckdb, numpy as np, pandas as pd
D = "data"; W = "data/checks/queue/work"
a = sys.argv[1:]; warm = a[:a.index("--")]; check = a[a.index("--") + 1:]
c = duckdb.connect(); c.execute("SET memory_limit='2GB'; SET threads=2")

book = {}      # (is_bid, px) -> {oid: remaining}
where = {}     # oid -> (is_bid, px)
res = {}

import heapq
heaps = {True: [], False: []}; inheap = set()
tot = {}       # (is_bid, px) -> live remaining at level
def best(is_bid):
    h = heaps[is_bid]
    while h:
        p = -h[0] if is_bid else h[0]
        if tot.get((is_bid, p), 0.0) > 1e-12:
            return p
        heapq.heappop(h); inheap.discard((is_bid, p))
    return None
def push(k):
    if k not in inheap:
        heapq.heappush(heaps[k[0]], -k[1] if k[0] else k[1]); inheap.add(k)

# cache of best prices maintained lazily: recompute only when needed (opens of touch candidates)
for day in warm + check:
    ev = c.execute(f"""
      SELECT row_number() OVER () - 1 AS r, block_number blk, oid, status, side='B' is_bid, limit_px px, sz,
             (coalesce(is_trigger,false) OR coalesce(tif,'')='Ioc' OR coalesce(order_type,'')='Market') nb,
             epoch_ms(CAST(substr(block_time,1,23) AS TIMESTAMP)) bms, "user" IS NOT NULL u
      FROM read_parquet('{D}/l4/order_statuses/xyz_SP500/{day}/*.parquet', file_row_number=true, filename=true)
      WHERE coin='xyz:SP500' AND (status IN ('open','filled','scheduledCancel') OR status LIKE '%anceled')
      ORDER BY CAST(regexp_extract(filename,'/(\\d+)\\.parquet$',1) AS INT), file_row_number""").df()
    fl = c.execute(f"""SELECT trade_id, order_id oid, CAST(size AS DOUBLE) sz, crossed, epoch_ms(timestamp) fms
      FROM read_parquet('{D}/raw/xyz/fills/{day[:4]}-{day[4:6]}-{day[6:]}.parquet') WHERE coin='xyz:SP500'""").df()
    mk = fl[~fl.crossed].copy()
    tk = fl[fl.crossed].groupby("trade_id").oid.first().rename("taker")
    mk = mk.join(tk, on="trade_id")
    # block per ms (first row of each block), fills map to the block with the same truncated ms, else next block within 3 ms
    bl = ev.groupby("blk").agg(bms=("bms", "first"), r0=("r", "min")).reset_index().sort_values("bms")
    # exact block (same ms, up to 3 ms later); fills in blocks with no SP500 status rows go just before
    # the next block that has rows (i.e. after everything earlier), never before earlier events
    mk = pd.merge_asof(mk.sort_values("fms"), bl[["bms", "blk", "r0"]], left_on="fms", right_on="bms",
                       direction="forward")
    mk.loc[(mk.bms - mk.fms) > 3, "blk"] = -1
    # taker's first status row in that block
    first = ev.groupby(["blk", "oid"]).r.min().rename("tr").reset_index().rename(columns={"oid": "taker"})
    mk = mk.merge(first, on=["blk", "taker"], how="left")
    mk["pos"] = mk.tr.fillna(mk.r0).fillna(-1).astype(np.int64)
    n_between = int((mk.blk == -1).sum())
    mk = mk[mk.pos >= 0].sort_values(["pos", "trade_id"])
    sweeps = {p: g[["oid", "sz"]].to_numpy() for p, g in mk.groupby("pos")}
    unplaced = int(len(fl[~fl.crossed]) - len(mk))
    ok = bad = unknown = 0
    touch = []   # (oid, pos, ahead_sz, px) for opens at/inside touch
    E = ev[["r", "oid", "status", "is_bid", "px", "sz", "nb"]].itertuples(index=False)
    for r, oid, st, is_bid, px, sz, nb in E:
        sw = sweeps.get(r)
        if sw is not None:
            hit = []
            for moid, msz in sw:
                k = where.get(int(moid))
                if k is None:
                    unknown += 1; continue
                lv = book[k]; take = min(msz, lv[int(moid)]); lv[int(moid)] -= take; tot[k] -= take
                hit.append((int(moid), k))
            for moid, k in hit:
                if any(o < moid and rem > 1e-12 for o, rem in book[k].items()):
                    bad += 1
                else:
                    ok += 1
        if st == "open":
            if nb: continue
            k = (bool(is_bid), float(px))
            if day in check:
                bs = best(k[0])
                if bs is None or (px > bs if is_bid else px < bs):
                    touch.append((oid, 0, 0.0))
                elif px == bs:
                    touch.append((oid, 1, tot[k]))
            book.setdefault(k, {})[int(oid)] = float(sz); where[int(oid)] = k; tot[k] = tot.get(k, 0.0) + float(sz); push(k)
        else:
            k = where.pop(int(oid), None)
            if k is not None:
                lv = book[k]; tot[k] -= lv.pop(int(oid), 0.0)
                if not lv: del book[k]; tot.pop(k, None)
    # flush sweeps placed after the last row (none expected)
    if day in check:
        res[day] = {"head": ok, "not_head": bad, "share": ok / (ok + bad), "unknown_maker": unknown,
                    "maker_fills": int((~fl.crossed).sum()), "unplaced": unplaced, "placed_between_blocks": n_between}
        pd.DataFrame(touch, columns=["oid", "pos", "ahead_sz"]).to_parquet(f"{W}/touch_{day}.parquet")
    print(day, res.get(day, "warm"), flush=True)
json.dump(res, open(f"data/checks/queue/fifo_{'_'.join(check)}.json", "w"), indent=1)
