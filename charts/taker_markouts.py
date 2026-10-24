"""xyz:SP500 taker markouts by taker cluster, @justinalick night. Data loading copied from
analysis/taker_clusters/plot.py (mk_res.json only; cluster labels stay T1..T11)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
import duckdb
import justinalick as ja

D = "data/derived/taker_clusters"
r = json.load(open(f"{D}/mk_res.json"))
cl = r["clusters"]; s = r["sessions"]; m = r["meta"]
# taker fees in bps of notional, T1 vs everyone else (same fills and window as mk.py)
FEE = dict(duckdb.sql(f"""
    WITH t1 AS (SELECT address FROM read_csv('{D}/cluster_map.csv')
                WHERE cluster = (SELECT "T1" FROM read_json('{D}/labels_local.json')))
    SELECT address IN (SELECT address FROM t1), sum(fee::DOUBLE) / sum(price::DOUBLE * size::DOUBLE) * 1e4
    FROM read_parquet('data/raw/xyz/fills/2026-10-*.parquet')
    WHERE coin = 'xyz:SP500' AND crossed AND timestamp >= '2026-10-08' AND timestamp < '2026-10-22' GROUP BY 1""").fetchall())
LEAD60 = cl["T1"]["60"][0]
assert (round(FEE[True], 2), round(FEE[False], 2), round(LEAD60, 2), round(100 * m["T1_share"])) == (0.30, 0.98, 0.38, 29), (FEE, LEAD60, m["T1_share"])
H = ["0", "1", "10", "60"]; xl = ["fill", "1s", "10s", "60s"]; x = np.arange(4)

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
a.set_xticks(x, xl); a.set_xlim(-0.2, 3.75); a.set_ylim(-0.65, 0.62)
a.set_yticks([-0.6, -0.4, -0.2, 0, 0.2, 0.4]); a.yaxis.set_major_formatter(bps)
t1, ot = cl["T1"], cl["All except T1"]
ja.signal(a, 3, t1["60"][0], label=f"{t1['60'][0]:+.2f} bps", dx=12, dy=-5, size=LB, ms=0, role="actual")
ja.label_at(a, -0.1, 0.52, f"largest taker T1, {100 * m['T1_share']:.0f}% of notional", "actual", dy=0, ha="left", size=LB)
ja.label_at(a, 1.6, -0.36, "all other takers", "model", dy=0, ha="left", size=LB)
ja.note_at(a, 2.0, -0.58, f"taker fees: T1 ~{FEE[True]:.2f}, others ~{FEE[False]:.2f}", role="muted", size=LB)
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
b.set_xticks(range(len(ks)), [k.replace(" (rest)", "") + f"\n{cl[k]['notional'] / 1e6:,.0f}M" for k in ks], fontsize=9)
b.grid(False, axis="x"); b.set_xlim(-0.6, len(ks) - 0.4); b.set_ylim(-0.9, 3.2)
b.set_yticks([-0.5, 0, 0.5, 1, 1.5, 2, 2.5, 3]); b.yaxis.set_major_formatter(bps)
ja.label_at(b, 1.4, cl["T2"]["60"][0], f"{cl['T2']['60'][0]:+.1f}", "actual", dy=-5, ha="left", size=LB)
ja.label_at(b, 5.4, cl["T6"]["60"][0], f"{cl['T6']['60'][0]:+.1f}", "actual", dy=-5, ha="left", size=LB)
key_row(b, [("60s after fill", "actual"), ("10s after fill", "muted")])
ja.note_at(b, 2.6, 2.8, "per dollar, some smaller takers lead the price more", role="muted", size=LB)
ja.panel_title(b, "markout by taker cluster, 95% CI", size=LB)
b.set_xlabel("taker cluster, taker notional $", **AX); b.set_ylabel("taker markout, bps", **AX)

# panel 3: T1 share by UTC hour, Mon to Fri
t1h, oth = r["T1_by_utc_hour_weekday"], r["oth_by_utc_hour_weekday"]
sh = [100 * t1h[h] / (t1h[h] + oth[h]) for h in range(24)]
c.axvspan(13.0, 20.0, ymax=49 / 58, color=ja.C["panel"], lw=0, zorder=0)
c.bar(range(24), sh, color=[ja.C["actual"] if h == 21 else ja.C["model"] for h in range(24)], width=0.75, zorder=2)
c.set_ylim(0, 58); c.set_yticks([0, 10, 20, 30, 40, 50]); c.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
c.set_xticks(range(0, 24, 3)); c.grid(False, axis="x"); c.set_xlim(-0.8, 23.8)
txt(c, 16.5, 45.5, "US cash hours", "muted", ha="center")
txt(c, 21, sh[21] + 1.2, "CME break", "actual", ha="center", va="bottom", rotation=90)
ss = {k: 100 * s[k]["T1_share"] for k in s}
txt(c, -0.6, 54, f"cash {ss['Cash hours']:.0f}%   overnight {ss['ES overnight']:.0f}%   ES closed {ss['ES closed']:.0f}%", "ink", bold=False)
ja.panel_title(c, "when T1 trades", size=LB)
c.set_xlabel("UTC hour, Mon to Fri", **AX); c.set_ylabel("T1 share of notional, %", **AX)

ja.finish(fig, f"The largest taker's fills lead the price by only {LEAD60:+.2f} bps", hl=f"{LEAD60:+.2f} bps",
          subtitle=f"xyz:SP500 perp on Hyperliquid, Oct 8 to 21, 2026, {m['n']:,} taker fills, " + r"\$" + f"{m['notional'] / 1e9:.2f}B notional",
          source="Data: Hydromancer Reservoir / node data. Gross of fees; T = sub-accounts grouped under one master.")
ja.save(fig, "out/taker_markouts.png")
