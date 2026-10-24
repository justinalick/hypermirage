#!/usr/bin/env python3
"""FIFO queue replay of the xyz:SP500 book from node order statuses plus Reservoir maker fills.

For every order that rests, records where it sat when it entered the book: improving the touch,
joining the touch (with the size already queued ahead of it at that price), or behind the touch.
Then records what happened: fills after resting, time to first fill, time to removal.

Assumptions (all checked or counted in the output, not taken on faith):
  * Price-time priority, FIFO within a price level. Priority = oid (oids rise strictly in the
    node's processing order, checked on 2026-10-20). Validated per maker fill: the filled order
    should be the head of its level in the replay.
  * Intra-block order: status events in node row order. Each match is placed immediately before
    the taker order's first status event in that block (fills carry the taker oid and trade_id).
  * Cancels are explicit in node data (every removal has a status event), so there are no
    inferred "hidden" cancels. Remaining blind spots: orders resting since before the first day
    with no event until later (discovered late; counted), and partial fills of reduce-only orders
    are taken from Reservoir fills like every other fill.
  * Sizes: remaining size at the open event (after any matching on arrival), reduced by maker
    fills; removed at the terminal status.

Days are replayed in sequence and the book carries over, so the first day is warm-up.

Output: data/derived/queue/<YYYYMMDD>.parquet (one row per order that opened), fifo_check.parquet.
"""
from __future__ import annotations

import heapq
import os
import sys
import time
from collections import deque

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = os.path.abspath(".")
COIN = "xyz:SP500"
SLUG = "xyz_SP500"
OUT = os.path.join(ROOT, "data/derived/queue")

EV_SQL = """
CREATE OR REPLACE TABLE ev AS
SELECT CAST(regexp_extract(filename, '/(\\d+)\\.parquet$', 1) AS BIGINT) * 100000000 + file_row_number AS key,
       block_number AS blk,
       epoch_ms(CAST(substr(event_time, 1, 23) AS TIMESTAMP)) AS t_ms,
       oid, status, side, limit_px AS px, sz, "user", tif, is_trigger, order_type
FROM read_parquet($glob, filename = true, file_row_number = true)
WHERE coin = $coin
"""

FILL_SQL = """
WITH f AS (
  SELECT trade_id, crossed, order_id, CAST(size AS DOUBLE) AS sz, CAST(price AS DOUBLE) AS px,
         epoch_ms(timestamp) AS t_ms
  FROM read_parquet($fills) WHERE coin = $coin
),
m AS (SELECT trade_id, order_id AS maker, sz, px, t_ms FROM f WHERE NOT crossed),
t AS (SELECT trade_id, any_value(order_id) AS taker FROM f WHERE crossed GROUP BY trade_id),
mt AS (SELECT m.*, t.taker FROM m LEFT JOIN t USING (trade_id)),
k AS (
  SELECT mt.trade_id, min(ev.key) AS key
  FROM mt JOIN ev ON ev.oid = mt.taker AND abs(ev.t_ms - mt.t_ms) <= 3
  GROUP BY mt.trade_id
),
blk AS (SELECT t_ms, min(key) AS first_key FROM ev GROUP BY t_ms),
j AS (
  SELECT mt.trade_id, mt.maker, mt.sz, mt.px, mt.t_ms, k.key AS k_key
  FROM mt LEFT JOIN k USING (trade_id)
)
SELECT j.trade_id, j.maker, j.sz, j.px, j.t_ms,
       coalesce(j.k_key, b.first_key, 0) AS key,
       j.k_key IS NULL AS fallback
FROM j ASOF LEFT JOIN blk b ON b.t_ms <= j.t_ms + 3
ORDER BY key, trade_id
"""


class Level:
    __slots__ = ("q", "total", "n")

    def __init__(self):
        self.q = deque()
        self.total = 0.0
        self.n = 0           # live orders at the level


def main() -> int:
    days = sorted(os.listdir(os.path.join(ROOT, "data/l4/order_statuses", SLUG)))
    days = [d for d in days if os.path.exists(os.path.join(ROOT, "data/derived/lifecycle", SLUG, f"{d}.parquet"))]
    if len(sys.argv) > 1:
        days = [d for d in days if d in sys.argv[1:]]
    os.makedirs(OUT, exist_ok=True)

    orders: dict[int, list] = {}          # oid -> [side_is_bid, px, remaining, rec_idx]
    levels: dict[tuple, Level] = {}       # (is_bid, px) -> Level
    bid_heap: list = []                   # -px
    ask_heap: list = []                   # px
    in_heap: set = set()                  # (is_bid, px) with an entry in its heap (one per price)
    fifo_rows = []
    diag = []

    def best(is_bid):
        h = bid_heap if is_bid else ask_heap
        while h:
            p = -h[0] if is_bid else h[0]
            lv = levels.get((is_bid, p))
            if lv is not None and lv.total > 1e-12:
                return p
            in_heap.discard((is_bid, p))
            heapq.heappop(h)
        return None

    def activate(is_bid, p, lv):
        if (is_bid, p) not in in_heap:
            heapq.heappush(bid_heap if is_bid else ask_heap, -p if is_bid else p)
            in_heap.add((is_bid, p))

    con = duckdb.connect()
    con.execute("SET threads = 4")
    con.execute("SET memory_limit = '1500MB'")
    for day in days:
        t0 = time.time()
        glob = os.path.join(ROOT, "data/l4/order_statuses", SLUG, day, "*.parquet")
        fills = os.path.join(ROOT, "data/raw/xyz/fills", f"{day[:4]}-{day[4:6]}-{day[6:]}.parquet")
        con.execute(EV_SQL, {"glob": glob, "coin": COIN}).fetchall()
        st = con.execute("""
            SELECT key, blk, t_ms, oid, status = 'open' AS is_open, side = 'B' AS is_bid,
                   coalesce(px, 0) AS px, coalesce(sz, 0) AS sz,
                   coalesce(is_trigger, false) OR coalesce(tif, '') = 'Ioc' OR coalesce(order_type, '') = 'Market' AS not_booked,
                   CASE WHEN status = 'open' THEN 0 WHEN status = 'filled' THEN 1 WHEN status = 'canceled' THEN 2 ELSE 3 END AS end_code
            FROM ev
            WHERE status = 'open' OR status = 'filled' OR status LIKE '%anceled' OR status = 'scheduledCancel'
            ORDER BY key
        """).fetchnumpy()
        fl = con.execute(FILL_SQL, {"fills": fills, "coin": COIN}).fetchnumpy()

        con.execute("DROP TABLE ev").fetchall()
        st = {k: (v.filled(0) if np.ma.isMaskedArray(v) else v) for k, v in st.items()}
        st["key"] = st["key"].tolist()
        fl = {k: (v.filled(0) if np.ma.isMaskedArray(v) else v).tolist() for k, v in fl.items()}
        n_st, n_fl = len(st["key"]), len(fl["key"])
        s_key, s_blk, s_t = st["key"], st["blk"], st["t_ms"]
        s_oid, s_open, s_bid, s_px, s_sz = st["oid"], st["is_open"], st["is_bid"], st["px"], st["sz"]
        s_nb, s_end = st["not_booked"], st["end_code"]
        END_NAMES = ("open", "filled", "canceled", "other_cancel")
        f_key, f_maker, f_sz, f_t = fl["key"], fl["maker"], fl["sz"], fl["t_ms"]
        f_fallback = fl["fallback"]

        # per-order records for orders opened today
        R = {k: [] for k in ("oid", "is_bid", "px", "sz0", "blk_open", "t_open",
                             "pos", "ahead_sz", "ahead_n", "level_sz", "best_same", "best_opp",
                             "fill_sz", "t_first_fill", "t_end", "blk_end", "end_status")}
        carried_out = []

        fifo_ok = fifo_bad = fifo_unknown = 0
        bad_ahead = []
        late_found = 0
        n_pos = [0, 0, 0]
        not_booked = crossed = 0

        i = j = 0
        while i < n_st or j < n_fl:
            if j < n_fl and (i >= n_st or f_key[j] < s_key[i] or (f_key[j] == s_key[i])):
                # one taker's matches (same key): apply them all, then check FIFO. Within a sweep
                # trade_id order need not follow queue order, so the test is whether any size is
                # left ahead of a filled order once the whole sweep is applied.
                j2 = j
                while j2 < n_fl and f_key[j2] == f_key[j]:
                    j2 += 1
                touched = []
                for jj in range(j, j2):
                    oid = int(f_maker[jj]); sz = float(f_sz[jj])
                    o = orders.get(oid)
                    if o is None:
                        fifo_unknown += 1
                        continue
                    lv = levels[(o[0], o[1])]
                    take = min(sz, o[2])
                    o[2] -= take
                    lv.total -= take
                    touched.append((oid, o, lv, jj))
                    if o[3] is not None:
                        d, idx = o[3]
                        if d == day:
                            R["fill_sz"][idx] += sz
                            if R["t_first_fill"][idx] < 0:
                                R["t_first_fill"][idx] = int(f_t[jj])
                        else:
                            carried_out.append((oid, "fill", sz, int(f_t[jj])))
                for oid, o, lv, jj in touched:
                    ahead = 0.0; head = None; scanned = 0
                    for q_oid in lv.q:
                        if q_oid == oid:
                            break
                        qo = orders.get(q_oid)
                        if qo is None or qo[2] <= 1e-12:
                            continue
                        if head is None:
                            head = q_oid
                        ahead += qo[2]
                        scanned += 1
                        if scanned > 5000:
                            break
                    if ahead <= 1e-12:
                        fifo_ok += 1
                    else:
                        fifo_bad += 1
                        bad_ahead.append(ahead * o[1])
                        ho = orders.get(head)
                        diag.append((day, int(f_t[jj]), int(f_key[jj]), oid, head, ahead * o[1],
                                     -1 if ho is None or ho[3] is None else ho[3][1] if ho[3][0] == day else -2,
                                     bool(f_fallback[jj])))
                j = j2
                continue

            is_open = bool(s_open[i]); oid = int(s_oid[i])
            if is_open and s_nb[i]:
                # resting trigger orders, IOC and market orders are not in the book
                not_booked += 1
                i += 1
                continue
            if is_open:
                is_bid = bool(s_bid[i])
                p = float(s_px[i]); sz = float(s_sz[i])
                bs = best(is_bid); bo = best(not is_bid)
                if bo is not None and ((p >= bo) if is_bid else (p <= bo)):
                    crossed += 1
                key = (is_bid, p)
                lv = levels.get(key)
                if lv is None:
                    lv = levels[key] = Level()
                if bs is None:
                    pos = 0
                elif (p > bs) if is_bid else (p < bs):
                    pos = 0          # improves the touch
                elif p == bs:
                    pos = 1          # joins the touch
                else:
                    pos = 2          # behind the touch
                ahead_n = 0
                if pos == 1:
                    for q_oid in lv.q:
                        qo = orders.get(q_oid)
                        if qo is not None and qo[2] > 1e-12:
                            ahead_n += 1
                n_pos[pos] += 1
                if pos == 2:
                    # behind the touch: kept in the book, not recorded (memory)
                    orders[oid] = [is_bid, p, sz, None]
                    lv.q.append(oid); lv.n += 1; lv.total += sz
                    activate(is_bid, p, lv)
                    i += 1
                    continue
                idx = len(R["oid"])
                R["oid"].append(oid); R["is_bid"].append(is_bid)
                R["px"].append(p); R["sz0"].append(sz); R["blk_open"].append(int(s_blk[i]))
                R["t_open"].append(int(s_t[i])); R["pos"].append(pos)
                R["ahead_sz"].append(lv.total if pos == 1 else (0.0 if pos == 0 else np.nan))
                R["ahead_n"].append(ahead_n); R["level_sz"].append(lv.total)
                R["best_same"].append(np.nan if bs is None else bs)
                R["best_opp"].append(np.nan if bo is None else bo)
                R["fill_sz"].append(0.0); R["t_first_fill"].append(-1); R["t_end"].append(-1)
                R["blk_end"].append(-1); R["end_status"].append(None)
                orders[oid] = [is_bid, p, sz, (day, idx)]
                lv.q.append(oid)
                lv.n += 1
                lv.total += sz
                activate(is_bid, p, lv)
            else:
                o = orders.pop(oid, None)
                if o is None:
                    # a removal for an order never seen open: resting since before the first
                    # replayed day, so it was missing from the queue until now
                    late_found += 1
                else:
                    lv = levels[(o[0], o[1])]
                    lv.n -= 1
                    lv.total -= o[2]
                    if lv.total < 1e-9:
                        lv.total = 0.0
                    # drop dead entries from the front to keep the deque short
                    while lv.q and lv.q[0] not in orders:
                        lv.q.popleft()
                    if len(lv.q) > 64 and len(lv.q) > 4 * lv.n:
                        lv.q = deque(x for x in lv.q if x in orders)
                    if not lv.q:
                        del levels[(o[0], o[1])]
                    if o[3] is None:
                        pass
                    elif o[3][0] == day:
                        idx = o[3][1]
                        R["t_end"][idx] = int(s_t[i]); R["blk_end"][idx] = int(s_blk[i])
                        R["end_status"][idx] = END_NAMES[s_end[i]]
                    else:
                        carried_out.append((oid, END_NAMES[s_end[i]], int(s_blk[i]), int(s_t[i])))
            i += 1

        tbl = pa.table({k: pa.array(v) for k, v in R.items()})
        tbl = tbl.append_column("day", pa.array([day] * tbl.num_rows))
        pq.write_table(tbl, os.path.join(OUT, f"{day}.parquet"), compression="zstd")
        if carried_out:
            co = carried_out
            pq.write_table(pa.table({
                "oid": [c[0] for c in co], "what": [c[1] for c in co],
                "a": [float(c[2]) for c in co], "b": [int(c[3]) for c in co]}),
                os.path.join(OUT, f"{day}_carried_events.parquet"), compression="zstd")
        fifo_rows.append({"day": day, "fills": n_fl, "fifo_head": fifo_ok, "fifo_not_head": fifo_bad,
                          "fill_unknown_order": fifo_unknown, "fill_fallback_key": int(sum(f_fallback)),
                          "late_found_removals": late_found, "live_orders_eod": len(orders),
                          "levels_eod": len(levels), "opens_improve": n_pos[0], "opens_join": n_pos[1], "opens_behind": n_pos[2], "opens_not_booked": not_booked, "opens_crossing_replayed_book": crossed,
                          "not_head_med_ahead_usd": float(np.median(bad_ahead)) if bad_ahead else 0.0,
                          "secs": round(time.time() - t0, 1)})
        print(fifo_rows[-1], flush=True)
    pq.write_table(pa.Table.from_pylist(fifo_rows), os.path.join(OUT, "fifo_check.parquet"))
    pq.write_table(pa.table({k: [d[n] for d in diag] for n, k in enumerate(
        ("day", "t_ms", "key", "filled_oid", "head_oid", "ahead_usd", "head_rec_idx", "fallback"))}),
        os.path.join(OUT, "fifo_not_head.parquet"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
