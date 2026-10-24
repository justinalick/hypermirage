"""archetypes_v2 in the @justinalick kit (night). Data loading copied from
analysis/archetypes/plot2.py (no new fits)."""
import sys, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib, matplotlib.patches, matplotlib.patheffects as pe; matplotlib.use("Agg")
from matplotlib.colors import LinearSegmentedColormap
from sklearn.preprocessing import StandardScaler
import justinalick as ja

O = "data/derived/archetypes"
d = np.load(f"{O}/plotdata.npz"); E1, E2, lab, lp, jac = d['E1'], d['E2'], d['lab'], d['lp'], d['jac']
rb = json.load(open(f"{O}/cluster_umap_res.json")); ra = json.load(open(f"{O}/cluster_res.json"))
f = pd.read_parquet(f"{O}/features.parquet"); f = f[f.n_orders.notna()].reset_index(drop=True)
X = pd.read_parquet(f"{O}/X.parquet").drop(columns='cl'); Z = StandardScaler().fit_transform(X)
rng2 = np.random.default_rng(9)  # same permutation as clusterwise.py
P = np.column_stack([rng2.permutation(Z[:, j]) for j in range(Z.shape[1])])
sys.path.insert(0, O)
from names import name_clusters
NAME, GRP = name_clusters(f, lab)
G = np.array([GRP.get(c, 'noise') for c in lab]); tot = f.notional.sum()
share = lambda m: 100 * f.notional[m].sum() / tot

fig, ax0 = ja.figure("wide_tall", "night"); ax0.remove()
W, H = 1536, 1656                                   # custom tall canvas, 69 grid units
fig.set_size_inches(W / ja.DPI, H / ja.DPI)
C = ja.C
DIM = "#566772"                                      # dim grey for noise, below faint in lightness
COL = {'maker': C['actual'], 'api': C['model'], 'ui': C['faint'], 'noise': DIM}
TXT = {'maker': C['actual'], 'api': C['model'], 'ui': C['faint'], 'noise': C['faint']}
LB = 10
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)

def short(s):
    s = s.replace("Post-only makers (ALO quotes, ", "post-only makers, ").replace(" s median rest)", "s rest")
    s = s.replace("Builder takers, ", "builder: ").replace("Builder takers", "builder takers")
    s = s.replace("API takers, ", "API: ").replace("front-end market orders", "front-end mkt")
    return s

def bare(ax):
    ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for s in ax.spines.values(): s.set_visible(False)

# ---- A: real accounts
a = ja._px_axes(fig, 48, 216, 696, 480); bare(a)
for k in ('noise', 'ui', 'api', 'maker'):
    m = G == k
    a.scatter(E1[m, 0], E1[m, 1], s=7 if k != 'noise' else 5, c=COL[k], lw=0, zorder=2)
for c in range(lab.max() + 1):
    x, y = np.median(E1[lab == c], axis=0)
    a.text(x, y, str(c + 1), fontsize=9.5, weight="bold", color=C['ink'], ha="center", va="center",
           family=ja.MONO, zorder=5, path_effects=[pe.withStroke(linewidth=3.5, foreground=C['ground'])])
ja.panel_title(a, f"real accounts: one dot per account, {lab.max()+1} clusters numbered", size=LB)
leg = [('maker', 'post-only makers (2 clusters)'), ('api', 'API-routed takers'),
       ('ui', 'builder / front-end takers'), ('noise', 'unassigned (noise)')]
for i, (k, t) in enumerate(leg):
    m = G == k
    yc = 720 + 12 + i * 24
    fig.add_artist(matplotlib.patches.Rectangle((48 / W, 1 - (yc + 6) / H), 12 / W, 12 / H, transform=fig.transFigure,
                                                fc=COL[k], ec="none"))
    fig.text(72 / W, 1 - yc / H, f"{t}: {m.sum():,} accounts, {share(m):.0f}% of notional",
             color=TXT[k], family=ja.MONO, fontsize=9.5, weight="semibold" if k == 'maker' else "regular", va="center")

# ---- B: shuffled null
b = ja._px_axes(fig, 792, 216, 696, 480); bare(b)
big = int(pd.Series(lp[lp >= 0]).value_counts().idxmax())
isl = np.array([not (l == big or l < 0) for l in lp])
b.scatter(E2[~isl, 0], E2[~isl, 1], s=5, c=C['faint'], lw=0)
b.scatter(E2[isl, 0], E2[isl, 1], s=7, c=ja.PUNK['highlight'], lw=0)
Pdf = pd.DataFrame(P, columns=X.columns)
lo, hi = E2.min(0), E2.max(0); SPAN = hi - lo
b.set_xlim(lo[0] - 0.42 * SPAN[0], hi[0] + 0.12 * SPAN[0]); b.set_ylim(lo[1] - 0.16 * SPAN[1], hi[1] + 0.24 * SPAN[1])
NICE = {'alo_share': 'high post-only share', 'net_flow_ratio': 'one-way net flow', 'twap_share': 'high TWAP share',
        'log_cancel_to_fill': 'high cancel-to-fill', 'trigger_share': 'high stop / TP share',
        'frontend_share': 'high front-end share', 'maker_share': 'high maker share', 'log_rest_s': 'long rest time'}
LBL = {}
for c in range(lp.max() + 1):
    m = lp == c; x, y = np.median(E2[m], axis=0)
    if c == big:
        t, col = f"main blob, {m.sum():,} accts:\nnothing unusual", C['faint']
    else:
        top = Pdf[m].mean().abs().idxmax(); t, col = f"{m.sum()} accts:\n{NICE.get(top, top)}", ja.PUNK['highlight']
    ha = va = "center"
    if c == big:   # above the blob, right-aligned to its right edge, in the clear band
        x, y = np.percentile(E2[m, 0], 99), hi[1] + 0.03 * SPAN[1]; ha, va = "right", "bottom"
    else:   # push the label outward from the main blob, clear of the island
        bc = np.median(E2[lp == big], axis=0)
        u = (np.array([x, y]) - bc) / SPAN; u /= np.hypot(*u)
        r = np.percentile(np.hypot(*((E2[m] - [x, y]) / SPAN).T), 80) + 0.02
        x, y = np.array([x, y]) + u * r * SPAN
        ha = "left" if u[0] > 0.5 else "right" if u[0] < -0.5 else "center"
        va = "bottom" if u[1] > 0.5 else "top" if u[1] < -0.5 else "center"
        if va == "bottom":   # the island right above the blob: label to its left, so the band above stays free
            x, y = np.percentile(E2[m, 0], 1) - 0.02 * SPAN[0], np.median(E2[m, 1]); ha, va = "right", "center"
    LBL[c] = b.text(x, y, t, fontsize=9.5, color=col, ha=ha, va=va, family=ja.MONO, linespacing=1.3, zorder=5,
                    weight="regular" if c == big else "semibold")
ja.panel_title(b, f"same pipeline, shuffled data: still {lp.max()+1} clusters", size=LB)
fig.text(792 / W, 1 - 720 / H, "Each feature shuffled on its own, so no account is real.\n"
         "Accounts that drew a rare nonzero value still split\n"
         "off as islands (light); gray is the main blob.",
         color=C['muted'], family=ja.MONO, fontsize=9.5, va="top", linespacing=1.5)

# ---- C: Jaccard per cluster
order = list(np.argsort(-jac)); n = len(order); yy = np.arange(n)
RP = 32; RT = 876; RB = RT + RP * (n + 0.9)
c_ = ja._px_axes(fig, 600, RT, 408, RB - RT)
c_.barh(yy, jac[order], color=[COL[GRP[k]] for k in order], height=0.66, zorder=2)
for y, k in zip(yy, order):
    m = lab == k
    hi = k == order[1]
    c_.text(jac[k] + (0.06 if hi else 0.02), y, f"{jac[k]:.2f}  n={int(m.sum())}  {share(m):.0f}%", va="center",
            fontsize=8.5, color=C['actual'] if hi else C['muted'], family=ja.MONO, weight="semibold" if hi else "regular",
            bbox=dict(boxstyle="square,pad=0.15", fc=C['ground'], ec="none"), zorder=4)
c_.set_yticks(yy, [f"{k+1:>2} {short(NAME[k])}" for k in order], fontsize=8.5)
for tl, k in zip(c_.get_yticklabels(), order):
    tl.set_color(COL[GRP[k]] if GRP[k] == 'maker' else C['muted'])
c_.set_ylim(n + 0.4, -0.5); c_.set_xlim(0, 1.4)
c_.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0", ".25", ".5", ".75", "1"])
c_.grid(False)
for x, t, ha, dx in ((0.75, "stable", "left", 0.015), (0.5, "dissolves", "right", -0.015)):
    c_.axvline(x, color=C['faint'], lw=1, ls=(0, (2, 3)), zorder=1)
    c_.text(x + dx, n + 0.3, t, fontsize=8.5, color=C['faint'], family=ja.MONO, va="bottom", ha=ha)
k2 = order[1]; m2 = lab == k2
# LED removed on request: the bold 0.71 row already marks the headline point
# ja.signal(c_, jac[k2], 1, ms=10)
c_.annotate(f"{int((jac >= 0.7).sum())} of {n} clusters come close to stable", (0, 1), xycoords="axes fraction",
            xytext=(-276, 5), textcoords="offset points", fontsize=LB, family=ja.MONO, color=C['ink'], va="bottom")
c_.set_xlabel("mean Jaccard vs best match, 30 refits", **AX); c_.set_ylabel("cluster", **AX)

# ---- D: feature profile heatmap, same rows as C
FN = {'log_notional': 'Total notional', 'maker_share': 'Maker share', 'log_med_order': 'Order size', 'log_cancel_to_fill': 'Cancel-to-fill',
 'log_rest_s': 'Rest time', 'log_dist_bps': 'Dist. from touch', 'has_resting': 'Has resting orders', 'alo_share': 'Post-only share',
 'frontend_share': 'Front-end mkt share', 'trigger_share': 'Stop / TP share', 'builder_share': 'Builder-routed', 'twap_share': 'TWAP share',
 'cash_share': 'US cash hours', 'weekend_share': 'Weekend share', 'hour_entropy': 'Spread over hours', 'days_active': 'Days active',
 'markout60': '60 s markout', 'log_turnover': 'Turnover', 'net_flow_ratio': 'One-way net flow'}
M = pd.DataFrame(Z, columns=X.columns).groupby(lab).median().loc[order]
h = ja._px_axes(fig, 1048, RT, 380, RP * n)          # rows line up with C's bars
mix = lambda a_, b_, t_: tuple((1 - t_) * np.array(matplotlib.colors.to_rgb(a_)) + t_ * np.array(matplotlib.colors.to_rgb(b_)))
cmap = LinearSegmentedColormap.from_list("ja_div", [(0, C['model']), (1 / 3, mix(C['panel'], C['model'], 0.72)), (0.5, C['panel']),
                                                    (2 / 3, mix(C['panel'], C['actual'], 0.72)), (1, C['actual'])])
im = h.pcolormesh(np.arange(M.shape[1] + 1) - 0.5, np.arange(n + 1) - 0.5, M.values.clip(-3, 3), cmap=cmap, vmin=-3, vmax=3,
                  edgecolors=C['ground'], linewidth=1.5)
h.set_xlim(-0.5, M.shape[1] - 0.5); h.set_ylim(n - 0.5, -0.5)
h.set_xticks(range(M.shape[1]), [FN[c] for c in M.columns], rotation=90, fontsize=8.5)
h.set_yticks([]); h.grid(False)
h.set_xlabel("feature", **AX); h.set_ylabel("cluster, same rows as C", **AX, labelpad=6)
for s in h.spines.values(): s.set_visible(False)
h.annotate("what defines each row, median z", (0, 1), xycoords="axes fraction", xytext=(0, 5),
           textcoords="offset points", fontsize=LB, family=ja.MONO, color=C['ink'], va="bottom")
cax = ja._px_axes(fig, 1444, RT, 12, RP * n)
cb = fig.colorbar(im, cax=cax, ticks=[-3, 0, 3]); cb.outline.set_visible(False)
cb.ax.set_yticklabels(["-3", "0", "+3"]); cb.ax.tick_params(labelsize=9, colors=C['muted']); cb.ax.grid(False)

fig.text(48 / W, 1 - (H - 76) / H,
         f"Robustness: HDBSCAN on the raw features finds no clusters in {ra['boot_nclusters'].get('0', 0)} of 200 resamples; "
         f"UMAP then HDBSCAN bootstrap ARI median {rb['boot_ari'][2]:.2f}.",
         color=C['muted'], family=ja.MONO, fontsize=9.5, va="baseline")

ja.finish(fig, f"Only 2 of {n} trader archetypes hold up", hl=f"2 of {n}",
          subtitle=f"xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, {len(f):,} accounts with 30+ fills",
          source="Data: Hydromancer Reservoir / node data. One address is not one firm.")
ja.save(fig, "out/archetypes_v2.png")
