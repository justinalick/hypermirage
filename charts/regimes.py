"""regimes in the @justinalick kit (night). Data loading copied from
analysis/regimes/chart.py (no HMM refit)."""
import sys, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib, matplotlib.patches; matplotlib.use("Agg")
from matplotlib.colors import ListedColormap, LinearSegmentedColormap
import justinalick as ja

D = "data/derived/regimes"
f = pd.read_parquet(f"{D}/states_K3.parquet")
r3 = json.load(open(f"{D}/regimes_K3.json")); r2 = json.load(open(f"{D}/regimes_K2.json"))
S = json.load(open(f"{D}/fit_summary.json"))["stability"]

fig, ax0 = ja.figure("wide_tall", "night"); ax0.remove()
W, H = 1536, 1344
C = ja.C
COL = [C['actual'], C['model'], C['muted']]          # thin, deep calm, deep active
NAME = ["thin (futures closed)", "deep, calm", "deep, active"]
LB = 10
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)

# ---- A: state by minute
ax = ja._px_axes(fig, 192, 240, 1296, 476)
f["day"] = f.t.dt.normalize(); days = sorted(f.day.unique())
grid = np.full((len(days), 1440), np.nan)
for i, d in enumerate(days):
    s = f[f.day == d]
    grid[i, (s.t.dt.hour * 60 + s.t.dt.minute).to_numpy()] = s.state.to_numpy()
ax.imshow(grid, aspect="auto", cmap=ListedColormap(COL), vmin=-0.5, vmax=2.5, interpolation="nearest",
          extent=[0, 24, len(days) - 0.5, -0.5])
ax.set_yticks(range(len(days)), [pd.Timestamp(d).strftime("%a %b %d") for d in days], fontsize=9.5)
ax.set_xticks(range(0, 25, 2)); ax.grid(False)
for sp in ax.spines.values(): sp.set_visible(False)
for x in (13.5, 20, 21, 22):
    ax.axvline(x, color=C['ground'], lw=1.5, ls=(0, (2, 2)))
for x, t, ha in [(13.5, "cash open", "center"), (19.9, "close", "right"), (21.0, "ES halt", "left")]:
    ax.text(x, -0.6, t, ha=ha, va="bottom", fontsize=9.5,
            color=C['muted'], family=ja.MONO)
ja.panel_title(ax, "HMM state by minute", size=LB).set_y(1.05)
ax.set_xlabel("UTC hour", loc="right", labelpad=2, **AX); ax.set_ylabel("day", **AX)
for i, (c, t) in enumerate(zip(COL, NAME)):
    xc = [192, 508, 728][i]; yc = 772
    fig.add_artist(matplotlib.patches.Rectangle((xc / W, 1 - (yc + 6) / H), 12 / W, 12 / H, transform=fig.transFigure,
                                                fc=c, ec="none"))
    fig.text((xc + 22) / W, 1 - yc / H, t, color=c, family=ja.MONO, fontsize=9.5, va="center",
             weight="semibold" if i == 0 else "regular")

RT, RH = 840, 296
# ---- B: medians by state
ax = ja._px_axes(fig, 264, RT, 312, RH)
prof = pd.DataFrame(r3["profile"])
metrics = [("depth10_musd", "depth ±10bps $M"), ("spread_bps", "spread bps"), ("rv5_ann_pct", "5m vol ann. %"),
           ("abs_imb", "|L1 imbalance|")]
y = np.arange(len(metrics))
for k in range(3):
    vals = [prof.loc[k, m] / prof[m].max() for m, _ in metrics]
    ax.barh(y + (k - 1) * 0.27, vals, height=0.24, color=COL[k])
    for yi, (m, _) in enumerate(metrics):
        v = prof.loc[k, m]
        ax.text(vals[yi] + 0.03, yi + (k - 1) * 0.27, f"{v:.2f}" if v < 10 else f"{v:.1f}", va="center",
                fontsize=8.5, color=COL[k], family=ja.MONO)
ax.set_yticks(y, [l for _, l in metrics], fontsize=9.5); ax.set_ylim(len(metrics) - 0.5, -0.5)
ax.set_xlim(0, 1.3); ax.set_xticks([]); ax.grid(False)
for sp in ax.spines.values(): sp.set_visible(False)
ax.annotate("median by state", (0, 1), xycoords="axes fraction", xytext=(-84, 8), textcoords="offset points",
            fontsize=LB, family=ja.MONO, color=C['ink'], va="bottom")
ja.x_caption(ax, "bar = share of the largest", size=9)
ax.set_ylabel("metric", **AX)

# ---- C: transition probability per minute
ax = ja._px_axes(fig, 760, RT, 312, RH)
A = np.array(r3["A"])
cmap = LinearSegmentedColormap.from_list("ja_seq", [C['panel'], C['model']])
ax.imshow(np.log10(A), cmap=cmap, vmin=-4, vmax=0, aspect="auto")
for i in range(3):
    for j in range(3):
        ax.text(j, i, f"{100 * A[i, j]:.2f}%", ha="center", va="center", fontsize=10, family=ja.MONO,
                color=C['ground'] if A[i, j] > 0.5 else C['ink'], weight="semibold" if i == j else "regular")
lab = ["thin", "calm", "active"]
ax.set_xticks(range(3), lab, fontsize=9.5)
ax.set_yticks(range(3), [f"{l}\n~{1 / (1 - A[i, i]):.0f} min" for i, l in enumerate(lab)], fontsize=9.5)
ax.grid(False)
for sp in ax.spines.values(): sp.set_visible(False)
ax.annotate("per-minute transitions", (0, 1), xycoords="axes fraction", xytext=(-48, 8), textcoords="offset points",
            fontsize=LB, family=ja.MONO, color=C['ink'], va="bottom")
ax.set_xlabel("to state", **AX); ax.set_ylabel("from state, mean dwell", **AX)

# ---- D: session mix
ax = ja._px_axes(fig, 1296, RT, 192, RH)
order = ["US cash", "ES overnight", "ES daily break", "futures closed (wknd)"]
nice = ["US cash\n13:30-20:00", "ES overnight", "ES daily break\n21-22 Mon-Thu", "futures closed\nFri 21-Sun 22"]
mins = r3["session_minutes"]
left = np.zeros(4)
for k in range(3):
    v = np.array([r3["session_mix"][s][str(k)] for s in order])
    ax.barh(range(4), v, left=left, color=COL[k], height=0.6, edgecolor=C['ground'], linewidth=1.5)
    left += v
ax.set_yticks(range(4), [f"{n}\n{mins[s]:,} min" for n, s in zip(nice, order)], fontsize=8.5)
ax.set_ylim(3.5, -0.5); ax.set_xlim(0, 1); ax.set_xticks([0, 0.5, 1], ["0", "50%", "100%"]); ax.grid(False)
for sp in ax.spines.values(): sp.set_visible(False)
wk = r3["session_mix"]["futures closed (wknd)"]["0"]
ja.signal(ax, wk, 3, label=f"{100 * wk:.1f}% thin", dx=-90, dy=14, size=9.5, ms=0, role="actual")
ax.set_xlabel("share of minutes, %", loc="right", **AX); ax.set_ylabel("session", **AX)
ax.annotate("state mix by session", (0, 1), xycoords="axes fraction", xytext=(-78, 8),
            textcoords="offset points", fontsize=LB, family=ja.MONO, color=C['ink'], va="bottom")

for yb, t in ((H - 100, f"Thin vs deep (2 states) holds on each week alone (ARI {S['2']['half_ari'][0]:.2f}, {S['2']['half_ari'][1]:.2f}) and session "
                        f"alone matches it in {100 * r2['clock_hour_accuracy_lodo']:.1f}% of minutes."),
              (H - 76, f"Calm vs active does not hold (ARI {S['3']['half_ari'][0]:.2f}, {S['3']['half_ari'][1]:.2f}). "
                       "Depth = displayed notional within 10 bps of mid. Two weekends only.")):
    fig.text(48 / W, 1 - yb / H, t, color=C['muted'], family=ja.MONO, fontsize=9.5, va="baseline")

ja.finish(fig, f"Regimes follow the CME clock: weekends {100 * wk:.1f}% thin", hl=f"{100 * wk:.1f}% thin",
          subtitle=f"xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, {r3['n_minutes']:,} minutes, 3-state HMM",
          source="Data: Hydromancer Reservoir / node data.")
ja.save(fig, "out/regimes.png")
