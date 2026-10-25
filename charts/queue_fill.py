"""queue in the @justinalick kit (night). Same inputs as analysis/queue_fill_chart.py:
one small GROUP BY on queue.duckdb table r (read-only, 2 GB / 2 threads) and km.json. Per-day parquets not touched."""
import sys, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, duckdb, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FixedLocator, NullLocator, FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

Q = "data/derived/queue"
con = duckdb.connect(f"{Q}/queue.duckdb", read_only=True)
con.execute("SET memory_limit='2GB'; SET threads=2")
rows = con.execute("""
    SELECT qb, count(*) n, 100 * avg(any_fill::INT) all_sizes,
           100 * avg(any_fill::INT) FILTER (WHERE own_usd BETWEEN 5000 AND 15000) mid_size
    FROM r GROUP BY 1 ORDER BY 1""").fetchall()
con.close()
km = json.load(open(f"{Q}/km.json"))
N = sum(r[1] for r in rows)

LABELS = ["improves\ntouch", "join\n≤$5k", "join\n$5-25k", "join\n$25-100k", "join\n$100-250k", "join\n>$250k"]
SHORT = ["improves touch", "join ≤$5k", "$5-25k", "$25-100k", "$100-250k", "join >$250k"]

fig, ax0 = ja.figure("wide", "night"); ax0.remove()
W, H = 1536, 864
C = ja.C
AX = dict(color=C["muted"], family=ja.MONO, fontsize=10)
pct = FuncFormatter(lambda v, _: f"{v:.0f}%")

# ---- A: share of touch orders with any fill
a = ja._px_axes(fig, 120, 228, 696, 396)
x = np.arange(len(rows)); w = 0.36
v_all = np.array([r[2] for r in rows]); v_mid = np.array([r[3] for r in rows])
a.bar(x - w / 2 - 0.02, v_all, w, color=C['actual'], zorder=2)
a.bar(x + w / 2 + 0.02, v_mid, w, color=C['model'], zorder=2)
for i, r in enumerate(rows):
    a.text(x[i] - w / 2 - 0.02, v_all[i] + 0.35, f"{v_all[i]:.1f}", ha="center", va="bottom", fontsize=9.5,
           color=C['actual'], family=ja.MONO, weight="semibold")
    a.text(x[i] + w / 2 + 0.02, v_mid[i] + 0.35, f"{v_mid[i]:.1f}", ha="center", va="bottom", fontsize=9,
           color=C['model'], family=ja.MONO)
a.set_xticks(x, [f"{l}\nn={r[1] / 1e6:.1f}M" if r[1] >= 1e6 and not WIN.IS_ATLAS else f"{l}\nn={r[1] / 1e3:,.0f}k" for l, r in zip(LABELS, rows)], fontsize=9)
for t in a.get_xticklabels(): t.set_linespacing(1.3)
a.set_ylim(*ja.fit(0, 17, np.r_[v_all, v_mid] + 1.5, 1)); a.set_yticks([v for v in range(0, 101, 5) if v < a.get_ylim()[1] - 1]); a.yaxis.set_major_formatter(pct)
a.set_xlim(-0.6, len(rows) - 0.4)
ja.label_at(a, 2.4, 14.6, "all order sizes", "actual", dy=0, ha="left", size=10)
ja.label_at(a, 2.4, 12.8, "own order $5-15k only", "model", dy=0, ha="left", size=10)
ja.panel_title(a, "touch orders with any fill, by queue ahead", size=10)
a.set_xlabel("queue ahead at entry", **AX); a.set_ylabel("orders with any fill, %", **AX)

# ---- B: cumulative fill probability by time resting
b = ja._px_axes(fig, 920, 228, 400, 396)
tt = [g for g in km["grid"] if g <= 5]
names = sorted(km["km"])
for i, qb in enumerate(names):
    y = km["km"][qb][:len(tt)]
    role = "actual" if i == 0 else "model" if i == len(names) - 1 else "faint"
    ja.line(b, tt, y, role, lw=2.5 if role != "faint" else 1.6, marker="o", ms=4, zorder=3 if role != "faint" else 2)
    lab = b.annotate(SHORT[i], (tt[-1], y[-1]), xytext=(8, 0), textcoords="offset points", va="center",
                     fontsize=9, family=ja.MONO, color=C[role], weight="semibold" if role != "faint" else "regular",
                     annotation_clip=False)
b.set_xscale("log"); b.set_xlim(0.08, 6)
b.xaxis.set_major_locator(FixedLocator(tt)); b.xaxis.set_minor_locator(NullLocator())
b.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}s"))
b.set_ylim(0, 40); b.set_yticks([0, 10, 20, 30, 40]); b.yaxis.set_major_formatter(pct)
ja.panel_title(b, "fill probability by time resting", size=10)
b.set_xlabel("time resting, log scale", **AX); b.set_ylabel("cumulative fill probability, %", **AX)
ja.note_at(b, 0.3, 30, "cancels censored,\nindicative only", role="muted", size=9)

fig.text(48 / W, 1 - 788 / H, "FIFO queue replayed from node order statuses; 95.8% of maker fills hit the replayed queue head. "
         "Queue ahead measured at entry only.", color=C['muted'], family=ja.MONO, fontsize=9.5, va="baseline")

ja.finish(fig, f"Fill odds drop from {v_all[0]:.1f}% to {v_all[-1]:.1f}% behind $250k+", hl=f"{v_all[-1]:.1f}%",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label(1)}, {N / 1e6:.2f}M orders at or inside the touch",
          source="Data: Hydromancer Reservoir / node data.")
ja.save(fig, "out/queue.png")
