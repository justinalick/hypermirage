"""Daily maker concentration by account rank, in the @justinalick kit (night).
Data: cache/concentration.json, written by concentration_cache.py (same queries as
analysis/concentration_chart.py; no addresses stored)."""
import json, sys, datetime as dt, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

D = json.load(open("data/derived/chart_cache/concentration.json"))
days = D["daily"]
r1 = np.array([100 * d["r1"] for d in days]); r23 = np.array([100 * d["r23"] for d in days])
r410 = np.array([100 * d["r410"] for d in days]); top3 = r1 + r23
g3 = np.array([100 * v for v in D["group_top3"]])
P, PG = 100 * D["pooled_top3"], 100 * D["pooled_group_top3"]
WIN.expect("concentration: daily top-3 min/max, pooled, merged", [round(top3.min()), round(top3.max()), round(P, 1), round(PG, 1)],
           [34, 46, 36.0, 36.1])
x = np.arange(len(days)); LB = 11.5
if len(days) > 21:      # long windows: a daily series instead of one labeled bar per day
    import pandas as pd
    import matplotlib.dates as md
    t = pd.to_datetime([d["d"] for d in days])
    lo, hi = np.percentile(top3, [10, 90])
    fig, _ax = ja.figure("wide", "night")
    matplotlib.rcParams["text.parse_math"] = False
    _ax.remove()
    ax = ja._px_axes(fig, 2 * ja.U + 64, 7 * ja.U + 52, 1536 - 2 * ja.U - 64 - 2 * ja.U, 864 - 7 * ja.U - 52 - 64 - 136)
    kw = dict(width=1.0, linewidth=0, zorder=2, align="center")
    ax.bar(t, r1, color=ja.C["actual"], **kw)
    ax.bar(t, r23, bottom=r1, color=ja.C["faint"], **kw)
    ax.bar(t, r410, bottom=top3, color=ja.C["tint_model"], **kw)
    ax.axhline(P, color=ja.C["ink"], lw=1.2, ls=(0, (4, 3)), zorder=3)
    ax.plot(t, g3, color=ja.C["model"], lw=1.6, zorder=4, drawstyle="steps-mid")
    ax.set_ylim(0, 100); ax.set_xlim(t[0] - pd.Timedelta(days=1), t[-1] + pd.Timedelta(days=1))
    ax.set_yticks(range(0, 101, 25)); ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.xaxis.set_major_locator(md.MonthLocator()); ax.xaxis.set_major_formatter(md.DateFormatter("%b"))
    x0 = t[0]
    ja.label_at(ax, x0, 95, "#1 account", "actual", dy=0, ha="left", size=LB)
    ja.label_at(ax, x0 + pd.Timedelta(days=0.12 * len(t)), 95, "#2 and #3", "faint", dy=0, ha="left", size=LB)
    k4 = ja.label_at(ax, x0 + pd.Timedelta(days=0.24 * len(t)), 95, "#4 to #10", "ink", dy=0, ha="left", size=LB)
    ja.label_at(ax, x0, 87.5, f"dashed: top 3, {len(t)} days pooled, {P:.1f}%", "ink", dy=0, ha="left", size=LB)
    ja.label_at(ax, x0, 80.0, f"blue line: top 3, declared sub-accounts merged ({PG:.1f}% pooled)",
                "model", dy=0, ha="left", size=LB)
    for tx in ax.texts:
        if getattr(tx, "_ja_label", False):
            tx.set_bbox(None)
    k4.set_bbox(dict(boxstyle="square,pad=0.25", fc=ja.C["tint_model"], ec="none"))   # key on a swatch of its band
    ja.panel_title(ax, "maker volume by account rank, per day", size=LB)
    ax.set_xlabel("day (UTC)", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
    ax.set_ylabel("share of daily maker volume, %", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
    rng = f"{lo:.0f}% to {hi:.0f}%"
    ja.finish(fig, f"Top 3 makers supply {rng} of daily maker volume", hl=rng,
              subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {D['n_makers']:,} maker accounts, ${D['total'] / 1e9:.2f}B volume",
              source=f"Data: Hydromancer Reservoir / node data. Range: middle 80% of days (all days {top3.min():.0f}% to {top3.max():.0f}%). "
                     "Undeclared links not merged.")
    ja.save(fig, "out/concentration.png")
    sys.exit(0)

fig, _ax = ja.figure("wide", "night")
matplotlib.rcParams["text.parse_math"] = False
_ax.remove()
ax = ja._px_axes(fig, 2 * ja.U + 64, 7 * ja.U + 52, 1536 - 2 * ja.U - 64 - 2 * ja.U, 864 - 7 * ja.U - 52 - 64 - 136)

w, kw = 0.68, dict(edgecolor=ja.C["ground"], linewidth=1.5, zorder=2)
ax.bar(x, r1, w, color=ja.C["actual"], **kw)
ax.bar(x, r23, w, bottom=r1, color=ja.C["faint"], **kw)
ax.bar(x, r410, w, bottom=top3, color=ja.C["tint_model"], **kw)
ax.axhline(P, color=ja.C["ink"], lw=1.2, ls=(0, (4, 3)), zorder=3)     # over the bars: the pooled share sits below most days
for i in x:   # merged sub-accounts: short bar per day
    ax.plot([i - w / 2, i + w / 2], [g3[i], g3[i]], color=ja.C["model"], lw=3.5, zorder=4, solid_capstyle="butt")

lo, hi = int(top3.argmin()), int(top3.argmax())
for i in x:
    strong = i in (lo, hi)
    y = max(top3[i], g3[i])
    if g3[i] - top3[i] >= 1:
        ja.label_at(ax, i, g3[i], f"{g3[i]:.0f}%", "model", dy=7, size=10.5)
        ja.label_at(ax, i, top3[i], f"{top3[i]:.0f}%", "ground", dy=-17, size=10.5)
    elif i != hi:
        ja.label_at(ax, i, y, f"{top3[i]:.0f}%", "ink" if strong else "muted", dy=7, size=11 if strong else 10.5)
ja.signal(ax, hi, top3[hi], ms=0, role="actual")
ja.label_at(ax, hi, top3[hi], f"{top3[hi]:.0f}%", "actual", dy=10, size=11)

# key, top-left inside the panel
ja.label_at(ax, -0.45, 95, "#1 account", "actual", dy=0, ha="left", size=LB)
ja.label_at(ax, 1.55, 95, "#2 and #3", "faint", dy=0, ha="left", size=LB)
k4 = ja.label_at(ax, 3.4, 95, "#4 to #10", "ink", dy=0, ha="left", size=LB)
ja.label_at(ax, -0.45, 87.5, f"dashed: top 3, {len(days)} days pooled, {P:.1f}%", "ink", dy=0, ha="left", size=LB)
ja.label_at(ax, 5.0, 87.5, f"blue tick: top 3, declared sub-accounts merged ({PG:.1f}%)", "model", dy=0, ha="left", size=LB)

ax.set_ylim(0, 100); ax.set_xlim(-0.55, len(days) - 0.45)
ax.set_yticks(range(0, 101, 25)); ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
lab = []
for d in days:
    day = dt.date.fromisoformat(d["d"])
    lab.append(f"{day:%a}\n{day:%b} {day.day}\n${d['vol'] / 1e6:,.0f}M")
ax.set_xticks(x, lab, fontsize=10, linespacing=1.3)
for t in ax.texts:   # no label boxes over bars
    if getattr(t, "_ja_label", False):
        t.set_bbox(None)
k4.set_bbox(dict(boxstyle="square,pad=0.25", fc=ja.C["tint_model"], ec="none"))   # key on a swatch of its band
ja.panel_title(ax, "maker volume by account rank, per day", size=LB)
ax.set_xlabel("day (UTC), with daily volume", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
ax.set_ylabel("share of daily maker volume, %", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

ja.finish(fig, "Top 3 makers supply 34% to 46% of daily maker volume", hl="34% to 46%",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {D['n_makers']:,} maker accounts, ${D['total'] / 1e9:.2f}B volume",
          source=f"Data: Hydromancer Reservoir / node data. Leaders rotate, so pooled is lower. Undeclared links not merged.")
ja.save(fig, "out/concentration.png")
