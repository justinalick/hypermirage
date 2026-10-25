"""Cache the aggregates of analysis/concentration_chart.py (same queries) to a small json.
No addresses are written. DuckDB capped at 2 GB / 2 threads per the brief."""
import json, sys, duckdb
sys.path.insert(0, "scripts")
import window as WIN
ROOT = "."
DAYS = WIN.ISO
FILES = [f"{ROOT}/data/raw/xyz/fills/{d}.parquet" for d in DAYS]
con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=2; SET TimeZone='UTC'")
con.execute(f"""CREATE TEMP TABLE mk AS
SELECT strftime(timestamp, '%Y-%m-%d') AS d, address, sum((price*size)::DOUBLE) AS usd
FROM read_parquet({FILES}) WHERE coin = 'xyz:SP500' AND NOT crossed GROUP BY ALL""")
daily = con.execute("""
SELECT d, sum(usd) AS vol, count(*) AS makers,
       sum(s) FILTER (WHERE rk = 1), sum(s) FILTER (WHERE rk BETWEEN 2 AND 3), sum(s) FILTER (WHERE rk BETWEEN 4 AND 10)
FROM (SELECT *, usd / sum(usd) OVER (PARTITION BY d) AS s,
             row_number() OVER (PARTITION BY d ORDER BY usd DESC) AS rk FROM mk)
GROUP BY d ORDER BY d""").fetchall()
pooled_top3, n_makers, total = con.execute("""
SELECT sum(usd) FILTER (WHERE r <= 3) / sum(usd), count(*), sum(usd)
FROM (SELECT address, sum(usd) AS usd, row_number() OVER (ORDER BY sum(usd) DESC) AS r FROM mk GROUP BY 1)""").fetchone()
roles = json.load(open(f"{ROOT}/data/derived/concentration/roles.json"))
master = {a.lower(): v["data"]["master"].lower() for a, v in roles["roles"].items() if v.get("role") == "subAccount"}
for m, sl in roles["subs"].items():
    for sub in (sl if isinstance(sl, list) else []):
        master.setdefault(sub["subAccountUser"].lower(), m.lower())
con.execute("CREATE TEMP TABLE links (a VARCHAR, g VARCHAR)")
con.executemany("INSERT INTO links VALUES (?, ?)", list(master.items()))
con.execute("""CREATE TEMP TABLE gk AS
SELECT d, coalesce(l.g, lower(address)) AS g, sum(usd) AS usd FROM mk LEFT JOIN links l ON l.a = lower(mk.address) GROUP BY ALL""")
group_top3 = [r[1] for r in con.execute("""
SELECT d, sum(s) FILTER (WHERE rk <= 3)
FROM (SELECT *, usd / sum(usd) OVER (PARTITION BY d) AS s,
             row_number() OVER (PARTITION BY d ORDER BY usd DESC) AS rk FROM gk) GROUP BY d ORDER BY d""").fetchall()]
pooled_group_top3 = con.execute("""
SELECT sum(usd) FILTER (WHERE r <= 3) / sum(usd)
FROM (SELECT g, sum(usd) AS usd, row_number() OVER (ORDER BY sum(usd) DESC) AS r FROM gk GROUP BY 1)""").fetchone()[0]
n_trades = con.execute(f"SELECT count(*) FROM read_parquet({FILES}) WHERE coin = 'xyz:SP500' AND crossed").fetchone()[0]
assert [r[0] for r in daily] == DAYS
out = dict(daily=[dict(d=r[0], vol=r[1], makers=r[2], r1=r[3], r23=r[4], r410=r[5]) for r in daily],
           pooled_top3=pooled_top3, n_makers=n_makers, total=total, group_top3=group_top3,
           pooled_group_top3=pooled_group_top3, n_trades=n_trades)
json.dump(out, open(f"{ROOT}/data/derived/chart_cache/concentration.json", "w"), indent=1)
print(pooled_top3, pooled_group_top3, n_makers, total, n_trades)
print([round(100 * (r[3] + r[4]), 1) for r in daily]); print([round(100 * g, 1) for g in group_top3])
