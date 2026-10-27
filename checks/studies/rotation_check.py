"""Independent recompute of analysis/maker_rotation/rotation.py, all in SQL with window ranks (no pandas pivots):
1. weekly top-3 share of maker volume, by address and with declared sub-accounts merged;
2. (groups) the week-to-week rank correlation of the top 20 groups by pooled maker volume: weekly volumes of those
   20 groups (0 in weeks without maker fills) from SQL, then scipy.stats.spearmanr (average ranks for ties) on each
   pair of consecutive weeks, instead of pandas rank + np.corrcoef; its median is compared with the rho list;
3. (groups) new entrants to the weekly top 3, by an SQL anti-join of each week's top 3 on the previous week's;
4. (groups) the closing run of weeks in which the largest pooled group ranks first.
Weeks are ISO weeks (UTC) of the run window, partial first and last weeks included, as in rotation.py.
Exit code 1 on a mismatch above 1e-9 (shares, correlations) or in counts."""
import json, sys
import duckdb, numpy as np
from scipy.stats import spearmanr
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/maker_rotation/rotation.json"))
roles = json.load(open("data/derived/concentration/roles.json"))
link = {a.lower(): v["data"]["master"].lower() for a, v in roles["roles"].items() if v.get("role") == "subAccount"}
for m, sl in roles["subs"].items():
    for sub in (sl if isinstance(sl, list) else []):
        link.setdefault(sub["subAccountUser"].lower(), m.lower())
con = duckdb.connect(); con.execute("SET memory_limit='3GB'; SET threads=2; SET TimeZone='UTC'")
con.execute("CREATE TABLE links (a VARCHAR, g VARCHAR)"); con.executemany("INSERT INTO links VALUES (?, ?)", list(link.items()))
FILES = [f"data/raw/xyz/fills/{d}.parquet" for d in WIN.ISO]
con.execute(f"""CREATE TABLE f AS SELECT strftime(timestamp, '%G-W%V') w, lower(address) a, (price*size)::DOUBLE usd
                FROM read_parquet({FILES}) WHERE coin = 'xyz:SP500' AND NOT crossed""")
ok = True
def report(good, msg):
    global ok
    ok &= bool(good)
    print(f"{'OK  ' if good else 'FAIL'} {msg}")

for key, grp in (("groups", "coalesce(l.g, f.a)"), ("addresses", "f.a")):
    rows = con.sql(f"""WITH x AS (SELECT w, {grp} k, sum(usd) usd FROM f LEFT JOIN links l ON l.a = f.a GROUP BY ALL),
                        r AS (SELECT *, usd / sum(usd) OVER (PARTITION BY w) s, row_number() OVER (PARTITION BY w ORDER BY usd DESC) rk FROM x)
                       SELECT w, sum(s) FILTER (WHERE rk <= 3) FROM r GROUP BY w ORDER BY w""").fetchall()
    want = dict(zip(R[key]["weeks"], R[key]["weekly_top3_share"]))
    bad = [(w, v, want.get(w)) for w, v in rows if want.get(w) is None or abs(v - want[w]) > 1e-12]
    report(not bad and len(rows) == len(want), f"{key}: weekly top-3 share, {len(rows)} weeks, mismatches {len(bad)} {bad[:3]}")

# rank statistics, groups (sub-accounts merged)
G = R["groups"]
con.execute("""CREATE TABLE wg AS SELECT w, coalesce(l.g, f.a) k, sum(usd) usd FROM f LEFT JOIN links l ON l.a = f.a GROUP BY ALL""")
con.execute("""CREATE TABLE pooled AS SELECT k, row_number() OVER (ORDER BY sum(usd) DESC) prk FROM wg GROUP BY k""")
weeks = [w for (w,) in con.sql("SELECT DISTINCT w FROM wg ORDER BY w").fetchall()]
report(weeks == G["weeks"], f"groups: {len(weeks)} ISO weeks ({weeks[0]} to {weeks[-1]})")
# weekly volume of the top-20 pooled groups, a full weeks x groups grid with 0 where a group has no maker fill
v = con.sql("""SELECT wk.w, p.prk, coalesce(wg.usd, 0) usd
               FROM (SELECT DISTINCT w FROM wg) wk CROSS JOIN (SELECT * FROM pooled WHERE prk <= 20) p
               LEFT JOIN wg ON wg.w = wk.w AND wg.k = p.k ORDER BY wk.w, p.prk""").fetchnumpy()
V = v["usd"].reshape(len(weeks), 20)
rho = np.array([spearmanr(V[i], V[i + 1]).statistic for i in range(len(weeks) - 1)])
want = np.array(G["rank_rho_week_to_week"])
report(len(rho) == len(want) and np.all(np.abs(rho - want) <= 1e-9),
       f"groups: week-to-week Spearman rho of the top 20, {len(rho)} pairs, max abs diff {np.max(np.abs(rho - want)):.2e}")
report(abs(np.median(rho) - np.median(want)) <= 1e-9,
       f"groups: median rho recompute {np.median(rho):.4f}  rotation.json {np.median(want):.4f}  (page: 0.93)")
# new entrants to the weekly top 3
ent = con.sql("""WITH r AS (SELECT w, k, row_number() OVER (PARTITION BY w ORDER BY usd DESC) rk FROM wg),
                      t3 AS (SELECT w, k, dense_rank() OVER (ORDER BY w) wi FROM r WHERE rk <= 3)
                 SELECT c.wi, count(*) FILTER (WHERE p.k IS NULL) FROM t3 c LEFT JOIN t3 p ON p.wi = c.wi - 1 AND p.k = c.k
                 WHERE c.wi > 1 GROUP BY c.wi ORDER BY c.wi""").fetchall()
ent = [int(n) for _, n in ent]
report(ent == G["top3_new_entrants"],
       f"groups: new top-3 entrants per week, mean recompute {np.mean(ent):.4f}  rotation.json {np.mean(G['top3_new_entrants']):.4f}  (page: 0.69)")
# closing run of weeks with the largest pooled group ranked first
rk1 = [int(r) for _, r in con.sql("""WITH r AS (SELECT w, k, row_number() OVER (PARTITION BY w ORDER BY usd DESC) rk FROM wg)
                                     SELECT r.w, r.rk FROM r JOIN pooled p USING (k) WHERE p.prk = 1 ORDER BY r.w""").fetchall()]
run = len(rk1) - next((i + 1 for i in range(len(rk1) - 1, -1, -1) if rk1[i] != 1), 0)
r1 = G["weekly_rank"]["G1"]; k = len(r1)
while k > 0 and r1[k - 1] == 1: k -= 1
report(len(rk1) == len(weeks) and run == len(r1) - k,
       f"groups: largest group ranked first in each of the last {run} weeks (rotation.json {len(r1) - k}, page: 17), present in {len(rk1)} of {len(weeks)} weeks")
print("ALL OK" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)
