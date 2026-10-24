"""archetypes_3d in the @justinalick kit (night). Static 3-D UMAP still, real vs shuffled.
Data loading copied from analysis/archetypes/plot3d_png.py."""
import sys, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib, matplotlib.patches; matplotlib.use("Agg")
import justinalick as ja

O = "data/derived/archetypes"
D = json.load(open(f"{O}/plot3d_data.json")); R = D['rows']; N = np.array(D['null'])
fig, ax0 = ja.figure("wide", "night"); ax0.remove()
W, H = 1536, 864
C = ja.C
DIM = "#566772"                                      # dim grey for noise, below faint in lightness
COL = {'maker': C['actual'], 'api': C['model'], 'ui': C['faint'], 'noise': DIM}
LAB = {'maker': 'post-only makers', 'api': 'API-routed takers', 'ui': 'builder takers', 'noise': 'noise'}

def ax3(x):
    ax = fig.add_axes([x / W, 1 - (168 + 552) / H, 720 / W, 552 / H], projection='3d')
    ax.set_facecolor(C['ground']); ax.view_init(elev=22, azim=-58)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_ticklabels([]); axis.set_pane_color(matplotlib.colors.to_rgba(C['ground']))
        axis.pane.set_edgecolor(C['axis']); axis.line.set_color(C['axis'])
        axis._axinfo["grid"].update(color=C['grid'], linewidth=1)
        axis._axinfo["tick"].update(inward_factor=0, outward_factor=0)
    for l, s in (("UMAP 1", ax.set_xlabel), ("UMAP 2", ax.set_ylabel), ("UMAP 3", ax.set_zlabel)):
        s(l, color=C['muted'], family=ja.MONO, fontsize=10.5, labelpad=-8)
    return ax

a = ax3(24); b = ax3(792)
rows = {g: np.array([x[:3] for x in R if x[4] == g]) for g in ['noise', 'api', 'ui', 'maker']}
for g, r in rows.items():
    a.scatter(r[:, 0], r[:, 1], r[:, 2], s=5 if g == 'noise' else 7, c=COL[g], depthshade=False, lw=0)
big = np.bincount(N[N[:, 3] >= 0, 3].astype(int)).argmax()
m = (N[:, 3] == big) | (N[:, 3] < 0)
b.scatter(N[m, 0], N[m, 1], N[m, 2], s=5, c=C['faint'], depthshade=False, lw=0)
b.scatter(N[~m, 0], N[~m, 1], N[~m, 2], s=7, c=ja.PUNK['highlight'], depthshade=False, lw=0)

# the LED: centroid of the fast post-only quoters (the cluster with 62% of notional)
fq = np.array([x[:3] for x in R if x[4] == 'maker' and "2 s median rest" in x[5]])
cx, cy, cz = np.median(fq, axis=0)
a.plot([cx], [cy], [cz], marker="s", ms=0, mfc=C['signal'], mec=ja.PUNK['ink'], mew=1.5, ls="none", zorder=10)
assert len(fq) == 69
from mpl_toolkits.mplot3d import proj3d
x2, y2, _ = proj3d.proj_transform(cx, cy, cz, a.get_proj())
t = a.annotate("69 fast quoters, 62% of notional", (x2, y2), xytext=(-30, 46), textcoords="offset points",
               color=C['actual'], family=ja.MONO, fontsize=9.5, weight="semibold", zorder=11,
               bbox=dict(boxstyle="square,pad=0.2", fc=C['ground'], ec="none"),
               arrowprops=dict(arrowstyle="-", color=C['actual'], lw=1, shrinkA=0, shrinkB=8))

for ax, t in ((a, "real accounts, colored by group"), (b, f"shuffled null: still {D['nnull']} clusters")):
    ax.text2D(0.04, 1.0, t, transform=ax.transAxes, color=C['ink'], family=ja.MONO, fontsize=10.5, va="top")

def legend(items):
    for col, t, bold, xc, yc in items:
        fig.add_artist(matplotlib.patches.Rectangle((xc / W, 1 - (yc + 6) / H), 12 / W, 12 / H,
                                                    transform=fig.transFigure, fc=col, ec="none"))
        fig.text((xc + 22) / W, 1 - yc / H, t, color=C['faint'] if col == DIM else col, family=ja.MONO, fontsize=9.5, va="center",
                 weight="semibold" if bold else "regular")
S = D['summ']
lt = lambda g: f"{LAB[g]}: {S[g][0]:,} accts, {S[g][1]}%" + (" of notional" if g == 'maker' else "")
legend([(COL['maker'], lt('maker'), True, 48, 744), (COL['noise'], lt('noise'), False, 600, 744),
        (COL['api'], lt('api'), False, 48, 768), (COL['ui'], lt('ui'), False, 468, 768),
        (C['faint'], "main blob", False, 900, 744), (ja.PUNK['highlight'], "split-off fake clusters", False, 900, 768)])

ja.finish(fig, f"Only the post-only makers stand apart, with {S['maker'][1]}% of notional", hl=f"{S['maker'][1]}%",
          subtitle=f"xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, {D['n']:,} accounts",
          source="Data: Hydromancer Reservoir / node data. 3-D UMAP of 19 features; null shuffles each feature.")
ja.save(fig, "out/archetypes_3d.png")
