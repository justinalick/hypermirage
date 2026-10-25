"""xyz:SP500 price impact, @justinalick night. Data loading copied from
analysis/impact/plot.py (orders.parquet, robust.json, bookwalk.json)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter, NullFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

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
pooled_meta, pooled_ord = rob['meta_G300'], rob['orders_i0']        # verified pooled exponents 0.38 and 0.39

# ---------------------------------------------------------------- canvas
fig, ax0 = ja.figure("wide", "night"); ax0.remove()
LB = 11
L, pw, gapx, pwb = 120, 600, 128, 472            # right panel leaves ~180 px for end labels
a = ja._px_axes(fig, L, 216, pw, 504)
b = ja._px_axes(fig, L + pw + gapx, 216, pwb, 504)


def txt(ax, x, y, s, role, ha="left", va="center", bold=True, **kw):
    """Unboxed direct label (counted by ja.check)."""
    t = ax.text(x, y, s, ha=ha, va=va, color=ja.C[role], fontsize=LB, family=ja.MONO,
                weight="semibold" if bold else "regular", zorder=20, **kw)
    t._ja_label = True
    return t
for ax in (a, b):
    ax.set_xscale('log'); ax.set_yscale('log')
    ax.yaxis.set_minor_formatter(NullFormatter()); ax.xaxis.set_minor_formatter(NullFormatter())
    ax.tick_params(which="minor", length=0)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))

# left: metaorder impact vs Q/V
groups = [(meta(o[o.a != top]), "actual", 'meta_G300_ex_top1'), (meta(o[o.a == top]), "muted", 'meta_G300_top1_only')]
for sub, role, key in groups:
    x, y, lo, hi, n = binned(sub, e); g = y > 0
    a.errorbar(x[g], y[g], yerr=[y[g] - np.maximum(lo[g], 1e-4), hi[g] - y[g]], color=ja.C[role], lw=0, elinewidth=1.2,
               marker='s', ms=6, mec=ja.C["ground"], mew=1, zorder=4)
xx = np.logspace(-6, -2, 50)
for key, ls, role in (('meta_G300_ex_top1', '-', "actual"), ('meta_G300_top1_only', (0, (3, 3)), "muted")):
    a.plot(xx, rob[key]['Y'] * np.sqrt(xx), color=ja.C[role], lw=1.2, ls=ls, zorder=2, alpha=0.55)
a.set_xlim(8e-7, 2e-2); a.set_ylim(6e-4, 0.4)
a.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"1e{int(round(np.log10(v)))}"))
r1, r2 = rob['meta_G300_ex_top1'], rob['meta_G300_top1_only']
txt(a, 1.1e-6, 0.25, f"pooled {pooled_meta['delta']:.2f} [{pooled_meta['delta_ci'][0]:.2f}, {pooled_meta['delta_ci'][1]:.2f}],"
    f" single orders {pooled_ord['delta']:.2f}", "ink", bold=False)
txt(a, 1.1e-6, 0.062, f"largest taker {r2['delta']:.2f} [{r2['delta_ci'][0]:.2f}, {r2['delta_ci'][1]:.2f}]", "muted")
txt(a, 1.8e-2, 0.0015, f"all others {r1['delta']:.2f} [{r1['delta_ci'][0]:.2f}, {r1['delta_ci'][1]:.2f}]", "actual", ha="right")
txt(a, 1.8e-2, 0.00085, f"lines: square-root law, Y {r2['Y']:.2f} / {r1['Y']:.2f}", "faint", ha="right", bold=False)
ja.panel_title(a, "concave: fitted exponents" if pooled_meta["delta_ci"][1] < 1 else "fitted exponents", size=LB)
a.set_xlabel("metaorder size / day's volume (Q/V), log", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
a.set_ylabel("peak impact / daily vol, log", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

# right: observed vs displayed-book walk
k = (cmp.Q <= 1.01e6) & (cmp.Q >= 1e3)
c = cmp[k].reset_index(drop=True)
ja.line(b, c.Q, c.book_mean, "model", lw=2.5, ls=(0, (5, 3)))
ja.line(b, c.Q, c.obs_order_i0, "muted", lw=2.5)
ja.line(b, c.Q, c.obs_meta_i0, "actual", lw=3)
b.set_xlim(8e2, 1.25e6); b.set_ylim(0.01, 10)
b.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e3:,.0f}k" if v < 1e6 else f"${v/1e6:,.0f}M"))
xe = c.Q.iloc[-1] * 1.18                                       # labels just right of the line ends
txt(b, xe, c.obs_meta_i0.iloc[-1], f"metaorders\nn={int(c.n_meta.sum()):,}", "actual", linespacing=1.3)
txt(b, xe, c.book_mean.iloc[-1] * 1.12, "top-20 book", "model", va="bottom")
txt(b, xe, c.obs_order_i0.iloc[-1] * 0.95, f"single orders\nn={int(c.n_ord.sum()):,}", "muted", va="top", linespacing=1.3)
i10 = int(np.argmin(np.abs(c.Q - 1e4)))
ratio = c.obs_meta_i0 / c.book_mean                            # observed metaorder impact / displayed-book walk
r_small = ratio[c.Q <= 1.01e4].median(); r_mid = ratio[(c.Q >= 4.6e4) & (c.Q <= 3.2e5)].median()
r_lo = ratio[c.Q >= 1e4].min()
WIN.expect("impact vs book: under $10k, $50k-$300k, lowest", [round(r_small), int(r_mid), round(r_lo)], [6, 3, 2])
fx = (lambda v: f"{v:.0f}") if WIN.IS_ATLAS else (lambda v: f"{v:.1f}")
ja.label_at(b, c.Q[i10], c.obs_meta_i0[i10], rf"about {round(r_small)}x under \$10k", "actual", dy=48, ha="center", size=LB)  # LED removed on request
txt(b, 1e5, 0.045, rf"about {int(r_mid) if WIN.IS_ATLAS else fx(r_mid)}x at \$50k to \$300k", "ink", ha="center", bold=False)
txt(b, 1e5, 0.024, r"book biased low above ~\$500k", "faint", ha="center", bold=False)
ja.panel_title(b, "vs the book", size=LB)
b.set_xlabel("signed taker notional, log", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
b.set_ylabel("mid move with the trade, bps, log", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

rng_txt = f"{round(r_lo)} to {round(r_small)}x"
ja.finish(fig, f"Metaorders move price {rng_txt} more than the book", hl=rng_txt,
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {int(c.n_meta.sum()):,} metaorders (gaps < 5 min)",
          source="Data: Hydromancer Reservoir / node data. Impact = mid 0.25 s after last fill vs before first fill.")
ja.save(fig, "out/impact.png")
