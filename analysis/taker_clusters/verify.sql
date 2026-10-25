-- Run from the repository root: duckdb < analysis/taker_clusters/verify.sql
set variable t1 = (select list(address) from read_csv('data/derived/taker_clusters/cluster_map.csv') where cluster = (select "T1" from read_json('data/derived/taker_clusters/labels_local.json')));
-- Independent recompute with DuckDB ASOF joins (not the numpy searchsorted path in mk.py)
create temp table b as select t, (best_bid+best_ask)/2 mid, best_bid, best_ask from 'data/derived/markout/bbo_t.parquet' where t is not null;
select 'bbo sanity' k, count(*) n, sum(case when best_bid>=best_ask then 1 else 0 end) crossed_or_locked, sum(case when best_bid is null or best_ask is null then 1 else 0 end) nulls from b;
create temp table f as
 select timestamp::timestamp ts, price::double px, price::double*size::double nt, case when side='buy' then 1 else -1 end s,
   list_contains(getvariable('t1'), address) t1, fee::double fee, trade_id
 from read_parquet('data/raw/xyz/fills/*.parquet')
 where coin='xyz:SP500' and crossed and timestamp >= strptime(getenv('HM_START'), '%Y%m%d') and timestamp < strptime(getenv('HM_END'), '%Y%m%d') + INTERVAL 1 DAY;
create temp table m as
 select f.*, b0.mid m0, b1.mid m1, b10.mid m10, b60.mid m60 from f
 asof left join b b0 on f.ts > b0.t
 asof left join b b1 on f.ts + interval 1 second >= b1.t
 asof left join b b10 on f.ts + interval 10 second >= b10.t
 asof left join b b60 on f.ts + interval 60 second >= b60.t;
select case when t1 then 'T1' else 'others' end g, count(*) n, round(sum(nt)/1e6) usd_m,
  round(sum(nt*s*(m0-px)/px)/sum(nt)*1e4,3) fill_bps, round(sum(nt*s*(m1-px)/px)/sum(nt)*1e4,3) s1,
  round(sum(nt*s*(m10-px)/px)/sum(nt)*1e4,3) s10,
  round(sum(case when ts + interval 60 second <= (select max(t) from b) then nt*s*(m60-px)/px end)/sum(case when ts + interval 60 second <= (select max(t) from b) then nt end)*1e4,3) s60,
  round(sum(fee)/sum(nt)*1e4,3) fee_bps
from m group by 1 order by 1;
-- ES sessions from raw timestamps (EDT: CME Globex Sun 22:00 UTC - Fri 21:00 UTC, break 21-22 UTC; cash 13:30-20:00 UTC)
with x as (select *, dayofweek(ts) dw, hour(ts)*60+minute(ts) md from f),
y as (select *, case
  when dw=6 or (dw=0 and md<1320) or (dw=5 and md>=1260) or (dw between 1 and 4 and md>=1260 and md<1320) then 'ES closed'
  when dw between 1 and 5 and md>=810 and md<1200 then 'Cash hours' else 'ES overnight' end sess from x)
select sess, round(sum(case when t1 then nt end)/sum(nt),4) t1_share, round(sum(case when t1 then nt end)/(select sum(nt) from f where t1),4) frac_of_t1,
  round(sum(nt)/(select sum(nt) from f),4) frac_of_all from y group by 1 order by 1;
select hour(ts) h, round(sum(case when t1 then nt end)/sum(nt),3) t1_share from f where dayofweek(ts) between 1 and 5 and hour(ts) in (13,20,21,22) group by 1 order by 1;
