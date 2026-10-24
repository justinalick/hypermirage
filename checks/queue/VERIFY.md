# Verify: queue (queue.png and caption)

Inputs: replay per-day outputs `data/derived/queue/2026????.parquet` + `*_carried_events.parquet` (not queue.duckdb),
Reservoir fills `data/raw/xyz/fills/`, node order statuses `data/l4/order_statuses/xyz_SP500/`.
Own SQL (recompute.py) rebuilds the sample and buckets; fill flag computed two ways: (rep) replay fill sizes incl.
carried events, (res) directly from Reservoir maker fills joined by order id (independent of the replay's fill
application). Own product-limit Kaplan-Meier in numpy. Own FIFO replay (fifo_replay.py) for the head-hit check.

| Number | Original | Recomputed | Match | Method |
|---|---|---|---|---|
| Orders at/inside touch | 2.75M (2,748,163) | 2,748,163 | yes | pos 0/1, Oct 9-21, rested past own block |
| Accounts | 1,264 | 1,264 | yes | oid -> user from raw `open` statuses |
| n improves / <=$5k / $5-25k / $25-100k / $100-250k / >$250k | 490k / 455k / 621k / 733k / 323k / 125k | 489,831 / 455,375 / 621,246 / 733,242 / 323,242 / 125,227 | yes | bucket on ahead_sz x px |
| Fill share, all sizes (%) | 14.5 / 12.7 / 7.1 / 5.6 / 4.5 / 3.2 | rep 14.47 / 12.72 / 7.06 / 5.56 / 4.51 / 3.23; res 14.54 / 12.73 / 7.06 / 5.56 / 4.51 / 3.23 | yes | any fill >1e-12 |
| Fill share, own $5-15k (%) | 8.8 / 10.8 / 4.2 / 2.7 / 2.3 / 1.3 | rep 8.83 / 10.85 / 4.18 / 2.66 / 2.30 / 1.30; res 8.88 / 10.86 / 4.19 / 2.67 / 2.30 / 1.30 | yes | sz0 x px in [5k, 15k] |
| KM fill prob. at 5s (%) | 35.7 / 21.7 / 14.3 / 11.2 / 7.4 / 5.2 (km.json, plotted) | 35.69 / 21.74 / 14.34 / 11.18 / 7.38 / 5.16 | yes | own KM; event = first fill, censor = removal |
| KM at 1s (note) | 10.9 / 6.3 / 3.7 / 2.5 / 1.5 / 0.8 | 10.91 / 6.27 / 3.72 / 2.49 / 1.45 / 0.80 | yes | same |
| FIFO head hits, replay counter Oct 9-21 | 95.8% | 547,268 / 571,261 = 95.80% | yes (arithmetic) | sum of fifo_check counters |
| FIFO head hits, own replay | 95.8% (pooled) | 4 days within 0.12 pp per day (below) | yes | independent replay |

Replay-flag vs Reservoir-flag agree on 99.98% of orders.

## FIFO head-hit check (own replay, four days)

Own code: per-level dict oid -> remaining size, priority = lowest live oid; fills mapped to blocks by Reservoir ms
timestamp, applied just before the taker's first status row in that block, else at block start; fills whose ms
matches no block with SP500 status rows (about 2-3k a day) are applied just before the next block (the original
puts them at the start of the previous block). A fill is "head" if no live size with a lower oid is left at its
level after the whole sweep. Warm-up: Oct 8 for Oct 9-10; Oct 11-12 for Oct 13-14 (original: one continuous
replay from Oct 8).

| Day | Original head share | Own replay | Diff |
|---|---|---|---|
| Oct 9 | 94.32% (29,597 / 31,379) | 94.29% (29,215 / 30,983) | -0.03 pp |
| Oct 10 | 99.62% (21,278 / 21,359) | 99.74% (21,227 / 21,283) | +0.12 pp |
| Oct 13 | 94.50% (35,128 / 37,171) | 94.50% (34,704 / 36,722) | 0.00 pp |
| Oct 14 | 94.27% (55,259 / 58,616) | 94.20% (54,313 / 57,657) | -0.07 pp |
| 4 days pooled | 95.11% | 95.10% | -0.01 pp |

The 95.8% headline is the Oct 9-21 pooled share; the four replayed days match the original within 0.12 pp per day,
so 95.8% stands. (A first attempt of mine that dropped the between-block fills gave 93.5%; that was my placement
bug, not the original's.) The own replay also reproduces the original entry position (improve/join) and
queue-ahead bucket for 100% of the 836,225 touch orders on these four days.

No discrepancies found for queue.

## Rerun
`flock data/tmp/heavy.lock .venv/bin/python -P checks/queue/recompute.py`
(after `extract.py`; FIFO: `fifo_replay.py 20261008 -- 20261009 20261010` and `fifo_replay.py 20261011 20261012 -- 20261013 20261014`, each under the same flock).
