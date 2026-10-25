"""cancels_2: what replaced each cancel in its block, by distance, and the size of price amends.
Reads data/derived/cancels/{amend_kinds,amend_ticks}.parquet (aggregate only)."""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

D = "data/derived/cancels"
DIST = ["1 improves touch", "2 at touch", "3 within 1 bp", "4 1-5 bps", "5 5-25 bps", "6 over 25 bps"]
DLBL = ["improves touch", "at touch", "within 1 bp", "1-5 bps", "5-25 bps", "over 25 bps"]
k = pd.read_parquet(f"{D}/amend_kinds.parquet")
k["k"] = np.where(k.kind == "price only", "price only, " + k.dir.fillna(""), k.kind)
tot = k.groupby("k").n.sum(); mix = tot / tot.sum()
kp = k[k.dist_bucket.isin(DIST)].groupby(["dist_bucket", "k"]).n.sum().unstack().reindex(DIST).fillna(0)
K = ["pure cancel", "refresh (same px, same size)", "price only, toward touch", "price only, away from touch",
     "price and size", "size only"]
KL = ["pure cancel", "identical re-place", "price only, toward touch", "price only, away", "price and size", "size only"]
kp = kp[K]; kp = kp.div(kp.sum(1), axis=0)
t = pd.read_parquet(f"{D}/amend_ticks.parquet"); t = t[t.kind == "price only"]

fig, ax0 = ja.figure("wide", "night"); ax0.remove()
# neighbours step in lightness; skin (away) sits next to the lighter highlight, brow only at the far end
KC = [ja.C["faint"], ja.C["muted"], ja.C["model"], ja.C["actual"], ja.PUNK["highlight"], ja.PUNK["brow"]]
ax = ja._px_axes(fig, 240, 264, 672, 360); ax.grid(False)
left = np.zeros(6)
for c, col in zip(K, KC):
    ax.barh(range(6), kp[c].values, left=left, color=col, height=0.56, edgecolor=ja.C["ground"], lw=1.5)
    left += kp[c].values
ax.set_yticks(range(6), DLBL); ax.set_ylim(5.5, -0.5); ax.set_xlim(0, 1)
ax.set_xticks([0, .25, .5, .75, 1]); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{100*v:.0f}%"))
ax.spines["bottom"].set_visible(False); ax.tick_params(axis="x", pad=6)
lg = ax.legend(handles=[Patch(color=c, label=l) for c, l in zip(KC, KL)], ncol=2, loc="upper left",
               bbox_to_anchor=(-0.02, -0.175), fontsize=10.5, columnspacing=1.4, handlelength=1.2)
for tx, c in zip(lg.get_texts(), KC): tx.set_color(c)
i1 = DIST.index("3 within 1 bp"); pc = kp.loc[DIST[i1], "pure cancel"]
ja.signal(ax, pc, i1, ms=0)
# label above the bar, in the gap between rows, no box
lt = ax.text(pc, i1 - 0.5, f"{100*(1-pc):.0f}% replaced", ha="center", va="center", color=ja.C["ink"],
             fontsize=11, family=ja.MONO, weight="semibold", zorder=20)
lt._ja_label = True
ja.panel_title(ax, "what replaced each cancel in its block", size=11)
ax.set_xlabel("share of cancels at that distance, %", color=ja.C["muted"], family=ja.MONO, fontsize=11, labelpad=6)
ax.set_ylabel("distance from touch", color=ja.C["muted"], family=ja.MONO, fontsize=11, labelpad=10)

bx = ja._px_axes(fig, 1032, 264, 432, 360)
ser = {}
for dr, role in [("toward touch", "model"), ("away from touch", "actual")]:
    s = t[t.dir == dr].groupby("ticks").n.sum().sort_index(); s = 100 * s / s.sum(); ser[dr] = s
    ja.line(bx, s.index, s.values, role, lw=2.5, marker="o", ms=5)
bx.set_xlim(0, 21); bx.set_ylim(*ja.fit(0, 42, [s.max() for s in ser.values()], 3)); bx.set_xticks([1, 5, 10, 15, 20]); bx.set_xticklabels(["1", "5", "10", "15", "20+"])
bx.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
ja.label_at(bx, 3.2, 33, "away from touch", "actual", dy=0, ha="left", size=11)
ja.label_at(bx, 3.2, 25, "toward touch", "model", dy=0, ha="left", size=11)
ja.note_at(bx, 16.5, 22, f"1 to 3 ticks:\n{ser['toward touch'].loc[1:3].sum():.0f}% toward,\n{ser['away from touch'].loc[1:3].sum():.0f}% away", size=10.5, role="muted")
ja.panel_title(bx, "size of price-only amends", size=11)
bx.set_xlabel("ticks moved (0.1 = ~0.13 bp)", color=ja.C["muted"], family=ja.MONO, fontsize=11, labelpad=6)
bx.set_ylabel("share of amends, %", color=ja.C["muted"], family=ja.MONO, fontsize=11, labelpad=6)

rep = 1 - mix[K[0]]                                   # replaced in the same block
share = "Half" if abs(rep - 0.5) < 0.05 else f"{rep:.0%}"
ja.finish(fig, f"{share} of {tot.sum()/1e6:.0f}M cancels are same-block replacements", hl=share,
          subtitle=(f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {100*mix[K[1]]:.0f}% identical, "
                    f"{100*(mix[K[2]]+mix[K[3]]):.0f}% price only"),
          source="Data: Hydromancer Reservoir / node data. Replacement = same account and side, same block.")
ja.save(fig, "out/cancels_2.png")
