import sys, os; sys.path.insert(0, "analysis/markout/rerun")
import duckdb as _d
_c = _d.connect
def _conn(*a, **k):
    c = _c(*a, **k); c.execute("SET memory_limit='3GB'; SET threads=2"); return c
_d.connect = _conn
try: _d.default_connection().execute("SET memory_limit='3GB'; SET threads=2")
except Exception: pass
"""Independent check of the xyz:SP500 fill markouts (Oct 8-21, 2026).

Rebuilds the block-timed mid from scratch, recomputes taker and maker markouts with DuckDB
as-of joins (the original uses numpy searchsorted), reads maker legs directly instead of
mirroring the taker, and compares every number with markout_res.json and hourly.json.

Checks
  1. bbo_t rebuild matches the file the charts used.
  2. Lookahead: each taker fill is tied to its own block via tx hash; the "fill" mid must come
     from a strictly earlier block.
  3. Sign: maker leg markout equals minus the taker leg on every trade.
  4. Markouts, 95% hour-block bootstrap CIs, size buckets, sample counts.
  5. Fees in bps of notional (taker / maker), with and without builder fees.
  6. Hourly means behind the violins.

Usage: .venv/bin/python analysis/markout/rerun/verify_markouts.py [--root .]
Memory: one day of order statuses at a time; DuckDB capped at 1.5 GB, 2 threads.
"""
import argparse, json, os
import duckdb
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=".")
ap.add_argument("--out", default=None, help="results json (default data/derived/markout/rerun/verify_res.json)")
a = ap.parse_args()
ROOT = a.root
MK = f"{ROOT}/data/derived/markout/rerun"
OUT = "data/checks/spotcheck/out_" + "markout_verify_res.json"
DAYS = [f"202610{d:02d}" for d in range(8, 22)]
H = [0, 0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300]

con = duckdb.connect()
con.execute("set memory_limit='1500MB'; set threads=2; set preserve_insertion_order=false")
rep = {}

# ---- taker and maker legs -------------------------------------------------------------------
fills = ",".join(f"'{ROOT}/data/raw/xyz/fills/{d[:4]}-{d[4:6]}-{d[6:]}.parquet'" for d in DAYS)
con.execute(f"""
create temp table legs as
select timestamp::timestamp ts, price::double px, size::double sz, price::double*size::double ntl,
       case when side='buy' then 1 else -1 end s, crossed, order_id, trade_id, tx_hash,
       fee::double fee, coalesce(builder_fee::double, 0) bfee
from read_parquet([{fills}])
where coin='xyz:SP500' and timestamp >= '2026-10-08' and timestamp < '2026-10-22'""")
c = con.execute("""select count(*) filter (where crossed), count(*) filter (where not crossed),
    count(distinct trade_id) filter (where crossed), count(distinct trade_id) filter (where not crossed)
    from legs""").fetchone()
rep["legs"] = dict(taker=c[0], maker=c[1], taker_trade_ids=c[2], maker_trade_ids=c[3])
con.execute("""
create temp table tk as
with o as (select order_id, sum(ntl) onot from legs where crossed group by 1)
select l.*, o.onot,
  case when o.onot < 1e4 then '< $10k' when o.onot < 1e5 then '$10k to $100k' else '>= $100k' end bucket
from legs l join o using(order_id) where l.crossed""")

# ---- 1+2. block times, bbo rebuild, fill-to-block lookahead check ---------------------------
con.execute("create temp table bbo (block bigint, t timestamp, best_bid double, best_ask double)")
con.execute("create temp table fillblk (trade_id ubigint, ts timestamp, fblock bigint, ftime timestamp)")
for d in DAYS:
    con.execute(f"""
    create or replace temp table blk as
    select block_number block, min(block_time::timestamp) t, any_value(hash) hash_any
    from read_parquet('{ROOT}/data/l4/order_statuses/xyz_SP500/{d}/*.parquet') group by 1""")
    con.execute(f"""insert into bbo select b.block, k.t, b.best_bid, b.best_ask
        from '{ROOT}/data/derived/bbo/xyz_SP500/{d}.parquet' b left join blk k using(block)""")
    # taker fill -> its block via tx hash (the taker order's status row carries the same hash)
    con.execute(f"""
    insert into fillblk
    with h as (select hash, min(block_number) fblock, min(block_time::timestamp) ftime
               from read_parquet('{ROOT}/data/l4/order_statuses/xyz_SP500/{d}/*.parquet')
               where hash is not null group by 1)
    select tk.trade_id, tk.ts, h.fblock, h.ftime from tk join h on tk.tx_hash = h.hash
    where tk.ts >= '{d[:4]}-{d[4:6]}-{d[6:]}'::timestamp and tk.ts < '{d[:4]}-{d[4:6]}-{d[6:]}'::timestamp + interval 1 day""")
    print("day", d, "done", flush=True)
con.execute("drop table if exists blk")

ref = f"{MK}/bbo_t.parquet"
r = con.execute(f"""select count(*), count(o.block), max(abs(epoch_us(o.t)-epoch_us(n.t))),
     sum((o.best_bid is distinct from n.best_bid or o.best_ask is distinct from n.best_ask)::int),
     (select count(*) from '{ref}'), sum((n.t is null)::int), sum((n.best_bid is null or n.best_ask is null)::int)
   from bbo n left join '{ref}' o using(block)""").fetchone()
rep["bbo_rebuild"] = dict(rows=r[0], matched_in_ref=r[1], max_time_diff_us=r[2], px_mismatch=r[3],
                          ref_rows=r[4], null_time=r[5], one_sided=r[6])

# lookahead: fill ms timestamp vs its block time, and the pre-fill as-of block vs the fill block
con.execute("create temp table bb as select * from bbo where t is not null and best_bid is not null and best_ask is not null")
r = con.execute("""
with f as (select * from fillblk),
pre as (select f.*, b.block pblock, b.t pt from f asof left join bb b on f.ts > b.t)
select count(*), (select count(*) from tk),
  sum((date_trunc('millisecond', ftime) = ts)::int) ts_is_trunc_of_block,
  sum((ts > ftime)::int) ts_after_block,
  sum((pblock >= fblock)::int) pre_mid_from_fill_block_or_later,
  median(epoch_us(ftime) - epoch_us(ts)) med_gap_us, max(epoch_us(ftime) - epoch_us(ts)) max_gap_us,
  min(epoch_us(ftime) - epoch_us(ts)) min_gap_us
from pre""").fetchone()
rep["lookahead"] = dict(fills_matched_to_block=r[0], taker_fills=r[1], ts_equals_block_ms=r[2],
                        ts_after_block_time=r[3], pre_mid_from_same_or_later_block=r[4],
                        median_gap_us=r[5], max_gap_us=r[6], min_gap_us=r[7])

# ---- 3+4. markouts via as-of joins -----------------------------------------------------------
tmax = con.execute("select max(t) from bb").fetchone()[0]
con.execute("create temp table mo (trade_id ubigint, h double, mid double)")
for h in H:
    us = int(h * 1e6)
    cond = "tk.ts > b.t" if h == 0 else "tk.ts + to_microseconds(%d) >= b.t" % us
    con.execute(f"""insert into mo select tk.trade_id, {h}, (b.best_bid+b.best_ask)/2
        from tk asof left join bb b on {cond}
        where tk.ts + to_microseconds({us}) <= '{tmax}'::timestamp""")
# taker markout per trade, maker markout from the maker legs themselves
con.execute("""
create temp table mk as
select tk.trade_id, tk.ts, tk.ntl, tk.bucket, mo.h,
       tk.s*(mo.mid - tk.px)/tk.px*1e4 taker_bps, m.s*(mo.mid - m.px)/m.px*1e4 maker_bps,
       m.ntl maker_ntl
from tk join mo using(trade_id) join (select * from legs where not crossed) m using(trade_id)""")
r = con.execute("""select count(*), max(abs(taker_bps + maker_bps)), max(abs(ntl - maker_ntl)),
    count(*) filter (where taker_bps is null) from mk""").fetchone()
rep["sign"] = dict(rows=r[0], max_abs_taker_plus_maker_bps=r[1], max_notional_diff=r[2], null_mid=r[3])

hours = con.execute("select distinct date_trunc('hour', ts) h from tk order by 1").fetchnumpy()["h"]
nh = len(hours)
rng = np.random.default_rng(2026)
draws = rng.integers(0, nh, (4000, nh))
def est(where):
    out = {}
    for h in H:
        q = con.execute(f"""select epoch(date_trunc('hour', ts)) hr, sum(ntl) w, sum(ntl*taker_bps) xw, sum(ntl*maker_bps) mw, count(*) n
            from mk where h={h} and taker_bps is not null and {where} group by 1""").fetchnumpy()
        idx = np.searchsorted(np.array([np.datetime64(x, 's').astype(np.int64) for x in hours]), q["hr"].astype(np.int64))
        sw = np.bincount(idx, q["w"], nh); sx = np.bincount(idx, q["xw"], nh); sm = np.bincount(idx, q["mw"], nh)
        bs = sx[draws].sum(1) / sw[draws].sum(1); bm = sm[draws].sum(1) / sw[draws].sum(1)
        out[str(h)] = dict(taker=[sx.sum()/sw.sum(), *np.percentile(bs, [2.5, 97.5])],
                           maker=[sm.sum()/sw.sum(), *np.percentile(bm, [2.5, 97.5])], n=int(q["n"].sum()))
    return out
res = {"all": est("true")}
for b in ["< $10k", "$10k to $100k", ">= $100k"]:
    res[b] = est(f"bucket = '{b}'")
rep["markouts"] = res
r = con.execute("""select count(*), sum(ntl), count(distinct date_trunc('hour', ts)),
    count(distinct order_id) filter (where bucket='< $10k'), count(distinct order_id) filter (where bucket='$10k to $100k'),
    count(distinct order_id) filter (where bucket='>= $100k'), count(*) filter (where bucket='< $10k'),
    count(*) filter (where bucket='$10k to $100k'), count(*) filter (where bucket='>= $100k') from tk""").fetchone()
rep["counts"] = dict(trades=r[0], notional=r[1], hours=r[2], orders={"< $10k": r[3], "$10k to $100k": r[4], ">= $100k": r[5]},
                     trades_by_bucket={"< $10k": r[6], "$10k to $100k": r[7], ">= $100k": r[8]})

# touch check: taker price at or through the pre-trade touch
r = con.execute("""with p as (select tk.*, b.best_bid, b.best_ask, b.t bt from tk asof left join bb b on tk.ts > b.t)
  select avg(case when s=1 then (px >= best_ask)::int else (px <= best_bid)::int end),
         avg(case when s=1 then (px >= best_ask)::int else (px <= best_bid)::int end) filter (where hour(ts) = 0),
         sum(ntl*(best_ask-best_bid)/2/((best_ask+best_bid)/2)*1e4)/sum(ntl),
         median(epoch(ts) - epoch(bt)) from p""").fetchone()
rep["touch"] = dict(share_at_or_through=r[0], share_hour00=r[1], quoted_half_spread_bps_ntl_wtd=r[2], median_quote_age_s=r[3])

# ---- 5. fees -----------------------------------------------------------------------------------
r = con.execute("""select sum(fee) filter (where crossed)/sum(ntl) filter (where crossed)*1e4,
    sum(fee-bfee) filter (where crossed)/sum(ntl) filter (where crossed)*1e4,
    sum(fee) filter (where not crossed)/sum(ntl) filter (where not crossed)*1e4,
    sum(fee-bfee) filter (where not crossed)/sum(ntl) filter (where not crossed)*1e4,
    sum(bfee)/sum(fee), count(*) filter (where not crossed and fee < 0) from legs""").fetchone()
rep["fees_bps"] = dict(taker=r[0], taker_ex_builder=r[1], maker=r[2], maker_ex_builder=r[3],
                       builder_share_of_fees=r[4], maker_legs_with_rebate=r[5])
r = con.execute("""select bucket, sum(fee)/sum(ntl)*1e4 from tk group by 1 order by 1""").fetchall()
rep["fees_bps"]["taker_by_bucket"] = dict(r)

# ---- 6. hourly means behind the violins (UTC hours with 5+ trades) ----------------------------
hv = {}
for key, b in [("lt10k", "< $10k"), ("10k_100k", "$10k to $100k"), ("ge100k", ">= $100k")]:
    for h in [1, 10, 60]:
        q = con.execute(f"""select sum(ntl*taker_bps)/sum(ntl) m from mk where h={h} and bucket='{b}' and taker_bps is not null
            group by date_trunc('hour', ts) having count(*) >= 5""").fetchnumpy()["m"]
        hv[f"{key}_{h}"] = np.sort(q).tolist()
rep["hourly_n"] = {k: len(v) for k, v in hv.items()}

# ---- compare with the original outputs -----------------------------------------------------------
orig = json.load(open(f"{MK}/markout_res.json"))
diffs = []
for k in ["all", "< $10k", "$10k to $100k", ">= $100k"]:
    for h in H:
        o = orig[k][str(h)]; n = res[k][str(h)]["taker"]
        diffs.append((k, h, o[0], n[0], o[0]-n[0], o[1], n[1], o[2], n[2]))
rep["max_mean_diff_bps"] = max(abs(d[4]) for d in diffs)
od = json.load(open(f"{MK}/hourly.json"))
rep["hourly_max_diff_bps"] = {k: (float(np.max(np.abs(np.sort(od[k]) - np.array(v)))) if len(od[k]) == len(v) else f"n {len(od[k])} vs {len(v)}")
                              for k, v in hv.items()}
json.dump(rep, open(OUT, "w"), indent=1, default=float)

print(json.dumps({k: v for k, v in rep.items() if k != "markouts"}, indent=1, default=float))
print("\nbucket   h    orig_mean  new_mean   diff    orig_CI            new_CI")
for d in diffs:
    if d[1] in (0, 1, 10, 60):
        print(f"{d[0]:<14}{d[1]:>4}  {d[2]:+.3f}    {d[3]:+.3f}   {d[4]:+.4f}  [{d[5]:+.2f},{d[7]:+.2f}]   [{d[6]:+.2f},{d[8]:+.2f}]")
print("\nmaker (read from maker legs), all trades:", {h: [round(x, 3) for x in res['all'][str(h)]['maker']] for h in ['0', '1', '10', '60']})
print("wrote", OUT)
