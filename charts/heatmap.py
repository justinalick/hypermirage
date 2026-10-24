"""Median resting depth within 10 bps by weekday x UTC hour, in the @justinalick kit (night).
Data: data/derived/heatmap/depth_minutes_v2.parquet, column d10_net (same input as heatmap_depth.py, v2)."""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import justinalick as ja

df = pd.read_parquet("data/derived/heatmap/depth_minutes_v2.parquet", columns=["t", "d10_net"])
t = df.t; dow = t.dt.dayofweek + 1; h = t.dt.hour; mm = h * 60 + t.dt.minute     # isodow 1 = Mon
closed = ((dow <= 4) & (h == 21)) | ((dow == 5) & (h >= 21)) | (dow == 6) | ((dow == 7) & (h < 22))
brk = (dow <= 4) & (h == 21)
cash = (dow <= 5) & (mm >= 810) & (mm < 1200)
sess = np.select([brk, closed, cash], ["break", "weekend", "cash"], "other")
med = df.d10_net.groupby(sess).median() / 1e6
open_all = df.d10_net[~closed].median() / 1e6
print(med.round(2).to_dict(), round(open_all, 2), round(med["break"] / open_all, 2), round(med["weekend"] / open_all, 2))
assert (round(med["cash"], 1), round(med["other"], 1), round(med["break"], 1), round(med["weekend"], 1)) == (15.4, 13.2, 4.7, 3.4)
r_brk, r_wk = med["break"] / open_all, med["weekend"] / open_all
g = df.assign(dow=dow, h=h).groupby(["dow", "h"]).d10_net
assert g.size().min() == g.size().max() == 120 and g.ngroups == 168
Z = (g.median() / 1e6).unstack().sort_index().to_numpy()   # rows Mon..Sun

fig, _ax = ja.figure("wide", "night")
_ax.remove()
X0, Y0, AW, AH = 2 * ja.U + 64, 7 * ja.U + 76, 1536 - (2 * ja.U + 64) - 2 * ja.U - 144, 864 - 7 * ja.U - 76 - 64 - 124
ax = ja._px_axes(fig, X0, Y0, AW, AH)
cax = ja._px_axes(fig, X0 + AW + 24, Y0, 16, AH)
cmap = LinearSegmentedColormap.from_list("night_model", [ja.C["panel"], ja.C["tint_model"], ja.C["model"], "#D6E6F3"])
im = ax.imshow(Z, cmap=cmap, vmin=0, vmax=18, aspect="auto", extent=(0, 24, 7, 0), interpolation="nearest")
for xx in range(1, 24):
    ax.axvline(xx, color=ja.C["ground"], lw=1.4)
for yy in range(1, 7):
    ax.axhline(yy, color=ja.C["ground"], lw=1.4)
ax.grid(False)
ax.set_yticks(np.arange(7) + 0.5, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
ax.set_xticks(range(0, 25, 3), [f"{v:02d}:00" for v in range(0, 25, 3)])
ax.spines["bottom"].set_visible(False)
top = ax.secondary_xaxis("top")
top.set_xticks(range(0, 25, 3), [f"{((v - 4) % 12) or 12}{'am' if (v - 4) % 24 < 12 else 'pm'}" for v in range(0, 25, 3)])
top.tick_params(length=0, colors=ja.C["faint"], labelsize=10)
for s in top.spines.values():
    s.set_visible(False)
LB = 11
top.set_xlabel("hour of day, New York time (EDT)", color=ja.C["muted"], family=ja.MONO, fontsize=LB, labelpad=8)

# US cash session, Mon-Fri 13:30-20:00 UTC: solid ink box
ax.add_patch(plt.Rectangle((13.5, 0.04), 6.5, 4.92, fill=False, ec=ja.C["ink"], lw=2.5, zorder=5))
# CME equity futures closed: daily 21-22 UTC break, Fri 21:00 to Sun 22:00 UTC: dashed outline
cl = np.zeros((7, 24), bool); cl[0:4, 21] = True; cl[4, 21:] = True; cl[5, :] = True; cl[6, :22] = True
for r in range(7):
    for c in range(24):
        if not cl[r, c]:
            continue
        for dr, dc, seg in [(-1, 0, ((c, c + 1), (r, r))), (1, 0, ((c, c + 1), (r + 1, r + 1))),
                            (0, -1, ((c, c), (r, r + 1))), (0, 1, ((c + 1, c + 1), (r, r + 1)))]:
            rr, cc = r + dr, c + dc
            if 0 <= rr < 7 and 0 <= cc < 24 and cl[rr, cc]:
                continue
            ax.plot(*seg, color=ja.C["actual"], lw=2.2, ls=(0, (3, 2)), zorder=6, clip_on=False)

# the LED: the daily futures break (Wed 21:00 UTC)
ax.plot([21.5], [2.5], marker="s", ms=0, mfc=ja.C["signal"], mec=ja.PUNK["ink"], mew=1.5, zorder=10)
def cell_label(x, y, text, role, **kw):   # no box on cells: text color picked for contrast
    t = ja.note_at(ax, x, y, text, role, size=11)
    t.set_bbox(None); t.set_weight("semibold"); t.set(**kw)
    return t


cell_label(11.0, 5.5, f"weekend: ${med['weekend']:.1f}M, {r_wk:.2f}x of futures-open hours", "actual")
cell_label(23.0, 1.0, f"break\n${med['break']:.1f}M\n{r_brk:.2f}x", "ground")
cell_label(16.75, 0.5, f"US cash hours: ${med['cash']:.1f}M", "ground")
cell_label(6.0, 0.5, f"other futures-open hours: ${med['other']:.1f}M", "ground")

cb = fig.colorbar(im, cax=cax, ticks=[0, 3, 6, 9, 12, 15, 18])
cb.outline.set_visible(False); cb.ax.tick_params(length=0, labelsize=10, colors=ja.C["muted"])
cb.ax.set_yticklabels([f"${v}M" for v in [0, 3, 6, 9, 12, 15, 18]])
cb.set_label("median depth within 10 bps, $", color=ja.C["muted"], family=ja.MONO, fontsize=LB, labelpad=8)

ax.set_xlabel("hour of day, UTC", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
ax.set_ylabel("day of week, UTC", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
ax.annotate("solid: US cash session (9:30am to 4pm ET)", (0, 0), xycoords="axes fraction", xytext=(0, -46),
            textcoords="offset points", ha="left", va="top", family=ja.MONO, fontsize=10.5, color=ja.C["ink"])
ax.annotate("dashed: CME equity futures closed (daily 5 to 6pm ET, weekend)", (0, 0), xycoords="axes fraction",
            xytext=(280, -46), textcoords="offset points", ha="left", va="top", family=ja.MONO, fontsize=10.5,
            color=ja.C["actual"])

ja.finish(fig, f"Depth follows CME hours: {r_brk:.2f}x in the daily break", hl=f"{r_brk:.2f}x",
          subtitle="xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, median depth within 10 bps of mid",
          source=f"Data: Hydromancer Reservoir / node data. Book replay net of fills; {len(df):,} one-minute snapshots, 120 per cell.")
ja.save(fig, "out/heatmap.png")
