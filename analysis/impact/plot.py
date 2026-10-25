"""Chart: square-root law check (left) and observed impact vs displayed-book walk (right)."""
import json, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
O = "data/derived/impact"
o = pd.read_parquet(f"{O}/orders.parquet"); o = o[~o.liq]
def meta(o, G=300):
    o = o.sort_values(['a', 't0', 'order_id'], kind='mergesort').reset_index(drop=True)
    o['mo'] = ((o.a != o.a.shift()) | (o.s != o.s.shift()) | ((o.t0 - o.t1.shift()) > G * 1e9)).cumsum()
    g = o.groupby('mo'); M = g.agg(q=('q', 'sum'), m0=('m0', 'first'), s=('s', 'first'), t0=('t0', 'min'), sig=('sig_d_bps', 'first'), V=('V_d', 'first'))
    last = o.loc[g.t1.idxmax().values]
    M['i0'] = M.s * (last.m0.values * (1 + last.s.values * last.i0.values / 1e4) - M.m0) / M.m0 * 1e4
    return M.dropna(subset=['i0'])
top = o.groupby('a').q.sum().idxmax()
rng = np.random.default_rng(3)
def binned(M, e):
    x = (M.q / M.V).values; y = (M.i0 / M.sig).values; b = np.digitize(x, e) - 1
    hr = np.unique((M.t0 // (3600 * 10**9)).values, return_inverse=True)[1]; nh = hr.max() + 1
    S = np.zeros((nh, len(e) - 1)); C = np.zeros_like(S); X = np.zeros_like(S); k = (b >= 0) & (b < len(e) - 1)
    np.add.at(S, (hr[k], b[k]), y[k]); np.add.at(C, (hr[k], b[k]), 1); np.add.at(X, (hr[k], b[k]), x[k])
    d = rng.integers(0, nh, (1000, nh)); bs = S[d].sum(1) / C[d].sum(1)
    n = C.sum(0); g = n >= 100
    return X.sum(0)[g] / n[g], S.sum(0)[g] / n[g], np.nanpercentile(bs, 2.5, 0)[g], np.nanpercentile(bs, 97.5, 0)[g], int(n[g].sum())
e = np.logspace(-6, -2, 13)
rob = json.load(open(f"{O}/robust.json")); bw = json.load(open(f"{O}/bookwalk.json")); cmp = pd.DataFrame(rob['dollar_cmp'])
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.parse_math": False, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF})
fig, (a, b) = plt.subplots(1, 2, figsize=(13, 7), dpi=170)
fig.subplots_adjust(left=0.07, right=0.98, top=0.78, bottom=0.2, wspace=0.3)
for ax in (a, b):
    ax.set_xscale('log'); ax.set_yscale('log'); ax.grid(color=GRID, lw=0.8, which='major'); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
for sub, c, lab, key in [(meta(o[o.a != top]), C1, "Metaorders, all other accounts", 'meta_G300_ex_top1'),
                         (meta(o[o.a == top]), C2, "Metaorders, largest taker account", 'meta_G300_top1_only')]:
    x, y, lo, hi, n = binned(sub, e); g = y > 0
    a.errorbar(x[g], y[g], yerr=[y[g] - np.maximum(lo[g], 1e-4), hi[g] - y[g]], color=c, lw=0, elinewidth=1.2, marker='o', ms=7,
               mec=SURF, mew=1.5, label=f"{lab} (n={n:,}; fit n={rob[key]['n']:,}): exponent {rob[key]['delta']:.2f} [{rob[key]['delta_ci'][0]:.2f}, {rob[key]['delta_ci'][1]:.2f}]")
xx = np.logspace(-6, -2, 50)
for Y, ls in [(rob['meta_G300_ex_top1']['Y'], '-'), (rob['meta_G300_top1_only']['Y'], '--')]:
    a.plot(xx, Y * np.sqrt(xx), color=INK2, lw=1, ls=ls)
a.text(1.2e-2, rob['meta_G300_ex_top1']['Y'] * 0.1, f"sqrt law\nY={rob['meta_G300_ex_top1']['Y']:.2f}", color=INK2, fontsize=9, va='center')
a.text(1.2e-2, rob['meta_G300_top1_only']['Y'] * 0.1, f"Y={rob['meta_G300_top1_only']['Y']:.2f}", color=INK2, fontsize=9, va='center')
a.set_xlim(8e-7, 3e-2); a.set_ylim(1e-3, 0.3)
a.set_xlabel("Metaorder size / that day's volume  (Q/V)"); a.set_ylabel("Peak impact / daily volatility  (I / σ)")
a.set_title("Square-root law: roughly, with a lower exponent", loc="left", fontsize=12, color=INK)
a.legend(frameon=False, loc="upper left", fontsize=8.6, labelcolor=INK2)
k = (cmp.Q <= 1.01e6) & (cmp.Q >= 1e3)
c = cmp[k]
b.plot(c.Q, c.book_mean, color=INK2, lw=2, ls='--', label=f"Displayed top-20 book, eaten at once ({bw['n_side_snaps']:,} snapshot-sides)")
b.plot(c.Q, c.obs_order_i0, color=C3, lw=2, marker='o', ms=6, mec=SURF, label=f"Observed: single taker orders (n={int(c.n_ord.sum()):,})")
b.plot(c.Q, c.obs_meta_i0, color=C1, lw=2, marker='o', ms=6, mec=SURF, label=f"Observed: metaorders, all accounts (n={int(c.n_meta.sum()):,})")
b.set_xlabel("Signed taker notional, $"); b.set_ylabel("Mid move in the trade direction, bps")
b.set_title("Metaorders move price 2-6x more than the book walk", loc="left", fontsize=12, color=INK)
b.legend(frameon=False, loc="upper left", fontsize=8.6, labelcolor=INK2)
b.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v/1e3:,.0f}k" if v < 1e6 else f"${v/1e6:,.0f}M"))
b.set_ylim(0.01, 5)
from matplotlib.ticker import FuncFormatter, LogLocator
import sys as _sys; _sys.path.insert(0, "scripts")
import window as _WIN
_WIN.atlas_only("charts/impact.py")   # first-version figure: its text describes the atlas window
for ax in (a, b):
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
a.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"1e{int(round(np.log10(v)))}"))
fig.text(0.07, 0.94, "Price impact on Hyperliquid's S&P 500 perp (xyz:SP500)", fontsize=17, weight="bold", color=INK)
fig.text(0.07, 0.895, "Taker orders and same-account metaorders (same direction, gaps under 5 min), 2026-10-08 to 2026-10-21, 14 days. ", fontsize=10.5, color=INK2)
fig.text(0.07, 0.035, "Impact = mid 0.25 s after the last fill vs mid before the first fill (replayed book). Left: hour-block bootstrap 95% CIs, bins with n>=100; fits on Q/V 1e-5 to 1e-2.\n"
         "Right: book line is the mean mid shift if the 1m top-20 L2 is consumed with no refill; above ~$500k, 14-31% of snapshots lack the depth (biased low). Source: Hydromancer Reservoir / node data.",
         fontsize=8.5, color=INK2)
fig.savefig(f"{O}/sp500_impact.png")
