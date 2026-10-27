"""Independent recompute of analysis/monthly/monthly.py from the source tables in SQL: per month the US-trading-day
median of daily cash-hours depth (d10_net), taker volume per US trading day, fill share of displayed notional (from the
lifecycles directly, not daily.py's table), and the share of cancels re-placed in the same block. Cash hours and the
session clock come from scripts/window.py. Exit code 1 on a relative mismatch above 1e-9."""
import json, sys
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/monthly/monthly.json"))["months"]
con = duckdb.connect(); con.execute("SET memory_limit='3GB'; SET threads=4")
dm = con.sql("SELECT t, d10_net FROM 'data/derived/heatmap/depth_minutes_v2.parquet'").df()
dm = dm[WIN.session(dm.t) == "cash"]
con.register("dm", dm)
td = [d for d in WIN.DATES if d.weekday() < 5 and d.isoformat() not in WIN.NYSE_HOLIDAYS]
con.register("td", pd.DataFrame({"dy": [d.strftime("%Y%m%d") for d in td]}))
got = {}
for m, v in con.sql("""SELECT substr(dy, 1, 4) || '-' || substr(dy, 5, 2) m, median(dmed) FROM
        (SELECT strftime(t, '%Y%m%d') dy, median(d10_net) dmed FROM dm GROUP BY 1) JOIN td USING (dy) GROUP BY 1""").fetchall():
    got.setdefault(m, {})["depth_cash_usd"] = v
for m, v in con.sql("""SELECT substr(dy, 1, 4) || '-' || substr(dy, 5, 2) m, avg(usd) FROM
        (SELECT "day" dy, sum(q) usd FROM 'data/derived/impact/orders.parquet' GROUP BY 1) JOIN td USING (dy) GROUP BY 1""").fetchall():
    got[m]["taker_usd_per_weekday"] = v
for m, v in con.sql("""SELECT substr(regexp_extract(filename, '(\\d{8})', 1), 1, 4) || '-' || substr(regexp_extract(filename, '(\\d{8})', 1), 5, 2) m,
        sum(least(coalesce(filled_usd, 0), notional_usd)) / sum(notional_usd)
        FROM read_parquet('data/derived/lifecycle_touch/xyz_SP500/*.parquet', filename=true)
        WHERE class IN ('displayed_pulled','displayed_partial','filled') AND displayed_blocks > 0
          AND dist_bucket NOT IN ('unknown','0 placed before window') GROUP BY 1""").fetchall():
    got[m]["fill_share"] = v
for m, v in con.sql("""SELECT substr("day", 1, 4) || '-' || substr("day", 5, 2) m, avg((new_oid IS NOT NULL)::DOUBLE)
        FROM read_parquet('data/derived/cancels/amends_*.parquet') GROUP BY 1""").fetchall():
    got[m]["replaced_share"] = v
KEYS = {"depth_cash_usd", "taker_usd_per_weekday", "fill_share", "replaced_share"}
ok = set(got) == set(R) and all(set(got[m]) == KEYS for m in got)
if not ok:
    print("FAIL months or values missing:", sorted(set(R) ^ set(got)), {m: sorted(KEYS - set(got[m])) for m in got})
for m in sorted(set(R) & set(got)):
    for k, v in got[m].items():
        good = abs(v - R[m][k]) <= 1e-9 * max(1, abs(v)); ok &= good
        print(f"{'OK  ' if good else 'FAIL'} {m} {k:22s} recompute {v:.6g}  monthly.json {R[m][k]:.6g}")
print("ALL OK" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)
