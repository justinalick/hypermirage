"""Who supplies maker volume, week by week, xyz:SP500, every day of the run window (scripts/window.py).
Maker volume per account per ISO week from Reservoir fills (maker legs), with declared sub-accounts merged into their
master (data/derived/concentration/roles.json, as charts/concentration_cache.py). Groups are labeled G1, G2, ... by
pooled maker volume; no address is written. Writes data/derived/maker_rotation/rotation.json: weekly volume share and
rank of the leading groups, how many distinct groups reach the weekly top 3, and week-to-week rank stability."""
import json, os, sys
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN

O = "data/derived/maker_rotation"
os.makedirs(O, exist_ok=True)
FILES = [f"data/raw/xyz/fills/{d}.parquet" for d in WIN.ISO]
con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=2; SET TimeZone='UTC'")
con.execute(f"""CREATE TEMP TABLE mk AS
SELECT strftime(timestamp, '%G-W%V') AS w, lower(address) AS a, sum((price*size)::DOUBLE) AS usd
FROM read_parquet({FILES}) WHERE coin = 'xyz:SP500' AND NOT crossed GROUP BY ALL""")
roles = json.load(open("data/derived/concentration/roles.json"))
master = {a.lower(): v["data"]["master"].lower() for a, v in roles["roles"].items() if v.get("role") == "subAccount"}
for m, sl in roles["subs"].items():
    for sub in (sl if isinstance(sl, list) else []):
        master.setdefault(sub["subAccountUser"].lower(), m.lower())
con.execute("CREATE TEMP TABLE links (a VARCHAR, g VARCHAR)")
con.executemany("INSERT INTO links VALUES (?, ?)", list(master.items()))
wk = con.execute("""SELECT w, coalesce(l.g, mk.a) g, count(DISTINCT mk.a) n_addr, sum(usd) usd
                    FROM mk LEFT JOIN links l ON l.a = mk.a GROUP BY ALL""").df()
by_addr = con.execute("SELECT w, a g, sum(usd) usd FROM mk GROUP BY ALL").df()
del master


def summarize(t, label):
    pooled = t.groupby("g").usd.sum().sort_values(ascending=False)
    lab = {g: f"{label}{i + 1}" for i, g in enumerate(pooled.index)}
    t = t.assign(lab=t.g.map(lab))
    t["share"] = t.usd / t.groupby("w").usd.transform("sum")
    t["rank"] = t.groupby("w").usd.rank(ascending=False, method="first").astype(int)
    weeks = sorted(t.w.unique())
    top3 = t[t["rank"] <= 3]
    lead = sorted(set(top3.lab), key=lambda s: int(s[len(label):]))
    keep = sorted(set(lead) | {f"{label}{i}" for i in range(1, 9)}, key=lambda s: int(s[len(label):]))
    piv = t[t.lab.isin(keep)].pivot_table(index="w", columns="lab", values=["share", "rank"])
    # week-to-week Spearman correlation of the top-20 pooled groups' volumes
    v = t[t.lab.isin([f"{label}{i}" for i in range(1, 21)])].pivot_table(index="w", columns="lab", values="usd", fill_value=0)
    rk = v.rank(axis=1, ascending=False)
    rho = [float(np.corrcoef(rk.iloc[i], rk.iloc[i + 1])[0, 1]) for i in range(len(rk) - 1)]
    turnover = [len(set(top3[top3.w == weeks[i]].lab) - set(top3[top3.w == weeks[i - 1]].lab)) for i in range(1, len(weeks))]
    return {"weeks": weeks, "pooled_share": {lab[g]: float(s) for g, s in (pooled / pooled.sum()).head(20).items()},
            "n_groups": int(len(pooled)), "top3_groups_ever": lead,
            "weekly_share": {k: [None if np.isnan(x) else float(x) for x in piv["share"][k].reindex(weeks)] for k in keep},
            "weekly_rank": {k: [None if np.isnan(x) else int(x) for x in piv["rank"][k].reindex(weeks)] for k in keep},
            "weekly_top3_share": [float(t[(t.w == w) & (t["rank"] <= 3)].share.sum()) for w in weeks],
            "rank_rho_week_to_week": rho, "top3_new_entrants": turnover}


res = {"window": WIN.span(), "groups": summarize(wk, "G"), "addresses": summarize(by_addr, "A"),
       "addresses_per_group_top8": {}}
pooled = wk.groupby("g").usd.sum().sort_values(ascending=False)
for i, g in enumerate(pooled.index[:8]):
    res["addresses_per_group_top8"][f"G{i + 1}"] = int(wk[wk.g == g].n_addr.max())
json.dump(res, open(f"{O}/rotation.json", "w"), indent=1)
G = res["groups"]
print(len(G["weeks"]), "weeks;", G["n_groups"], "groups; top-3 groups ever:", G["top3_groups_ever"])
print("pooled share top 8:", {k: round(v, 3) for k, v in list(G["pooled_share"].items())[:8]})
print("addresses in top-8 groups:", res["addresses_per_group_top8"])
print("rank rho week to week: median", round(float(np.median(G["rank_rho_week_to_week"])), 2),
      "| new top-3 entrants per week: mean", round(float(np.mean(G["top3_new_entrants"])), 2))
