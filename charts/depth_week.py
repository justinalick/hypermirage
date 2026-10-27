"""depth_week: median depth within 10 bps for each hour of the week, as one line, so the daily CME
break and the weekend show as drops. @justinalick kit, night, wide (16:9).
Data: data/derived/heatmap/depth_minutes_v2.parquet, column d10_net (same input as heatmap.py).
Run: .venv/bin/python charts/depth_week.py"""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter, FixedLocator
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

df = pd.read_parquet("data/derived/heatmap/depth_minutes_v2.parquet", columns=["t", "d10_net"])
s_ = WIN.session(df.t)                                  # holiday-aware CME / NYSE clock
sess = np.select([s_ == "break", s_ == "closed", s_ == "cash"], ["break", "weekend", "cash"], "other")
med = df.d10_net.groupby(sess).median() / 1e6
WIN.expect("depth_week medians $M: cash, break", [round(med["cash"], 1), round(med["break"], 1)], [15.4, 4.7])
wk = df[~df.t.dt.strftime("%Y-%m-%d").isin(WIN.HOLIDAYS)]  # regular weeks: holidays left out
g = wk.assign(dow=wk.t.dt.dayofweek + 1, h=wk.t.dt.hour).groupby(["dow", "h"]).d10_net
assert g.ngroups == 168
if WIN.IS_ATLAS:
    assert g.size().min() == g.size().max() == 120
OFF = int(WIN.utc_offset_hours())
y = (g.median() / 1e6).to_numpy()                      # Mon 00 UTC .. Sun 23 UTC
x = np.arange(168)
xs = np.repeat(np.r_[x, 168], 2)[1:-1]; ys = np.repeat(y, 2)   # hour-wide steps

fig, ax = ja.figure("wide", "night")
pos = ax.get_position(); ax.set_position([pos.x0 + 40 / 1536, pos.y0, pos.width - 40 / 1536, pos.height])
ja.gap(ax, xs, np.zeros_like(ys), ys, role="model")
ja.line(ax, xs, ys, "actual", lw=3)
ax.set_xlim(0, 168); ax.set_ylim(0, max(22, 5 * np.ceil(y.max() / 5 + 0.3)))
ax.xaxis.set_major_locator(FixedLocator(np.arange(12, 168, 24)))
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(v // 24)]))
ax.tick_params(axis="x", length=0, labelsize=14); ax.tick_params(axis="y", labelsize=13)
for d in range(1, 7):
    ax.axvline(24 * d, color=ja.C["axis"], lw=1, zorder=0)
ax.yaxis.set_major_locator(FixedLocator([0, 5, 10, 15, 20]))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}M"))
nwk = df.t.dt.isocalendar().week.nunique()
ja.panel_title(ax, "one week, hour by hour (median across the two weeks)" if WIN.IS_ATLAS
               else f"one week, hour by hour (median across {nwk} weeks; holidays left out)", size=11)
ax.set_ylabel("median depth within 10 bps, $", color=ja.C["muted"], family=ja.MONO, fontsize=11)
ax.set_xlabel("day of week, UTC", color=ja.C["muted"], family=ja.MONO, fontsize=11)

wed_brk = 2 * 24 + 17 - OFF                             # Wed 5pm New York (21:00 UTC in daylight time)
ja.signal(ax, wed_brk + 0.5, y[wed_brk], ms=0)
ytop = ax.get_ylim()[1]
ja.label_at(ax, 3 * 24 + 17, ytop - 2.8, f"US cash hours: ${med['cash']:.1f}M", "actual", dy=0, ha="center", size=15)
ja.label_at(ax, wed_brk - 1.5, 1.0, f"daily break, 5pm ET: ${med['break']:.1f}M", "actual", dy=0, ha="right", size=15)
ja.label_at(ax, 5 * 24 + 24, 7.0, "futures closed\n(weekend)", "muted", dy=0, ha="center", size=15)
r = med["break"] / df.d10_net[np.isin(s_, ["cash", "overnight"])].median() * 1e6
words = [(0.28, 0.38, "a third"), (0.2, 0.28, "a quarter"), (0.38, 0.45, "two fifths"), (0.45, 0.55, "half")]
frac = next((w for lo, hi, w in words if lo <= r < hi), f"{r:.0%}")
ja.finish(fig, f"A 24/7 market whose depth falls to {frac} in the CME daily break",
          hl=frac,
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {len(df):,} one-minute book snapshots",
          source="Data: Hydromancer Reservoir / node data. Book replay net of fills. Weekend rests on two weekends." if WIN.IS_ATLAS
          else f"Data: Hydromancer Reservoir / node data. Book replay net of fills. {nwk} weeks; holidays left out.")
ja.save(fig, "out/depth_week.png", strict=True)
