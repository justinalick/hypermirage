"""cancels_3: cumulative share of near-touch resting orders pulled after the opposite touch moves.
Reads data/derived/cancels/latency.parquet (aggregate only)."""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
import json
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

L = pd.read_parquet("data/derived/cancels/latency.parquet")
L["grp"] = np.where(L.ev == "control", "control",
           np.where(L.ev == "adverse", np.where(L.mv >= 2, "adverse 2+", "adverse 1"),
           np.where(L.mv >= 2, "favorable 2+", "favorable 1")))
MS = round(json.load(open("data/derived/cancels/latency_meta.json"))["ms_per_block"], 1)   # mean block time, ms
WIN.expect("mean block time, ms", MS, 71.5, tol=0.3)
if WIN.IS_ATLAS:
    MS = 71.5   # the published chart's conversion
fig, ax0 = ja.figure("wide", "night"); ax0.remove()
ax = ja._px_axes(fig, 120, 216, 1368, 504)   # panel title clear of the header band
G = [("favorable 2+", "model", "-", "favorable, 2+ ticks"), ("favorable 1", "model", (0, (4, 3)), "favorable, 1 tick"),
     ("adverse 2+", "actual", "-", "adverse, 2+ ticks"), ("adverse 1", "actual", (0, (4, 3)), "adverse, 1 tick"),
     ("control", "faint", "-", "no touch move")]
cur, ntot = {}, 0
for g, role, ls, lab in G:
    s = L[L.grp == g]; n = s.n.sum(); ntot += n
    c = s.dropna(subset=["k"]).groupby("k").n.sum().reindex(range(1, 101), fill_value=0).cumsum() / n
    x = np.r_[0, c.index * MS / 1000]; y = np.r_[0, 100 * c.values]
    ax.plot(x, y, color=ja.C[role], ls=ls, lw=3 if ls == "-" else 2.5)
    cur[g] = (x, y, n, lab, role)
ax.set_xlim(0, 9.6); ax.set_ylim(*ja.fit(0, 66, [v[1].max() for v in cur.values()], 5))
ax.set_xticks([0, 1, 2, 3, 4, 5, 6, 7]); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}s"))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
# direct labels to the right of each line end
offs = {"favorable 2+": 0, "favorable 1": 9, "adverse 2+": -9, "adverse 1": 0, "control": 0}
for g, (x, y, n, lab, role) in cur.items():
    t = ja.label_at(ax, x[-1] + 0.08, y[-1], f"{lab} n={n/1e6:.1f}M", role, dy=offs[g] - 5, ha="left", size=10.5)
i1 = int(round(1000 / MS))   # blocks in 1.0 s (14 at ~71.5 ms)
xf, yf = cur["favorable 2+"][0][i1], cur["favorable 2+"][1][i1]
yc = cur["control"][1][i1]
ax.axvline(xf, color=ja.C["axis"], lw=1, zorder=0)
ja.signal(ax, xf, yf, ms=0)
ytop = ax.get_ylim()[1]
ja.label_at(ax, 0.2, ytop - 11, f"{yf:.0f}% pulled by 1 s after a 2+ tick\nfavorable move, vs {yc:.0f}% with no move", "model", dy=0, ha="left", size=11)
fav = max(cur[g][1][i1] for g in ("favorable 2+", "favorable 1")); adv = max(cur[g][1][i1] for g in ("adverse 2+", "adverse 1"))
if fav >= adv:
    ja.note_at(ax, 5.6, 11, "favorable moves trigger as many or more pulls than adverse:\nmostly quotes re-centering", role="muted", size=10.5)
else:
    ja.note_at(ax, 5.6, 11, f"adverse moves trigger more pulls than favorable by 1 s:\n{adv:.0f}% vs {fav:.0f}%", role="muted", size=10.5)
ja.panel_title(ax, "exposed orders, after the opposite best price moves", size=11)
ax.set_xlabel(f"seconds after the move (blocks of ~{MS:.1f} ms)", color=ja.C["muted"], family=ja.MONO, fontsize=11, labelpad=6)
ax.set_ylabel("orders pulled, cumulative %", color=ja.C["muted"], family=ja.MONO, fontsize=11, labelpad=8)
ratio = max(cur[g][1][i1] for g in ("favorable 2+", "favorable 1", "adverse 2+", "adverse 1")) / yc
WIN.expect("pull-rate ratio at 1 s vs no move", round(ratio, 1), 3.3)
ja.finish(fig, f"After a touch move, orders are pulled up to {ratio:.1f}x faster", hl=f"{ratio:.1f}x",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, orders resting within 1 bp of the touch",
          source="Data: Hydromancer Reservoir / node data. 30% sample of moves; adverse = opposite best moves toward the order.")
ja.save(fig, "out/cancels_3.png")
