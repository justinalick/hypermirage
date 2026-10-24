"""Regime chart: day x UTC-minute raster of HMM states (K=3), state profiles, transition matrix, session mix."""
import json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

D = "data/derived/regimes"
f = pd.read_parquet(f"{D}/states_K3.parquet")
r3 = json.load(open(f"{D}/regimes_K3.json")); r2 = json.load(open(f"{D}/regimes_K2.json"))
S = json.load(open(f"{D}/fit_summary.json"))["stability"]
SURF, INK, INK2, MUTE, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
COL = ["#eb6834", "#2a78d6", "#1baf7a"]  # thin, open-calm, open-active
NAME = ["Thin (futures closed)", "Deep, calm", "Deep, active"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID, "figure.facecolor": SURF,
                     "axes.facecolor": SURF})

fig = plt.figure(figsize=(13, 9.6))
gs = fig.add_gridspec(2, 3, height_ratios=[1.35, 1], hspace=0.42, wspace=0.62, left=0.115, right=0.97, top=0.86, bottom=0.14)
fig.text(0.115, 0.955, "xyz:SP500 book regimes follow the CME clock, to the minute", fontsize=16, weight="bold")
fig.text(0.115, 0.925, "3-state Gaussian HMM on per-minute depth (10 bps), spread, L1 imbalance, 5-min realized vol. "
         "14 days, 2026-10-08 to 10-21 UTC, 20,151 minutes, 2 weekends.", fontsize=10, color=INK2)
fig.text(0.115, 0.902, " ", fontsize=10, color=INK2, style="italic")

# A: raster
ax = fig.add_subplot(gs[0, :])
f["day"] = f.t.dt.normalize(); days = sorted(f.day.unique())
grid = np.full((len(days), 1440), np.nan)
for i, d in enumerate(days):
    s = f[f.day == d]
    grid[i, (s.t.dt.hour * 60 + s.t.dt.minute).to_numpy()] = s.state.to_numpy()
ax.imshow(grid, aspect="auto", cmap=ListedColormap(COL), vmin=-0.5, vmax=2.5, interpolation="nearest",
          extent=[0, 24, len(days) - 0.5, -0.5])
ax.set_yticks(range(len(days))); ax.set_yticklabels([pd.Timestamp(d).strftime("%a %b %d") for d in days], fontsize=9)
ax.set_xticks(range(0, 25, 2)); ax.set_xlabel("UTC hour")
for x, lab in [(13.5, "US cash open 13:30"), (20, "close 20:00"), (21, "ES halt 21:00"), (22, "ES reopen 22:00")]:
    ax.axvline(x, color=INK, lw=0.8, ls=(0, (2, 2)), alpha=0.6)
ax.text(13.5, -0.9, "cash open", ha="center", fontsize=8.5, color=INK2)
ax.text(20, -0.9, "close ", ha="right", fontsize=8.5, color=INK2)
ax.text(21.0, -0.9, " ES halt", ha="left", fontsize=8.5, color=INK2)
ax.text(22.4, -0.9, "reopen", ha="left", fontsize=8.5, color=INK2)
for sp in ax.spines.values(): sp.set_visible(False)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COL]
ax.legend(handles, NAME, ncol=3, loc="upper left", bbox_to_anchor=(0, -0.09), frameon=False, fontsize=9.5)
ax.set_title("A  State by minute", loc="left", fontsize=11, weight="bold", pad=16)

# B: profiles
ax = fig.add_subplot(gs[1, 0])
prof = pd.DataFrame(r3["profile"])
metrics = [("depth10_musd", "Depth ±10 bps, $M"), ("spread_bps", "Spread, bps"), ("rv5_ann_pct", "5-min RV, ann. %"), ("abs_imb", "|L1 imbalance|")]
y = np.arange(len(metrics))
for k in range(3):
    vals = [prof.loc[k, m] / prof[m].max() for m, _ in metrics]
    ax.barh(y + (k - 1) * 0.26, vals, height=0.24, color=COL[k])
    for yi, (m, _) in zip(y, metrics):
        v = prof.loc[k, m]
        ax.text(vals[list(y).index(yi)] + 0.02, yi + (k - 1) * 0.26, f"{v:.2f}" if v < 10 else f"{v:.1f}", va="center", fontsize=8, color=INK2)
ax.set_yticks(y); ax.set_yticklabels([l for _, l in metrics]); ax.invert_yaxis()
ax.set_xlim(0, 1.3); ax.set_xticks([])
for sp in ax.spines.values(): sp.set_visible(False)
ax.set_title("B  Median by state (bar = share of max)", loc="left", fontsize=11, weight="bold")

# C: transition matrix (per minute) and dwell
ax = fig.add_subplot(gs[1, 1])
A = np.array(r3["A"])
ax.imshow(np.log10(A), cmap="Greys", vmin=-4, vmax=0.3)
for i in range(3):
    for j in range(3):
        ax.text(j, i, f"{100 * A[i, j]:.2f}%", ha="center", va="center", fontsize=9.5, color="white" if A[i, j] > 0.5 else INK)
lab = ["Thin", "Calm", "Active"]
ax.set_xticks(range(3)); ax.set_xticklabels(lab); ax.set_yticks(range(3))
ax.set_yticklabels([f"{l}\n~{1 / (1 - A[i, i]):.0f} min" for i, l in enumerate(lab)])
ax.set_xlabel("to (next minute)"); ax.set_ylabel("from  (mean dwell)")
for sp in ax.spines.values(): sp.set_visible(False)
ax.set_title("C  Transition probability per minute", loc="left", fontsize=11, weight="bold")

# D: session mix
ax = fig.add_subplot(gs[1, 2])
order = ["US cash", "ES overnight", "ES daily break", "futures closed (wknd)"]
nice = ["US cash\n13:30-20:00", "ES overnight", "ES daily break\n21-22 Mon-Thu", "Futures closed\nFri 21 - Sun 22"]
mins = r3["session_minutes"]
left = np.zeros(4)
for k in range(3):
    v = np.array([r3["session_mix"][s][str(k)] for s in order])
    ax.barh(range(4), v, left=left, color=COL[k], height=0.62, edgecolor=SURF, linewidth=2)
    left += v
ax.set_yticks(range(4)); ax.set_yticklabels([f"{n}\n{mins[s]:,} min" for n, s in zip(nice, order)], fontsize=8.5)
ax.invert_yaxis(); ax.set_xlim(0, 1); ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0", "50%", "100%"])
for sp in ax.spines.values(): sp.set_visible(False)
ax.set_title("D  Share of minutes by session", loc="left", fontsize=11, weight="bold")

fig.text(0.115, 0.004,
         f"Stability: thin vs deep split (K=2) agrees with fits on each week alone (ARI {S['2']['half_ari'][0]:.2f}, {S['2']['half_ari'][1]:.2f}); "
         f"the calm/active split (K=3) does not (ARI {S['3']['half_ari'][0]:.2f}, {S['3']['half_ari'][1]:.2f}). "
         f"\nSession alone predicts the K=2 state in {100 * r2['clock_hour_accuracy_lodo']:.1f}% of minutes.\n"
         "Depth: replayed displayed notional within 10 bps of mid (not executable size). Spread/imbalance: time-weighted replayed L1. Source: Hyperliquid node order statuses + Reservoir fills.",
         fontsize=8.5, color=MUTE)
fig.savefig(f"{D}/regimes.png", dpi=150)
fig.savefig(f"{D}/regimes@2x.png", dpi=300)
