import json, matplotlib, numpy as np
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys as _sys; _sys.path.insert(0, "scripts")
import window as _WIN
_WIN.atlas_only("charts/ofi.py")   # first-version figure: its text describes the atlas window
O = "data/derived/ofi"
r = json.load(open(f"{O}/ofi_res.json")); g = json.load(open(f"{O}/gap_res.json"))
HZ = ["1", "5", "10", "30", "60", "300"]; xl = ["1s", "5s", "10s", "30s", "1m", "5m"]; x = np.arange(len(HZ))
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.parse_math": False, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF})
fig, (a, b) = plt.subplots(1, 2, figsize=(12, 6.75), dpi=200)
fig.subplots_adjust(left=0.07, right=0.97, top=0.76, bottom=0.22, wspace=0.22)
for ax in (a, b):
    ax.set_xticks(x, xl); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.set_xlabel("Bin length h")
h = r["h"]
hh = HZ[:5]; xi = x[:5]
med = [100 * h[k]["cont_halfhour_r2_median"] for k in hh]
lo = [100 * h[k]["cont_halfhour_r2_iqr"][0] for k in hh]; hi = [100 * h[k]["cont_halfhour_r2_iqr"][1] for k in hh]
a.fill_between(xi, lo, hi, color=C1, alpha=0.15, lw=0)
a.plot(xi, med, color=C1, lw=2, marker="o", ms=5, label="OFI, beta refit every half hour (median, IQR)")
a.plot(x, [100 * h[k]["cont_ofi_r2"] for k in HZ], color=C2, lw=2, marker="o", ms=5, label="OFI / trailing depth, one pooled beta")
a.plot(x, [100 * h[k]["cont_ti_r2"] for k in HZ], color=C3, lw=2, marker="o", ms=5, label="Signed taker volume, one pooled beta")
a.set_ylabel("R² of mid return on same-bin flow (%)"); a.set_ylim(0, 75)
a.set_title("Same bin: OFI explains price moves, trades alone do not", loc="left", fontsize=12, color=INK)
a.legend(frameon=False, loc="upper left", fontsize=9, labelcolor=INK2)
b.axhline(0, color=INK2, lw=1)
CLIP = -3
for i, k in enumerate(HZ):
    dv = np.array(h[k]["oos_ofi_r2_days"]) * 100
    jit = np.linspace(-0.18, 0.18, len(dv))
    b.scatter(x[i] + jit, np.maximum(dv, CLIP), s=14, color="#8a8984", zorder=2, lw=0)
b.plot(x, [100 * h[k]["oos_ofi_r2"] for k in HZ], color=C1, lw=2, marker="o", ms=6, zorder=3, label="Lagged OFI, all 13 test days pooled")
b.plot(x, [100 * h[k]["oos_lagret_r2"] for k in HZ], color=C2, lw=2, marker="o", ms=5, ls="--", zorder=3, label="Lagged mid return only")
b.scatter([], [], s=14, color="#8a8984", label="Lagged OFI, single test day")
b.set_ylim(CLIP - 0.3, 3.2); b.set_ylabel("Out-of-sample R² of next-bin mid return (%)")
b.text(x[0] + 0.25, CLIP + 0.05, "Dots at -3% are clipped; most are Sat Oct 10 (as low as -78%)", fontsize=8.5, color=INK2, va="bottom")
b.set_title("Next bin: about 1% at 1 second, nothing past 10 seconds", loc="left", fontsize=12, color=INK)
b.legend(frameon=False, loc="upper right", fontsize=9, labelcolor=INK2)
fig.text(0.07, 0.94, "Order flow imbalance on Hyperliquid's S&P 500 perp: descriptive, not predictive", fontsize=16, weight="bold", color=INK)
fig.text(0.07, 0.895, f"OFI (Cont, Kukanov and Stoikov 2014) lines up with same-bin mid moves about as well as in equities when the slope is refit often.\nAs a forecast it is close to zero: 1.3% out-of-sample at 1s, falling to {100*g['1s_gap250ms']:.1f}% with a 250 ms delay, and no edge at 10s or longer.", fontsize=11, color=INK2, va="top")
foot = (f"xyz:SP500, Oct 8 to 21, 2026 (14 days). {r['n_l1_states']:,} top-of-book states replayed from order-level data (prices match the 1-minute L2 snapshots ~100%, sizes 91 to 98% of snapshots\n"
        f"on most days, 65% on Sun Oct 11). Bins are non-overlapping UTC intervals: {h['1']['n_bins']:,} at 1s down to {h['300']['n_bins']:,} at 5m. OFI and the mid use only book states before each bin edge.\n"
        "Out-of-sample: fit on all earlier days, score the next day (13 test days), R² against a zero forecast. Gross of spread and fees.\n"
        "Source: Hydromancer Reservoir / node data.  Analysis: @justinalick")
fig.text(0.07, 0.03, foot, fontsize=8.2, color=INK2, va="bottom", linespacing=1.45)
fig.savefig(f"{O}/sp500_ofi.png")
