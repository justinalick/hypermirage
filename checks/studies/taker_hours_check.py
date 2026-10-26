"""Independent recompute of analysis/taker_hours/hours.py: notional-weighted 60 s taker markout by hour of the week
(New York time) for takers other than the largest cluster, with the mid 60 s after each fill found by an SQL ASOF join
on the replayed BBO instead of numpy searchsorted. Exit code 1 on a mismatch above 1e-9 bps in any hour."""
import json, sys
import duckdb, numpy as np
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/taker_hours/hours.json"))["how"]["ex_T1"]
con = duckdb.connect(); con.execute("SET memory_limit='4GB'; SET threads=4; SET TimeZone='UTC'")
FILES = [f"data/raw/xyz/fills/{d}.parquet" for d in WIN.ISO]
con.execute("""CREATE TABLE b AS SELECT epoch_ns(t)::BIGINT tn, (best_bid + best_ask) / 2 mid
               FROM 'data/derived/markout/bbo_t.parquet' WHERE t IS NOT NULL ORDER BY tn""")
endn, startn = con.sql("SELECT max(tn), min(tn) FROM b").fetchall()[0]
con.execute(f"""CREATE TABLE t AS SELECT epoch_ns(timestamp::TIMESTAMP)::BIGINT ft, price::DOUBLE px, size::DOUBLE sz,
        CASE WHEN side IN ('B', 'buy') THEN 1 ELSE -1 END s, cm.cluster c
    FROM read_parquet({FILES}) f JOIN read_csv('data/derived/taker_clusters/cluster_map.csv') cm USING (address)
    WHERE coin = 'xyz:SP500' AND crossed AND timestamp >= '{WIN.T0}' AND timestamp < '{WIN.T1}'""")
top = con.sql("SELECT c FROM t GROUP BY c ORDER BY sum(px * sz) DESC LIMIT 1").fetchall()[0][0]
r = con.sql(f"""WITH x AS (SELECT t.*, t.ft + 60000000000 fh FROM t WHERE c <> '{top}' AND ft > {startn} AND ft + 60000000000 <= {endn}),
     y AS (SELECT x.*, b.mid FROM x ASOF JOIN b ON b.tn <= x.fh)
     SELECT (isodow(timezone('America/New_York', to_timestamp(ft / 1e9))) - 1) * 24
              + hour(timezone('America/New_York', to_timestamp(ft / 1e9))) how,
            sum(s * (mid - px) / px * 1e4 * px * sz) / sum(px * sz) mk
     FROM y GROUP BY 1 ORDER BY 1""").fetchall()
got = np.full(168, np.nan)
for h, v in r: got[int(h)] = v
want = np.array(R["mk60"]); n = np.array(R["notional"])
m = n > 0
bad = np.where(m & ~(np.abs(got - want) <= 1e-9))[0]
print(f"{'OK  ' if len(bad) == 0 else 'FAIL'} hour-of-week 60 s markout, {int(m.sum())} hours with fills, mismatches {len(bad)}"
      + (f": e.g. hour {bad[0]} recompute {got[bad[0]]:+.6f} hours.json {want[bad[0]]:+.6f}" if len(bad) else ""))
sys.exit(0 if len(bad) == 0 else 1)
