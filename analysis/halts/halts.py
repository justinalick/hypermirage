"""Chain halts and slow blocks, xyz:SP500 window days (scripts/window.py). Block numbers keep counting through a
pause while block times jump, so a halt shows as a long time between consecutive blocks. From the blocks that carry
xyz:SP500 order events: per day, the median ms per block, and every gap where the time per block between
consecutive event blocks exceeds 1 s (normal is about 70 ms). Quiet stretches with no SP500 events but normal block
times are not halts and are not reported. Writes data/derived/halts/halts.json."""
import json, os, sys
import duckdb
sys.path.insert(0, "scripts")
import window as WIN

O = "data/derived/halts"
os.makedirs(O, exist_ok=True)
con = duckdb.connect(); con.execute("SET memory_limit='1GB'; SET threads=2")
days, gaps = {}, []
for d in WIN.DAYS:
    g = con.sql(f"""
      WITH blk AS (SELECT DISTINCT block_number::BIGINT b, epoch_ms(block_time::TIMESTAMP) ms
                   FROM read_parquet('data/l4/order_statuses/xyz_SP500/{d}/[0-9]*.parquet')),
           x AS (SELECT b, ms, b - lag(b) OVER (ORDER BY b) db, ms - lag(ms) OVER (ORDER BY b) dms FROM blk)
      SELECT * FROM x WHERE db IS NOT NULL""").df()
    days[d] = {"blocks_with_events": int(len(g)), "ms_per_block": float(g.dms.sum() / g.db.sum()),
               "max_gap_s": float(g.dms.max() / 1000)}
    slow = g[(g.dms / g.db > 1000)]
    for r in slow.itertuples():
        gaps.append({"day": d, "block": int(r.b), "end_ms": int(r.ms), "blocks": int(r.db), "seconds": r.dms / 1000})
json.dump({"window": WIN.span(), "days": days, "slow_gaps": gaps}, open(f"{O}/halts.json", "w"), indent=1)
mpb = sorted(v["ms_per_block"] for v in days.values())
print(f"{len(days)} days; ms per block: min {mpb[0]:.1f}, median {mpb[len(mpb) // 2]:.1f}, max {mpb[-1]:.1f}")
print(f"gaps slower than 1 s per block: {len(gaps)}")
for x in sorted(gaps, key=lambda z: -z["seconds"])[:15]:
    print(x)
