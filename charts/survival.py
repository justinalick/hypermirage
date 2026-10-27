"""Kaplan-Meier survival of displayed orders by distance from the touch, in the @justinalick kit (night).
Data: cache/survival.json, written by survival_cache.py (same query as analysis/survival_viz.py)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FixedLocator, NullLocator, FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

D = json.load(open("data/derived/chart_cache/survival.json"))
t = np.array(D["grid_s"]); cv = D["curves"]
BUCKETS = [("a", "at or inside the touch", "actual"), ("b", "up to 1 bp behind", "model"),
           ("c", "1 to 5 bps behind", "faint"), ("d", "more than 5 bps behind", "dim")]
c1 = {b: cv[b]["cancel_1s"] for b, _, _ in BUCKETS}
WIN.expect("cancelled within 1s, buckets a/b/d (%)", [round(100 * c1[b]) for b in "abd"], [65, 72, 26])
LB = 11.5

fig, ax = ja.figure("wide", "night")
_p = ax.get_position(); _l = 136 / 1536   # room for the y label
ax.set_position([_l, _p.y0, _p.x1 - _l, _p.height])
ja.C["dim"] = "#687A85"   # darker grey than faint: four lightness steps
for b, lab, role in BUCKETS[::-1]:
    s = np.array(cv[b]["s"]); k = t >= cv[b]["t_first_s"] * 0.999
    x = np.r_[t[k][0], t[k]]; y = 100 * np.r_[1.0, s[k]]
    ja.line(ax, x, y, role, lw=3 if b == "a" else 2.5, drawstyle="steps-post")
ax.axvline(1, color=ja.C["faint"], lw=1, ls=(0, (2, 3)), zorder=1)
ax.set_xscale("log"); ax.set_xlim(0.028, 3600); ax.set_ylim(0, 103)
ax.xaxis.set_major_locator(FixedLocator([0.1, 1, 10, 60, 600, 3600])); ax.xaxis.set_minor_locator(NullLocator())
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: {0.1: "0.1 s", 1: "1 s", 10: "10 s", 60: "1 min", 600: "10 min", 3600: "1 h"}.get(round(v, 1), "")))
ax.set_yticks([0, 25, 50, 75, 100]); ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))

def lab(x, y, text, role, ha="left", va="center", rot=0, size=LB):
    t = ax.text(x, y, text, color=ja.C[role], fontsize=size, family=ja.MONO, weight="semibold",
                ha=ha, va=va, rotation=rot, rotation_mode="anchor", zorder=20)
    t._ja_label = True
    return t


def along(b, x0, x1, dy_px, text, role, va="bottom"):
    """Label rotated along a curve's straight stretch, offset dy_px above it (below it when dy_px < 0, with va="top")."""
    s_ = 100 * np.array(cv[b]["s"])
    p0 = ax.transData.transform((x0, np.interp(x0, t, s_ / 100) * 100))
    p1 = ax.transData.transform((x1, np.interp(x1, t, s_ / 100) * 100))
    ang = np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0]))
    n = np.array([-np.sin(np.radians(ang)), np.cos(np.radians(ang))])
    xy = ax.transData.inverted().transform(p0 + dy_px * n)
    t_ = lab(xy[0], xy[1], text, role, va=va, rot=ang)
    t_._ja_label = False   # ja.check tests axis-aligned boxes, which a rotated label's box is not; checked by eye
    return t_


fig.canvas.draw()
# 1s readings
sa = 100 * (1 - c1["a"])
ja.signal(ax, 1, sa, ms=0)
N = {b: f"{cv[b]['n'] / 1e6:.1f}M" for b in "abcd"}
lab(0.86, 18.5, f"at or inside the touch ({N['a']})\n{c1['a']:.0%} cancelled by 1 s", "actual", ha="right", size=11)
lab(0.86, 5.5, f"up to 1 bp behind ({N['b']})\n{c1['b']:.0%} cancelled by 1 s", "model", ha="right", size=11)
# the two outer curves are close together, so they get a small key (line swatch in the curve color) instead of labels on the curves
lab(1.2, 100 * (1 - c1["d"]) + 13.5, f"\u2501\u2501 more than 5 bps behind ({N['d']}): {c1['d']:.0%} cancelled by 1 s", "dim", va="bottom")
lab(1.2, 100 * (1 - c1["d"]) + 5.5, f"\u2501\u2501 1 to 5 bps behind ({N['c']}): {c1['c']:.0%} cancelled by 1 s", "faint", va="bottom")

ja.panel_title(ax, "displayed orders, by distance from the touch at entry", size=LB)
ax.set_xlabel("time since the order first appeared in the book, log scale", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
ax.set_ylabel("share of orders still resting, %", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
m = D["meta"]
ja.finish(fig, f"{c1['a']:.0%} of quotes at or inside the touch are cancelled within 1 s", hl=f"{c1['a']:.0%}",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {m['n'] / 1e6:.1f}M orders, {m['accts']:,} accounts",
          source="Data: Hydromancer Reservoir / node data. Kaplan-Meier; fills and day-end orders censored. Dotted line: 1 s.")
ja.save(fig, "out/survival.png")
