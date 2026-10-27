"""Quoted spread and depth vs realized volatility, clock removed, in the @justinalick kit (night).
Data: data/derived/vol_spread/vol_spread_deciles.parquet (from vol_spread.py).
Run: .venv/bin/python charts/vol_spread.py"""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, duckdb, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter, FixedLocator, NullLocator
import json
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

S = "data/derived/vol_spread/"
dec = duckdb.sql(f"SELECT * FROM '{S}vol_spread_deciles.parquet' ORDER BY es, q").df()
META = json.load(open(f"{S}vol_spread_meta.json"))
p = lambda v: np.expm1(v) * 100
gap = {(es, k): p(g[k].iloc[-1] - g[k].iloc[0]) for es, g in dec.groupby("es") for k in ("sp", "dep")}
WIN.expect("vol_spread gaps %: open sp, open dep, closed sp, closed dep",
           [round(gap["open", "sp"], 1), round(gap["open", "dep"], 1), round(gap["closed", "sp"], 1), round(gap["closed", "dep"], 1)],
           [18.9, -1.2, 56.8, -19.1])
ROLE = {"open": "actual", "closed": "muted"}   # closed in gray, as in the depth vs volatility chart
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
    xr = np.exp(dec.rv)                                            # every decile of both series stays on the panel
    ax.set_xlim(min(0.28, xr.min() / 1.12), max(3, xr.max() * 1.12))
    ax.set_xlabel("realized vol vs its hour and day, x", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
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

# drawn: both lines, and the band of the futures-open series only
lim = lambda k, lo, hi: ja.fit(lo, hi, np.r_[p(dec[k]), p(dec[dec.es == "open"][k + "_lo"]), p(dec[dec.es == "open"][k + "_hi"])], 3)
aL.set_ylim(*lim("sp", -35, 25))
aR.set_ylim(*lim("dep", -12, 18))
o = dec[dec.es == "open"]
ja.signal(aL, np.exp(o.rv.iloc[-1]), p(o.sp.iloc[-1]), ms=0)
ja.label_at(aL, 2.9, 19.5 if WIN.IS_ATLAS else -12, f"futures open: {gap['open', 'sp']:+.0f}%", "actual", dy=0, ha="right", size=LB)
ja.label_at(aL, 0.3, aL.get_ylim()[0] + 2, "futures closed: noisy" if WIN.IS_ATLAS else f"futures closed or break: {gap['closed', 'sp']:+.0f}%",
            "muted", dy=0, ha="left", size=LB)
ja.panel_title(aL, "quoted spread, time-weighted", size=LB)
aL.set_ylabel("spread vs its hour and day, %", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

ja.label_at(aR, 2.9, 4.5, f"futures open: {gap['open', 'dep']:+.0f}%" if WIN.IS_ATLAS else f"futures open: {gap['open', 'dep']:+.1f}%", "actual", dy=0, ha="right", size=LB)
ja.label_at(aR, 0.3, aR.get_ylim()[0] + 2.5, "futures closed: noisy" if WIN.IS_ATLAS else f"futures closed or break: {gap['closed', 'dep']:+.0f}%",
            "muted", dy=0, ha="left", size=LB)
ja.panel_title(aR, "depth within 10 bps of mid", size=LB)
aR.set_ylabel("depth vs its hour and day, %", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

holds = "depth holds" if abs(gap["open", "dep"]) < 5 else f"depth {gap['open', 'dep']:+.0f}%"
ja.finish(fig, f"Volatile minutes widen the spread {gap['open', 'sp']:+.0f}%; {holds}",
          hl=f"{gap['open', 'sp']:+.0f}%",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {META['n_minutes']:,} one-minute snapshots",
          source="Data: Hydromancer Reservoir / node data. Labels: top vs bottom vol decile. Band: 90% bootstrap over days.")
ja.save(fig, "out/vol_spread.png")
