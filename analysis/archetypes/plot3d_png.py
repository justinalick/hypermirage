"""Static 3-D preview of the interactive page (same embedding, fixed camera)."""
import json, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
O = "data/derived/archetypes"
D = json.load(open(f"{O}/plot3d_data.json")); R = D['rows']; N = np.array(D['null'])
SURF, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
COL = {'maker': "#2a78d6", 'ui': "#eb6834", 'api': "#1baf7a", 'noise': "#c9c8c2"}
LAB = {'maker': 'Post-only makers', 'api': 'API-routed takers', 'ui': 'Builder / front-end takers', 'noise': 'Unassigned (noise)'}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "figure.facecolor": SURF, "text.parse_math": False})
fig = plt.figure(figsize=(16, 7.6), dpi=160)
a = fig.add_axes([0.0, 0.08, 0.5, 0.78], projection='3d'); b = fig.add_axes([0.5, 0.08, 0.5, 0.78], projection='3d')
for g in ['noise', 'api', 'ui', 'maker']:
    r = np.array([x[:3] for x in R if x[4] == g])
    a.scatter(r[:,0], r[:,1], r[:,2], s=5 if g == 'noise' else 8, c=COL[g], depthshade=False, lw=0,
              label=f"{LAB[g]}: {D['summ'][g][0]} accts, {D['summ'][g][1]}% of notional")
big = np.bincount(N[N[:,3] >= 0, 3].astype(int)).argmax()
m = (N[:,3] == big) | (N[:,3] < 0)
b.scatter(N[m,0], N[m,1], N[m,2], s=5, c="#8a8984", depthshade=False, lw=0, label="Main blob")
b.scatter(N[~m,0], N[~m,1], N[~m,2], s=8, c=COL['ui'], depthshade=False, lw=0, label="Split-off fake clusters")
for ax, t in ((a, "Real accounts, colored by group"), (b, f"Shuffled null: still {D['nnull']} clusters")):
    ax.set_facecolor(SURF); ax.view_init(elev=22, azim=-58)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis): axis.set_ticklabels([]); axis.pane.set_facecolor(SURF)
    ax.set_xlabel("UMAP 1", color=INK2); ax.set_ylabel("UMAP 2", color=INK2); ax.set_zlabel("UMAP 3", color=INK2)
    ax.set_title(t, loc="left", fontsize=12, color=INK)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.02, 0.0), fontsize=8.8, labelcolor=INK2, markerscale=2, ncol=2)
fig.text(0.02, 0.95, "xyz:SP500 trader archetypes in 3-D: two post-only maker groups, then a continuum of takers", fontsize=15, weight="bold", color=INK)
fig.text(0.02, 0.915, f"2026-10-08 to 2026-10-21 UTC, {D['n']:,} accounts with at least 30 fills, 19 standardized features, 3-D UMAP for display. "
         "Shuffled null = each feature permuted on its own. Source: Hydromancer Reservoir / node data.", fontsize=9.5, color=INK2)
fig.savefig(f"{O}/sp500_archetypes_3d.png")
