"""xyz:SP500 quoting behavior month by month, @justinalick night. Reads data/derived/monthly/monthly.json
(analysis/monthly/monthly.py): cancel-replace share and price-amend size by month, and cancels per day against
that day's volatility."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/monthly/monthly.json"))
d = pd.DataFrame(R["daily"]); d["t"] = pd.to_datetime(d.day)
M = pd.DataFrame(R["months"]).T
M["t"] = d.groupby(d.month).t.mean().reindex(M.index).values
full = (M.days >= 28).values
LB = 11
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)
fig, ax0 = ja.figure("wide", "night"); ax0.remove()
a = ja._px_axes(fig, 110, 250, 380, 450)
b = ja._px_axes(fig, 590, 250, 380, 450)
c = ja._px_axes(fig, 1080, 250, 410, 450)


def monthly(ax, col, role, fmt, title):
    y = M[col].astype(float).values
    ax.plot(M.t, y, color=ja.C[role], lw=2.5, zorder=3)
    ax.plot(M.t[full], y[full], "o", ms=7, color=ja.C[role], zorder=4)
    ax.plot(M.t[~full], y[~full], "o", ms=7, mfc=ja.C["ground"], mec=ja.C[role], mew=2, zorder=4)
    ax.xaxis.set_major_locator(mdates.MonthLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_xlim(pd.Timestamp(WIN.ISO[0]) - pd.Timedelta(days=4), pd.Timestamp(WIN.ISO[-1]) + pd.Timedelta(days=4))
    ax.yaxis.set_major_formatter(FuncFormatter(fmt)); ja.panel_title(ax, title, size=LB)


monthly(a, "replaced_share", "actual", lambda v, _: f"{v:.0%}", "cancels re-placed in the same block")
a.set_ylim(0, 0.8)
monthly(b, "amend_ticks_median", "model", lambda v, _: f"{v:.0f}", "median price amend, ticks")
b.set_ylim(0, max(M.amend_ticks_median.astype(float)) + 2)
months = list(M.index); cmap = matplotlib.colormaps["viridis"]
for i, m in enumerate(months):
    g = d[(d.month == m) & d.wd]
    c.scatter(g.vol_d_bps.astype(float), g.cancels.astype(float), s=18, color=cmap(i / max(len(months) - 1, 1)), lw=0, alpha=0.85,
              label=pd.Timestamp(f"{m}-01").strftime("%b"))
c.set_xscale("log"); c.set_yscale("log")
c.set_xticks([30, 40, 60, 100, 150]); c.set_yticks([1e6, 2e6, 3e6, 4e6])
c.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}")); c.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1e6:g}M"))
c.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); c.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
leg = c.legend(loc="lower right", frameon=False, fontsize=9.5, ncol=2, handletextpad=0.2, columnspacing=0.8)
for t_ in leg.get_texts(): t_.set_color(ja.C["muted"]); t_.set_family(ja.MONO)
ja.panel_title(c, "cancels per day vs that day's vol", size=LB)
c.set_xlabel("daily vol of 1-min mid returns, bps", **AX)
w = d[d.wd]
rho = np.corrcoef(np.log(w.vol_d_bps.astype(float)), np.log(w.cancels.astype(float)))[0, 1]
ja.label_at(c, c.get_xlim()[0] * 1.08, c.get_ylim()[1] / 1.25, f"US trading days, rho {rho:+.2f} (logs)", "ink", dy=0, ha="left", size=10).set_bbox(None)
ja.finish(fig, "In summer, fewer cancels re-placed, larger price amends", hl="larger",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {int(d.cancels.sum()) / 1e6:.0f}M cancels, month by month",
          source="Data: Hydromancer Reservoir / node data. Hollow: partial months. 1 tick = 0.1 index points.")
ja.save(fig, "out/quotes_monthly.png")
