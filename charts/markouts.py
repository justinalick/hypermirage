"""Taker/maker markouts by horizon and by taker order size, in the @justinalick kit (night).
Data: data/derived/markout/rerun/markout_res.json (same input as rerun/plot.py)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.colors import to_rgb, to_hex
import justinalick as ja

S = "data/derived/markout/rerun"
r = json.load(open(f"{S}/markout_res.json"))
H = ["0", "0.5", "1", "2", "5", "10", "20", "30", "60", "120", "300"]
XL = ["fill", "0.5s", "1s", "2s", "5s", "10s", "20s", "30s", "1m", "2m", "5m"]
x = np.arange(len(H))
LB = 11.5


def mix(c, a):
    """Pre-mixed tint of role color c over the ground (no alpha)."""
    c, g = np.array(to_rgb(ja.C[c])), np.array(to_rgb(ja.C["ground"]))
    return to_hex(g + a * (c - g))


def series(d, sign=1):
    m = np.array([sign * d[h][0] for h in H])
    lo = np.array([sign * d[h][1] for h in H]); hi = np.array([sign * d[h][2] for h in H])
    return m, np.minimum(lo, hi), np.maximum(lo, hi)


fig, _ax = ja.figure("wide", "night")
matplotlib.rcParams["text.parse_math"] = False   # dollar signs are text
_ax.remove()
W = 1536
top, ph = 7 * ja.U + 52, 864 - 7 * ja.U - 52 - 64 - 76
L0, gap = 2 * ja.U + 64, 120
pw = (W - L0 - 2 * ja.U - gap) // 2
a = ja._px_axes(fig, L0, top, pw, ph)
b = ja._px_axes(fig, L0 + pw + gap, top, pw, ph)

for ax in (a, b):
    ja.zero(ax)
    ax.set_xticks(x, XL); ax.set_xlim(-0.4, len(H) - 0.6)
    ax.set_ylim(-1.0, 0.55); ax.set_yticks([-0.8, -0.6, -0.4, -0.2, 0, 0.2, 0.4])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.1f}" if v else "0"))
    ax.set_xlabel("time after fill", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
    ax.set_ylabel("markout vs fill price, bps", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

def nobox(t):
    t.set_bbox(None)
    return t


# left: all fills, taker vs maker
mt, lt, ht = series(r["all"])
mm, lm, hm = series(r["all"], -1)
a.fill_between(x, lm, hm, color=ja.C["panel"], lw=0, zorder=0.6)
a.fill_between(x, lt, ht, color=ja.C["tint_actual"], lw=0, zorder=0.7)
ja.line(a, x, mm, "faint", lw=2.5, ls=(0, (4, 3)), marker="o", ms=5)
ja.line(a, x, mt, "actual", lw=3, marker="o", ms=5.5)
a.set_xlim(-0.4, len(H) + 0.6)          # room for direct end labels past the 5m point
ja.label_at(a, 10.25, mt[-1], "taker", "actual", dy=-5, ha="left", size=LB).set_bbox(None)
ja.label_at(a, 10.25, mm[-1], "maker", "faint", dy=-5, ha="left", size=LB).set_bbox(None)
ja.signal(a, 0, mt[0], dx=14, dy=-30, size=LB, ms=0, role="actual")
nobox(ja.label_at(a, 0.25, mt[0], f"{mt[0]:.2f} at fill", "actual", dy=-34, ha="left", size=LB))
ja.note_at(a, 4.6, 0.45, "taker turns positive after about 5s,\nabout +0.17 bps at 2 to 5 min", "ink", size=10.5)
ja.panel_title(a, "all fills, taker vs maker (95% CI)", size=LB)

# right: taker markout by order size (key band only: under $10k; grey band for $100k and over)
B = [(">= $100k", "faint", "$100k and over"), ("$10k to $100k", "model", "$10k to $100k"), ("< $10k", "actual", "under $10k")]
m, lo, hi = series(r[">= $100k"]); b.fill_between(x, lo, hi, color=ja.C["panel"], lw=0, zorder=0.6)
m, lo, hi = series(r["< $10k"]); b.fill_between(x, lo, hi, color=ja.C["tint_actual"], lw=0, zorder=0.7)
for k, role, _ in B:
    m, lo, hi = series(r[k])
    ja.line(b, x, m, role, lw=3 if role == "actual" else 2.5, marker="o", ms=5)
n = r["n_orders_by_bucket"]
for i, (k, role, lab) in enumerate(B[::-1]):
    ja.label_at(b, -0.2, 0.48 - 0.105 * i, f"{lab}  ({n[k]:,} orders)", role, dy=0, ha="left", size=LB)
nobox(ja.note_at(b, 5.75, -0.68, "gross of fees: avg taker fee 0.78 bps\n"
                 "incl. builder fees (exchange alone 0.58)\n"
                 "under $10k pay 1.13: about 1 bp underwater", "muted", size=10.5))
ja.panel_title(b, "taker side, by taker order size", size=LB)

ja.finish(fig, "Takers pay 0.37 bps to cross, then the price follows them", hl="0.37 bps",
          subtitle=f"xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, {r['n_trades']:,} trades, ${r['notional'] / 1e9:.1f}B notional",
          source="Data: Hydromancer Reservoir / node data. Mid as of every top-of-book change, so 0.5s and 1s are exact.")
ja.save(fig, "out/markouts.png")
