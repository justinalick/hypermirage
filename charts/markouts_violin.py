"""Hourly taker markouts by order size (violins), in the @justinalick kit (night).
Data: data/derived/markout/rerun/hourly.json and markout_res.json (same inputs as rerun/plot_violin2.py)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb, to_hex
from matplotlib.ticker import FuncFormatter
import justinalick as ja

S = "data/derived/markout/rerun"
d = json.load(open(f"{S}/hourly.json")); r = json.load(open(f"{S}/markout_res.json"))
B = [("lt10k", "< $10k", "under $10k", "actual"), ("10k_100k", "$10k to $100k", "$10k to $100k", "model"),
     ("ge100k", ">= $100k", "$100k+", "faint")]
Hs = [1, 10, 60]; HL = ["1s", "10s", "1m"]
YL = (-1.6, 1.6)
LB = 11.5


def mix(c, a):
    c, g = np.array(to_rgb(ja.C[c])), np.array(to_rgb(ja.C["ground"]))
    return to_hex(g + a * (c - g))


def kde(v, grid):
    bw = 1.06 * min(v.std(), np.subtract(*np.percentile(v, [75, 25])) / 1.34) * len(v) ** -0.2
    z = (grid[:, None] - v[None, :]) / bw
    return np.exp(-0.5 * z * z).sum(1) / (len(v) * bw * np.sqrt(2 * np.pi))


ahead = {h: float((np.array(d[f"lt10k_{h}"]) > 0).mean()) for h in Hs}
assert round(ahead[1] * 100) == 55 and round(ahead[10] * 100) == 67, ahead

fig, _ax = ja.figure("wide", "night")
matplotlib.rcParams["text.parse_math"] = False
_ax.remove()
top, ph = 7 * ja.U + 52, 864 - 7 * ja.U - 52 - 64 - 76
L0, gap = 2 * ja.U + 64, 36
pw = (1536 - L0 - 2 * ja.U - 2 * gap) // 3
axs = [ja._px_axes(fig, L0 + i * (pw + gap), top, pw, ph) for i in range(3)]

for j, (ax, (k, rk, lab, role)) in enumerate(zip(axs, B)):
    ja.zero(ax)
    c = ja.C[role]; fill = mix(role, 0.30)
    nh = None
    for i, h in enumerate(Hs):
        v = np.array(d[f"{k}_{h}"]); nh = len(v)
        lo_, hi_ = max(v.min(), YL[0] - 0.5), min(v.max(), YL[1] + 0.5)
        g = np.linspace(lo_, hi_, 400); dens = kde(v, g); dens = dens / dens.max() * 0.34
        ax.fill_betweenx(g, i - dens, i + dens, color=fill, lw=0, zorder=2)
        ax.plot(i - dens, g, color=c, lw=1.2, zorder=3); ax.plot(i + dens, g, color=c, lw=1.2, zorder=3)
        q1, med, q3 = np.percentile(v, [25, 50, 75])
        ax.add_patch(plt.Rectangle((i - 0.04, q1), 0.08, q3 - q1, facecolor=c, edgecolor="none", zorder=4))
        ax.plot([i - 0.04, i + 0.04], [med, med], color=ja.C["ground"], lw=2.5, zorder=5)
        m, l, u = r[rk][str(h)]
        ax.errorbar(i + 0.2, m, yerr=[[m - l], [u - m]], fmt="D", ms=6.5, color=ja.C["ink"],
                    elinewidth=1.4, capsize=3.5, zorder=6)
        nhi, nlo = int((v > YL[1]).sum()), int((v < YL[0]).sum())
        if nhi:
            ax.text(i + 0.13, YL[1] - 0.04, f"↑{nhi}", ha="left", va="top", fontsize=10, color=ja.C["muted"],
                    family="IBM Plex Sans")
        if nlo:
            ax.text(i + 0.13, YL[0] + 0.04, f"↓{nlo}", ha="left", va="bottom", fontsize=10, color=ja.C["muted"],
                    family="IBM Plex Sans")
        if k == "lt10k" and h == 10:   # LED beside the median box, not on it
            ja.signal(ax, i - 0.14, med, ms=0, role="actual")
            ja.label_at(ax, i, -0.88, f"ahead in {ahead[10]:.0%} at 10s", "actual", dy=0, size=LB).set_bbox(None)
        if k == "lt10k" and h == 1:
            ja.label_at(ax, i + 0.05, 0.72, f"ahead in {ahead[1]:.0%}\nat 1s", "actual", dy=0, size=LB).set_bbox(None)
    ax.set_xticks(range(3), HL, fontsize=11); ax.set_xlim(-0.55, 2.55); ax.set_ylim(*YL)
    ax.set_yticks([-1.5, -1, -0.5, 0, 0.5, 1, 1.5])
    if j == 0:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.1f}" if v else "0"))
        ax.set_ylabel("taker markout per hour, bps", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
    else:
        ax.tick_params(labelleft=False)
    hrs = f" in {nh} h" if nh < 300 else ""
    ja.panel_title(ax, f"{lab}, {r['n_orders_by_bucket'][rk]:,} orders{hrs}", size=LB)
    if j == 1:   # shared x: one label under the middle panel
        ax.set_xlabel("time after fill", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

_k = ja.note_at(axs[1], -0.48, -1.22, "box: middle 50% of hours\ndiamond: pooled mean, 95% CI\narrows: beyond the axis",
               "muted", size=10)
_k.set_bbox(None); _k.set_ha("left")

ja.finish(fig, "Orders under $10k are ahead in 67% of hours at 10s", hl="67%",
          subtitle="xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, taker markout per UTC hour, bps",
          source="Data: Hydromancer Reservoir / node data. Gross of fees: 0.78 bps taker fee incl. builder (0.58 exchange); 1.13 under $10k.")
ja.save(fig, "out/markouts_violin.png")
