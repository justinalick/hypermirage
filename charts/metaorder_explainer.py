"""What is a metaorder: a schematic with made-up numbers (it reads no data, so it is the same for every window).
How one account's taker orders group into metaorders, how impact is measured, how it compares with sweeping the
displayed book, the fill-path shapes, and the square-root law. Definitions as in analysis/impact/build.py."""
import sys, warnings; warnings.filterwarnings("ignore")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
sys.path.insert(0, "charts")
import justinalick as ja

ja.SIZES["explainer"] = (1536, 2040)   # five panels: desktop width, taller than wide_tall
fig, ax0 = ja.figure("explainer", "night"); ax0.remove()
C, M = ja.C, ja.MONO
LB = 11
AXL = dict(color=C["muted"], family=M, fontsize=LB)
def T(ax, x, y, s, role="muted", size=10.5, ha="center", va="center", bold=False, **kw):
    return ax.text(x, y, s, ha=ha, va=va, color=C[role], family=M, fontsize=size,
                   weight="semibold" if bold else "regular", zorder=20, **kw)
def clean(ax):
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.tick_params(colors=C["faint"], labelsize=10)

# ---------------- the example account: (minute, notional $k, side)
MO = {
 1: [(2.0, 120, +1)],
 2: [(9.0, 60, +1), (10.5, 45, +1), (12.0, 70, +1)],
 3: [(20.0, 80, -1), (21.5, 90, -1), (23.0, 60, -1)],
 4: [(30.0, 60, +1), (31.0, 50, +1), (32.5, 35, +1), (34.0, 60, +1), (35.0, 30, +1), (36.5, 45, +1)],
 5: [(52.0, 160, +1), (53.0, 70, +1), (54.5, 30, +1), (55.5, 25, +1), (56.5, 15, +1)],
}
Q4 = sum(q for _, q, _ in MO[4])                       # $280k

# ---------------- 1. timeline
a = ja._px_axes(fig, 96, 236, 1392, 400)
for k, os_ in MO.items():
    for t, q, s in os_:
        a.bar(t, s * q, width=0.7, color=C["model"] if s > 0 else C["accent"], zorder=3)
a.axhline(0, color=C["axis"], lw=1)
a.set_xlim(-1, 62); a.set_ylim(-250, 330); a.set_yticks([])
a.set_xticks(range(0, 61, 10), [f"{m} min" for m in range(0, 61, 10)]); clean(a); a.spines["left"].set_visible(False)
def bracket(k, sub, role="ink"):
    ts = [t for t, _, _ in MO[k]]; top = max(q for _, q, _ in MO[k])
    y = top + 22
    a.plot([ts[0] - 0.5, ts[-1] + 0.5], [y, y], color=C[role], lw=4, solid_capstyle="butt")
    T(a, (ts[0] + ts[-1]) / 2, y + 12, f"MO {k}", role, 12, bold=True, va="bottom")
    T(a, (ts[0] + ts[-1]) / 2, y + 52, sub, "muted", 9.5, linespacing=1.25, va="bottom")
bracket(1, "1 order")
bracket(2, "3 child orders")
bracket(4, f"6 child orders, ${Q4}k")
bracket(5, "5 child orders")
ts = [t for t, _, _ in MO[3]]
a.plot([ts[0] - 0.5, ts[-1] + 0.5], [-112, -112], color=C["accent"], lw=4, solid_capstyle="butt")
T(a, 21.5, -124, "MO 3", "accent", 12, bold=True, va="top")
T(a, 21.5, -164, "sells: the side flipped,\nso a new metaorder", "muted", 9.5, linespacing=1.25, va="top")
def gap(x0, x1, y, s):
    a.annotate("", xy=(x1, y), xytext=(x0, y), arrowprops=dict(arrowstyle="<->", color=C["faint"], lw=1))
    T(a, (x0 + x1) / 2, y - 14, s, "faint", 9.5, linespacing=1.25, va="top")
gap(2.5, 8.5, -30, "7 min > 5:\nMO 1 ends")
gap(37.0, 51.5, -30, "15 min > 5: MO 4 ends")
T(a, 33.3, -48, "gaps < 5 min:\nsame metaorder", "faint", 9.5, linespacing=1.25)
a.annotate("child order: one taker order\n(it can fill against several makers)", xy=(34.0, 62), xytext=(41.0, 262),
           color=C["muted"], family=M, fontsize=9.5, ha="center", va="center",
           arrowprops=dict(arrowstyle="-", color=C["faint"], lw=1))
T(a, 14.6, 30, "buys", "model", 10.5, ha="left", bold=True); T(a, 24.4, -40, "sells", "accent", 10.5, ha="left", bold=True)
ja.panel_title(a, "1  one account's taker orders: same side, gaps of 5 min or less = one metaorder", size=LB)
a.set_ylabel("order size", **AXL)

# ---------------- 2. impact of MO 4
b = ja._px_axes(fig, 96, 770, 600, 400)
tg = np.linspace(28.5, 38.5, 1200)
mid = 0.06 * np.sin(tg * 5.1) + 0.04 * np.sin(tg * 13.7)
for t, q, _ in MO[4]:
    j = q / 50 * 0.45
    mid += np.where(tg >= t, j * (0.55 + 0.45 * np.exp(-(tg - t) / 0.4)), 0)
mid += np.clip((tg - 30.0) / 6.5, 0, 1) * 0.8                      # drift while the metaorder trades
mid -= np.interp(29.99, tg, mid)
t_end = MO[4][-1][0] + 0.25 / 60
I = float(np.interp(t_end, tg, mid))
b.axvspan(30.0, 36.5, color=C["panel"], lw=0, zorder=0)
b.plot(tg, mid, color=C["ink"], lw=1.8, zorder=3)
for t, q, _ in MO[4]:
    b.plot(t, np.interp(t + 0.02, tg, mid), "o", ms=4 + q / 12, color=C["model"], zorder=4)
b.axhline(0, color=C["faint"], lw=1, ls=(0, (4, 3)))
b.plot([36.5, 38.5], [I, I], color=C["faint"], lw=1, ls=(0, (4, 3)))
b.annotate("", xy=(37.6, I), xytext=(37.6, 0), arrowprops=dict(arrowstyle="->", color=C["accent"], lw=2))
T(b, 37.45, I / 2, f"impact\n+{I:.1f} bps", "accent", 11, ha="right", bold=True, linespacing=1.2)
T(b, 28.6, -0.25, "mid before the first fill", "faint", 9.5, ha="left", va="top")
T(b, 35.0, -0.55, "duration of MO 4", "faint", 9.5)
T(b, 33.0, I + 0.75, "dots: child orders (size = notional)", "model", 9.5)
b.set_xlim(28.5, 38.5); b.set_ylim(-0.8, I + 1.1)
b.set_xticks([30, 32, 34, 36, 38], ["30", "32", "34", "36", "38 min"]); clean(b)
b.set_yticks([0, 1, 2]); b.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}" if v else "0"))
ja.panel_title(b, "2  impact: mid after last fill vs before first", size=LB)
b.set_ylabel("mid vs start, bps", **AXL)

# ---------------- 3. the same size against the displayed book
c = ja._px_axes(fig, 888, 770, 600, 400)
lv = 0.08 + 0.155 * np.arange(10)                                  # ask levels, bps from mid
dep = np.array([60, 70, 55, 80, 65, 90, 75, 85, 95, 80])
cum = np.cumsum(dep); kk = int(np.searchsorted(cum, Q4))           # last level the sweep reaches
for i, (y, d) in enumerate(zip(lv, dep)):
    take = d if i < kk else (Q4 - (cum[kk - 1] if kk else 0)) if i == kk else 0
    c.barh(y, d, height=0.11, color=C["axis"], zorder=2)
    if take: c.barh(y, take, height=0.11, color=C["model"], zorder=3)
book = lv[kk]
c.axhline(book, color=C["model"], lw=1.2, ls=(0, (4, 3)))
c.axhline(I, color=C["accent"], lw=1.6, ls=(0, (4, 3)))
T(c, 162, book + 0.05, f"one sweep of ${Q4}k:\n+{book:.1f} bps", "model", 10.5, ha="right", va="bottom", bold=True, linespacing=1.2)
T(c, 166, I + 0.05, f"MO 4 actually\nmoved +{I:.1f} bps", "accent", 10.5, ha="right", va="bottom", bold=True, linespacing=1.2)
c.annotate("", xy=(168, I), xytext=(168, book), arrowprops=dict(arrowstyle="->", color=C["ink"], lw=1.5))
T(c, 162, (book + I) / 2 + 0.1, f"about {I / book:.0f}x\nthe book", "ink", 11, ha="right", bold=True, linespacing=1.2)
T(c, 3, 2.55, "blue: depth one sweep would take\ngrey: the rest of the displayed asks", "faint", 9.5, ha="left", va="top", linespacing=1.25)
c.set_xlim(0, 170); c.set_ylim(0, 2.6); c.set_xticks([0, 40, 80, 120]); clean(c)
c.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}k"))
c.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"+{v:.1f}" if v else "0"))
ja.panel_title(c, "3  vs the book: one sweep of the same size", size=LB)
c.set_xlabel("displayed ask size per level", **AXL); c.set_ylabel("price above mid, bps", **AXL)

# ---------------- 4. fill-path shapes
d = ja._px_axes(fig, 96, 1330, 600, 520)
u = np.linspace(0, 1, 60)
for f_, role, lab, xy in ((1 - (1 - u) ** 3.5, "actual", "front-loaded", (0.20, 0.97)),
                          (u, "model", "spread out", (0.80, 0.50)), (u ** 3.5, "faint", "back-loaded", (0.80, 0.08))):
    d.plot(u, f_, color=C[role], lw=5, alpha=0.2, zorder=1)
def path(k, role, lab, xy):
    ts = np.array([t for t, _, _ in MO[k]]); qs = np.array([q for _, q, _ in MO[k]])
    x = (ts - ts[0]) / (ts[-1] - ts[0]); y = np.cumsum(qs) / qs.sum()
    d.step(np.r_[0, x], np.r_[0, y], where="post", color=C[role], lw=2.5, zorder=3)
    d.plot(x, y, "o", color=C[role], ms=6, zorder=4)
    ja.label_at(d, *xy, lab, role, dy=0, ha="left", size=10.5).set_va("center")
path(4, "model", "MO 4: spread out", (0.50, 0.28))
path(5, "actual", "MO 5: front-loaded", (0.24, 0.92))
T(d, 1.0, 0.05, "faint: typical front-loaded,\nspread out, back-loaded shapes", "faint", 9.5, ha="right", va="bottom", linespacing=1.25)
d.set_xlim(-0.02, 1.02); d.set_ylim(0, 1.05); clean(d)
d.set_xticks([0, 0.5, 1], ["first fill", "50%", "last fill"])
d.set_yticks([0, 0.5, 1], ["0%", "50%", "100%"])
ja.panel_title(d, "4  shape (4+ child orders only): when the size fills", size=LB)
d.set_xlabel("elapsed share of the metaorder's duration", **AXL); d.set_ylabel("share of notional filled", **AXL)

# ---------------- 5. across many metaorders
e = ja._px_axes(fig, 888, 1330, 600, 520)
x = np.logspace(-6, -2, 13); rng = np.random.default_rng(4)
Y, DL = 0.4, 0.4
yb = Y * x ** DL * np.exp(rng.normal(0, 0.12, len(x)))
e.plot(x, 0.55 * np.sqrt(x), color=C["faint"], lw=1.5, ls=(0, (4, 3)))
e.plot(x, Y * x ** DL, color=C["accent"], lw=2)
e.plot(x, yb, "s", color=C["accent"], ms=6)
qv, isg = Q4 * 1e3 / 245e6, I / 100                                 # a $245M day, 1% daily vol
e.plot(qv, isg, "o", ms=11, mfc=C["ground"], mec=C["model"], mew=2.5, zorder=5)
T(e, qv / 1.6, isg * 1.45, "MO 4", "model", 10.5, ha="right", bold=True)
e.set_xscale("log"); e.set_yscale("log"); clean(e)
e.set_xlim(5e-7, 2e-2); e.set_ylim(3e-4, 0.3)
T(e, 7e-7, 0.17, "bigger metaorders move price more,\nbut less than in proportion (concave)", "ink", 10, ha="left", linespacing=1.3)
T(e, 1.6e-2, 2.6e-3, "fitted slope (exponent delta)", "accent", 10, ha="right", bold=True)
T(e, 1.6e-2, 1.3e-3, "slope 0.5: square-root law", "faint", 10, ha="right")
T(e, 1.6e-2, 6.5e-4, "I/sigma = Y x (Q/V)^delta", "muted", 10, ha="right")
e.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0e}".replace("e-0", "e-")))
e.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
ja.panel_title(e, "5  across many metaorders (binned)", size=LB)
e.set_xlabel("size / day's volume (Q/V), log", **AXL); e.set_ylabel("impact / daily vol (I/sigma), log", **AXL)

ja.finish(fig, "What is a metaorder?", hl="metaorder",
          subtitle="How taker orders group, and how their impact is measured. Illustrative numbers, not real data.",
          source="Schematic. Definitions as in the report: same account and side, gaps <= 5 min, liquidations excluded.")
ja.save(fig, "out/metaorder_explainer.png")
