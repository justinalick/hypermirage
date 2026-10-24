"""Quoted spread and depth vs realized volatility, clock removed, in the @justinalick kit (night).
Data: data/derived/vol_spread/vol_spread_deciles.parquet (from vol_spread.py).
Run: .venv/bin/python charts/vol_spread.py"""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, duckdb, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter, FixedLocator, NullLocator
import justinalick as ja

S = "data/derived/vol_spread/"
dec = duckdb.sql(f"SELECT * FROM '{S}vol_spread_deciles.parquet' ORDER BY es, q").df()
p = lambda v: np.expm1(v) * 100
gap = {(es, k): p(g[k].iloc[-1] - g[k].iloc[0]) for es, g in dec.groupby("es") for k in ("sp", "dep")}
assert round(gap["open", "sp"], 1) == 18.9 and round(gap["open", "dep"], 1) == -1.2, gap
assert round(gap["closed", "sp"], 1) == 56.8 and round(gap["closed", "dep"], 1) == -19.2, gap
ROLE = {"open": "actual", "closed": "model"}
LB = 11.5

fig, _ax = ja.figure("wide", "night")
_ax.remove()
top, ph = 7 * ja.U + 52, 864 - 7 * ja.U - 52 - 64 - 76
L0, gp = 2 * ja.U + 72, 120
pw = (1536 - L0 - 2 * ja.U - gp) // 2
aL = ja._px_axes(fig, L0, top, pw, ph)
aR = ja._px_axes(fig, L0 + pw + gp, top, pw, ph)


def xfmt(ax):
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator([0.5, 1, 2]))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}x"))
    ax.set_xlim(0.28, 3)
    ax.set_xlabel("realized vol vs same day and hour, x", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}%" if v else "0%"))
    ja.zero(ax)


for ax, k in ((aL, "sp"), (aR, "dep")):
    for es in ("closed", "open"):
        x = dec[dec.es == es]
        rv = np.exp(x.rv)
        if es == "open":   # one band only (the key series), per house rules
            ja.gap(ax, rv, p(x[k + "_lo"]), p(x[k + "_hi"]), role=ROLE[es])
        ja.line(ax, rv, p(x[k]), ROLE[es], lw=3 if es == "open" else 2.5, marker="o", ms=5, zorder=3)
    xfmt(ax)

aL.set_ylim(-35, 25)
aR.set_ylim(-12, 18)
o = dec[dec.es == "open"]
ja.signal(aL, np.exp(o.rv.iloc[-1]), p(o.sp.iloc[-1]), ms=11)
ja.label_at(aL, 2.9, 19.5, f"futures open: {gap['open', 'sp']:+.0f}%", "actual", dy=0, ha="right", size=LB)
ja.label_at(aL, 0.3, -33, "futures closed: noisy", "model", dy=0, ha="left", size=LB)
ja.panel_title(aL, "quoted spread, time-weighted", size=LB)
aL.set_ylabel("spread vs same day and hour, %", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

ja.label_at(aR, 2.9, 4.5, f"futures open: {gap['open', 'dep']:+.0f}%", "actual", dy=0, ha="right", size=LB)
ja.label_at(aR, 0.3, -9.5, "futures closed: noisy", "model", dy=0, ha="left", size=LB)
ja.panel_title(aR, "depth within 10 bps of mid", size=LB)
aR.set_ylabel("depth vs same day and hour, %", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

ja.finish(fig, f"Volatile minutes widen the spread {gap['open', 'sp']:+.0f}%; depth holds",
          hl=f"{gap['open', 'sp']:+.0f}%",
          subtitle="xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, 20,122 one-minute snapshots",
          source="Data: Hydromancer Reservoir / node data. Labels: top vs bottom vol decile. Band: 90% bootstrap over days.")
ja.save(fig, "out/vol_spread.png")
