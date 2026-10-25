import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys as _sys; _sys.path.insert(0, "scripts")
import window as _WIN
_WIN.atlas_only("charts/markouts.py")   # first-version figure: its text describes the atlas window
S = "data/derived/markout/rerun"
r = json.load(open(f"{S}/markout_res.json"))
H = ["0", "0.5", "1", "2", "5", "10", "20", "30", "60", "120", "300"]
xl = ["fill", "0.5s", "1s", "2s", "5s", "10s", "20s", "30s", "1m", "2m", "5m"]
x = list(range(len(H)))
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.usetex": False, "text.parse_math": False, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF,
    "figure.facecolor": SURF})
fig, (a, b) = plt.subplots(1, 2, figsize=(12, 6.75), dpi=200, sharey=False)
fig.subplots_adjust(left=0.07, right=0.98, top=0.76, bottom=0.235, wspace=0.22)
def curve(ax, d, color, label, sign=1, ls="-"):
    m = [sign*d[h][0] for h in H]; lo = [sign*d[h][1 if sign > 0 else 2] for h in H]; hi = [sign*d[h][2 if sign > 0 else 1] for h in H]
    ax.fill_between(x, lo, hi, color=color, alpha=0.15, lw=0)
    ax.plot(x, m, color=color, lw=2, ls=ls, marker="o", ms=4.5, label=label)
    return m
for ax in (a, b):
    ax.axhline(0, color=INK2, lw=1)
    ax.set_xticks(x, xl); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.set_xlabel("Time after fill")
a.set_ylabel("Markout vs fill price (bps, notional-weighted)")
mt = curve(a, r["all"], INK, "Taker")
mm = curve(a, r["all"], "#8a8984", "Maker", sign=-1, ls="--")
a.text(x[-1]+0.15, mt[-1], "Taker", color=INK, va="center", fontsize=10)
a.text(x[-1]+0.15, mm[-1], "Maker", color=INK2, va="center", fontsize=10)
a.set_xlim(-0.3, len(H)-0.2)
a.set_title("All fills: takers pay to cross, then the price follows them", loc="left", fontsize=12, color=INK)
cols = {"< $10k": "#2a78d6", "$10k to $100k": "#eb6834", ">= $100k": "#1baf7a"}
lab = {"< $10k": "Under $10k", "$10k to $100k": "$10k to $100k", ">= $100k": "$100k and over"}
for k, c in cols.items():
    m = curve(b, r[k], c, f"{lab[k]} ({r['n_orders_by_bucket'][k]:,} orders)")
b.set_title("Taker markout by taker order size", loc="left", fontsize=12, color=INK)
b.legend(frameon=False, loc="lower right", fontsize=9.5, labelcolor=INK2)
ylo = min(a.get_ylim()[0], b.get_ylim()[0]); yhi = max(a.get_ylim()[1], b.get_ylim()[1])
for ax in (a, b): ax.set_ylim(ylo, yhi)
fig.text(0.07, 0.94, "Who is informed on Hyperliquid's S&P 500 perp?", fontsize=17, weight="bold", color=INK)
fig.text(0.07, 0.895, "Small taker orders see the price move their way within seconds. Orders of $100k and over pay the most\nto cross and only get back to about break-even after a minute or more.", fontsize=11.5, color=INK2, va="top")
n = r["n_trades"]; usd = r["notional"]/1e9
foot = (f"xyz:SP500, Oct 8 to 21, 2026 (14 days, {r['hours']} hours). {n:,} matched trades, ${usd:.1f}B notional. Markout = price change from the fill price to the mid at t, signed in the\n"
        "taker's direction (maker is the mirror image). 'fill' uses the mid just before the trade. Mid = best bid/ask replayed from order-level data at every block (about 70 ms),\n"
        "last change at or before t, so every horizon (0.5s and 1s included) is exact. Shaded bands: 95% CI, bootstrap over 1-hour blocks.\n"
        "Gross of fees. Average taker fee 0.78 bps including builder fees (exchange fee alone 0.58 bps). Orders under $10k pay 1.13 bps, so they end up about 1 bp underwater after fees.\n"
        "Source: Hydromancer Reservoir / node data.  Analysis: @justinalick")
fig.text(0.07, 0.035, foot, fontsize=8.3, color=INK2, va="bottom", linespacing=1.45)
fig.savefig(f"{S}/sp500_markouts.png")
