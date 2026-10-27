"""xyz:SP500 taker markouts by hour of the week and by month per taker cluster, @justinalick night.
Reads data/derived/taker_hours/hours.json (analysis/taker_hours/hours.py)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import matplotlib.patches
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/taker_hours/hours.json"))
LB = 11
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)
fig, ax0 = ja.figure("wide", "night"); ax0.remove()
a = ja._px_axes(fig, 130, 250, 760, 430)
b = ja._px_axes(fig, 1010, 250, 480, 430)

g = R["how"]["ex_T1"]
mk = np.array(g["mk60"]).reshape(7, 24); n = np.array(g["notional"]).reshape(7, 24)
thin = n < np.percentile(n[n > 0], 10)
cm = LinearSegmentedColormap.from_list("div", [ja.C["model"], ja.C["panel"], ja.C["accent"]])   # zero is not the page color
img = np.where(thin | (n == 0), np.nan, mk)
L = 1.0
a.grid(False)
a.imshow(img, aspect="auto", cmap=cm, norm=TwoSlopeNorm(0, -L, L), interpolation="nearest")
for (r_, c_) in zip(*np.where(np.isnan(img))):                 # blank (thinnest) hours: hatched, so they differ from ~0
    a.add_patch(matplotlib.patches.Rectangle((c_ - 0.5, r_ - 0.5), 1, 1, fill=False, hatch="///", ec=ja.C["axis"], lw=0))
a.set_yticks(range(7), ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
a.set_xticks(range(0, 24, 3), [f"{h:02d}" for h in range(0, 24, 3)])
for s_ in a.spines.values(): s_.set_visible(False)
a.axvline(9.5 - 0.5, color=ja.C["ink"], lw=0.8, ls=(0, (2, 2))); a.axvline(16 - 0.5, color=ja.C["ink"], lw=0.8, ls=(0, (2, 2)))
ja.panel_title(a, "60s markout by hour, all but the largest taker (T1), bps", size=LB)
a.set_xlabel("New York hour (dotted: US cash; hatched: thinnest 10%)", **AX)
sm = matplotlib.cm.ScalarMappable(norm=TwoSlopeNorm(0, -L, L), cmap=cm)
cb = fig.colorbar(sm, ax=a, fraction=0.03, pad=0.01); cb.outline.set_visible(False)
cb.ax.tick_params(colors=ja.C["faint"], labelsize=9); cb.set_ticks([-1, -0.5, 0, 0.5, 1])
cb.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.1f}" if v else "0"))

months = R["months"]; x = np.arange(len(months))
ja.zero(b)
C = R["clusters"]
best = max(C, key=lambda k: np.nanmean([v for v in C[k]["mk60_by_month"] if v is not None]))
worst = min(C, key=lambda k: np.nanmean([v for v in C[k]["mk60_by_month"] if v is not None]))
for k, r in C.items():
    y = np.array([np.nan if v is None else v for v in r["mk60_by_month"]])
    role = "actual" if k == best else "model" if k == worst else "ink" if k == "T1" else "faint"
    hi = k in (best, worst, "T1")
    b.plot(x, y, color=ja.C[role], lw=2.5 if hi else 1.2, alpha=1 if hi else 0.6, marker="o", ms=4 if hi else 2, zorder=3 if hi else 2)
    if hi:
        t = ja.label_at(b, x[-1] + 0.2, y[-1], k, role, dy=0, ha="left", size=10); t.set_va("center")
b.set_xticks(x, [pd.Timestamp(f"{m}-01").strftime("%b") for m in months]); b.set_xlim(-0.3, len(months) + 0.2)
b.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}" if v else "0"))
ja.panel_title(b, "60s markout by month, bps", size=LB)
b.text(0.98, 0.03, "bold: highest, lowest, T1\ngray: rest of top 10", transform=b.transAxes, ha="right", va="bottom", color=ja.C["muted"], family=ja.MONO, fontsize=10, linespacing=1.3)
cross = np.mean([np.corrcoef(*[[C[k]["mk60_by_month"][i] for k in C] for i in (j, j + 1)])[0, 1] for j in range(len(months) - 1)
                 if all(C[k]["mk60_by_month"][j] is not None and C[k]["mk60_by_month"][j + 1] is not None for k in C)])
ja.finish(fig, f"Takers who lead the price keep leading: r = {cross:.2f}", hl=f"r = {cross:.2f}",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {R['n_fills']:,} taker fills, markout gross of fees",
          source="Data: Hydromancer Reservoir / node data. Markout + = taker gains. Tn: n-th largest taker cluster. r: month vs next.")
ja.save(fig, "out/taker_hours.png")
