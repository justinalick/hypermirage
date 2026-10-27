"""Independent recompute of analysis/taker_hours/hours.py, with the mid 60 s after each fill found by an SQL ASOF join
on the replayed BBO instead of numpy searchsorted, and all grouping in SQL:
1. notional-weighted 60 s taker markout by hour of the week (New York time) for takers other than the largest cluster;
2. the month-by-month (New York calendar months) 60 s markout of each of the ten largest taker clusters (by taker
   notional), left out where a cluster has fewer than 200 fills with a markout in a month, as in hours.py;
3. the month-to-month correlation shown on the page (r): for each pair of consecutive months in which all ten
   clusters have a value, the Pearson correlation of the ten clusters' markouts, averaged over those pairs
   (charts/taker_hours.py), here computed with an explicit centered formula instead of np.corrcoef. The Spearman
   (rank) version of the same average is printed for reference, not compared.
Exit code 1 on a mismatch above 1e-9 bps in any hour or cluster-month, or 1e-9 in r."""
import json, sys
import duckdb, numpy as np
sys.path.insert(0, "scripts")
import window as WIN

H = json.load(open("data/derived/taker_hours/hours.json"))
R = H["how"]["ex_T1"]
con = duckdb.connect(); con.execute("SET memory_limit='3GB'; SET threads=2; SET TimeZone='UTC'")
FILES = [f"data/raw/xyz/fills/{d}.parquet" for d in WIN.ISO]
con.execute("""CREATE TABLE b AS SELECT epoch_ns(t)::BIGINT tn, (best_bid + best_ask) / 2 mid
               FROM 'data/derived/markout/bbo_t.parquet' WHERE t IS NOT NULL ORDER BY tn""")
endn, startn = con.sql("SELECT max(tn), min(tn) FROM b").fetchall()[0]
con.execute(f"""CREATE TABLE t AS SELECT epoch_ns(timestamp::TIMESTAMP)::BIGINT ft, price::DOUBLE px, size::DOUBLE sz,
        CASE WHEN side IN ('B', 'buy') THEN 1 ELSE -1 END s, cm.cluster c
    FROM read_parquet({FILES}) f JOIN read_csv('data/derived/taker_clusters/cluster_map.csv') cm USING (address)
    WHERE coin = 'xyz:SP500' AND crossed AND timestamp >= '{WIN.T0}' AND timestamp < '{WIN.T1}'""")
top = con.sql("SELECT c FROM t GROUP BY c ORDER BY sum(px * sz) DESC LIMIT 1").fetchall()[0][0]
ok = True

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
ok &= len(bad) == 0
print(f"{'OK  ' if len(bad) == 0 else 'FAIL'} hour-of-week 60 s markout, {int(m.sum())} hours with fills, mismatches {len(bad)}"
      + (f": e.g. hour {bad[0]} recompute {got[bad[0]]:+.6f} hours.json {want[bad[0]]:+.6f}" if len(bad) else ""))

# month by month, ten largest clusters
mon = con.sql(f"""
    WITH top10 AS (SELECT c, row_number() OVER (ORDER BY sum(px * sz) DESC) rk FROM t GROUP BY c QUALIFY rk <= 10),
    x AS (SELECT t.*, top10.rk, t.ft + 60000000000 fh FROM t JOIN top10 USING (c)
          WHERE ft > {startn} AND ft + 60000000000 <= {endn}),
    y AS (SELECT x.*, b.mid FROM x ASOF JOIN b ON b.tn <= x.fh)
    SELECT rk, strftime(timezone('America/New_York', to_timestamp(ft // 1000000000)), '%Y-%m') mon,
           count(*) n, sum(s * (mid - px) / px * 1e4 * px * sz) / sum(px * sz) mk
    FROM y WHERE mid IS NOT NULL AND isfinite(mid) GROUP BY ALL""").fetchall()
months = H["months"]
M = np.full((10, len(months)), np.nan)
for rk, mm, n_, v in mon:
    if mm in months and n_ >= 200: M[rk - 1, months.index(mm)] = v
seen = sorted({mm for _, mm, _, _ in mon})
want = np.array([[np.nan if v is None else v for v in H["clusters"][f"T{i + 1}"]["mk60_by_month"]] for i in range(10)])
same_nan = np.array_equal(np.isnan(M), np.isnan(want))
diff = np.nanmax(np.abs(M - want)) if same_nan else np.inf
good = seen == months and same_nan and diff <= 1e-9
ok &= good
print(f"{'OK  ' if good else 'FAIL'} cluster-month 60 s markout, 10 clusters x {len(months)} months ({months[0]} to {months[-1]}), "
      f"{int((~np.isnan(M)).sum())} values, max abs diff {diff:.2e} bps")

def pearson(a, b):
    a = a - a.mean(); b = b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum()))
def ranks(a):
    o = np.argsort(a); r_ = np.empty(len(a)); r_[o] = np.arange(1, len(a) + 1); return r_   # no ties in practice
pairs = [j for j in range(len(months) - 1) if not np.isnan(M[:, j]).any() and not np.isnan(M[:, j + 1]).any()]
rs = [pearson(M[:, j], M[:, j + 1]) for j in pairs]
rr = [pearson(ranks(M[:, j]), ranks(M[:, j + 1])) for j in pairs]
C = H["clusters"]   # the chart's own formula, from hours.json
cross = np.mean([np.corrcoef(*[[C[k]["mk60_by_month"][i] for k in C] for i in (j, j + 1)])[0, 1] for j in range(len(months) - 1)
                 if all(C[k]["mk60_by_month"][j] is not None and C[k]["mk60_by_month"][j + 1] is not None for k in C)])
good = abs(np.mean(rs) - cross) <= 1e-9
ok &= good
print(f"{'OK  ' if good else 'FAIL'} month-to-month r: recompute {np.mean(rs):.4f}  chart formula on hours.json {cross:.4f}  (page: 0.71), "
      f"{len(pairs)} month pairs, per pair {[round(x, 2) for x in rs]}")
print(f"     for reference: Spearman (rank) version {np.mean(rr):.4f}, per pair {[round(x, 2) for x in rr]}")
print("ALL OK" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)
