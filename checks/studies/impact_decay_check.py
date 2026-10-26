"""Independent recompute of analysis/impact_decay/decay.py (clean metaorders, all accounts): metaorders rebuilt in SQL
with window functions instead of pandas, mean impact at 0.25 s / 10 s / 60 s / 300 s per size bucket, compared with
decay.json. Exit code 1 on any mismatch above 1e-6 bps or in counts."""
import json, sys
import duckdb
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/impact_decay/decay.json"))["groups"]["all"]
con = duckdb.connect(); con.execute("SET memory_limit='4GB'; SET threads=4")
q = con.sql("""
WITH o AS (SELECT * FROM 'data/derived/impact/orders.parquet' WHERE NOT liq),
s AS (SELECT *, CASE WHEN lag(a) OVER w IS DISTINCT FROM a OR lag(s) OVER w IS DISTINCT FROM s
                       OR t0 - lag(t1) OVER w > 300e9 THEN 1 ELSE 0 END AS new
      FROM o WINDOW w AS (ORDER BY a, t0, order_id)),
g AS (SELECT *, sum(new) OVER (ORDER BY a, t0, order_id ROWS UNBOUNDED PRECEDING) mo FROM s),
lastrow AS (SELECT mo, arg_max(g, t1) l FROM g GROUP BY mo),
m0 AS (SELECT g.mo, any_value(g.a) a, any_value(g.s) s, sum(q) q, arg_min(m0, t0) m0_first, min(t0) t0_first, max(t1) t1_last FROM g GROUP BY g.mo),
m AS (SELECT *, lead(t0_first) OVER (PARTITION BY a ORDER BY mo) next_t0 FROM m0)   -- the account's next metaorder
SELECT m.q, m.next_t0, m.t1_last t1,
  m.s * ((l.l).m0 * (1 + (l.l).s * (l.l).i0 / 1e4) - m.m0_first) / m.m0_first * 1e4 i0,
  m.s * ((l.l).m0 * (1 + (l.l).s * (l.l).i10 / 1e4) - m.m0_first) / m.m0_first * 1e4 i10,
  m.s * ((l.l).m0 * (1 + (l.l).s * (l.l).i60 / 1e4) - m.m0_first) / m.m0_first * 1e4 i60,
  m.s * ((l.l).m0 * (1 + (l.l).s * (l.l).i300 / 1e4) - m.m0_first) / m.m0_first * 1e4 i300
FROM m JOIN lastrow l USING (mo)""").df()
q = q.dropna(subset=["i0", "i10", "i60", "i300"])
clean = ~((q.next_t0 - q.t1) / 1e9 <= 300).fillna(False).astype(bool)   # no next metaorder: clean
ok = True
for lo, hi, lab in [(1e3, 1e4, "$1k to $10k"), (1e4, 1e5, "$10k to $100k"), (1e5, 1e6, "$100k to $1M"), (1e6, float("inf"), "$1M+")]:
    S = q[clean & (q.q >= lo) & (q.q < hi)]
    r = R[lab]
    for h in ("i0", "i10", "i60", "i300"):
        good = abs(S[h].mean() - r[h][0]) < 1e-6
        ok &= good
        print(f"{'OK  ' if good else 'FAIL'} {lab:14s} {h:5s} recompute {S[h].mean():+.6f}  decay.json {r[h][0]:+.6f}")
    good = len(S) == r["n"]; ok &= good
    print(f"{'OK  ' if good else 'FAIL'} {lab:14s} n     recompute {len(S)}  decay.json {r['n']}")
print("ALL OK" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)
