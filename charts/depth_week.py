"""depth_week: median depth within 10 bps for each hour of the week, as one line, so the daily CME
break and the weekend show as drops. @justinalick kit, night, wide (16:9).
Data: data/derived/heatmap/depth_minutes_v2.parquet, column d10_net (same input as heatmap.py).
Run: .venv/bin/python charts/depth_week.py"""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter, FixedLocator
import justinalick as ja

df = pd.read_parquet("data/derived/heatmap/depth_minutes_v2.parquet", columns=["t", "d10_net"])
t = df.t; dow = t.dt.dayofweek + 1; h = t.dt.hour; mm = h * 60 + t.dt.minute
closed = ((dow <= 4) & (h == 21)) | ((dow == 5) & (h >= 21)) | (dow == 6) | ((dow == 7) & (h < 22))
brk = (dow <= 4) & (h == 21)
cash = (dow <= 5) & (mm >= 810) & (mm < 1200)
sess = np.select([brk, closed, cash], ["break", "weekend", "cash"], "other")
med = df.d10_net.groupby(sess).median() / 1e6
assert (round(med["cash"], 1), round(med["break"], 1)) == (15.4, 4.7), med
g = df.assign(dow=dow, h=h).groupby(["dow", "h"]).d10_net
assert g.size().min() == g.size().max() == 120 and g.ngroups == 168
y = (g.median() / 1e6).to_numpy()                      # Mon 00 UTC .. Sun 23 UTC
x = np.arange(168)
xs = np.repeat(np.r_[x, 168], 2)[1:-1]; ys = np.repeat(y, 2)   # hour-wide steps

fig, ax = ja.figure("wide", "night")
pos = ax.get_position(); ax.set_position([pos.x0 + 40 / 1536, pos.y0, pos.width - 40 / 1536, pos.height])
ja.gap(ax, xs, np.zeros_like(ys), ys, role="model")
ja.line(ax, xs, ys, "actual", lw=3)
ax.set_xlim(0, 168); ax.set_ylim(0, 22)
ax.xaxis.set_major_locator(FixedLocator(np.arange(12, 168, 24)))
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(v // 24)]))
ax.tick_params(axis="x", length=0, labelsize=14); ax.tick_params(axis="y", labelsize=13)
for d in range(1, 7):
    ax.axvline(24 * d, color=ja.C["axis"], lw=1, zorder=0)
ax.yaxis.set_major_locator(FixedLocator([0, 5, 10, 15, 20]))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}M"))
ja.panel_title(ax, "one week, hour by hour (median across the two weeks)", size=11)
ax.set_ylabel("median depth within 10 bps, $", color=ja.C["muted"], family=ja.MONO, fontsize=11)
ax.set_xlabel("day of week, UTC", color=ja.C["muted"], family=ja.MONO, fontsize=11)

wed_brk = 2 * 24 + 21                                   # Wed 21:00 UTC, 5pm ET
ja.signal(ax, wed_brk + 0.5, y[wed_brk], ms=0)
ja.label_at(ax, 3 * 24 + 17, 19.2, "US cash hours: $15.4M", "actual", dy=0, ha="center", size=15)
ja.label_at(ax, wed_brk - 1.5, 1.0, "5pm ET, CME pause: $4.7M", "actual", dy=0, ha="right", size=15)
ja.label_at(ax, 5 * 24 + 24, 7.0, "weekend", "muted", dy=0, ha="center", size=15)

ja.finish(fig, "A 24/7 market whose depth falls to a third when CME pauses",
          hl="a third",
          subtitle="xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, 20,160 one-minute book snapshots",
          source="Data: Hydromancer Reservoir / node data. Book replay net of fills. Weekend rests on two weekends.")
ja.save(fig, "out/depth_week.png", strict=True)
