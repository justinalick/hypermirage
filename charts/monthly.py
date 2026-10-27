"""xyz:SP500 month by month, @justinalick night. Reads data/derived/monthly/monthly.json (analysis/monthly/monthly.py).
Dots: days (US trading days for the cash-hours panels); line: the month; hollow markers: partial months."""
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
M["t"] = d.groupby(d.month).t.mean().reindex(M.index).values   # middle of the days covered
full = M.days >= 28
LB = 11
fig, ax0 = ja.figure("wide_tall", "night"); ax0.remove()
X, Yr, W, Hh = [110, 610, 1110], [250, 800], 400, 420
P = [ja._px_axes(fig, X[c], Yr[r], W, Hh) for r in range(2) for c in range(3)]


def panel(ax, title, dots, mvals, role="actual", fmt=None, zero=False, dots_wd=True):
    if dots is not None:
        dd = d[d.wd] if dots_wd else d
        ax.scatter(dd.t, dd[dots], s=7, color=ja.C["faint"], alpha=0.5, lw=0, zorder=1)
    y = M[mvals].astype(float)
    ax.plot(M.t, y, color=ja.C[role], lw=2.5, zorder=3)
    ax.plot(M.t[full], y[full], "o", ms=7, color=ja.C[role], zorder=4)
    ax.plot(M.t[~full], y[~full], "o", ms=7, mfc=ja.C["ground"], mec=ja.C[role], mew=2, zorder=4)
    if zero: ja.zero(ax)
    ax.set_xticks(list(M.t), [("\n" if i == 0 and len(M) > 1 and (M.t.iloc[1] - t).days < 25 else "") + t.strftime("%b") for i, t in enumerate(M.t)])   # a tick under each monthly point
    ax.set_xlim(pd.Timestamp(WIN.ISO[0]) - pd.Timedelta(days=3), pd.Timestamp(WIN.ISO[-1]) + pd.Timedelta(days=3))
    if fmt: ax.yaxis.set_major_formatter(FuncFormatter(fmt))
    ja.panel_title(ax, title, size=LB)


panel(P[0], "depth within 10 bps, US cash hours", "depth_cash", "depth_cash_usd", fmt=lambda v, _: f"${v / 1e6:.0f}M")
P[0].set_ylim(0, None); P[0].set_yticks(np.arange(0, 2.6e7, 5e6))
panel(P[1], "quoted spread, US cash hours, bps", "spread_cash", "spread_cash_bps", role="model", fmt=lambda v, _: f"{v:.2f}")
d["taker_m"] = d.taker_usd
panel(P[2], "taker volume per US trading day", "taker_usd", "taker_usd_per_weekday", fmt=lambda v, _: f"${v / 1e6:.0f}M")
P[2].set_ylim(0, None)
panel(P[3], "top-3 maker share of maker volume, %", "top3", "top3_median", fmt=lambda v, _: f"{v:.0%}", dots_wd=False)
y = M.top3_merged_median.astype(float)
P[3].plot(M.t, y, color=ja.C["model"], lw=2, ls=(0, (4, 3)), zorder=3)
ja.label_at(P[3], M.t.iloc[-1], y.iloc[-1], "sub-accounts merged", "model", dy=22, ha="right", size=10)
ja.label_at(P[3], M.t.iloc[3], float(M.top3_median.iloc[3]), "by address", "actual", dy=-18, ha="center", size=10)
for b, role, lab, yl in (("a", "actual", "at or inside the touch", 0.93), ("b", "model", "up to 1 bp behind", 0.86),
                         ("d", "faint", "more than 5 bps away", 0.12)):
    y = np.array([M.cancel_1s.iloc[i][b] for i in range(len(M))])
    P[4].plot(M.t, y, color=ja.C[role], lw=2.5, zorder=3)
    P[4].plot(M.t[full], y[full.values], "o", ms=6, color=ja.C[role], zorder=4)
    P[4].plot(M.t[~full], y[~full.values], "o", ms=6, mfc=ja.C["ground"], mec=ja.C[role], mew=2, zorder=4)
    t_ = ja.label_at(P[4], M.t.iloc[0], yl, lab, role, dy=0, ha="left", size=9.5); t_.set_bbox(None)
P[4].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}")); P[4].set_ylim(0, 1)
P[4].set_xticks(list(M.t), [("\n" if i == 0 and len(M) > 1 and (M.t.iloc[1] - t).days < 25 else "") + t.strftime("%b") for i, t in enumerate(M.t)])
P[4].set_xlim(P[0].get_xlim())
ja.panel_title(P[4], "orders cancelled within 1 s, %", size=LB)
panel(P[5], "taker markout at 1 min, bps", "mk60", "mk60_bps", role="actual", fmt=lambda v, _: f"{v:+.2f}" if v else "0",
      zero=True, dots_wd=False)
lo, hi = np.nanpercentile(d.mk60.astype(float), [2, 98]); P[5].set_ylim(lo, hi); P[5].yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.25))
P[5].text(0.02, 0.98, "per order, + = taker gains", transform=P[5].transAxes, ha="left", va="top", color=ja.C["muted"], family=ja.MONO, fontsize=10)

j, ju = M.depth_cash_usd.astype(float), M.index
peak = ju[int(np.argmax(j))]; low = ju[int(np.argmin(j[full.values] if full.any() else j))]
g = float(M.depth_cash_usd.loc["2026-07"] / M.depth_cash_usd.loc["2026-05"])
ja.finish(fig, f"Cash-hours depth grew {g:.1f}x from May to July, then eased", hl=f"{g:.1f}x",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, month by month",
          source="Data: Hydromancer Reservoir / node data. Lines: months, dots: days, hollow: partial. Merged: sub-accounts declared today.")
ja.save(fig, "out/monthly.png")
