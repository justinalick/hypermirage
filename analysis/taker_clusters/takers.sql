-- Step 1. Run from the repository root: duckdb < analysis/taker_clusters/takers.sql
-- Taker notional per address, xyz:SP500, 2026-10-08..21 UTC.
copy (select address, sum(price::double*size::double) tak, count(*) n
      from read_parquet('data/raw/xyz/fills/2026-10-*.parquet')
      where coin='xyz:SP500' and crossed and timestamp>='2026-10-08' and timestamp<'2026-10-22'
      group by 1 order by 2 desc)
to 'data/derived/taker_clusters/takers.csv';
