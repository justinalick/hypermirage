"""Descriptive version: named clusters, annotated null islands, Jaccard bars, feature-profile heatmap."""
import numpy as np, pandas as pd, json, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from sklearn.preprocessing import StandardScaler
O = "data/derived/archetypes"
d = np.load(f"{O}/plotdata.npz"); E1, E2, lab, lp, jac = d['E1'], d['E2'], d['lab'], d['lp'], d['jac']
rb = json.load(open(f"{O}/cluster_umap_res.json")); ra = json.load(open(f"{O}/cluster_res.json"))
f = pd.read_parquet(f"{O}/features.parquet"); f = f[f.n_orders.notna()].reset_index(drop=True)
X = pd.read_parquet(f"{O}/X.parquet").drop(columns='cl'); Z = StandardScaler().fit_transform(X)
rng2 = np.random.default_rng(9)  # same permutation as clusterwise.py
P = np.column_stack([rng2.permutation(Z[:, j]) for j in range(Z.shape[1])])
SURF, INK, INK2, INK3, GRID, GRAY = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#c9c8c2"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.parse_math": False, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF})
# names from each cluster's median feature profile (see clusterwise profile table in the note)
import sys; sys.path.insert(0, "analysis/archetypes")
from names import name_clusters
sys.path.insert(0, "scripts")
import window as WIN
import sys as _sys; _sys.path.insert(0, "scripts")
import window as _WIN
_WIN.atlas_only("charts/archetypes_v2.py")   # first-version figure: its text describes the atlas window
NAME, GRP = name_clusters(f, lab, WIN.N_DAYS)
COL = {'maker': C1, 'ui': C2, 'api': C3, 'noise': GRAY}
G = np.array([GRP.get(c, 'noise') for c in lab]); tot = f.notional.sum()
share = lambda m: 100*f.notional[m].sum()/tot
fig = plt.figure(figsize=(18, 14), dpi=160)
# A: real accounts
a = fig.add_axes([0.03, 0.56, 0.45, 0.30])
for k, t in [('noise', 'Unassigned (noise)'), ('api', 'API-routed takers'), ('ui', 'Builder / front-end takers'), ('maker', 'Post-only makers (2 clusters)')]:
    m = G == k
    a.scatter(E1[m, 0], E1[m, 1], s=9 if k != 'noise' else 6, c=COL[k], lw=0.3, edgecolors=SURF,
              label=f"{t}: {m.sum():,} accounts, {share(m):.0f}% of notional")
for c in range(lab.max()+1):
    x, y = np.median(E1[lab == c], axis=0)
    a.text(x, y, str(c+1), fontsize=8.5, weight="bold", color=INK, ha="center", va="center",
           bbox=dict(boxstyle="circle,pad=0.18", fc=SURF, ec=INK3, lw=0.6))
a.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.01), ncol=2, fontsize=8.6, labelcolor=INK2, markerscale=1.8)
a.set_title(f"A. Real accounts. Each dot is one account; numbered circles mark the {lab.max()+1} clusters (names in C)",
            loc="left", fontsize=11, color=INK)
# B: shuffled null
b = fig.add_axes([0.53, 0.56, 0.45, 0.30])
big = int(pd.Series(lp[lp >= 0]).value_counts().idxmax())
b.scatter(E2[:, 0], E2[:, 1], s=7, c=[INK3 if l == big or l < 0 else C2 for l in lp], lw=0)
Pdf = pd.DataFrame(P, columns=X.columns)
NICE = {'alo_share': 'high post-only share', 'net_flow_ratio': 'one-way net flow', 'twap_share': 'high TWAP share',
        'log_cancel_to_fill': 'high cancel-to-fill', 'trigger_share': 'high stop / TP share',
        'frontend_share': 'high front-end market share', 'maker_share': 'high maker share', 'log_rest_s': 'long rest time'}
for c in range(lp.max()+1):
    m = lp == c; x, y = np.median(E2[m], axis=0)
    if c == big: t = f"Main blob ({m.sum():,} accts):\nnothing unusual"
    else:
        top = Pdf[m].mean().abs().idxmax(); t = f"{m.sum()} accts:\n{NICE.get(top, top)}"
    b.annotate(t, (x, y), fontsize=8.6, color=INK, ha="center", va="center",
               bbox=dict(boxstyle="round,pad=0.3", fc=SURF, ec=INK3, lw=0.6, alpha=0.92))
b.set_title(f"B. Same pipeline on shuffled data still finds {lp.max()+1} clusters. Each island is one rare feature",
            loc="left", fontsize=11, color=INK)
b.text(0, -0.04, "Every feature was shuffled across accounts on its own, so no account is real and no features co-occur. "
       "Accounts that drew a rare\nnonzero value (most accounts have zero ALO, TWAP or one-way flow) still split off. "
       "Orange = split-off island, gray = main blob.", transform=b.transAxes, fontsize=8.6, color=INK2, va="top")
for ax_ in (a, b):
    ax_.set_xticks([]); ax_.set_yticks([]); [ax_.spines[s].set_visible(False) for s in ax_.spines]
# C: Jaccard per cluster
order = list(np.argsort(-jac))
c_ = fig.add_axes([0.30, 0.16, 0.205, 0.32])
yy = np.arange(len(order))
c_.barh(yy, jac[order], color=[COL[GRP[k]] for k in order], height=0.68)
for y, k in zip(yy, order):
    m = lab == k
    c_.text(jac[k]+0.01, y, f"{jac[k]:.2f}", va="center", fontsize=8.3, color=INK2)
c_.set_yticks(yy, [f"{k+1}. {NAME[k]}  (n={int((lab==k).sum())}, {share(lab==k):.0f}%)" for k in order], fontsize=8.6)
c_.invert_yaxis(); c_.set_xlim(0, 1)
for x, t in ((0.75, "stable"), (0.5, "dissolves")):
    c_.axvline(x, color=INK2, lw=0.9, ls=(0, (3, 3))); c_.text(x+0.01, len(order)-0.3, t, fontsize=8.3, color=INK2, va="bottom")
c_.set_xlabel("Stability: mean Jaccard overlap with the best-matching\ncluster after re-fitting on 30 bootstrap resamples")
c_.spines['top'].set_visible(False); c_.spines['right'].set_visible(False); c_.grid(axis='x', color=GRID, lw=0.8); c_.set_axisbelow(True)
c_.set_title(f"C. Only {int((jac>=0.7).sum())} of {len(jac)} clusters come close to stable; the rest dissolve", loc="right", fontsize=11, color=INK)
# D: feature profile heatmap (median z-score per cluster), same order as C
h = fig.add_axes([0.53, 0.16, 0.41, 0.32])
FN = {'log_notional': 'Total notional', 'maker_share': 'Maker share', 'log_med_order': 'Order size', 'log_cancel_to_fill': 'Cancel-to-fill',
 'log_rest_s': 'Rest time', 'log_dist_bps': 'Dist. from touch', 'has_resting': 'Has resting orders', 'alo_share': 'Post-only (ALO) share',
 'frontend_share': 'Front-end market share', 'trigger_share': 'Stop / TP share', 'builder_share': 'Builder-routed share', 'twap_share': 'TWAP share',
 'cash_share': 'US cash-hours share', 'weekend_share': 'Weekend share', 'hour_entropy': 'Spread across hours', 'days_active': 'Days active',
 'markout60': '60 s markout', 'log_turnover': 'Inventory turnover', 'net_flow_ratio': 'One-way net flow'}
M = pd.DataFrame(Z, columns=X.columns).groupby(lab).median().loc[order]
cmap = LinearSegmentedColormap.from_list("div", [C1, "#f0efec", C2])
im = h.imshow(M.values.clip(-3, 3), cmap=cmap, vmin=-3, vmax=3, aspect="auto")
h.set_xticks(range(M.shape[1]), [FN[c] for c in M.columns], rotation=55, ha="right", fontsize=8.3)
h.set_yticks(range(len(order)), [str(k+1) for k in order], fontsize=8.6)
for s in h.spines.values(): s.set_visible(False)
cb = fig.colorbar(im, cax=fig.add_axes([0.95, 0.16, 0.008, 0.32])); cb.set_label("Median z-score vs all accounts (clipped at ±3)", color=INK2); cb.outline.set_visible(False)
h.set_title("D. Same rows as C: what defines each cluster (mostly one order-type or routing flag)", loc="left", fontsize=11, color=INK)
fig.text(0.03, 0.955, "Do xyz:SP500 traders form distinct archetypes? Mostly no: two post-only maker groups, then a continuum of takers",
         fontsize=16, weight="bold", color=INK)
fig.text(0.03, 0.91, f"2026-10-08 to 2026-10-21 UTC. {len(f):,} accounts with at least 30 fills (of 11,528 with any fill). "
  "19 behavior features per account, standardized,\nreduced to 10 dimensions with UMAP, then clustered with HDBSCAN. A and B use a 2-D UMAP for display only; its axes have no units.", fontsize=9.5, color=INK2)
fig.text(0.03, 0.885, " Percentages are share of total notional traded in the window.", fontsize=9.5, color=INK2)
fig.text(0.03, 0.035, f"Robustness: HDBSCAN on the raw 19 features finds {ra['n_clusters']} clusters and leaves {100*ra['noise_share']:.0f}% of accounts "
  f"({ra['profiles'][0]['notional_share']*100:.0f}% of notional) as noise; {ra['boot_nclusters'].get('0', 0)} of 200 resamples find none. UMAP then HDBSCAN: overall bootstrap adjusted Rand index median {rb['boot_ari'][2]:.2f} "
  f"(5-95%: {rb['boot_ari'][0]:.2f} to {rb['boot_ari'][4]:.2f});\non 10 shuffled datasets it finds {min(a for a,_ in rb['null'])} to {max(a for a,_ in rb['null'])} clusters.", fontsize=8.6, color=INK2)
fig.text(0.03, 0.012, "One address is not one firm. Source: Hydromancer Reservoir / node data.", fontsize=8.6, color=INK2)
fig.savefig(f"{O}/sp500_archetypes_v2.png")
