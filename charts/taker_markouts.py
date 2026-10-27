"""xyz:SP500 taker markouts by taker cluster, @justinalick night. Data loading copied from
analysis/taker_clusters/plot.py (mk_res.json only; cluster labels stay T1..T11)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
import duckdb
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

D = "data/derived/taker_clusters"
r = json.load(open(f"{D}/mk_res.json"))
cl = r["clusters"]; s = r["sessions"]; m = r["meta"]
# taker fees in bps of notional, T1 vs everyone else (same fills and window as mk.py)
FEE = dict(duckdb.sql(f"""
    WITH t1 AS (SELECT address FROM read_csv('{D}/cluster_map.csv')
                WHERE cluster = (SELECT "T1" FROM read_json('{D}/labels_local.json')))
    SELECT address IN (SELECT address FROM t1), sum(fee::DOUBLE) / sum(price::DOUBLE * size::DOUBLE) * 1e4
    FROM read_parquet('data/raw/xyz/fills/*.parquet')
    WHERE coin = 'xyz:SP500' AND crossed AND timestamp >= '{WIN.T0}' AND timestamp < '{WIN.T1}' GROUP BY 1""").fetchall())
LEAD60 = cl["T1"]["60"][0]
WIN.expect("taker fees T1 / others, T1 60s markout, T1 share %",
           [round(FEE[True], 2), round(FEE[False], 2), round(LEAD60, 2), round(100 * m["T1_share"])], [0.30, 0.98, 0.38, 29])
OFF = int(WIN.utc_offset_hours()); BRK = 16 - OFF + 1      # UTC hour of the daily CME halt (21 in daylight time)
H = ["0", "1", "10", "60"]; xl = ["fill", "1 s", "10 s", "60 s"]; x = np.arange(4)

fig, ax0 = ja.figure("wide_tall", "night"); ax0.remove()
LB = 11
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)
a = ja._px_axes(fig, 120, 216, 568, 408)
c = ja._px_axes(fig, 856, 216, 632, 408)
b = ja._px_axes(fig, 120, 768, 1368, 384)


def txt(ax, x, y, s, role, ha="left", va="center", bold=True, **kw):
    """Unboxed direct label (counted by ja.check)."""
    t = ax.text(x, y, s, ha=ha, va=va, color=ja.C[role], fontsize=LB, family=ja.MONO,
                weight="semibold" if bold else "regular", zorder=20, **kw)
    t._ja_label = True
    return t


def key_row(ax, items, size=LB, gap=3):
    """Colored text row, right-aligned on the panel-title baseline (no boxes)."""
    off = 0
    for text, role in reversed(items):
        ax.annotate(text, (1, 1.035), xycoords="axes fraction", xytext=(-off, 0), textcoords="offset points",
                    ha="right", va="bottom", color=ja.C[role], fontsize=size, family=ja.MONO, weight="semibold")
        off += (len(text) + gap) * 0.6 * size


bps = FuncFormatter(lambda v, _: f"{v:+.1f}" if abs(v) > 1e-9 else "0")

# panel 1: T1 vs all other takers
ja.zero(a)
for key, role in (("All except T1", "model"), ("T1", "actual")):
    d = cl[key]
    a.fill_between(x, [d[h][1] for h in H], [d[h][2] for h in H], color=ja.C[f"tint_{role}"], lw=0, zorder=0.5)
    ja.line(a, x, [d[h][0] for h in H], role, lw=3 if role == "actual" else 2.5, marker="o", ms=6, zorder=4)
_v = [cl[k][h][i] for k in ("All except T1", "T1") for h in H for i in (1, 2)]
a.set_xticks(x, xl); a.set_xlim(-0.2, 3.75); a.set_ylim(*ja.fit(-0.65, 0.62, [cl[k][h][0] for k in ("All except T1", "T1") for h in H], 0.1))
a.set_yticks([-0.6, -0.4, -0.2, 0, 0.2, 0.4]); a.yaxis.set_major_formatter(bps)
t1, ot = cl["T1"], cl["All except T1"]
ja.signal(a, 3, t1["60"][0], label=f"{t1['60'][0]:+.2f} bps", dx=12, dy=-5, size=LB, ms=0, role="actual")
ylo_a, yhi_a = a.get_ylim()
ja.label_at(a, -0.1, yhi_a - 0.1, f"largest taker T1, {100 * m['T1_share']:.0f}% of notional", "actual", dy=0, ha="left", size=LB)
ja.label_at(a, 1.6 if WIN.IS_ATLAS else 0.15, -0.36 if WIN.IS_ATLAS else (t1["0"][0] + ot["1"][0]) / 2, "all other takers", "model", dy=0, ha="left", size=LB)
ja.panel_title(a, "T1 vs the rest (maker markout = minus)", size=LB)
a.set_xlabel("time after fill", **AX); a.set_ylabel("taker markout, bps", **AX)

# panel 2: clusters at 10s and 60s
ja.zero(b)
ks = [f"T{i}" for i in range(1, 11)] + ["T11+ (rest)"]
for h, role, off in (("10", "muted", -0.17), ("60", "actual", 0.17)):
    for i, k in enumerate(ks):
        d = cl[k][h]
        b.plot([i + off] * 2, [d[1], d[2]], color=ja.C[role], lw=1.4, zorder=2)
        b.plot(i + off, d[0], "o", color=ja.C[role], ms=6, mec=ja.C["ground"], mew=1, zorder=3)
b.set_xticks(range(len(ks)), [k.replace(" (rest)", "") + f"\n{100 * cl[k]['notional'] / m['notional']:.0f}%" for k in ks], fontsize=9)
_w = [cl[k][h][i] for k in ks for h in ("10", "60") for i in (1, 2)]
ytop_b = ja.fit(-0.9, 3.2, _w, 0.2)[1]
b.grid(False, axis="x"); b.set_xlim(-0.6, len(ks) - 0.4); b.set_ylim(*ja.fit(-0.9, 3.2, _w, 0.2))
b.set_yticks([v for v in np.arange(-3, 10.01, 0.5) if b.get_ylim()[0] < v < ytop_b]); b.yaxis.set_major_formatter(bps)
# label the two clusters (T2 to T10) with the highest 60s markout
hi2 = sorted(ks[1:10], key=lambda k: -cl[k]["60"][0])[:2]
WIN.expect("taker clusters labeled (highest 60s markout)", sorted(int(k[1:]) for k in hi2), [2, 6])
for k in hi2:
    ja.label_at(b, ks.index(k) + 0.4, cl[k]["60"][0], f"{cl[k]['60'][0]:+.1f}", "actual", dy=-5, ha="left", size=LB)
key_row(b, [("60 s after fill", "actual"), ("10 s after fill", "muted")])
if max(cl[k]["60"][0] for k in hi2) > LEAD60:
    ja.note_at(b, 2.6, ytop_b - 0.4, "per dollar, some smaller takers lead the price more", role="muted", size=LB)
ja.panel_title(b, "markout by taker cluster, 95% CI", size=LB)
b.set_xlabel("taker cluster, share of taker notional", **AX); b.set_ylabel("taker markout, bps", **AX)

# panel 3: T1 share by UTC hour, Mon to Fri
t1h, oth = r["T1_by_utc_hour_weekday"], r["oth_by_utc_hour_weekday"]
sh = [100 * t1h[h] / (t1h[h] + oth[h]) for h in range(24)]
ytop_c = ja.fit(0, 58, [v + 12 for v in sh], 0)[1]
c.axvspan(9.0 - OFF, 16.0 - OFF, ymax=(ytop_c - 9) / ytop_c, color=ja.C["panel"], lw=0, zorder=0)
c.bar(range(24), sh, color=[ja.C["actual"] if h == BRK else ja.C["model"] for h in range(24)], width=0.75, zorder=2)
c.set_ylim(0, ytop_c); c.set_yticks([v for v in range(0, 101, 10) if v < ytop_c - 5]); c.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
c.set_xticks(range(0, 24, 3)); c.grid(False, axis="x"); c.set_xlim(-0.8, 23.8)
txt(c, 12.5 - OFF, ytop_c - 12.5, "US cash hours", "muted", ha="center")
txt(c, BRK, sh[BRK] + 1.2, "daily break", "actual", ha="center", va="bottom", rotation=90)
ss = {k: 100 * s[k]["T1_share"] for k in s}
txt(c, -0.6, ytop_c - 4, f"cash {ss['Cash hours']:.0f}%   overnight {ss['ES overnight']:.0f}%   futures closed {ss['ES closed']:.0f}%", "ink", bold=False)
ja.panel_title(c, "when T1 trades", size=LB)
c.set_xlabel("UTC hour, Mon to Fri", **AX); c.set_ylabel("T1 share of notional, %", **AX)

ja.finish(fig, f"The largest taker's fills lead the price by only {LEAD60:+.2f} bps", hl=f"{LEAD60:+.2f} bps",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {m['n']:,} taker fills, " + r"\$" + f"{m['notional'] / 1e9:.2f}B notional",
          source="Data: Hydromancer Reservoir / node data. Gross of fees; T = sub-accounts grouped under one master.")
ja.save(fig, "out/taker_markouts.png")
