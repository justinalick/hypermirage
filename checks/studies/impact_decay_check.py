"""Independent recompute of analysis/impact_decay/decay.py (clean metaorders, all accounts). Metaorders are rebuilt in
SQL with window functions instead of pandas, then:
1. mean impact at 0.25 s / 10 s / 60 s / 300 s and the count per size bucket;
2. the momentum control: the placebo mids are looked up with an SQL ASOF join on the replayed BBO (instead of numpy
   searchsorted), the placebo bins (20 quantile bins of the metaorder's own move i0 x 5 of the minute before, pre60)
   are built in SQL (quantile_cont edges, edge counting with list_filter) and the expectation cells are an SQL
   GROUP BY with the >= 100 placebo rule; this gives the expected continuation exp_i10/60/300 and the excess beyond
   momentum ex_i10/60/300 per size bucket. The placebo draws (time offset of 1 to 7 days, random side) use the
   analysis seed (13) in the same metaorder order, since the placebo is defined by those draws;
3. the 95% intervals (day-block bootstrap, 1000 draws) of every horizon, the momentum terms and the kept shares
   kept_10/60/300, with each draw's day weights as a count matrix (draws x days) and a matrix product instead of
   indexing per-day sums, and percentiles by explicit sorting and linear interpolation. The draws use the analysis
   seed (11), so the intervals must agree to rounding: tolerance 1e-9 (bps for means and intervals, a fraction for
   kept shares). A different seed would move the 2.5% and 97.5% points by bootstrap noise; this check does not
   test that.
The mid level at each horizon is formed in the same floating-point order as decay.py (i / 1e4 * s * m0 + m0): a
mid that returns exactly to the start gives i0 = 0 there, and 0 is one of the placebo bin edges, so a one-ulp
difference would move metaorders between bins. Like decay.py, pre60 of a metaorder is its first order's non-missing pre60 (pandas "first"); the number of metaorders
where that differs from the first order's own pre60 is printed. Exit code 1 on any mismatch above 1e-9 or in counts."""
import json, sys
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/impact_decay/decay.json"))["groups"]["all"]
con = duckdb.connect(); con.execute("SET memory_limit='3GB'; SET threads=2")
q = con.sql("""
WITH o AS (SELECT * FROM 'data/derived/impact/orders.parquet' WHERE NOT liq),
s AS (SELECT *, CASE WHEN lag(a) OVER w IS DISTINCT FROM a OR lag(s) OVER w IS DISTINCT FROM s
                       OR t0 - lag(t1) OVER w > 300e9 THEN 1 ELSE 0 END AS new, row_number() OVER w rn
      FROM o WINDOW w AS (ORDER BY a, t0, order_id)),
g AS (SELECT *, sum(new) OVER (ORDER BY a, t0, order_id ROWS UNBOUNDED PRECEDING) mo FROM s),
lastrow AS (SELECT mo, arg_max(g, t1) l FROM g GROUP BY mo),
m0 AS (SELECT g.mo, any_value(g.a) a, any_value(g.s) s, sum(q) q, first(m0 ORDER BY rn) m0_first, min(t0) t0_first, max(t1) t1_last,
              first(day ORDER BY rn) AS day, first(pre60 ORDER BY rn) pre60_row,
              first(pre60 ORDER BY rn) FILTER (WHERE pre60 IS NOT NULL AND NOT isnan(pre60)) pre60
       FROM g GROUP BY g.mo),
m AS (SELECT *, lead(t0_first) OVER (PARTITION BY a ORDER BY mo) next_t0 FROM m0)   -- the account's next metaorder
SELECT m.mo, m.q, m.next_t0, m.t0_first t0, m.t1_last t1, m.day, m.pre60, m.pre60_row,
  m.s * ((l.l).i0 / 1e4 * (l.l).s * (l.l).m0 + (l.l).m0 - m.m0_first) / m.m0_first * 1e4 i0,
  m.s * ((l.l).i10 / 1e4 * (l.l).s * (l.l).m0 + (l.l).m0 - m.m0_first) / m.m0_first * 1e4 i10,
  m.s * ((l.l).i60 / 1e4 * (l.l).s * (l.l).m0 + (l.l).m0 - m.m0_first) / m.m0_first * 1e4 i60,
  m.s * ((l.l).i300 / 1e4 * (l.l).s * (l.l).m0 + (l.l).m0 - m.m0_first) / m.m0_first * 1e4 i300
FROM m JOIN lastrow l USING (mo) ORDER BY m.mo""").df()
q = q.dropna(subset=["i0", "i10", "i60", "i300"]).reset_index(drop=True)
q["clean"] = ~((q.next_t0 - q.t1) / 1e9 <= 300).fillna(False).astype(bool)   # no next metaorder: clean
BK = [(1e3, 1e4, "$1k to $10k"), (1e4, 1e5, "$10k to $100k"), (1e5, 1e6, "$100k to $1M"), (1e6, float("inf"), "$1M+")]
ok = True
def report(good, msg):
    global ok
    ok &= bool(good)
    print(f"{'OK  ' if good else 'FAIL'} {msg}")

for lo, hi, lab in BK:
    S = q[q.clean & (q.q >= lo) & (q.q < hi)]
    r = R[lab]
    for h in ("i0", "i10", "i60", "i300"):
        report(abs(S[h].mean() - r[h][0]) < 1e-6, f"{lab:14s} {h:5s} recompute {S[h].mean():+.6f}  decay.json {r[h][0]:+.6f}")
    report(len(S) == r["n"], f"{lab:14s} n     recompute {len(S)}  decay.json {r['n']}")
nd = int(((q.pre60_row.isna() | np.isnan(q.pre60_row.astype(float))) & q.pre60.notna()).sum())
print(f"     note: {nd} metaorders take pre60 from a later order (first order's pre60 missing)")

# ---- momentum control
C = q[q.clean].reset_index(drop=True)            # metaorder order, as decay.py (M is indexed by metaorder id)
rng_p = np.random.default_rng(13)
k = rng_p.choice(np.r_[-7:0, 1:8], len(C)) * 86400 * 10**9
sp = rng_p.choice([-1, 1], len(C))
P = pd.DataFrame({"id": np.arange(len(C)), "tp": C.t1.values + k, "lb": np.maximum(C.t1.values - C.t0.values, 250_000_000),
                  "sp": sp.astype(float)})
con.register("p_df", P)
con.register("c_df", C[["i0", "pre60", "i10", "i60", "i300", "q"]].assign(id=np.arange(len(C))))
con.execute("""CREATE TABLE b AS SELECT epoch_ns(t)::BIGINT tn, (best_bid + best_ask) / 2 mid FROM 'data/derived/markout/bbo_t.parquet'
               WHERE t IS NOT NULL AND best_ask > best_bid AND NOT isnan(best_bid) AND NOT isnan(best_ask)""")
con.execute("CREATE TABLE p AS SELECT * FROM p_df"); con.execute("CREATE TABLE c AS SELECT * FROM c_df")
con.execute("""CREATE TABLE pt AS
  SELECT id, 'now' k, tp t FROM p UNION ALL SELECT id, 'back', tp - lb FROM p UNION ALL SELECT id, 'back60', tp - lb - 60000000000 FROM p
  UNION ALL SELECT id, 'f10', tp + 10000000000 FROM p UNION ALL SELECT id, 'f60', tp + 60000000000 FROM p
  UNION ALL SELECT id, 'f300', tp + 300 * 1000000000::BIGINT FROM p""")
con.execute("""CREATE TABLE pm AS SELECT pt.id, pt.k, b.mid FROM pt ASOF LEFT JOIN b ON b.tn <= pt.t""")
con.execute("""CREATE TABLE pl AS
  WITH w AS (SELECT id, max(mid) FILTER (WHERE k = 'now') m_now, max(mid) FILTER (WHERE k = 'back') m_back,
                    max(mid) FILTER (WHERE k = 'back60') m_back60, max(mid) FILTER (WHERE k = 'f10') m_f10,
                    max(mid) FILTER (WHERE k = 'f60') m_f60, max(mid) FILTER (WHERE k = 'f300') m_f300 FROM pm GROUP BY id),
       e AS (SELECT min(tn) t0, max(tn) t1 FROM b)
  SELECT p.id, p.tp - p.lb > e.t0 AND p.tp + 300 * 1000000000::BIGINT < e.t1 inside,
         p.sp * (w.m_now - w.m_back) / w.m_now * 1e4 back,
         p.sp * (w.m_back - w.m_back60) / w.m_now * 1e4 pre,
         p.sp * (w.m_f10 - w.m_now) / w.m_now * 1e4 f_i10, p.sp * (w.m_f60 - w.m_now) / w.m_now * 1e4 f_i60,
         p.sp * (w.m_f300 - w.m_now) / w.m_now * 1e4 f_i300
  FROM p JOIN w USING (id), e""")
QS = np.linspace(0, 1, 21).tolist(); QS5 = np.linspace(0, 1, 6).tolist()
con.execute(f"""CREATE TABLE ed AS SELECT
    list_sort(list_distinct(quantile_cont(i0, {QS}::DOUBLE[]))) e1,
    list_sort(list_distinct(quantile_cont(CASE WHEN isnan(pre60) THEN NULL ELSE pre60 END, {QS5}::DOUBLE[]))) e2 FROM c""")
def bin_sql(x, e):   # np.digitize(x, e) - 1 clipped to the inner bins; missing or non-finite values: their own bin
    return f"""CASE WHEN {x} IS NULL OR NOT isfinite({x}) THEN len({e}) - 1
                    ELSE least(greatest(len(list_filter({e}, lambda v: v <= {x})) - 1, 0), len({e}) - 2) END"""
con.execute(f"""CREATE TABLE pk AS SELECT pl.*, ({bin_sql('back', 'e1')}) * (len(e2) + 1) + ({bin_sql('pre', 'e2')}) key FROM pl, ed""")
con.execute(f"""CREATE TABLE ck AS SELECT c.*, ({bin_sql('i0', 'e1')}) * (len(e2) + 1) + ({bin_sql('pre60', 'e2')}) key FROM c, ed""")
for h in ("i10", "i60", "i300"):
    e = con.sql(f"""WITH cell AS (SELECT key, avg(f_{h}) mu, count(*) n FROM pk
                                  WHERE inside AND back IS NOT NULL AND isfinite(back) AND f_{h} IS NOT NULL AND isfinite(f_{h}) GROUP BY key)
                    SELECT ck.id, CASE WHEN cell.n >= 100 THEN cell.mu END ex FROM ck LEFT JOIN cell USING (key) ORDER BY ck.id""").df()
    C[f"exp_{h}"] = e.ex.values
    C[f"ex_{h}"] = (C[h] - C.i0) - C[f"exp_{h}"]

# ---- bootstrap over days
days = np.array(sorted(q.day.unique())); nday = len(days)
DRAW = np.random.default_rng(11).integers(0, nday, (1000, nday))
W = np.zeros((1000, nday)); np.add.at(W, (np.repeat(np.arange(1000), nday), DRAW.ravel()), 1)
def pct(x, p):
    x = np.sort(x[np.isfinite(x)]); pos = p / 100 * (len(x) - 1); i = int(np.floor(pos)); f = pos - i
    return x[i] if f == 0 else x[i] + (x[min(i + 1, len(x) - 1)] - x[i]) * f
def boot(S, col):
    v = S[["day", col]].dropna()
    g = v.groupby("day")[col].agg(["sum", "size"]).reindex(days, fill_value=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return float(v[col].mean()), (W @ g["sum"].values) / (W @ g["size"].values.astype(float))
PAGE = {("$1M+", "kept_300"): "page: 85%, CI 71% to 96%", ("$1M+", "ex_i300"): "page: about -0.3 bps",
        ("$100k to $1M", "kept_300"): "page: 108%", ("$1k to $10k", "ex_i300"): "page: +0.09 bps",
        ("$10k to $100k", "ex_i300"): "page: +0.08 bps"}
for lo, hi, lab in BK:
    S = C[(C.q >= lo) & (C.q < hi)]
    r = R[lab]; bs = {}
    for h in ("i0", "i10", "i60", "i300", "exp_i10", "exp_i60", "exp_i300", "ex_i10", "ex_i60", "ex_i300"):
        mu, bs[h] = boot(S, h)
        got = [mu, pct(bs[h], 2.5), pct(bs[h], 97.5)]
        d = max(abs(a - b_) for a, b_ in zip(got, r[h]))
        report(d <= 1e-9, f"{lab:14s} {h:8s} recompute {got[0]:+.4f} [{got[1]:+.4f}, {got[2]:+.4f}]  "
                          f"decay.json {r[h][0]:+.4f} [{r[h][1]:+.4f}, {r[h][2]:+.4f}]  {PAGE.get((lab, h), '')}")
    for h in ("i10", "i60", "i300"):
        kk = f"kept_{h[1:]}"
        rat = bs[h] / bs["i0"]
        got = [C.loc[S.index, h].mean() / C.loc[S.index, "i0"].mean(), pct(rat, 2.5), pct(rat, 97.5)]
        d = max(abs(a - b_) for a, b_ in zip(got, r[kk]))
        report(d <= 1e-9, f"{lab:14s} {kk:8s} recompute {got[0]:.4f} [{got[1]:.4f}, {got[2]:.4f}]  "
                          f"decay.json {r[kk][0]:.4f} [{r[kk][1]:.4f}, {r[kk][2]:.4f}]  {PAGE.get((lab, kk), '')}")
print("ALL OK" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)
