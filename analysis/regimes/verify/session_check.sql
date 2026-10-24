-- Independent recompute (SQL, session definition copied from offhours/offhours_depth.py) of the session mix,
-- per-state medians and the clock baseline, from the per-minute state files written by analyze.py.
SET TimeZone='UTC';
CREATE MACRO sess(t) AS CASE
    WHEN (dayofweek(t) = 5 AND hour(t) >= 21) OR dayofweek(t) = 6 OR (dayofweek(t) = 0 AND hour(t) < 22) THEN 'weekend'
    WHEN dayofweek(t) BETWEEN 1 AND 5 AND (hour(t) * 60 + minute(t)) BETWEEN 810 AND 1199 THEN 'cash'
    WHEN dayofweek(t) BETWEEN 1 AND 4 AND hour(t) = 21 THEN 'break'
    ELSE 'overnight' END;
CREATE TABLE s AS SELECT 2 k, t, state, d10, spread_bps, abs_imb, rv5, session py_session FROM 'data/derived/regimes/states_K2.parquet'
  UNION ALL SELECT 3, t, state, d10, spread_bps, abs_imb, rv5, session FROM 'data/derived/regimes/states_K3.parquet';
.print '-- session labels: python vs SQL (should be a 1:1 mapping)'
SELECT py_session, sess(t) sql_session, count(*) FROM s WHERE k = 2 GROUP BY ALL ORDER BY 1;
.print '-- share of minutes in each state by session'
SELECT k, sess_name, state, n_min, round(n_min / sum(n_min) OVER (PARTITION BY k, sess_name), 3) share
FROM (SELECT k, sess(t) AS sess_name, state, count(*) AS n_min FROM s GROUP BY ALL) ORDER BY k, sess_name, state;
.print '-- per-state medians'
SELECT k, state, count(*) AS n_min, round(median(d10) / 1e6, 3) depth10_musd, round(median(spread_bps), 3) spread_bps,
       round(median(abs_imb), 3) abs_imb, round(100 * median(rv5), 2) rv5_pct FROM s GROUP BY ALL ORDER BY k, state;
.print '-- clock baseline, leave-one-day-out: majority state per (session, UTC hour) from the other 13 days'
WITH c AS (SELECT k, t::DATE AS d, sess(t) || hour(t) clk, state FROM s),
     pred AS (SELECT a.k, a.d, a.clk, a.state,
                (SELECT mode(b.state) FROM c b WHERE b.k = a.k AND b.clk = a.clk AND b.d <> a.d) p
              FROM (SELECT k, d, clk, state, count(*) n FROM c GROUP BY ALL) a)
SELECT k, round(sum(n_ok) / sum(n), 4) lodo_accuracy FROM (
  SELECT p.k, sum(c2.n) n, sum(c2.n) FILTER (WHERE p.state = p.p) n_ok
  FROM pred p JOIN (SELECT k, d, clk, state, count(*) n FROM c GROUP BY ALL) c2
    ON c2.k = p.k AND c2.d = p.d AND c2.clk = p.clk AND c2.state = p.state GROUP BY p.k) GROUP BY k ORDER BY k;
.print '-- K=2 state switches (time, new state)'
SELECT t, state, sess(t) FROM (SELECT t, state, lag(state) OVER (ORDER BY t) ps FROM s WHERE k = 2) WHERE state <> ps ORDER BY t;
