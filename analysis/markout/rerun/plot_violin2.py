import json, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys as _sys; _sys.path.insert(0, "scripts")
import window as _WIN
_WIN.atlas_only("charts/markouts_violin.py")   # first-version figure: its text describes the atlas window
S = "data/derived/markout/rerun"
d = json.load(open(f"{S}/hourly.json")); r = json.load(open(f"{S}/markout_res.json"))
SURF, INK, INK2, MUTE, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12, "text.parse_math": False,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.facecolor": SURF, "figure.facecolor": SURF})
B = [("lt10k", "< $10k", "Under $10k", "#2a78d6"), ("10k_100k", "$10k to $100k", "$10k to $100k", "#eb6834"),
     ("ge100k", ">= $100k", "$100k and over", "#1baf7a")]
Hs = [1, 10, 60]; HL = ["1s", "10s", "1m"]
YL = (-1.6, 1.6)
def kde(v, grid):
    bw = 1.06*min(v.std(), np.subtract(*np.percentile(v, [75, 25]))/1.34)*len(v)**-0.2
    z = (grid[:, None]-v[None, :])/bw
    return np.exp(-0.5*z*z).sum(1)/(len(v)*bw*np.sqrt(2*np.pi))
fig, axs = plt.subplots(1, 3, figsize=(12, 6.75), dpi=200, sharey=True)
fig.subplots_adjust(left=0.075, right=0.985, top=0.735, bottom=0.225, wspace=0.08)
for ax, (k, rk, lab, c) in zip(axs, B):
    ax.axhline(0, color=INK2, lw=1, zorder=1)
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s_ in ("top", "right", "left"): ax.spines[s_].set_visible(False)
    ax.tick_params(axis="y", length=0)
    nh = None; out_hi = out_lo = 0
    for i, h in enumerate(Hs):
        v = np.array(d[f"{k}_{h}"]); nh = len(v)
        lo_, hi_ = max(v.min(), YL[0]-0.5), min(v.max(), YL[1]+0.5)
        g = np.linspace(lo_, hi_, 400); dens = kde(v, g); dens = dens/dens.max()*0.36
        ax.fill_betweenx(g, i-dens, i+dens, color=c, alpha=0.28, lw=0, zorder=2)
        ax.plot(i-dens, g, color=c, lw=1.2, zorder=3); ax.plot(i+dens, g, color=c, lw=1.2, zorder=3)
        q1, med, q3 = np.percentile(v, [25, 50, 75])
        ax.add_patch(plt.Rectangle((i-0.035, q1), 0.07, q3-q1, facecolor=c, edgecolor="none", zorder=4))
        ax.plot([i-0.035, i+0.035], [med, med], color=SURF, lw=2, zorder=5)
        m, l, u = r[rk][str(h)]
        ax.errorbar(i+0.17, m, yerr=[[m-l], [u-m]], fmt="D", ms=6, color=INK, elinewidth=1.6, capsize=3.5, zorder=6)
        nhi, nlo = int((v > YL[1]).sum()), int((v < YL[0]).sum())
        if nhi: ax.text(i+0.12, YL[1]-0.04, f"↑{nhi}", ha="left", va="top", fontsize=9, color=MUTE)
        if nlo: ax.text(i+0.12, YL[0]+0.04, f"↓{nlo}", ha="left", va="bottom", fontsize=9, color=MUTE)
    ax.set_xticks(range(3), HL, fontsize=13); ax.set_xlim(-0.55, 2.55); ax.set_ylim(*YL)
    ax.set_title(lab, loc="left", fontsize=15, weight="bold", color=c, pad=24)
    ax.text(0, 1.02, f"{r['n_orders_by_bucket'][rk]:,} taker orders · {nh} hours", transform=ax.transAxes, fontsize=10, color=INK2)
axs[0].set_ylabel("Taker markout vs fill price (bps)")
fig.text(0.53, 0.165, "Time after fill", ha="center", fontsize=12, color=INK2)
# key, drawn once in the last panel
ax = axs[2]
fig.text(0.075, 0.945, "Small orders lead the price. Big orders pay to trade.", fontsize=21, weight="bold", color=INK)
fig.text(0.075, 0.895, "Hourly taker markouts on Hyperliquid's S&P 500 perp. Orders under $10k are ahead in 55% of hours at 1s and 67% at 10s.\nOrders of $100k and over pay more to cross and land below zero in a typical hour.", fontsize=11.5, color=INK2, va="top", linespacing=1.4)
foot = (f"How to read: each violin is the spread of hourly averages (notional-weighted, UTC hours with 5+ trades). Box = middle 50% of hours, white line = median hour.\n"
        f"Black diamond = pooled 14-day mean with 95% CI (bootstrap over 1-hour blocks). Arrows count hours beyond the axis range. Markout = mid at t minus fill price, in the taker's\n"
        f"direction; makers are the mirror image. Mid = best bid/ask replayed from order-level data at every block (about 70 ms), so 1s is exact.\n"
        f"Gross of fees. Average taker fee 0.78 bps including builder fees (exchange fee alone 0.58 bps). Orders under $10k pay 1.13 bps, so they end up about 1 bp underwater after fees.\n"
        f"xyz:SP500, Oct 8 to 21, 2026: {r['n_trades']:,} matched trades, ${r['notional']/1e9:.1f}B notional.   Source: Hydromancer Reservoir / node data.   Analysis: @justinalick")
fig.text(0.075, 0.022, foot, fontsize=8.2, color=INK2, va="bottom", linespacing=1.5)
fig.savefig(f"{S}/sp500_markouts_violin.png")
