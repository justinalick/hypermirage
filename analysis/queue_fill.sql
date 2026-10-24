-- Fill probability vs queue position at the touch, from data/derived/queue/*.parquet (queue_replay.py).
-- Run from the repo root: duckdb data/derived/queue/queue.duckdb < analysis/queue_fill.sql
SET memory_limit = '1500MB';
SET threads = 4;

CREATE OR REPLACE TABLE q AS
SELECT * FROM read_parquet('data/derived/queue/2026????.parquet') WHERE day >= '20261009';

-- outcomes of orders that carried past their open day
CREATE OR REPLACE TABLE co AS
SELECT oid,
       sum(a) FILTER (WHERE what = 'fill')               AS c_fill_sz,
       min(b) FILTER (WHERE what = 'fill')               AS c_first_fill,
       min(b) FILTER (WHERE what <> 'fill')              AS c_t_end,
       arg_min(what, b) FILTER (WHERE what <> 'fill')    AS c_end_status
FROM read_parquet('data/derived/queue/*_carried_events.parquet')
GROUP BY oid;

CREATE OR REPLACE TABLE s AS
SELECT q.oid, q.day, q.is_bid, q.px, q.sz0, q.pos, q.ahead_n,
       q.sz0 * q.px                                            AS own_usd,
       coalesce(q.ahead_sz, 0) * q.px                          AS ahead_usd,
       (q.best_opp - q.best_same) * CASE WHEN q.is_bid THEN 1 ELSE -1 END AS spread_px,
       q.t_open,
       q.fill_sz + coalesce(co.c_fill_sz, 0)                   AS fill_sz,
       CASE WHEN q.t_first_fill >= 0 THEN q.t_first_fill ELSE co.c_first_fill END AS t_first_fill,
       CASE WHEN q.t_end >= 0 THEN q.t_end ELSE co.c_t_end END AS t_end,
       coalesce(q.end_status, co.c_end_status)                 AS end_status,
       q.blk_open, q.blk_end
FROM q LEFT JOIN co USING (oid)
WHERE q.pos IN (0, 1);

-- rested: survived past its own block (never-displayed orders are excluded)
CREATE OR REPLACE TABLE r AS
SELECT *,
       fill_sz > 1e-12                                          AS any_fill,
       end_status = 'filled'                                    AS full_fill,
       (t_first_fill - t_open) / 1000.0                         AS secs_to_fill,
       (t_end - t_open) / 1000.0                                AS secs_alive,
       CASE WHEN pos = 0 THEN '0 improves (alone)'
            WHEN ahead_usd <= 5e3   THEN '1 join, <=$5k ahead'
            WHEN ahead_usd <= 25e3  THEN '2 join, $5-25k'
            WHEN ahead_usd <= 100e3 THEN '3 join, $25-100k'
            WHEN ahead_usd <= 250e3 THEN '4 join, $100-250k'
            ELSE                         '5 join, >$250k' END AS qb
FROM s
WHERE blk_end IS DISTINCT FROM blk_open;
