"""Print the atlas headline numbers from whatever outputs exist under data/derived.
Each line shows the value recomputed here next to the value printed in the atlas."""
import json, os
import duckdb

D = "data/derived"
rows = []

def check(section, label, atlas, fn):
    try:
        got = fn()
    except FileNotFoundError:
        got = "(not built)"
    except Exception as e:  # missing column or table: report, keep going
        got = f"(error: {type(e).__name__})"
    rows.append((section, label, atlas, got))

def j(p): return json.load(open(f"{D}/{p}"))

def survival():
    c = j("chart_cache/survival.json")["curves"]
    return " / ".join(f"{100 * c[b]['cancel_1s']:.0f}%" for b in "abd") + f", {j('chart_cache/survival.json')['meta']['n'] / 1e6:.1f}M orders"
check("survival", "cancelled within 1s: at touch / <=1 bp / >5 bps", "65% / 72% / 26%, 26.0M orders", survival)

check("concentration", "top-3 maker share, pooled / declared sub-accounts merged", "36.0% / 36.1%",
      lambda: f"{100 * j('chart_cache/concentration.json')['pooled_top3']:.1f}% / {100 * j('chart_cache/concentration.json')['pooled_group_top3']:.1f}%")

def markouts():
    r = j("markout/rerun/markout_res.json")["all"]
    return f"{r['0'][0]:+.2f} bps at 0s, {r['120'][0]:+.2f} at 2m, {r['300'][0]:+.2f} at 5m"
check("markouts", "pooled taker markout", "about -0.37 at 0s, about +0.17 at 2 to 5 min", markouts)

def cancels():
    if not os.path.exists(f"{D}/cancels/rates.parquet"): raise FileNotFoundError
    f, p = duckdb.sql(f"SELECT sum(filled_usd), sum(placed_usd) FROM '{D}/cancels/rates.parquet'").fetchall()[0]
    return f"{100 * f / p:.2f}% of ${p / 1e12:.2f}T"
check("cancels", "share of displayed notional ever filled", "0.28% of $1.08T", cancels)

def queue():
    k = j("queue/km.json")["km"]
    return " / ".join(f"{v[3]:.1f}%" for _, v in sorted(k.items()))
check("queue", "KM fill probability at 5s, improve .. >$250k ahead", "35.7 / 21.7 / 14.3 / 11.2 / 7.4 / 5.2", queue)

def funding():
    r = json.load(open("data/checks/funding/recompute.json"))
    return (f"{r['es_open_median']:+.2f} bps ES open, {r['es_closed_median']:+.2f} closed, "
            f"{100 * r['share_neg']:.0f}% negative, long {-r['cum_long_funding_pct']:+.2f}%")
check("funding", "premium and funding (checks/funding/recompute.py)", "-3.2 bps ES open, -0.05 closed, 78% negative, long +0.67%", funding)

w = max(len(r[0]) for r in rows)
for s, l, a, g in rows:
    print(f"{s:<{w}}  {l}\n{'':<{w}}    atlas: {a}\n{'':<{w}}    here:  {g}")
