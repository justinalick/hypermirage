-- Step 1. Run from the repository root: duckdb < analysis/taker_clusters/takers.sql
-- Taker notional per address, xyz:SP500, 2026-10-08..21 UTC.
copy (select address, sum(price::double*size::double) tak, count(*) n
      from read_parquet('data/raw/xyz/fills/*.parquet')
      where coin='xyz:SP500' and crossed and timestamp >= strptime(getenv('HM_START'), '%Y%m%d') and timestamp < strptime(getenv('HM_END'), '%Y%m%d') + INTERVAL 1 DAY
      group by 1 order by 2 desc)
to 'data/derived/taker_clusters/takers.csv';
