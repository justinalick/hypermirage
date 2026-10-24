"""Depth vs realized volatility, across hours and within a day, in the @justinalick kit (night).
Data: data/derived/depth_vol/hourly2.parquet and deciles2.parquet (same inputs as depth_vol/chart2.py,
which produced depth_vs_vol_v2.png)."""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, duckdb, matplotlib; matplotlib.use("Agg")
from matplotlib.colors import to_rgb, to_hex
from matplotlib.ticker import FuncFormatter, FixedLocator, NullLocator
import justinalick as ja

S = "data/derived/depth_vol/"
dec = duckdb.sql(f"SELECT * FROM '{S}deciles2.parquet'").df()
hr = duckdb.sql(f"SELECT * FROM '{S}hourly2.parquet'").df()
h = hr[hr.rv > 0]
rho = np.corrcoef(np.log(h.rv), np.log(h.d10))[0, 1]
p = lambda v: (np.exp(v) - 1) * 100
gap = {k: p(g.sort_values("q").rel.iloc[-1] - g.sort_values("q").rel.iloc[0]) for k, g in dec.groupby("k")}
assert round(rho, 2) == 0.63 and len(h) == 336 and round(gap["cash"], 1) == -3.8 and round(gap["overnight"], 1) == 4.8, (rho, gap)
ROLE = {"cash": "actual", "overnight": "model", "closed": "faint"}
LB = 11.5


def mix(c, a):
    c, g = np.array(to_rgb(ja.C[c])), np.array(to_rgb(ja.C["ground"]))
    return to_hex(g + a * (c - g))


fig, _ax = ja.figure("wide", "night")
_ax.remove()
top, ph = 7 * ja.U + 52, 864 - 7 * ja.U - 52 - 64 - 76
L0, gp = 2 * ja.U + 72, 120
pw = (1536 - L0 - 2 * ja.U - gp) // 2
aL = ja._px_axes(fig, L0, top, pw, ph)
aR = ja._px_axes(fig, L0 + pw + gp, top, pw, ph)


def xfmt(ax, lo):
    ax.set_xscale("log"); ax.xaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 40]))
    ax.xaxis.set_minor_locator(NullLocator()); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}%"))
    ax.set_xlim(lo, 45)
    ax.set_xlabel("realized vol, trailing 15 min, annualized", color=ja.C["muted"], family=ja.MONO, fontsize=LB)


# left: across hours
for g in ["closed", "overnight", "cash"]:
    x = h[h.g == g]
    aL.scatter(x.rv, x.d10 / 1e6, s=30, color=ja.C[ROLE[g]], edgecolor=ja.C["ground"], lw=0.8, zorder=3)
b = np.polyfit(np.log(h.rv), np.log(h.d10), 1); xx = np.geomspace(0.8, 45, 50)
aL.plot(xx, np.exp(np.polyval(b, np.log(xx))) / 1e6, color=ja.C["muted"], lw=1.6, ls=(0, (5, 4)), zorder=4)
xfmt(aL, 0.6)
aL.set_yscale("log"); aL.yaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 40])); aL.yaxis.set_minor_locator(NullLocator())
aL.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}M")); aL.set_ylim(0.8, 50)
ja.label_at(aL, 0.65, 33, f"all hours: rho {rho:+.2f}", "muted", dy=0, ha="left", size=LB)
ja.label_at(aL, 24, 7.2, "US cash hours", "actual", dy=0, ha="center", size=LB)
ja.label_at(aL, 2.6, 21, "overnight, futures open", "model", dy=0, ha="center", size=LB)
ja.label_at(aL, 1.0, 1.25, "futures closed (weekend, daily break)", "faint", dy=0, ha="left", size=LB)
ja.panel_title(aL, "across hours, hourly medians", size=LB)
aL.set_ylabel("depth within 10 bps, log scale", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

# right: within a day
aR.axhline(0, color=ja.C["faint"], lw=1, zorder=2)
for k, role, ls in [("W1009", "faint", (0, (4, 3))), ("W1016", "faint", "-"), ("overnight", "model", "-"), ("cash", "actual", "-")]:
    x = dec[dec.k == k].sort_values("q")
    if x.lo.notna().any():
        aR.fill_between(x.rv, p(x.lo), p(x.hi), color=ja.C[f"tint_{role}"] if role != "faint" else ja.C["panel"], lw=0, zorder=1)
    ja.line(aR, x.rv, p(x.rel), role, lw=3 if k == "cash" else 2.5, ls=ls, marker="o", ms=5, zorder=3)
xfmt(aR, 0.45); aR.set_ylim(-22, 38)
aR.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}%" if v else "0%"))
c = dec[dec.k == "cash"].sort_values("q")
ja.signal(aR, c.rv.iloc[-1], p(c.rel.iloc[-1]), ms=0)
ja.label_at(aR, 42, -9.5, f"cash: {gap['cash']:+.1f}%", "actual", dy=0, ha="right", size=LB)
ja.label_at(aR, 14, 9.5, f"overnight: {gap['overnight']:+.1f}%", "model", dy=0, ha="center", size=LB)
ja.label_at(aR, 1.45, 33, "weekend Oct 16 to 18", "faint", dy=0, ha="left", size=LB)
ja.label_at(aR, 0.5, -18, "weekend Oct 9 to 11 (dashed)", "faint", dy=0, ha="left", size=LB)
ja.note_at(aR, 13, 27, "the two weekends disagree:\none dropped, one did not", "ink", size=11)
ja.panel_title(aR, "within a day", size=LB)
aR.set_ylabel("depth vs same day and hour, %", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

ja.finish(fig, f"Volatile minutes keep their depth: {gap['cash']:+.1f}% in cash hours",
          hl=f"{gap['cash']:+.1f}%",
          subtitle="xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, 20,160 one-minute snapshots",
          source="Data: Hydromancer Reservoir / node data. Right: top vs bottom vol decile by session. Bands: 90% bootstrap.")
ja.save(fig, "out/depth_vol.png")
