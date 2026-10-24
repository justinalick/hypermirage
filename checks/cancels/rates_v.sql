-- Heatmap, totals and same-block cancel shares from my own order tables (work/orders_*.parquet)
SET memory_limit='2GB'; SET threads=2;
CREATE TEMP TABLE x AS SELECT cls, ntl, fusd, brest*mpb life_ms, brest,
  CASE WHEN cls='pre' THEN '0' WHEN dist IS NULL THEN 'u' WHEN dist<0 THEN '1 improves' WHEN dist=0 THEN '2 at'
       WHEN dist<=1 THEN '3 lt1bp' WHEN dist<=5 THEN '4 1-5' WHEN dist<=25 THEN '5 5-25' ELSE '6 gt25' END db
FROM (SELECT * REPLACE (round(dist,9) AS dist) FROM 'data/checks/cancels/work/orders_*.parquet');
CREATE TEMP TABLE rest AS SELECT * FROM x WHERE cls IN ('pulled','partial','filled') AND brest>0 AND db NOT IN ('0','u');
.mode markdown
SELECT count(*) n, sum(ntl)/1e12 usd_T, sum(least(coalesce(fusd,0),ntl))/sum(ntl)*100 fill_pct FROM rest;
SELECT db, CASE WHEN life_ms<100 THEN 'a <100ms' WHEN life_ms<250 THEN 'b 100-250' WHEN life_ms<1000 THEN 'c 250-1s'
  WHEN life_ms<5000 THEN 'd 1-5s' WHEN life_ms<30000 THEN 'e 5-30s' WHEN life_ms<300000 THEN 'f 30s-5m' ELSE 'g >5m' END lb,
  count(*) n, round(sum(ntl)/1e9,2) placed_busd, round(100*sum(least(coalesce(fusd,0),ntl))/sum(ntl),4) fill_pct
FROM rest GROUP BY ALL ORDER BY 1,2;
SELECT db, round(100*count(*) FILTER (WHERE cls='samebk')/count(*),2) samebk_pct
FROM x WHERE cls IN ('samebk','pulled','partial','filled') GROUP BY 1 ORDER BY 1;
