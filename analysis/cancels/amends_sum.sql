SET threads=6; SET memory_limit='10GB';
CREATE TEMP TABLE a AS
SELECT a.*, l.dist_bucket, l.class, l.blocks_rested*l.ms_per_block life_ms, l.notional_usd,
  CASE WHEN new_oid IS NULL THEN 'pure cancel'
       WHEN new_px=old_px AND abs(new_sz-old_sz)<1e-9 THEN 'refresh (same px, same size)'
       WHEN new_px=old_px THEN 'size only'
       WHEN abs(new_sz-old_sz)<1e-9 THEN 'price only'
       ELSE 'price and size' END kind,
  CASE WHEN new_oid IS NULL OR new_px=old_px THEN NULL
       WHEN (a.side='B') = (new_px>old_px) THEN 'toward touch' ELSE 'away from touch' END dir,
  round(abs(new_px-old_px)/0.1) ticks
FROM 'data/derived/cancels/amends_2026*.parquet' a
LEFT JOIN 'data/derived/lifecycle_touch/xyz_SP500/2026*.parquet' l ON l.oid=a.old_oid;
COPY (SELECT kind, dir, dist_bucket, count(*) n, sum(notional_usd) usd FROM a GROUP BY ALL) TO 'data/derived/cancels/amend_kinds.parquet';
COPY (SELECT kind, dir, least(ticks,20) ticks, count(*) n FROM a WHERE ticks IS NOT NULL GROUP BY ALL) TO 'data/derived/cancels/amend_ticks.parquet';
SELECT kind, count(*) n, round(100*count(*)/sum(count(*)) over (),1) pct, round(100*avg((class IS NULL)::int),2) no_lc FROM a GROUP BY 1 ORDER BY 2 DESC;
SELECT dir, count(*), median(ticks) FROM a WHERE dir IS NOT NULL GROUP BY 1;
-- same block size changes: grow or shrink
SELECT kind, round(100*avg((new_sz>old_sz)::int),1) pct_up FROM a WHERE kind IN ('size only','price and size') GROUP BY 1;
