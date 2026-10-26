"""Independent recompute of analysis/maker_rotation/rotation.py: weekly top-3 share of maker volume, by address and
with declared sub-accounts merged, in one SQL pass with window ranks (no pandas pivots). Exit code 1 on a mismatch
above 1e-12."""
import json, sys
import duckdb
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/maker_rotation/rotation.json"))
roles = json.load(open("data/derived/concentration/roles.json"))
link = {a.lower(): v["data"]["master"].lower() for a, v in roles["roles"].items() if v.get("role") == "subAccount"}
for m, sl in roles["subs"].items():
    for sub in (sl if isinstance(sl, list) else []):
        link.setdefault(sub["subAccountUser"].lower(), m.lower())
con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=2; SET TimeZone='UTC'")
con.execute("CREATE TABLE links (a VARCHAR, g VARCHAR)"); con.executemany("INSERT INTO links VALUES (?, ?)", list(link.items()))
FILES = [f"data/raw/xyz/fills/{d}.parquet" for d in WIN.ISO]
con.execute(f"""CREATE TABLE f AS SELECT strftime(timestamp, '%G-W%V') w, lower(address) a, (price*size)::DOUBLE usd
                FROM read_parquet({FILES}) WHERE coin = 'xyz:SP500' AND NOT crossed""")
ok = True
for key, grp in (("groups", "coalesce(l.g, f.a)"), ("addresses", "f.a")):
    rows = con.sql(f"""WITH x AS (SELECT w, {grp} k, sum(usd) usd FROM f LEFT JOIN links l ON l.a = f.a GROUP BY ALL),
                        r AS (SELECT *, usd / sum(usd) OVER (PARTITION BY w) s, row_number() OVER (PARTITION BY w ORDER BY usd DESC) rk FROM x)
                       SELECT w, sum(s) FILTER (WHERE rk <= 3) FROM r GROUP BY w ORDER BY w""").fetchall()
    want = dict(zip(R[key]["weeks"], R[key]["weekly_top3_share"]))
    bad = [(w, v, want.get(w)) for w, v in rows if want.get(w) is None or abs(v - want[w]) > 1e-12]
    ok &= not bad and len(rows) == len(want)
    print(f"{'OK  ' if not bad else 'FAIL'} {key}: weekly top-3 share, {len(rows)} weeks, mismatches {len(bad)} {bad[:3]}")
print("ALL OK" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)
