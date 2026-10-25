"""cancels_1: share of displayed notional ever filled, by distance x rest time, plus orders opened and
cancelled in the same block. Reads data/derived/cancels/{rates,class_by_dist}.parquet (aggregate only)."""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
from matplotlib.colors import LinearSegmentedColormap, LogNorm
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

D = "data/derived/cancels"
cnt = (lambda n: f"{n/1e3:,.0f}k") if WIN.IS_ATLAS else (lambda n: f"{n/1e6:.1f}M" if n >= 1e6 else f"{n/1e3:,.0f}k")
DIST = ["1 improves touch", "2 at touch", "3 within 1 bp", "4 1-5 bps", "5 5-25 bps", "6 over 25 bps"]
DLBL = ["improves touch", "at touch", "within 1 bp", "1-5 bps", "5-25 bps", "over 25 bps"]
r = pd.read_parquet(f"{D}/rates.parquet")
LIFE = sorted(r.life_bucket.unique()); LLBL = [x[2:] for x in LIFE]
fs = r.pivot(index="dist_bucket", columns="life_bucket", values="filled_usd").reindex(DIST)[LIFE] / \
     r.pivot(index="dist_bucket", columns="life_bucket", values="placed_usd").reindex(DIST)[LIFE]
nn = r.pivot(index="dist_bucket", columns="life_bucket", values="n").reindex(DIST)[LIFE]
share = r.filled_usd.sum() / r.placed_usd.sum()
c = pd.read_parquet(f"{D}/class_by_dist.parquet")
tot = c[c["class"].isin(["never_displayed", "displayed_pulled", "displayed_partial", "filled"])].groupby("dist_bucket").n.sum()
nd = (c[c["class"] == "never_displayed"].groupby("dist_bucket").n.sum() / tot).reindex(DIST)

fig, ax0 = ja.figure("wide", "night"); ax0.remove()
ax = ja._px_axes(fig, 240, 240, 864, 408); ax.grid(False)
cmap = LinearSegmentedColormap.from_list("b", [ja.C["panel"], ja.C["model"], "#D6E6F3"])
cmap.set_bad(ja.C["panel"])
v = fs.values.astype(float)
# LED cell: the cell holding the most displayed notional (1-5 bps, 5-30 s), where almost nothing fills
pl = r.pivot(index="dist_bucket", columns="life_bucket", values="placed_usd").reindex(DIST)[LIFE].values
li, lj = np.unravel_index(np.argmax(pl), pl.shape)
ax.imshow(np.where(v > 0, v, np.nan), cmap=cmap, norm=LogNorm(1e-5, 0.7), aspect="auto")
for i in range(v.shape[0]):
    for j in range(v.shape[1]):
        t = "0" if v[i, j] == 0 else (f"{100*v[i,j]:.1f}%" if v[i, j] >= 0.001 else f"{100*v[i,j]:.3f}%")
        rgb = cmap(LogNorm(1e-5, 0.7)(v[i, j]))[:3] if v[i, j] > 0 else (0, 0, 0)
        light = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] > 0.5
        dx_ = 0.13 if (i, j) == (li, lj) else 0
        ax.text(j + dx_, i - 0.14, t, ha="center", va="center", fontsize=11, weight="semibold",
                color=ja.C["ground"] if light else ja.C["ink"])
        ax.text(j + dx_, i + 0.24, cnt(nn.values[i, j]), ha="center", va="center", fontsize=9,
                color=ja.C["ground"] if light else ja.C["muted"])

for x in range(v.shape[1] + 1): ax.axvline(x - .5, color=ja.C["ground"], lw=2)
for y in range(v.shape[0] + 1): ax.axhline(y - .5, color=ja.C["ground"], lw=2)
for sp in ax.spines.values(): sp.set_visible(False)
ax.set_xticks(range(len(LIFE)), [x.replace(" (<100 ms)", "\n<100 ms").replace("30 s-5 min", "30 s-\n5 min").replace("100-250 ms", "100-\n250 ms").replace("250 ms-1 s", "250 ms-\n1 s").replace("over 5 min", "over\n5 min") for x in LLBL]); ax.set_yticks(range(6), DLBL)
ax.tick_params(length=0)
ja.signal(ax, lj - 0.38, li - 0.14, ms=0)
ja.panel_title(ax, "cell: % of displayed notional ever filled, and order count", size=11)
ax.set_xlabel("time the order rested before it was filled or pulled", color=ja.C["muted"], family=ja.MONO, fontsize=11, labelpad=8)
ax.set_ylabel("distance from touch at placement", color=ja.C["muted"], family=ja.MONO, fontsize=11, labelpad=10)

bx = ja._px_axes(fig, 1176, 240, 288, 408)
bx.barh(range(6), 100 * nd.values, color=ja.C["faint"], height=0.56)
bx.set_ylim(5.5, -0.5); bx.set_yticks([]); bx.set_xlim(0, max(30, 10 * np.ceil(100 * np.nanmax(nd.values) / 10 + 0.4)))
bx.grid(False); bx.set_xticks([0, 10, 20, 30]); bx.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
for i, x in enumerate(100 * nd.values):
    bx.text(x + 0.8, i, f"{x:.0f}%", va="center", fontsize=11, color=ja.C["ink"], weight="semibold")
bx.spines["bottom"].set_color(ja.C["axis"])
ja.panel_title(bx, "cancelled in same block", size=11)
bx.set_xlabel("share of placed orders, %", color=ja.C["muted"], family=ja.MONO, fontsize=11, labelpad=8)

ja.finish(fig, f"Only {100*share:.2f}% of displayed notional ever filled", hl=f"{100*share:.2f}%",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {r.n.sum()/1e6:.0f}M resting orders, ${r.placed_usd.sum()/1e12:.2f}T displayed",
          source="Data: Hydromancer Reservoir / node data. Filled orders stop resting when they fill.")
ja.save(fig, "out/cancels_1.png")
