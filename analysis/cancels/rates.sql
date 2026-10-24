-- Fill vs cancel by distance at placement x resting lifetime, xyz:SP500 2026-10-08..21.
-- Rested orders only (classes displayed_pulled, displayed_partial, filled with >= 1 displayed block).
SET threads=6; SET memory_limit='8GB';
COPY (
WITH o AS (
  SELECT class, dist_bucket, notional_usd, coalesce(filled_usd,0) filled_usd,
         blocks_rested * ms_per_block AS life_ms
  FROM 'data/derived/lifecycle_touch/xyz_SP500/2026*.parquet'
  WHERE class IN ('displayed_pulled','displayed_partial','filled') AND displayed_blocks > 0
    AND dist_bucket NOT IN ('unknown','0 placed before window'))
SELECT dist_bucket,
  CASE WHEN life_ms < 100 THEN '1 block (<100 ms)' WHEN life_ms < 250 THEN '2 100-250 ms'
       WHEN life_ms < 1000 THEN '3 250 ms-1 s' WHEN life_ms < 5000 THEN '4 1-5 s'
       WHEN life_ms < 30000 THEN '5 5-30 s' WHEN life_ms < 300000 THEN '6 30 s-5 min' ELSE '7 over 5 min' END life_bucket,
  count(*) n, sum(notional_usd) placed_usd, sum(least(filled_usd, notional_usd)) filled_usd,
  count(*) FILTER (WHERE class='displayed_pulled') n_pulled_nofill
FROM o GROUP BY ALL ORDER BY 1,2) TO 'data/derived/cancels/rates.parquet';
COPY (SELECT dist_bucket, class, count(*) n, sum(notional_usd) usd
  FROM 'data/derived/lifecycle_touch/xyz_SP500/2026*.parquet' GROUP BY ALL) TO 'data/derived/cancels/class_by_dist.parquet';
SELECT * FROM 'data/derived/cancels/rates.parquet';
