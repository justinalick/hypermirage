"""xyz:SP500 maker rotation week by week, @justinalick night. Reads data/derived/maker_rotation/rotation.json
(analysis/maker_rotation/rotation.py). Groups: declared sub-accounts merged into their master, labeled by pooled volume."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/maker_rotation/rotation.json"))
G, A = R["groups"], R["addresses"]
weeks = G["weeks"]; x = np.arange(len(weeks))
LB = 11
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)
fig, ax0 = ja.figure("wide", "night"); ax0.remove()
a = ja._px_axes(fig, 110, 250, 820, 450)
b = ja._px_axes(fig, 1040, 250, 450, 450)
MAXR = 12
ROLE = {"G1": "actual", "G2": "model", "G3": "ink", "G4": "muted"}
for k in G["top3_groups_ever"]:
    r = np.array([MAXR + 0.5 if v is None or v > MAXR else v for v in G["weekly_rank"][k]], float)
    role = ROLE.get(k, "faint")
    a.plot(x, r, color=ja.C[role], lw=3 if k in ROLE else 1.5, alpha=1 if k in ROLE else 0.6, marker="o", ms=4 if k in ROLE else 3,
           zorder=3 if k in ROLE else 2)
    if k in ROLE:
        t = ja.label_at(a, x[-1] + 0.4, r[-1], f"{k}  {100 * G['pooled_share'][k]:.0f}%", role, dy=0, ha="left", size=10)
        t.set_va("center")
a.invert_yaxis(); a.set_ylim(MAXR + 1, 0.4); a.set_yticks([1, 3, 5, 10, MAXR + 0.5], ["1", "3", "5", "10", f"{MAXR}+"])
a.axhspan(0.5, 3.5, color=ja.C["panel"], lw=0, zorder=0)
step = max(1, len(weeks) // 9)
a.set_xticks(x[::step], [w[5:] for w in weeks[::step]]); a.set_xlim(-0.5, len(weeks) + 2.5)
ja.panel_title(a, "weekly rank by maker volume of the groups that ever made the top 3", size=LB)
a.set_xlabel("ISO week (shade: top 3; thin gray: other groups that made the top 3;\n"
             "end label: share of all maker volume)", **AX); a.set_ylabel("rank (1 = largest; 12+ = below 12)", **AX)

ja.line(b, x, G["weekly_top3_share"], "model", lw=2.5, marker="o", ms=4)
ja.line(b, x, A["weekly_top3_share"], "actual", lw=2.5, marker="o", ms=4)
b.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
b.set_xticks(x[::step * 2], [w[5:] for w in weeks[::step * 2]]); b.set_ylim(0, max(G["weekly_top3_share"]) + 0.12)
ja.label_at(b, 0, max(G["weekly_top3_share"]) + 0.07, "groups (sub-accounts merged)", "model", dy=0, ha="left", size=10).set_bbox(None)
ja.label_at(b, 0, max(G["weekly_top3_share"]) + 0.02, "single addresses", "actual", dy=0, ha="left", size=10).set_bbox(None)
ja.panel_title(b, "top-3 share of maker volume, %", size=LB); b.set_xlabel("ISO week", **AX)
rho = float(np.median(G["rank_rho_week_to_week"]))
r1 = G["weekly_rank"]["G1"]; k = len(r1)
while k > 0 and r1[k - 1] == 1: k -= 1                 # start of G1's closing run at rank 1
n_lead = len(r1) - k
ja.finish(fig, f"One maker group has led every week for the last {n_lead} weeks", hl=f"{n_lead} weeks",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {len(weeks)} weeks, {G['n_groups']:,} maker groups",
          source=f"Data: Hydromancer Reservoir / node data. Groups: sub-accounts declared today. Top-20 rank correlation week to week: {rho:.2f}.")
ja.save(fig, "out/maker_rotation.png")
