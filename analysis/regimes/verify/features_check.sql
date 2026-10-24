-- Independent recompute of per-minute spread, |imbalance|, RV from ofi/l1, compared to features.parquet
SET TimeZone='UTC'; SET threads=3; SET memory_limit='3GB'; SET preserve_insertion_order=false;
CREATE VIEW l1 AS SELECT * FROM read_parquet('data/derived/ofi/l1/*.parquet');
CREATE TABLE st AS
SELECT t_ns // 60000000000 AS mn,
       (ask_px - bid_px) / ((ask_px + bid_px) / 2) * 1e4 AS spr,
       abs(bid_sz - ask_sz) / (bid_sz + ask_sz) AS aimb,
       least(coalesce(lead(t_ns) OVER w, t_ns), (t_ns // 60000000000 + 1) * 60000000000) - t_ns AS dur
FROM l1 WINDOW w AS (ORDER BY t_ns, block);
CREATE TABLE tw AS SELECT mn, sum(spr * dur) / sum(dur) spr, sum(aimb * dur) / sum(dur) aimb FROM st WHERE dur > 0 GROUP BY mn;
-- 5s buckets: mid at edge (b+1)*5s = last state in bucket b, forward-filled over empty buckets
CREATE TABLE lastmid AS SELECT t_ns // 5000000000 b, arg_max((ask_px + bid_px) / 2, block) mid FROM l1 GROUP BY 1;
CREATE TABLE g AS
SELECT r.range AS b, last_value(l.mid IGNORE NULLS) OVER (ORDER BY r.range ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) mid
FROM range((SELECT min(b) FROM lastmid), (SELECT max(b) FROM lastmid)) r LEFT JOIN lastmid l ON l.b = r.range;
CREATE TABLE rv AS
SELECT ((b + 1) * 5 - 1) // 60 AS mn_s, sqrt(sum(ret * ret)) * sqrt(365 * 1440) rv
FROM (SELECT b, ln(mid / lag(mid) OVER (ORDER BY b)) ret FROM g) WHERE ret IS NOT NULL GROUP BY 1;
CREATE TABLE f AS SELECT epoch_ms(t) // 60000 mn, * FROM 'data/derived/regimes/features.parquet';
CREATE TABLE cmp AS SELECT f.t, f.spread_bps, tw.spr, f.abs_imb, tw.aimb, f.rv_ann, rv.rv
FROM f LEFT JOIN tw ON tw.mn = f.mn LEFT JOIN rv ON rv.mn_s = f.mn;
SELECT count(*) n,
  count(*) FILTER (WHERE isnan(spread_bps) OR spread_bps IS NULL) feat_spread_missing,
  count(*) FILTER (WHERE spr IS NULL OR isnan(spr)) sql_spread_missing,
  max(abs(spread_bps - spr)) FILTER (WHERE NOT isnan(spread_bps) AND NOT isnan(spr)) max_diff_spread,
  max(abs(abs_imb - aimb)) FILTER (WHERE NOT isnan(abs_imb) AND NOT isnan(aimb)) max_diff_imb,
  max(abs(rv_ann - rv)) FILTER (WHERE NOT isnan(rv_ann) AND NOT isnan(rv)) max_diff_rv,
  count(*) FILTER (WHERE abs(rv_ann - rv) > 1e-9) n_rv_mismatch
FROM cmp;
SELECT * FROM cmp WHERE isnan(spread_bps) OR isnan(spr) OR isnan(rv) OR isnan(rv_ann) OR abs(rv_ann - rv) > 1e-9 OR abs(abs_imb - aimb) > 1e-9 ORDER BY t LIMIT 40;
