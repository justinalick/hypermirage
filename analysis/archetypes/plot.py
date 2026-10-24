import numpy as np, pandas as pd, json, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
O = "data/derived/archetypes"
d = np.load(f"{O}/plotdata.npz"); E1, E2, lab, lp, jac = d['E1'], d['E2'], d['lab'], d['lp'], d['jac']
rb = json.load(open(f"{O}/cluster_umap_res.json")); ra = json.load(open(f"{O}/cluster_res.json"))
f = pd.read_parquet(f"{O}/features.parquet"); f = f[f.n_orders.notna()].reset_index(drop=True); f['cl'] = lab
SURF, INK, INK2, GRID, GRAY = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#b5b4ae"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "text.parse_math": False, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF})
# coarse groups: post-only makers / builder-UI takers / other API flow
g = f.groupby('cl').agg(alo=('alo_share','median'), bld=('builder_share','median'))
def grp(c):
    if c < 0: return 'noise'
    if g.alo[c] > 0.5: return 'maker'
    if g.bld[c] > 0.5: return 'ui'
    return 'api'
G = np.array([grp(c) for c in lab])
tot = f.notional.sum()
lbl = {'maker': ('Post-only makers', C1), 'ui': ('Builder / front-end takers', C2), 'api': ('Other API takers', C3), 'noise': ('Unassigned (noise)', GRAY)}
fig, ax = plt.subplots(1, 3, figsize=(17, 6.4), dpi=170, gridspec_kw={"width_ratios": [1, 1, 1.25]})
fig.subplots_adjust(left=0.035, right=0.985, top=0.78, bottom=0.25, wspace=0.18)
a = ax[0]
for k in ['noise', 'api', 'ui', 'maker']:
    m = G == k; n = m.sum(); sh = f.notional[m].sum()/tot
    a.scatter(E1[m,0], E1[m,1], s=10 if k!='noise' else 7, c=lbl[k][1], lw=0.3, edgecolors=SURF, alpha=0.9,
              label=f"{lbl[k][0]}: {n:,} accts, {100*sh:.0f}% of notional")
a.set_title("Real accounts: one clear maker group, the rest fragments", loc="left", fontsize=11.5, color=INK)
a.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.08), ncol=2, fontsize=8.3, labelcolor=INK2, markerscale=1.6, columnspacing=1)
a = ax[1]
a.scatter(E2[lp<0,0], E2[lp<0,1], s=7, c=GRAY, lw=0)
a.scatter(E2[lp>=0,0], E2[lp>=0,1], s=10, c=INK2, lw=0.3, edgecolors=SURF)
a.set_title(f"Shuffled null: still {lp.max()+1} clusters, no noise", loc="left", fontsize=11.5, color=INK)
for a in ax[:2]:
    a.set_xticks([]); a.set_yticks([]); [a.spines[s].set_visible(False) for s in a.spines]
    a.set_xlabel("UMAP 1 (no units)"); a.set_ylabel("UMAP 2")
a = ax[2]
o = np.argsort(-jac); cols = [lbl[grp(k)][1] for k in o]
a.bar(range(len(o)), jac[o], color=cols, width=0.75)
for y, t in ((0.75, "stable (0.75)"), (0.5, "dissolved (0.5)")):
    a.axhline(y, color=INK2, lw=0.9, ls=(0,(3,3))); a.text(len(o)-0.4, y+0.015, t, ha="right", fontsize=8.3, color=INK2)
a.set_xticks(range(len(o)), [f"n={int((lab==k).sum())}\n{100*f.notional[lab==k].sum()/tot:.0f}%" for k in o], fontsize=7.4)
a.set_ylim(0, 1); a.set_ylabel("Mean best-match Jaccard over 30 bootstrap refits")
a.set_xlabel("UMAP+HDBSCAN cluster: accounts, share of notional (color = group at left)")
a.spines['top'].set_visible(False); a.spines['right'].set_visible(False); a.grid(axis='y', color=GRID, lw=0.8); a.set_axisbelow(True)
a.set_title("Two clusters sit at the stability line; most dissolve", loc="left", fontsize=11.5, color=INK)
fig.text(0.035, 0.93, "xyz:SP500 trader archetypes: weak structure", fontsize=16, weight="bold", color=INK)
fig.text(0.035, 0.875, f"2026-10-08 to 2026-10-21 UTC. {len(f):,} accounts with at least 30 fills, 19 standardized behavior features "
  "(maker share, size, cancel-to-fill, rest time, distance from touch, order types, hours, markout, turnover). ", fontsize=9.5, color=INK2)
fig.text(0.035, 0.06, f"HDBSCAN directly on the 19 features (min cluster 25): {ra['n_clusters']} clusters, {100*ra['noise_share']:.0f}% of accounts and "
  f"98% of notional left as noise; bootstrap ARI median {ra['boot_ari'][1]:.2f}, 5th pct {ra['boot_ari'][0]:.2f}. "
  f"UMAP(10d) then HDBSCAN: {rb['n_clusters']} clusters, bootstrap ARI median {rb['boot_ari'][2]:.2f} [5-95%: {rb['boot_ari'][0]:.2f}-{rb['boot_ari'][4]:.2f}].", fontsize=8.5, color=INK2)
fig.text(0.035, 0.025, "Shuffled null = each feature permuted independently (marginals kept, joint structure destroyed). Source: Hydromancer Reservoir / node data.", fontsize=8.5, color=INK2)
fig.savefig(f"{O}/sp500_archetypes.png")
print(G.tolist().count('maker'), {k: round(float(f.notional[G==k].sum()/tot),3) for k in lbl})
