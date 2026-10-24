"""Quoted spread and depth vs realized volatility, xyz:SP500, 2026-10-08..21, controlling for the clock.

Inputs: data/derived/offhours/offhours_depth_minutes.parquet (mid, d10 per minute, replayed book) and
data/derived/vol_spread/spread_minutes.parquet (time-weighted quoted spread per minute).
Every series (vol, spread, depth) is taken relative to the median for the same UTC hour of day
(weekend hours separate) and then to the median for the same day (each weekend is one day), in logs.
Minutes are split by whether CME index futures are open (cash + overnight) or closed (weekend +
Mon-Thu 21:00 hour), and binned into deciles of relative vol within each group.
Writes vol_spread_deciles.parquet and prints top vs bottom decile gaps with day-bootstrap 90% CIs.
"""
import numpy as np, pandas as pd, duckdb

R = "data/derived/"
OUT = R + "vol_spread/"
m = duckdb.sql(f"""SELECT d.t, d.mid, d.d10, s.tw_spread_bps sp
    FROM '{R}offhours/offhours_depth_minutes.parquet' d
    LEFT JOIN '{R}vol_spread/spread_minutes.parquet' s USING (t) ORDER BY d.t""").df()
m["r"] = np.log(m.mid).diff() * 1e4
m["rv"] = m.r.rolling(15, min_periods=12).std() * np.sqrt(365 * 1440) / 100
dow, h = m.t.dt.day_of_week, m.t.dt.hour
wk = ((dow == 4) & (h >= 21)) | (dow == 5) | ((dow == 6) & (h < 22))
m["es"] = np.where(wk | ((dow < 4) & (h == 21)), "closed", "open")
m["hod"] = h.astype(str) + np.where(wk, "w", "d")
fri = m.t - pd.to_timedelta((dow - 4) % 7, unit="D")
m["day"] = np.where(wk, "W" + fri.dt.strftime("%m%d"), m.t.dt.strftime("%m%d"))
m = m.dropna(subset=["rv", "sp"])
m = m[m.rv > 0].copy()
for c in ["rv", "sp", "d10"]:
    lx = np.log(m[c])
    x = lx - lx.groupby(m.hod).transform("median")
    m[c + "_rel"] = x - x.groupby([m.es, m.day]).transform("median")

rng = np.random.default_rng(7)
pct = lambda v: np.expm1(v) * 100
rows, got = [], {}
for es, g in m.groupby("es"):
    g = g.assign(q=pd.qcut(g.rv_rel.rank(method="first"), 10, labels=False).values)
    days = g.day.unique()
    base = g.groupby("q").agg(rv=("rv_rel", "median"), sp=("sp_rel", "median"), dep=("d10_rel", "median"))
    boots = {k: [] for k in ["sp", "dep"]}
    for _ in range(1000):
        s = pd.concat([g[g.day == d] for d in rng.choice(days, len(days))])
        b = s.groupby("q").agg(sp=("sp_rel", "median"), dep=("d10_rel", "median"))
        for k in boots:
            boots[k].append(b[k])
    for k in ["sp", "dep"]:
        B = pd.concat(boots[k], axis=1)
        base[k + "_lo"], base[k + "_hi"] = B.quantile(0.05, axis=1), B.quantile(0.95, axis=1)
        gap = pct(B.loc[9] - B.loc[0])
        print(f"{es:6s} {k:3s} n={len(g)} days={len(days)} top vs bottom vol decile "
              f"{pct(base[k][9] - base[k][0]):+.1f}% (90% CI {gap.quantile(.05):+.1f} to {gap.quantile(.95):+.1f}); "
              f"vol ratio top/bottom {np.exp(base.rv[9] - base.rv[0]):.1f}x")
        got[es, k] = (pct(base[k][9] - base[k][0]), gap.quantile(.05), gap.quantile(.95))
    base["es"] = es
    rows.append(base.reset_index())
pd.concat(rows).to_parquet(OUT + "vol_spread_deciles.parquet")
# published values: gap and 90% CI, top vs bottom volatility decile (atlas and README)
want = {("open", "sp"): (18.9, 14.7, 24.1), ("open", "dep"): (-1.2, -4.9, 2.4),
        ("closed", "sp"): (56.8, 10.5, 135.2), ("closed", "dep"): (-19.2, -29.4, -3.0)}
bad = {k: tuple(round(v, 1) for v in got[k]) for k in want if any(abs(a - b) > 0.15 for a, b in zip(got[k], want[k]))}
assert not bad, f"published gaps or CIs not reproduced: {bad}"
print("published gaps and 90% CIs reproduced")
print("minute-level corr (rel): ", {es: (round(np.corrcoef(g.rv_rel, g.sp_rel)[0, 1], 3),
      round(np.corrcoef(g.rv_rel, g.d10_rel)[0, 1], 3)) for es, g in m.groupby("es")})
print("raw medians:", m.groupby("es").agg(sp=("sp", "median"), d10=("d10", "median"), rv=("rv", "median"), n=("rv", "size")).round(3).to_dict())
