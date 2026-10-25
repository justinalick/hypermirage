"""Independent recompute of queue.png numbers from replay per-day outputs + Reservoir fills (own SQL, own KM)."""
import duckdb, json, sys, numpy as np
sys.path.insert(0, "scripts")
import window as WIN
D = "data/derived/queue"; W = "data/checks/queue/work"
c = duckdb.connect(); c.execute("SET memory_limit='2GB'; SET threads=2")
D1, DN = WIN.DAYS[1], WIN.DAYS[-1]              # the first day of the window is the replay's warm-up
DAYFILES = [f"{D}/{d}.parquet" for d in WIN.DAYS[1:]]
# base: touch orders opened after the warm-up day that rested past their open block
c.execute(f"""CREATE TABLE base AS
SELECT oid, day, px, sz0, sz0*px AS own_usd, pos, ifnull(ahead_sz,0)*px AS ahead_usd, t_open,
       fill_sz AS fill_day, nullif(t_first_fill,-1) AS tff_day, nullif(t_end,-1) AS tend_day, end_status
FROM read_parquet({DAYFILES})
WHERE day BETWEEN '{D1}' AND '{DN}' AND pos < 2 AND (blk_end = -1 OR blk_end <> blk_open)""")
c.execute(f"""CREATE TABLE carry AS SELECT oid,
   sum(CASE WHEN what='fill' THEN a ELSE 0 END) cf, min(CASE WHEN what='fill' THEN b END) ctff,
   min(CASE WHEN what<>'fill' THEN b END) cend FROM read_parquet('{D}/*_carried_events.parquet') GROUP BY oid""")
c.execute(f"CREATE TABLE mf AS SELECT oid, sum(sz) rsz, min(t_ms) rtff FROM '{W}/maker_fills.parquet' GROUP BY oid")
c.execute("""CREATE TABLE t AS SELECT b.*,
   b.fill_day + ifnull(k.cf,0) AS fill_rep, coalesce(b.tff_day, k.ctff) tff_rep, coalesce(b.tend_day, k.cend) tend,
   ifnull(m.rsz,0) AS fill_res, m.rtff AS tff_res,
   CASE WHEN pos=0 THEN 0 WHEN ahead_usd<=5000 THEN 1 WHEN ahead_usd<=25000 THEN 2
        WHEN ahead_usd<=100000 THEN 3 WHEN ahead_usd<=250000 THEN 4 ELSE 5 END AS bk
FROM base b LEFT JOIN carry k USING(oid) LEFT JOIN mf m USING(oid)""")
out = {}
rows = c.execute("""SELECT bk, count(*) n,
  100*avg(CASE WHEN fill_rep>1e-12 THEN 1 ELSE 0 END) fill_rep,
  100*avg(CASE WHEN fill_res>1e-12 THEN 1 ELSE 0 END) fill_res,
  100*avg(CASE WHEN fill_rep>1e-12 THEN 1 ELSE 0 END) FILTER (WHERE own_usd>=5000 AND own_usd<=15000) mid_rep,
  100*avg(CASE WHEN fill_res>1e-12 THEN 1 ELSE 0 END) FILTER (WHERE own_usd>=5000 AND own_usd<=15000) mid_res,
  count(*) FILTER (WHERE own_usd>=5000 AND own_usd<=15000) n_mid
FROM t GROUP BY bk ORDER BY bk""").fetchall()
out["buckets"] = [dict(zip(["bk","n","fill_rep","fill_res","mid_rep","mid_res","n_mid"], r)) for r in rows]
out["n_total"] = c.execute("SELECT count(*) FROM t").fetchone()[0]
out["accounts"] = c.execute(f"SELECT count(DISTINCT u.acct), count(*) FILTER (WHERE u.acct IS NULL) FROM t LEFT JOIN read_parquet('{W}/oid_user/*.parquet') u USING(oid)").fetchone()
out["agree_rep_res"] = c.execute("SELECT avg(((fill_rep>1e-12)=(fill_res>1e-12))::INT) FROM t").fetchone()[0]
# own Kaplan-Meier (product-limit) on time to first fill, cancels/ends censored; still-open at data end censored at last obs
grid = [0.1, 0.5, 1, 5, 30, 300]
km = {}
for bk in range(6):
    d = c.execute("""SELECT CASE WHEN fill_rep>1e-12 AND tff_rep IS NOT NULL THEN (tff_rep-t_open)/1000.0 ELSE (tend-t_open)/1000.0 END tt,
                     (fill_rep>1e-12 AND tff_rep IS NOT NULL) ev FROM t WHERE bk=? AND
                     (tend IS NOT NULL OR (fill_rep>1e-12 AND tff_rep IS NOT NULL))""", [bk]).fetchnumpy()
    tt, ev = d["tt"], d["ev"].astype(bool)
    o = np.argsort(tt, kind="stable"); tt, ev = tt[o], ev[o]
    ut, idx = np.unique(tt, return_index=True)
    n_at = len(tt) - idx
    d_at = np.add.reduceat(ev.astype(int), idx)
    S = np.cumprod(1 - d_at / n_at)
    km[bk] = [100 * (1 - (S[np.searchsorted(ut, g, side="right") - 1] if g >= ut[0] else 1.0)) for g in grid]
    km[f"n{bk}"] = int(len(tt))
out["km"] = km
# headline FIFO share from the replay's own counter table (cross-check of the 95.8% arithmetic)
out["fifo_counter"] = c.execute(f"""SELECT sum(fifo_head) FILTER (WHERE day>='{D1}'), sum(fifo_not_head) FILTER (WHERE day>='{D1}'),
   sum(fifo_head) FILTER (WHERE day>='{D1}')/sum(fifo_head+fifo_not_head) FILTER (WHERE day>='{D1}') FROM '{D}/fifo_check.parquet'""").fetchone()
json.dump(out, open("data/checks/queue/recompute.json", "w"), indent=1, default=float)
print(json.dumps(out, indent=1, default=float))
