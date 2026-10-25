"""Median resting depth within 10 bps of mid by UTC hour x weekday, xyz:SP500, every day of the run window (scripts/window.py).

Input: per-minute depth net of partial fills (depth_minutes_v2.parquet, written by depth_check.py).
Usage: .venv/bin/python analysis/heatmap/heatmap_depth.py <out.png>
Prints the session medians that the subtitle quotes, so the text can be checked against the data.
"""
import sys
import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
sys.path.insert(0, "scripts")
import window as WIN

SRC = "data/derived/heatmap/depth_minutes_v2.parquet"
COL = "d10_net"
OUT = sys.argv[1]

con = duckdb.connect()
con.execute("SET TimeZone='UTC'")
m = con.sql(f"SELECT t, {COL} v FROM '{SRC}' ORDER BY t").df()
m["session"] = WIN.session(m.t)
n_min, n_days = len(m), m.t.dt.date.nunique()
# the hour-of-week grid is a regular week (UTC): holiday dates are left out of it
wk = m[~m.t.dt.strftime("%Y-%m-%d").isin(WIN.HOLIDAYS)]
df = wk.groupby([wk.t.dt.dayofweek + 1, wk.t.dt.hour]).v.agg(["median", "size"]).rename_axis(["dow", "h"]).reset_index()
df["m"] = df["median"] / 1e6; df["n"] = df["size"]
assert len(df) == 168, df.describe()
if WIN.IS_ATLAS:
    assert df.n.min() == df.n.max() == 120 and n_days == 14, df.describe()
Z = df.pivot(index="dow", columns="h", values="m").sort_index().to_numpy()  # rows Mon..Sun

# Session medians over minutes (scripts/window.py clock: daylight time and holidays handled)
names = {"break": "break", "closed": "weekend", "cash": "cash", "overnight": "futures open, cash closed"}
sess = (m.groupby(m.session.map(names)).v.agg(n_minutes="size", median_musd=lambda v: v.median() / 1e6)
        .rename_axis("session").reset_index().sort_values("median_musd", ascending=False))
print(sess.round(2).to_string(index=False))
med = dict(zip(sess.session, sess.median_musd))
open_all = m.v[m.session.isin(["cash", "overnight"])].median() / 1e6
print(f"break / futures-open {med['break'] / open_all:.2f}, weekend / futures-open "
      f"{med['weekend'] / open_all:.2f}, cash / other futures-open "
      f"{med['cash'] / med['futures open, cash closed']:.2f}")

SURF, INK, INK2, INK3, RED = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#c0392b"
ramp = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
        "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
cmap = LinearSegmentedColormap.from_list("blue", ramp)

plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})
fig = plt.figure(figsize=(12, 6.75), dpi=200, facecolor=SURF)
ax = fig.add_axes([0.075, 0.2, 0.80, 0.56], facecolor=SURF)
cax = fig.add_axes([0.895, 0.2, 0.014, 0.56])

im = ax.imshow(Z, cmap=cmap, vmin=0, vmax=18, aspect="auto", extent=(0, 24, 7, 0),
               interpolation="nearest")
for x in range(1, 24):  # surface gap between cells
    ax.axvline(x, color=SURF, lw=1.2)
for y in range(1, 7):
    ax.axhline(y, color=SURF, lw=1.2)

ax.set_yticks(np.arange(7) + 0.5, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
ax.set_xticks(range(0, 25, 3), [f"{h:02d}:00" for h in range(0, 25, 3)])
ax.set_xlabel("Hour of day (UTC)", fontsize=10, labelpad=6)
ax.tick_params(length=0, labelsize=9.5)
for s in ax.spines.values():
    s.set_visible(False)
top = ax.secondary_xaxis("top")
OFF = int(WIN.utc_offset_hours())                      # -4 in daylight time (EDT), -5 in standard time
TZN = "EDT" if OFF == -4 else "EST"
top.set_xticks(range(0, 25, 3), [f"{((h + OFF) % 12) or 12}{'am' if (h + OFF) % 24 < 12 else 'pm'}"
                                  for h in range(0, 25, 3)])
top.tick_params(length=0, labelsize=9, colors=INK3)
top.set_xlabel(f"New York time ({TZN})", fontsize=9, color=INK3, labelpad=5)
for s in top.spines.values():
    s.set_visible(False)

# US cash session: Mon-Fri 9:30-16:00 New York time (13:30-20:00 UTC in daylight time)
ax.add_patch(plt.Rectangle((9.5 - OFF, 0.04), 6.5, 4.92, fill=False, ec=INK, lw=1.8, zorder=5))
# CME equity futures closed or halted in a regular week (daily break, weekend), from the window's clock.
# Outline the union of closed cells by drawing every cell edge that borders an open cell.
closed = WIN.closed_weeks_grid()
for r in range(7):
    for c in range(24):
        if not closed[r, c]:
            continue
        for dr, dc, seg in [(-1, 0, ((c, c + 1), (r, r))), (1, 0, ((c, c + 1), (r + 1, r + 1))),
                            (0, -1, ((c, c), (r, r + 1))), (0, 1, ((c + 1, c + 1), (r, r + 1)))]:
            rr, cc = r + dr, c + dc
            if 0 <= rr < 7 and 0 <= cc < 24 and closed[rr, cc]:
                continue
            ax.plot(*seg, color=RED, lw=1.6, ls=(0, (3, 2)), zorder=6, clip_on=False)

cb = fig.colorbar(im, cax=cax, ticks=[0, 3, 6, 9, 12, 15, 18])
cb.outline.set_visible(False)
cb.ax.tick_params(length=0, labelsize=9, colors=INK2)
cb.ax.set_yticklabels([f"${v}M" for v in [0, 3, 6, 9, 12, 15, 18]])

fig.text(0.075, 0.935, "S&P 500 perp liquidity on Hyperliquid runs on the futures clock",
         fontsize=17, weight="bold", color=INK)
fall = lambda r: f"{1 - r:.0%}"
fig.text(0.075, 0.888, "Median resting depth within 10 bps of mid, both sides, xyz:SP500. "
         f"It falls by about {fall(med['break'] / open_all)} in the daily hour\nCME equity futures "
         f"pause and by about {fall(med['weekend'] / open_all)} when futures are closed. US cash hours add "
         f"{med['cash'] / med['futures open, cash closed'] - 1:+.0%}.",
         fontsize=10.5, color=INK2, va="top", linespacing=1.4)

lx, ly = 0.075, 0.095
fig.add_artist(plt.Rectangle((lx, ly), 0.022, 0.022, transform=fig.transFigure, fill=False,
                             ec=INK, lw=1.8))
fig.text(lx + 0.03, ly + 0.011, "US cash session (9:30am to 4pm ET)", fontsize=9.5,
         color=INK2, va="center")
lx2 = 0.38
fig.add_artist(plt.Rectangle((lx2, ly), 0.022, 0.022, transform=fig.transFigure, fill=False,
                             ec=RED, lw=1.6, ls=(0, (3, 2))))
fig.text(lx2 + 0.03, ly + 0.011, "CME equity futures closed (daily 5 to 6pm ET break, weekend)",
         fontsize=9.5, color=INK2, va="center")
l2 = con.sql("SELECT avg((abs(rep_net_usd / l2_usd - 1) <= 0.02)::INT) FROM 'data/derived/heatmap/l2_check.parquet' WHERE l2_usd > 0").fetchall()[0][0]
hol = f" Holidays ({len(WIN.HOLIDAYS)}) are left out of the grid." if WIN.HOLIDAYS else ""
fig.text(0.075, 0.035,
         f"Sample: {n_days} days, {WIN.label()}, {n_min:,} one-minute snapshots; each cell is the median of "
         f"{df.n.min():,} to {df.n.max():,}.{hol} Depth from an order-level book replay, net of\n"
         f"partial fills; within 2% of the exchange's top-20 L2 snapshots in {l2:.0%} of them. "
         "Source: Hydromancer Reservoir / node data. One market.",
         fontsize=8.5, color=INK3, va="bottom", linespacing=1.45)
fig.text(0.975, ly + 0.011, "@justinalick", fontsize=9.5, color=INK2, ha="right", va="center",
         weight="bold")
fig.savefig(OUT, facecolor=SURF)
