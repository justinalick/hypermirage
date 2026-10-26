"""Month by month, xyz:SP500, every day of the run window: the book (depth within 10 bps and quoted spread in US cash
hours), taker volume, top-3 maker share (by address and with declared sub-accounts merged), share of displayed notional
filled, taker markout 1 min after the fill, share of orders cancelled within 1 s by distance from the touch
(Kaplan-Meier, as charts/survival_cache.py), and cancel-replace behavior. Inputs are the existing per-day outputs plus
data/derived/monthly/ (analysis/monthly/daily.py). Writes data/derived/monthly/monthly.json with a daily table and
monthly values; pooled over the window, the survival shares must match data/derived/chart_cache/survival.json."""
import json, sys
import numpy as np, pandas as pd, duckdb
sys.path.insert(0, "scripts")
import window as WIN

D = "data/derived"
O = f"{D}/monthly"
con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=2")
day = lambda t: pd.to_datetime(t).dt.strftime("%Y%m%d")
mon = lambda d: pd.Series(d).str[:4] + "-" + pd.Series(d).str[4:6]

# book: cash-hours medians per day
dm = pd.read_parquet(f"{D}/heatmap/depth_minutes_v2.parquet", columns=["t", "d10_net"])
dm["sess"] = WIN.session(dm.t)
sm = pd.read_parquet(f"{D}/vol_spread/spread_minutes.parquet", columns=["t", "tw_spread_bps"])
sm["sess"] = WIN.session(sm.t)
daily = pd.DataFrame({"day": WIN.DAYS}).set_index("day")
daily["depth_cash"] = dm[dm.sess == "cash"].groupby(day(dm.t[dm.sess == "cash"])).d10_net.median()
daily["depth_closed"] = dm[dm.sess == "closed"].groupby(day(dm.t[dm.sess == "closed"])).d10_net.median()
daily["spread_cash"] = sm[sm.sess == "cash"].groupby(day(sm.t[sm.sess == "cash"])).tw_spread_bps.median()
del dm, sm

# takers: volume and 1-min markout against the fill price (notional-weighted), liquidations excluded for markouts
o = pd.read_parquet(f"{D}/impact/orders.parquet", columns=["q", "sz", "s", "m0", "i60", "liq", "day", "sig_d_bps"])
daily["taker_usd"] = o.groupby("day").q.sum()
daily["vol_d_bps"] = o.groupby("day").sig_d_bps.first()          # daily vol of 1-min mid returns (analysis/impact/build.py)
o = o[~o.liq].dropna(subset=["i60", "m0"])
o["mk60"] = o.i60 - o.s * (o.q / o.sz - o.m0) / o.m0 * 1e4        # mid 1 min after vs fill price, bps
daily["mk60"] = (o.mk60 * o.q).groupby(o.day).sum() / o.q.groupby(o.day).sum()
sm_ = o[o.q < 1e4]
daily["mk60_lt10k"] = (sm_.mk60 * sm_.q).groupby(sm_.day).sum() / sm_.q.groupby(sm_.day).sum()
del o, sm_

# makers
c = json.load(open(f"{D}/chart_cache/concentration.json"))
cd = pd.DataFrame(c["daily"]); cd["day"] = cd.d.str.replace("-", ""); cd = cd.set_index("day")
daily["top3"] = cd.r1 + cd.r23
daily["top3_merged"] = pd.Series(c["group_top3"], index=cd.index)
daily["makers"] = cd.makers
daily["maker_usd"] = cd.vol

# fills and cancels
f = con.sql(f"SELECT * FROM '{O}/fill.parquet'").df().set_index("day")
daily["placed_usd"], daily["filled_usd"] = f.placed_usd, f.filled_usd
am = con.sql(f"SELECT * FROM '{O}/am.parquet'").df()
k = am.groupby(["day", "kind"]).n.sum().unstack(fill_value=0)
daily["cancels"] = k.sum(1); daily["replaced"] = k.sum(1) - k.get("pure cancel", 0)
daily["wd"] = [pd.Timestamp(d).weekday() < 5 and pd.Timestamp(d).date().isoformat() not in WIN.NYSE_HOLIDAYS
               for d in daily.index]                       # US trading days: the cash-hours medians use only these
daily["month"] = mon(daily.index.to_numpy()).values

km = con.sql(f"SELECT * FROM '{O}/km.parquet'").df(); kn = con.sql(f"SELECT * FROM '{O}/kn.parquet'").df()
def km_1s(days):
    out = {}
    for b in "abcd":
        r = km[(km.b == b) & km.day.isin(days)].groupby("t")[["ev", "w"]].sum().sort_index()
        n = kn[(kn.b == b) & kn.day.isin(days)].n.sum()
        at = n - r.w.cumsum().shift(fill_value=0)
        out[b] = float(1 - np.prod(1 - r.ev / at))
    return out
def ticks_median(days):
    t = am[am.day.isin(days) & am.dir.notna()].groupby("ticks").n.sum().sort_index()
    cs = t.cumsum(); return float(t.index[np.searchsorted(cs.values, cs.values[-1] / 2)])

pooled = km_1s(WIN.DAYS)
ref = json.load(open(f"{D}/chart_cache/survival.json"))["curves"]
for b in "abcd":
    assert abs(pooled[b] - ref[b]["cancel_1s"]) < 1e-9, (b, pooled[b], ref[b]["cancel_1s"])

M = {}
for m, g in daily.groupby("month"):
    days = list(g.index); wd = g[g.wd]
    M[m] = {"days": len(g), "weekdays": int(len(wd)),
            "depth_cash_usd": float(wd.depth_cash.median()), "depth_closed_usd": float(g.depth_closed.median()),
            "spread_cash_bps": float(wd.spread_cash.median()),
            "taker_usd_per_weekday": float(wd.taker_usd.mean()),
            "top3_median": float(g.top3.median()), "top3_merged_median": float(g.top3_merged.median()),
            "makers_median": float(g.makers.median()),
            "fill_share": float(g.filled_usd.sum() / g.placed_usd.sum()),
            "replaced_share": float(g.replaced.sum() / g.cancels.sum()), "amend_ticks_median": ticks_median(days),
            "mk60_bps": float((g.mk60 * g.taker_usd).sum() / g.taker_usd.sum()),
            "mk60_lt10k_bps": float(g.mk60_lt10k.mean()),
            "cancel_1s": km_1s(days)}
res = {"window": WIN.span(), "pooled_cancel_1s": pooled, "months": M,
       "daily": daily.reset_index().replace({np.nan: None}).to_dict(orient="list")}
json.dump(res, open(f"{O}/monthly.json", "w"), indent=1)
cols = ["days", "depth_cash_usd", "spread_cash_bps", "taker_usd_per_weekday", "top3_median", "top3_merged_median",
        "fill_share", "mk60_bps", "replaced_share", "amend_ticks_median"]
t = pd.DataFrame({m: {c_: v[c_] for c_ in cols} for m, v in M.items()}).T
t["cancel_1s_touch"] = [v["cancel_1s"]["a"] for v in M.values()]; t["cancel_1s_far"] = [v["cancel_1s"]["d"] for v in M.values()]
print(t.round(4).to_string())
print("pooled KM at 1 s matches survival.json:", {b: round(v, 4) for b, v in pooled.items()})
