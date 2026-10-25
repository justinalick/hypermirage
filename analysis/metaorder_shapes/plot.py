"""Chart: execution-shape clusters (left) and impact coefficient by group (right)."""
import json, numpy as np, pandas as pd, matplotlib
import sys as _sys; _sys.path.insert(0, "scripts")
import window as _WIN
_WIN.atlas_only("charts/metaorder.py")   # first-version figure: its text describes the atlas window
matplotlib.use("Agg"); import matplotlib.pyplot as plt
O = "data/derived/metaorder_shapes"
C = pd.read_parquet(f"{O}/curves.parquet"); L = pd.read_parquet(f"{O}/labels.parquet"); R = json.load(open(f"{O}/impact.json"))
S = json.load(open(f"{O}/stability.json"))
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COL = {'front-loaded': "#eb6834", 'spread out': "#2a78d6", 'back-loaded': "#1baf7a"}
names = {0: 'front-loaded', 1: 'spread out', 2: 'back-loaded'}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.parse_math": False, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF})
fig, (a, b) = plt.subplots(1, 2, figsize=(13, 7), dpi=170, gridspec_kw=dict(width_ratios=[1, 1.15]))
fig.subplots_adjust(left=0.07, right=0.98, top=0.78, bottom=0.2, wspace=0.42)
for ax in (a, b):
    ax.grid(color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
u = np.linspace(0, 1, C.shape[1])
for c, nm in names.items():
    X = C.values[L.k3.values == c]; q25, q50, q75 = np.percentile(X, [25, 50, 75], 0)
    a.fill_between(u, q25, q75, color=COL[nm], alpha=0.15, lw=0)
    a.plot(u, q50, color=COL[nm], lw=2.2)
    a.text(1.02, q50[-4] if nm != 'back-loaded' else 0.12, f"{nm}\n{len(X):,}", color=INK2, fontsize=10, va='center',
           transform=a.transData)
a.plot([0, 1], [0, 1], color=INK2, lw=1, ls=(0, (3, 3)))
a.set_xlim(0, 1.0); a.set_ylim(0, 1.02); a.set_xlabel("Elapsed share of metaorder duration"); a.set_ylabel("Cumulative share of notional filled")
a.set_title("Median fill path per cluster (band = 25th-75th pct)", loc='left', fontsize=11.5, color=INK)
groups = ['single order', '2-3 orders', 'front-loaded', 'spread out', 'back-loaded']
yy = np.arange(len(groups))[::-1]
for off, tag, mk, lab in [(0.17, 'ex_top', 'o', 'All other accounts'), (-0.17, 'top_only', 's', 'Largest taker account')]:
    for y, g in zip(yy, groups):
        r = R[tag][g]['Y_i0']; c = COL.get(g, INK2)
        b.errorbar(r['Y'], y + off, xerr=[[r['Y'] - r['lo']], [r['hi'] - r['Y']]], color=c, marker=mk, ms=8, mec=SURF if tag == 'ex_top' else c, mew=1.5 if tag == 'ex_top' else 2,
                   lw=0, elinewidth=1.6, mfc=c if tag == 'ex_top' else SURF)
        b.text(r['hi'] + 0.05, y + off, f"{r['Y']:.2f}  n={r['n']:,}", va='center', fontsize=9, color=INK2)
b.set_yticks(yy); b.set_yticklabels(groups); b.set_xlim(0, 2.6)
b.set_xlabel("Impact coefficient Y in I/sigma = Y sqrt(Q/V)\n95% CI, hour-block bootstrap")
b.set_title("Impact by group. Filled = all other accounts, hollow = largest taker", loc='left', fontsize=11.5, color=INK)
sil = S['silhouette']; ab = S['ari_boot']
fig.text(0.07, 0.95, "Execution shape barely separates metaorders, and does not separate their impact", fontsize=16, color=INK, weight='bold')
fig.text(0.07, 0.905, f"xyz:SP500 taker metaorders, 2026-10-08..21 (14 days). 13,393 metaorders with 4+ child orders clustered by banded DTW (10%) k-medoids, k=3.",
         fontsize=10.5, color=INK2)
fig.text(0.07, 0.875, f"Stability: silhouette {sil['2']:.2f} (k=2), {sil['3']:.2f} (k=3), <0.30 for k>=4. Bootstrap ARI median {ab['3'][1]:.2f}, min {ab['3'][0]:.2f} at k=3; k>=4 unstable. "
         " ", fontsize=10.5, color=INK2)
fig.text(0.07, 0.06, "Impact I = signed mid move from before first fill to 0.25 s after last fill; Q/V = notional / day taker notional; sigma = daily vol. Q/V >= 1e-5 only.\n"
         "Native TWAPs (399) fall 81% in 'spread out'. Source: Hydromancer Reservoir / node data.", fontsize=9, color=INK2)
fig.savefig(f"{O}/sp500_metaorder_shapes.png")
