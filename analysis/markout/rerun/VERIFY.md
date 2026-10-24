# Markout check, xyz:SP500, Oct 8 to 21, 2026

Independent recompute (verify_markouts.py: DuckDB as-of joins, maker legs read directly, own
bootstrap seed) against the published charts' numbers (markout_res.json, hourly.json).

## Verdict
The numbers are right. Every mean (4 groups x 11 horizons) matches to within 0.00004 bps, and the CIs
match to within 0.01 bps. The violin hourly means match exactly.

| Check | Result |
|---|---|
| Sample | 612,067 trades, one maker and one taker leg each, $3.10B, 336 hours. Orders by bucket 329,495 / 51,334 / 4,404 |
| Lookahead | 474,803 taker fills tied to their own block by tx hash. In every case the fill time is the block time truncated to the millisecond, no fill is later than its block, and the "fill" mid always comes from an earlier block |
| Sign | taker = side x (mid - fill px). Maker legs computed on their own come out at exactly minus the taker on every trade (max difference 0.0) |
| Touch | 98.6% of taker fills at or through the pre-trade touch (98.9% in the 00 UTC hour, so the daily replay restart is not a problem) |
| Fee 0.78 bps | Correct, but it includes builder fees (29% of all fees). Exchange fee alone: 0.58 bps taker, 0.04 bps maker |

## Discrepancies and fixes
1. Fee footnote: say "0.78 bps including builder fees". By bucket, orders under $10k pay 1.13 bps, so
   their +0.16 bps at 1 min is about 1 bp net negative.
2. Method-note caveat is wrong: the mid is as-of every top-of-book change, so a 2.2 s median quote age
   does not make the 0.5s and 1s points coarse. The real limit is replay accuracy (98.6% touch match).
3. Violin wording: "steadily positive hour to hour" overstates it. Under $10k is positive in 55% of
   hours at 1s and 67% at 10s and 1m. The method note says 16 hour values were clipped at +-2 bps. The
   final chart clips at +-1.6 bps, which hides 30 values; the arrows on the chart show the right counts.
4. Reproducibility: the step that adds block times to the mid was never saved, and the scripts read from a
   temporary folder. It is now saved as prep_bbo_t.sql, with paths fixed in this folder.
5. Negligible: 14 one-sided book rows give a NaN mid that the original counts as a 0 markout.

## Rerun
    bash analysis/markout/rerun/run.sh
Takes about 5 minutes and stays under 1.5 GB RAM.
