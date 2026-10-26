"""xyz:SP500 execution shape and cost, @justinalick night. Reads data/derived/shape_cost/shape_cost.json
(analysis/shape_cost/shape_cost.py): spread-out metaorders against front- and back-loaded ones, matched across
traders and within the same account."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/shape_cost/shape_cost.json"))
LB = 11
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)
fig, ax0 = ja.figure("wide", "night"); ax0.remove()
P = {"shortfall": ja._px_axes(fig, 330, 250, 540, 430), "impact": ja._px_axes(fig, 950, 250, 540, 430)}
ROWS = [("front-loaded", "strata", "matched across traders"), ("front-loaded", "account", "within one account"),
        ("back-loaded", "strata", "matched across traders"), ("back-loaded", "account", "within one account")]
Y = [3.2, 2.5, 1.0, 0.3]
lim = max(abs(v) for m in ("strata", "account") for v in np.ravel([R[m][k][:3] for k in R[m]])) + 0.08
for y_, (key, ax) in enumerate(P.items()):
    ax.axvline(0, color=ja.C["axis"], lw=1.2)
    for (other, m, lab), yy in zip(ROWS, Y):
        est, lo, hi = R[m][f"{key}: spread out - {other}"][:3]
        role = "model" if m == "strata" else "actual"
        ax.plot([lo, hi], [yy, yy], color=ja.C[role], lw=3, solid_capstyle="round")
        ax.plot(est, yy, "D" if m == "account" else "o", ms=10, color=ja.C[role], mec=ja.C["ground"], mew=1.5, zorder=4)
        ax.text(hi + 0.02 * lim, yy, f"{est:+.2f}", va="center", ha="left", color=ja.C[role], family=ja.MONO, fontsize=10.5)
    ax.set_ylim(-0.4, 4.1); ax.set_xlim(-lim, lim + 0.1)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.1f}" if v else "0"))
    for s in ("left", "right", "top"): ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", left=False)
    ax.set_yticks([])
    ja.panel_title(ax, {"shortfall": "fill price vs the mid before, bps", "impact": "mid after the last fill vs before, bps"}[key], size=LB)
    ax.set_xlabel("spread out minus the other shape  (- = spread out cheaper)", **AX) if key == "shortfall" else ax.set_xlabel("same, for impact", **AX)
a = P["shortfall"]
for yy, h in ((3.75, "vs front-loaded"), (1.55, "vs back-loaded")):
    a.text(-lim - 0.04 * lim, yy, h, ha="right", va="center", family=ja.MONO, fontsize=11, weight="semibold", color=ja.C["ink"])
for (other, m, lab), yy in zip(ROWS, Y):
    a.text(-lim - 0.04 * lim, yy, lab, ha="right", va="center", family=ja.MONO, fontsize=10.5,
           color=ja.C["model" if m == "strata" else "actual"])
n = R["n"]
ja.finish(fig, "Spreading an order out looks cheaper, mostly because of who does it",
          hl="who does it",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {sum(n.values()):,} metaorders with 4+ child orders",
          source="Data: Hydromancer Reservoir / node data. Largest taker left out. 95% CI: day bootstrap.")
ja.save(fig, "out/shape_cost.png")
