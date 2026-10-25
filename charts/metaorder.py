"""xyz:SP500 metaorder execution shapes, @justinalick night. Data loading copied from
analysis/metaorder_shapes/plot.py (curves.parquet, labels.parquet, impact.json, stability.json)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

O = "data/derived/metaorder_shapes"
C = pd.read_parquet(f"{O}/curves.parquet"); L = pd.read_parquet(f"{O}/labels.parquet"); R = json.load(open(f"{O}/impact.json"))
S = json.load(open(f"{O}/stability.json"))
names = {0: 'front-loaded', 1: 'spread out', 2: 'back-loaded'}
ROLE = {'front-loaded': "actual", 'spread out': "model", 'back-loaded': "faint", 'single order': "muted", '2-3 orders': "muted"}

fig, ax0 = ja.figure("wide", "night"); ax0.remove()
LB = 11
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)
a = ja._px_axes(fig, 120, 216, 528, 504)
b = ja._px_axes(fig, 936, 216, 552, 504)

# left: median fill path per shape cluster
u = np.linspace(0, 1, C.shape[1])
a.plot([0, 1], [0, 1], color=ja.C["faint"], lw=1.2, ls=(0, (3, 3)), zorder=1)
n_by = {}; Q = {}
for c, nm in names.items():
    X = C.values[L.k3.values == c]; q25, q50, q75 = np.percentile(X, [25, 50, 75], 0)
    n_by[nm] = len(X); Q[nm] = (q25, q50, q75)
    if nm == 'spread out':                         # only the key band is filled, in its own tint
        a.fill_between(u, q25, q75, color=ja.C["tint_model"], lw=0, zorder=0.5)
    else:                                          # the others: thin IQR edges in their own color
        for q in (q25, q75):
            a.plot(u, q, color=ja.C[ROLE[nm]], lw=0.9, ls=(0, (1, 2.5)), zorder=2)
    ja.line(a, u, q50, ROLE[nm], lw=3, zorder=3)
a.set_xlim(0, 1); a.set_ylim(0, 1.03)
a.set_yticks([0, 0.25, 0.5, 0.75, 1]); a.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
a.set_xticks([0, 0.25, 0.5, 0.75, 1]); a.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
# cluster labels, placed from the curves: front-loaded top left; spread out between the shaded band and the
# back-loaded path (x 45% to 85%); back-loaded just under its own path (x 42% to 75%)
xs = np.linspace(0.45, 0.85, 40)
lo_band, hi_back = np.interp(xs, u, Q['spread out'][0]).min(), np.interp(xs, u, Q['back-loaded'][1]).max()
xb = np.linspace(0.42, 0.75, 40)
pos = {'front-loaded': (0.04, 0.985), 'spread out': (0.45, (lo_band + hi_back) / 2),
       'back-loaded': (0.42, max(0.035, np.interp(xb, u, Q['back-loaded'][1]).min() - 0.055))}
if WIN.IS_ATLAS and n_by['spread out'] == 6479:          # the published atlas layout
    pos = {'front-loaded': (0.04, 0.985), 'spread out': (0.45, 0.33), 'back-loaded': (0.16, 0.15)}
for nm, (x_, y_) in pos.items():
    t = ja.label_at(a, x_, y_, f"{nm} {n_by[nm]:,}", ROLE[nm], dy=0, ha="left", size=LB); t.set_bbox(None); t.set_va("center")
ja.panel_title(a, "fill path, median  (IQR: shade, dotted)", size=LB)
a.set_xlabel("elapsed share of duration, %", **AX); a.set_ylabel("share of metaorder filled, %", **AX)

# right: impact coefficient by group
groups = ['single order', '2-3 orders', 'front-loaded', 'spread out', 'back-loaded']
yy = np.arange(len(groups))[::-1]
for off, tag in ((0.17, 'ex_top'), (-0.17, 'top_only')):
    for y, g in zip(yy, groups):
        r = R[tag][g]['Y_i0']; col = ja.C[ROLE[g]]
        b.plot([r['lo'], r['hi']], [y + off] * 2, color=col, lw=1.6, zorder=2)
        hollow = tag == 'top_only'
        b.plot(r['Y'], y + off, marker="s" if hollow else "o", ms=8, mfc=ja.C["ground"] if hollow else col,
               mec=col, mew=2, ls="none", zorder=3)
        b.text(r['hi'] + 0.06, y + off, f"{r['Y']:.2f}", va="center", fontsize=LB - 1, color=ja.C["muted"], family=ja.MONO)
b.set_yticks(yy); b.set_yticklabels(groups, fontsize=LB); b.set_ylim(-0.6, len(groups) - 0.4)
b.set_xlim(0, max(2.2, max(R[t][g]['Y_i0']['hi'] for t in ('ex_top', 'top_only') for g in groups) + 0.35)); b.set_xticks([0, 0.5, 1, 1.5, 2]); b.grid(True, axis="x"); b.grid(False, axis="y")
sp = R['ex_top']['spread out']['Y_i0']
ja.signal(b, sp['Y'], 1 + 0.17, label=None, ms=0)
ja.label_at(b, 1.6, 4.25, "filled: other accounts", "ink", dy=-4, ha="center", size=LB)
ja.label_at(b, 1.6, 3.8, "hollow: largest taker", "muted", dy=-4, ha="center", size=LB)
shp = [R['ex_top'][g]['Y_i0'] for g in ('front-loaded', 'spread out', 'back-loaded')]
overlap = max(r['lo'] for r in shp) < min(r['hi'] for r in shp)
ja.label_at(b, 1.6, 3.35, "shape CIs overlap" if overlap else "shape CIs do not all overlap", "muted", dy=-4, ha="center", size=LB)
ja.panel_title(b, "Y by group, 95% CI, hour-block bootstrap", size=LB)
b.set_xlabel("impact Y, I/sigma = Y sqrt(Q/V)", **AX); b.set_ylabel("metaorder group", **AX)

ab, aw = S['ari_boot']['3'][1], S['ari_week']['3']
ylo, yhi = min(r['Y'] for r in shp), max(r['Y'] for r in shp)
# atlas published 0.68 to 1.23 with a tie-dependent metaorder order; with the stable order (order_id tie-break) it is 0.65 to 1.20
WIN.expect("metaorder shape Y range (other accounts)", [round(ylo, 2), round(yhi, 2)], [0.65, 1.20])
yr = f"Y {ylo:.2f} to {yhi:.2f}"
ja.finish(fig, f"Execution shape barely moves impact: {yr}" if overlap else f"Execution shape and impact: {yr}", hl=yr,
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {len(L):,} multi-child metaorders",
          source=f"Data: Hydromancer Reservoir / node data. DTW k-medoids, k=3: bootstrap ARI {ab:.2f}, "
                 f"{'week to week' if WIN.IS_ATLAS else 'first vs second half'} {aw:.2f}.")
ja.save(fig, "out/metaorder.png")
