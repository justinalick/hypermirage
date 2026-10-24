"""Median resting depth within 10 bps of mid by UTC hour x weekday, xyz:SP500, 2026-10-08..21.

Input: per-minute depth net of partial fills (depth_minutes_v2.parquet, written by depth_check.py).
Usage: .venv/bin/python analysis/heatmap/heatmap_depth.py <out.png>
Prints the session medians that the subtitle quotes, so the text can be checked against the data.
"""
import sys
import duckdb
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

SRC = "data/derived/heatmap/depth_minutes_v2.parquet"
COL = "d10_net"
OUT = sys.argv[1]
CLOSED_SQL = """((isodow(t) BETWEEN 1 AND 4 AND hour(t) = 21) OR (isodow(t) = 5 AND hour(t) >= 21)
                 OR isodow(t) = 6 OR (isodow(t) = 7 AND hour(t) < 22))"""

con = duckdb.connect()
con.execute("SET TimeZone='UTC'")
df = con.sql(f"""SELECT isodow(t) dow, hour(t) h, median({COL}) / 1e6 m, count(*) n
                 FROM '{SRC}' GROUP BY 1, 2""").df()
n_min, n_days = con.sql(f"SELECT count(*), count(DISTINCT t::DATE) FROM '{SRC}'").fetchall()[0]
assert len(df) == 168 and df.n.min() == df.n.max() == 120 and n_days == 14, df.describe()
Z = df.pivot(index="dow", columns="h", values="m").sort_index().to_numpy()  # rows Mon..Sun

# Session medians over minutes (UTC; US daylight time throughout the window)
sess = con.sql(f"""
  SELECT CASE
           WHEN isodow(t) BETWEEN 1 AND 4 AND hour(t) = 21                     THEN 'break'
           WHEN {CLOSED_SQL}                                                   THEN 'weekend'
           WHEN isodow(t) BETWEEN 1 AND 5
                AND hour(t) * 60 + minute(t) >= 810 AND hour(t) * 60 + minute(t) < 1200 THEN 'cash'
           ELSE 'futures open, cash closed' END session,
         count(*) AS n_minutes, median({COL}) / 1e6 AS median_musd
  FROM '{SRC}' GROUP BY 1 ORDER BY 3 DESC""").df()
print(sess.round(2).to_string(index=False))
med = dict(zip(sess.session, sess.median_musd))
open_all = con.sql(f"SELECT median({COL}) / 1e6 FROM '{SRC}' WHERE NOT {CLOSED_SQL}").fetchall()[0][0]
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
top.set_xticks(range(0, 25, 3), [f"{((h - 4) % 12) or 12}{'am' if (h - 4) % 24 < 12 else 'pm'}"
                                  for h in range(0, 25, 3)])  # EDT = UTC-4
top.tick_params(length=0, labelsize=9, colors=INK3)
top.set_xlabel("New York time (EDT)", fontsize=9, color=INK3, labelpad=5)
for s in top.spines.values():
    s.set_visible(False)

# US cash session: Mon-Fri 13:30-20:00 UTC
ax.add_patch(plt.Rectangle((13.5, 0.04), 6.5, 4.92, fill=False, ec=INK, lw=1.8, zorder=5))
# CME equity futures closed: daily 21:00-22:00 UTC break, Fri 21:00 to Sun 22:00 UTC.
# Outline the union of closed cells by drawing every cell edge that borders an open cell.
closed = np.zeros((7, 24), bool)
closed[0:4, 21] = True
closed[4, 21:] = True
closed[5, :] = True
closed[6, :22] = True
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
fig.text(0.075, 0.888, "Median resting depth within 10 bps of mid, both sides, xyz:SP500. "
         "It falls by about two thirds in the daily hour\nCME equity futures "
         "pause and by about three quarters over the weekend. US cash hours add only about a sixth.",
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
fig.text(0.075, 0.035,
         f"Sample: {n_days} days, Oct 8 to 21, 2026 (each weekday twice), {n_min:,} one-minute "
         "snapshots; each cell is the median of 120. Depth from an order-level book replay, net of\n"
         "partial fills; within 2% of the exchange's top-20 L2 snapshots in 99% of them. "
         "Source: Hydromancer Reservoir / node data. Two weeks, one market.",
         fontsize=8.5, color=INK3, va="bottom", linespacing=1.45)
fig.text(0.975, ly + 0.011, "@justinalick", fontsize=9.5, color=INK2, ha="right", va="center",
         weight="bold")
fig.savefig(OUT, facecolor=SURF)
