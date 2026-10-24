-- Step 1: attach block times to the replayed best bid/ask (output of scripts/touch.py).
-- Mid at t = last top-of-book change at or before t. Block time comes from node order statuses.
-- Run from the repository root:  duckdb -c ".read analysis/markout/rerun/prep_bbo_t.sql"
set memory_limit='1500MB'; set threads=2;
copy (
 with bt as (select block_number block, min(block_time::timestamp) t
             from read_parquet('data/l4/order_statuses/xyz_SP500/*/*.parquet', filename=true)
             where filename not like '%20261022%' group by 1)
 select b.block, bt.t, b.best_bid, b.best_ask
 from 'data/derived/bbo/xyz_SP500/*.parquet' b left join bt using(block) order by block
) to 'data/derived/markout/bbo_t.parquet';
select count(*), count(t), min(t), max(t) from 'data/derived/markout/bbo_t.parquet';
