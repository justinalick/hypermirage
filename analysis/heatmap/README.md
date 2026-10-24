# Depth heatmap: xyz:SP500, hour x weekday, 2026-10-08..21

Aggregates only, no accounts.

## Files
- `depth_check.py`: rebuilds resting depth from the order-lifecycle replay at the last block of
  every minute (5/10/25 bps of mid), both at original order size and net of partial fills (Reservoir
  maker fills matched on order_id). Also validates the replay against every Reservoir 1m L2 snapshot
  (top 20 levels per side, same price band). Writes `depth_minutes_v2.parquet` and `l2_check.parquet`.
- `heatmap_depth.py`: draws the chart from `depth_minutes_v2.parquet` (column `d10_net`) and prints
  the session medians quoted in the subtitle.
- `sp500_depth_heatmap_v2.png`: the chart to use. `sp500_depth_heatmap.png` / `heatmap_depth_v1.py`:
  first version (original order size, read from data/derived/offhours/offhours_depth_minutes.parquet).

## Rerun (from .)
    .venv/bin/python analysis/heatmap/depth_check.py data/derived/heatmap      # ~35 min, 14 days
    .venv/bin/python analysis/heatmap/heatmap_depth.py data/derived/heatmap/sp500_depth_heatmap_v2.png

Inputs: data/l4/order_statuses (block clock), data/derived/lifecycle_touch, data/derived/bbo,
data/raw/xyz/fills, data/raw/xyz/book_1m/SP500.

## Checks done (2026-10-23)
- Coverage: 14 full days, 24 contiguous hour files each, 1,440 minutes per day; 120 minutes per cell.
- The v2 script reproduces the first chart's per-minute depth exactly (max diff < $0.0001).
- Grid recomputed independently in pandas: same cell values, weekday-to-date mapping correct.
- Replay vs exchange L2 (40,320 side-snapshots): net-of-fills depth is within 2% of L2 on 98.7%
  (median ratio 1.000); original-size depth on 85.8% (weekend median ratio up to 1.016).
- Effect of the fix at 10 bps: cash 15.58 -> 15.44 $M, other futures-open 13.28 -> 13.24,
  break 4.86 -> 4.65, weekend 3.47 -> 3.37. Ratios: break 0.34x, weekend 0.24x of futures-open
  hours; cash 1.17x other futures-open hours.

## Limits
- L2 validates only the top 20 levels (about 3 bps from mid); 10 bps depth beyond that relies on
  the replay. Orders resting since before a day with no event that day are missed (mostly far).
- Reduce-only orders: remaining size can shrink with the position, not a fill; small.
- Two weeks of one market; each weekday cell is two days.
