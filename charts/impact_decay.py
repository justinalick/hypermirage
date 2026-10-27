"""xyz:SP500 metaorder impact after the last fill, @justinalick night. Reads data/derived/impact_decay/decay.json
(analysis/impact_decay/decay.py): clean metaorders only (the account sends no taker order for 300 s after)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/impact_decay/decay.json"))
G = R["groups"]["all"]
BK = ["$1k to $10k", "$10k to $100k", "$100k to $1M", "$1M+"]
ROLE = {"$1k to $10k": "faint", "$10k to $100k": "muted", "$100k to $1M": "model", "$1M+": "actual"}
LB = 11
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)
fig, ax0 = ja.figure("wide", "night"); ax0.remove()
a = ja._px_axes(fig, 120, 240, 600, 470)
b = ja._px_axes(fig, 970, 240, 520, 470)

# left: share of the end impact still there, by size
x = np.arange(4); XL = ["0.25 s", "10 s", "1 min", "5 min"]
a.axhline(1, color=ja.C["axis"], lw=1.2)
ends = {}
for k in BK:
    g = G[k]
    y = [1.0] + [g[f"kept_{h}"][0] for h in ("10", "60", "300")]
    lo = [1.0] + [g[f"kept_{h}"][1] for h in ("10", "60", "300")]
    hi = [1.0] + [g[f"kept_{h}"][2] for h in ("10", "60", "300")]
    a.fill_between(x, lo, hi, color=ja.C[ROLE[k]], alpha=0.15, lw=0)
    ja.line(a, x, y, ROLE[k], lw=3 if k == "$1M+" else 2.5, marker="o", ms=5)
    ends[k] = y[-1]
top = max(max(G[k]["kept_300"][2] for k in BK), 1.2)
a.set_ylim(0.5, top + 0.15); a.set_xlim(-0.2, 3.9); a.set_xticks(x, XL)
a.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
ys = sorted(BK, key=lambda k: ends[k]); sep = 0.07 * (top + 0.15 - 0.5); yl = {}
for i, k in enumerate(ys):
    yl[k] = max(ends[k], yl[ys[i - 1]] + sep) if i else ends[k]
for k in BK:
    t = ja.label_at(a, 3.08, yl[k], f"{k}  {ends[k]:.0%}".replace("$", r"\$"), ROLE[k], dy=0, ha="left", size=10.5); t.set_va("center")
ja.panel_title(a, "impact kept, share of move at last fill; bands: 95% CI", size=LB)
a.set_xlabel("time after the metaorder's last fill", **AX); a.set_ylabel("share of end impact", **AX)

# right: drift after the end vs what the trend and the move itself predict
ja.zero(b)
for i, k in enumerate(BK):
    g = G[k]
    obs = g["i300"][0] - g["i0"][0]; ex = g["ex_i300"]
    b.bar(i - 0.17, obs, width=0.3, color=ja.C["faint"], zorder=2)
    b.bar(i + 0.17, g["exp_i300"][0], width=0.3, color=ja.C["model"], alpha=0.75, zorder=2)
    b.errorbar(i, ex[0], yerr=[[ex[0] - ex[1]], [ex[2] - ex[0]]], fmt="D", ms=8, color=ja.C[ROLE[k]],
               mec=ja.C["ground"], ecolor=ja.C[ROLE[k]], elinewidth=2, capsize=4, zorder=4)
lo_ = min(min(G[k]["ex_i300"][1], G[k]["i300"][0] - G[k]["i0"][0]) for k in BK)
hi_ = max(max(G[k]["ex_i300"][2], G[k]["i300"][0] - G[k]["i0"][0]) for k in BK)
b.set_ylim(lo_ - 0.12, hi_ + 0.5); b.set_xlim(-0.6, 3.6)
b.set_xticks(range(4), ["$1k-10k", "$10k-100k", "$100k-1M", "$1M+"])
b.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.1f}" if v else "0"))
ytop = b.get_ylim()[1]
ja.label_at(b, -0.5, ytop - 0.06, "gray: drift in the 5 min after the end", "muted", dy=0, ha="left", size=9.5).set_bbox(None)
ja.label_at(b, -0.5, ytop - 0.16, "blue: random moves, same size and trend", "model", dy=0, ha="left", size=9.5).set_bbox(None)
ja.label_at(b, -0.5, ytop - 0.26, "diamond: the difference (color = size), 95% CI", "ink", dy=0, ha="left", size=9.5).set_bbox(None)
ja.panel_title(b, "5-min drift vs matched control, bps", size=LB)
b.set_xlabel("metaorder size", **AX); b.set_ylabel("bps, + = the trade's direction", **AX)

big = G["$1M+"]["kept_300"][0]
n = sum(G[k]["n"] for k in BK)
ja.finish(fig, f"Big metaorders keep {big:.0%} of their impact after 5 minutes", hl=f"{big:.0%}",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {n:,} metaorders, no own trading for 5 min after",
          source="Data: Hydromancer Reservoir / node data. Equal-weighted means; CIs: day bootstrap. Control: same time of day, other days.")
ja.save(fig, "out/impact_decay.png")
