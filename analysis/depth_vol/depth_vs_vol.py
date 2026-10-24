"""Step 2: depth vs realized volatility for xyz:SP500, 2026-10-08..21, and the two-panel chart.

Input: per-minute depth table from minute_depth.py (t, mid, d5, d10, d25, d_all).
Output: depth_vs_vol_v2.png (1600x900) and @2x, plus the numbers printed to stdout.

Usage: .venv/bin/python depth_vs_vol.py MINUTES.parquet OUT_DIR [--depth d10]

Definitions
  return      r_t = 1e4 * ln(mid_t / mid_{t-1})                      (bps, 1-minute)
  vol         std(r) over the trailing 15 minutes (>= 12 present), x sqrt(365*1440) / 100
              = annualized %, 24/7 basis
  session     cash      Mon-Fri 13:30-20:00 UTC
              weekend   Fri 21:00 -> Sun 22:00 UTC (index futures closed)
              break     Mon-Thu 21:00-22:00 UTC (futures closed; left panel only)
              overnight everything else (futures open, cash closed)
  rel depth   ln(depth) - median ln(depth) for the same UTC hour (weekend hours separate),
              then minus the median of that for the same session and day (each weekend is one
              "day"). So minutes are compared only with the same hour and the same day.
  gap         top vs bottom vol decile (deciles within each session, or each weekend):
              exp(median rel | decile 9 - median rel | decile 0) - 1
  bands       90% bootstrap over days (1000 draws), decile edges fixed
  left panel  hourly medians of depth and vol; session at minute :30; rho on log-log
"""
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

src, out_dir = sys.argv[1], sys.argv[2].rstrip("/") + "/"
DEPTH = sys.argv[sys.argv.index("--depth") + 1] if "--depth" in sys.argv else "d10"
ANN = np.sqrt(365 * 1440) / 100

# ---------- data ----------
df = pd.read_parquet(src).sort_values("t").reset_index(drop=True)
assert len(df) == 20160 and (df.t.diff().dropna() == pd.Timedelta("1min")).all()
df["r"] = np.log(df.mid).diff() * 1e4
df["rv"] = df.r.rolling(15, min_periods=12).std() * ANN

dow, h = df.t.dt.day_of_week, df.t.dt.hour
mm = h * 60 + df.t.dt.minute
wk = ((dow == 4) & (h >= 21)) | (dow == 5) | ((dow == 6) & (h < 22))
brk = (dow < 4) & (h == 21)
cash = (dow < 5) & (mm >= 810) & (mm < 1200)
df["g"] = np.select([cash, wk, brk], ["cash", "weekend", "break"], "overnight")
df["hod"] = h.astype(str) + np.where(wk, "w", "d")
# day key: calendar date; a weekend is one block keyed by its Friday
fri = df.t - pd.to_timedelta((dow - 4) % 7, unit="D")
df["blk"] = np.where(wk, "W" + fri.dt.strftime("%m%d"), df.t.dt.strftime("%m%d"))

df["lnd"] = np.log(df[DEPTH])
df["rel"] = df.lnd - df.groupby("hod").lnd.transform("median")
d = df.dropna(subset=["rv"])
d = d[d.g != "break"].copy()
d["rel2"] = d.rel - d.groupby(["g", "blk"]).rel.transform("median")

# ---------- right panel: decile curves ----------
rng = np.random.default_rng(7)
pct = lambda v: np.expm1(v) * 100


def deciles(gg):
    q = pd.qcut(gg.rv.rank(method="first"), 10, labels=False)
    return gg.assign(q=q.values)


curves, gaps = {}, {}
for key, gg in [("cash", d[d.g == "cash"]), ("overnight", d[d.g == "overnight"])] + \
        [(k, x) for k, x in d[d.g == "weekend"].groupby("blk")]:
    gg = deciles(gg)
    c = gg.groupby("q").agg(rv=("rv", "median"), rel=("rel2", "median"))
    gaps[key] = pct(c.rel[9] - c.rel[0])
    if key in ("cash", "overnight"):
        days = gg.blk.unique()
        boot = []
        for _ in range(1000):
            s = pd.concat([gg[gg.blk == x] for x in rng.choice(days, len(days))])
            boot.append(s.groupby("q").rel2.median())
        B = pd.concat(boot, axis=1)
        c["lo"], c["hi"] = B.quantile(0.05, axis=1), B.quantile(0.95, axis=1)
        g9 = pct(B.loc[9] - B.loc[0])
        print(f"{key:10s} n={len(gg):5d} days={len(days):2d} gap {gaps[key]:+.1f}% "
              f"(90% CI {g9.quantile(0.05):+.1f} to {g9.quantile(0.95):+.1f})")
    else:
        print(f"{key:10s} n={len(gg):5d} gap {gaps[key]:+.1f}%")
    curves[key] = c

# ---------- left panel: hourly medians ----------
at30 = df[df.t.dt.minute == 30].set_index(df.t[df.t.dt.minute == 30].dt.floor("h")).g
hr = (df.dropna(subset=["rv"]).assign(hr=lambda x: x.t.dt.floor("h"))
      .groupby("hr").agg(dep=(DEPTH, "median"), rv=("rv", "median")).join(at30))
hr["g"] = hr.g.replace({"weekend": "closed", "break": "closed"})
hr = hr[hr.rv > 0]
rho = np.corrcoef(np.log(hr.rv), np.log(hr.dep))[0, 1]
print(f"left panel: {len(hr)} hours, rho {rho:+.3f}")

# ---------- chart ----------
SURF, INK, INK2, MUTE, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
COL = {"cash": "#2a78d6", "overnight": "#eb6834", "closed": "#1baf7a"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.facecolor": SURF, "figure.facecolor": SURF})
fig = plt.figure(figsize=(16, 9), dpi=100)
axL = fig.add_axes([0.065, 0.235, 0.40, 0.51])
axR = fig.add_axes([0.56, 0.235, 0.40, 0.51])


def vol_axis(ax):
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 40]))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}%"))
    ax.set_xlabel("Realized volatility, trailing 15 min (annualized)")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0, pad=6)


for g in ("closed", "overnight", "cash"):
    x = hr[hr.g == g]
    axL.scatter(x.rv, x.dep / 1e6, s=46, color=COL[g], alpha=0.85, edgecolor=SURF, lw=1.2, zorder=3)
b = np.polyfit(np.log(hr.rv), np.log(hr.dep), 1)
xx = np.geomspace(0.8, 45, 50)
axL.plot(xx, np.exp(np.polyval(b, np.log(xx))) / 1e6, color=INK2, lw=2, ls=(0, (5, 4)), zorder=4)
axL.text(32, np.exp(np.polyval(b, np.log(32))) / 1e6 * 1.22, f"all hours\nρ = {rho:+.2f}",
         color=INK2, ha="center", va="bottom", fontsize=12.5)
vol_axis(axL)
axL.set_xlim(0.6, 45)
axL.set_yscale("log")
axL.yaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 40]))
axL.yaxis.set_minor_locator(NullLocator())
axL.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}M"))
axL.set_ylim(0.8, 50)
axL.set_ylabel("Depth within ±10 bps of mid (hourly median)")
axL.set_title("Across hours: busier hours are deeper", loc="left", color=INK, fontsize=15,
              fontweight="bold", pad=12)

axR.axhline(0, color=MUTE, lw=1.2, zorder=2)
w1, w2 = sorted(k for k in curves if k.startswith("W"))
for k, col, ls in [("cash", COL["cash"], "-"), ("overnight", COL["overnight"], "-"),
                   (w1, COL["closed"], (0, (4, 3))), (w2, COL["closed"], "-")]:
    c = curves[k]
    if "lo" in c:
        axR.fill_between(c.rv, pct(c.lo), pct(c.hi), color=col, alpha=0.10, lw=0, zorder=1)
    axR.plot(c.rv, pct(c.rel), color=col, lw=2.4, ls=ls, zorder=3)
    axR.scatter(c.rv, pct(c.rel), s=56, color=col, edgecolor=SURF, lw=2, zorder=4)
vol_axis(axR)
axR.set_xlim(0.45, 45)
axR.set_ylim(-22, 38)
axR.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}%" if v else "0%"))
axR.set_ylabel("Depth vs. the same day and hour of day")
axR.set_title("Within a day: no consistent drop", loc="left", color=INK, fontsize=15,
              fontweight="bold", pad=12)
lab = lambda v: f"{v:+.0f}%".replace("-", "−")
axR.text(37, -5.5, f"Cash hours: {lab(gaps['cash'])}", color=INK, fontsize=12, ha="right", va="top")
axR.text(17, 10.5, f"Overnight: {lab(gaps['overnight'])}", color=INK, fontsize=12, va="center")
axR.text(0.55, -13, f"Weekend Oct 9–11 (dashed): {lab(gaps[w1])}", color=INK, fontsize=12, va="center")
axR.text(2.6, 31, f"Weekend Oct 16–18: {lab(gaps[w2])}", color=INK, fontsize=12, va="center")

handles = [Line2D([0], [0], marker="o", color=COL[g], lw=2.4, markersize=9, markeredgecolor=SURF)
           for g in ("cash", "overnight", "closed")]
fig.legend(handles, ["US cash hours", "Overnight (futures open)",
                     "Futures closed (weekend; left also daily break)"],
           loc="upper left", bbox_to_anchor=(0.06, 0.845), ncol=3, frameon=False, fontsize=13,
           labelcolor=INK, handlelength=2.2, columnspacing=2.2)
fig.text(0.065, 0.94, "Order book depth follows the clock, not volatility.", fontsize=23,
         fontweight="bold", color=INK)
fig.text(0.065, 0.865,
         "Hyperliquid xyz:SP500 perp. Across hours, depth and volatility rise together because US "
         "trading hours have more of both.\nCompared within the same day and hour, the most volatile "
         "minutes carry about the same depth as the calmest. One of two weekends is the exception.",
         fontsize=13, color=INK2)
foot = (f"Sample: 20,160 one-minute book snapshots, 2026-10-08 to 2026-10-21 UTC (14 days: 10 weekdays, "
        f"2 weekends). Left: {len(hr)} hourly medians, colored by session at :30.\n"
        "Depth: displayed bid + ask notional within ±10 bps of mid, from an order-level book replay. "
        "Vol: std of 1-min log mid returns, trailing 15 min, annualized (24/7).\n"
        "Right: vol deciles within each session; depth relative to the median for the same UTC hour, "
        "then to that day (or weekend). Labels: top vs. bottom decile. Bands: 90% bootstrap over days.\n"
        "Futures closed: Fri 21:00 to Sun 22:00 UTC plus the Mon to Thu 21:00 hour (break hours, "
        "480 min, are left out of the right panel).\n"
        "Source: Hydromancer Reservoir / node data.   @justinalick")
fig.text(0.065, 0.02, foot, fontsize=10.5, color=INK2, va="bottom", linespacing=1.5)
fig.savefig(out_dir + "depth_vs_vol_v2.png", dpi=100, facecolor=SURF)
fig.savefig(out_dir + "depth_vs_vol_v2@2x.png", dpi=200, facecolor=SURF)
