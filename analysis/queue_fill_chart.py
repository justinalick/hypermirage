#!/usr/bin/env python3
"""Chart: fill probability vs size queued ahead at the touch (data/derived/queue/queue.duckdb)."""
import json
import os

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.abspath(".")
OUT = os.path.join(ROOT, "out/queue_fill_v1.png")

INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]
LABELS = ["Improves touch\n(alone)", "Join, ≤$5k\nahead", "Join,\n$5–25k", "Join,\n$25–100k",
          "Join,\n$100–250k", "Join,\n>$250k"]

con = duckdb.connect(os.path.join(ROOT, "data/derived/queue/queue.duckdb"), read_only=True)
rows = con.execute("""
    SELECT qb, count(*) n, 100 * avg(any_fill::INT) all_sizes,
           100 * avg(any_fill::INT) FILTER (WHERE own_usd BETWEEN 5000 AND 15000) mid_size
    FROM r GROUP BY 1 ORDER BY 1""").fetchall()
km = json.load(open(os.path.join(ROOT, "data/derived/queue/km.json")))

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
fig, (a, b) = plt.subplots(1, 2, figsize=(12.5, 5.2), facecolor=SURF,
                           gridspec_kw={"width_ratios": [1.35, 1]})
for ax in (a, b):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)

x = np.arange(len(rows))
w = 0.38
v_all = [r[2] for r in rows]
v_mid = [r[3] for r in rows]
a.bar(x - w / 2 - 0.01, v_all, w, color=RAMP, edgecolor=SURF, linewidth=2, label="All order sizes")
a.bar(x + w / 2 + 0.01, v_mid, w, color=RAMP, edgecolor=SURF, linewidth=2, hatch="////", alpha=0.55,
      label="Own order $5–15k only")
for i, r in enumerate(rows):
    a.text(x[i] - w / 2, v_all[i] + 0.3, f"{v_all[i]:.1f}%", ha="center", va="bottom", fontsize=9, color=INK)
    a.text(x[i] + w / 2, v_mid[i] + 0.3, f"{v_mid[i]:.1f}%", ha="center", va="bottom", fontsize=8, color=INK2)
    a.text(x[i], -2.6, f"n={r[1] / 1e3:,.0f}k", ha="center", va="top", fontsize=8, color=INK2)
a.set_xticks(x, LABELS, fontsize=8.5)
a.set_ylim(0, max(v_all) * 1.18)
a.set_ylabel("Orders with any fill before they left the book (%)")
a.set_title("Share of touch orders that get any fill", loc="left", fontsize=11, color=INK, pad=10)
leg = a.legend(frameon=False, fontsize=8.5, loc="upper right")
for h in leg.legend_handles:
    h.set_facecolor(RAMP[2])

grid = km["grid"]
names = sorted(km["km"])
tt = [g for g in grid if g <= 5]
for i, qb in enumerate(names):
    y = km["km"][qb][:len(tt)]
    b.plot(tt, y, color=RAMP[i], lw=2, marker="o", ms=4)
    b.text(tt[-1] * 1.08, y[-1], LABELS[i].replace("\n", " "), va="center", fontsize=8, color=INK2)
b.set_xscale("log")
b.set_xticks(tt, [f"{g:g}s" for g in tt])
b.set_xlim(0.08, 30)
b.set_ylabel("Cumulative fill probability (%), cancels censored")
b.set_title("Fill probability by time resting (first 5 seconds)", loc="left", fontsize=11, color=INK, pad=10)
b.spines["bottom"].set_bounds(0.08, 5)

fig.suptitle("xyz:SP500: fill odds fall steeply with size queued ahead at the touch", x=0.01, ha="left",
             fontsize=13, fontweight="bold", color=INK)
fig.text(0.01, 0.005,
         "2.75M orders placed at or inside the touch, Oct 9–21 2026 (Oct 8 used as warm-up). FIFO queue replayed from "
         "node order statuses plus maker fills; 95.8% of maker fills hit the replayed queue head.\n"
         "Queue ahead measured at entry only. Right panel assumes cancels are independent of fill risk, which they "
         "are not; read it as indicative. Source: Hydromancer Reservoir / node data.",
         fontsize=7.5, color=INK2, va="bottom")
fig.tight_layout(rect=(0, 0.07, 1, 0.95))
fig.savefig(OUT, dpi=150, facecolor=SURF)
print(OUT)
