"""How long xyz:SP500 positions are held, in the @justinalick kit (night). Two charts:
  out/holding.png        histograms of position length, by count vs by notional (top) and long vs short (bottom)
  out/holding_types.png  how long each dollar is held (FIFO lots), by account type
Data: data/derived/holding/holding.json and holding_hist.json, written by analysis/holding/holding.py."""
import json, os, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FixedLocator, NullLocator, FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

R = json.load(open("data/derived/holding/holding.json"))
H = json.load(open("data/derived/holding/holding_hist.json"))
E = np.array(H["edges_s"])
LB = 11.5
TICKS = {1: "1 s", 10: "10 s", 60: "1 min", 600: "10 min", 3600: "1 h", 21600: "6 h", 86400: "1 d", 604800: "1 wk",
         2592000: "30 d"}
XLIM = (0.3, 1.6e7)
os.makedirs("out", exist_ok=True)


def fmt(s):
    for u, v in (("d", 86400), ("h", 3600), ("min", 60), ("s", 1)):
        if s >= v:
            return f"{s / v:.2g} {u}" if s / v < 10 else f"{s / v:.0f} {u}"
    return f"{s:.2g} s"


def curve(group, key):
    """Share per bin, folding everything under XLIM[0] into the first visible bin so nothing is dropped silently."""
    s = np.array(H[key][group]["share"]) * 100
    x = E[1:]                              # bin upper edges; bin 0 is under 1 ms
    k0 = np.searchsorted(x, XLIM[0])
    s = s.copy(); s[k0] += s[:k0].sum(); s[:k0] = 0
    return E[k0:-1], s[k0:]


def axes_style(ax, ymax):
    ax.set_xscale("log"); ax.set_xlim(*XLIM); ax.set_ylim(0, ymax)
    ax.xaxis.set_major_locator(FixedLocator(list(TICKS))); ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: TICKS.get(int(round(v)), "")))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))


def hist(ax, group, key, role, fill=True, lw=2.5):
    x, s = curve(group, key)
    ja.line(ax, x, s, role, lw=lw, drawstyle="steps-post")
    if fill:
        ax.fill_between(x, s, step="post", color=ja.C["tint_" + role] if "tint_" + role in ja.C else ja.C[role],
                        alpha=1 if "tint_" + role in ja.C else 0.25, zorder=1, lw=0)
    return s


def median_mark(ax, x, role, text, y, ha="left", dx=1.12):
    ax.axvline(x, color=ja.C[role], lw=1.5, ls=(0, (2, 3)), zorder=3)
    t = ax.text(x * (dx if ha == "left" else 1 / dx), y, text, color=ja.C[role], fontsize=LB, family=ja.MONO,
                weight="semibold", ha=ha, va="top", zorder=20)
    t._ja_label = True


def ylabel(ax, text):
    ax.set_ylabel(text, color=ja.C["muted"], family=ja.MONO, fontsize=LB)


ep, epn = R["episodes"], R["episodes_notional_weighted"]
n_pos = ep["all"]["episodes"]
sub = f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {n_pos:,} positions, {R['accounts']:,} accounts"

# ---------------------------------------------------------------- chart 1
fig, A = ja.figure("wide_tall", "night", layout="pair")
top, bot = A["top"], A["bot"]
for ax in (top, bot):
    _p = ax.get_position(); _l = 136 / 1536
    ax.set_position([_l, _p.y0, _p.x1 - _l, _p.height])

c = hist(top, "all", "positions_count", "model")
n = hist(top, "all", "positions_notional", "actual")
ym = 1.25 * max(c.max(), n.max()); axes_style(top, ym)
mc, mn = ep["all"]["km"]["p50"], epn["all"]["km"]["p50"]
median_mark(top, mc, "model", f"half of positions\nare closed by {fmt(mc)}", 0.97 * ym, ha="right")
median_mark(top, mn, "actual", f"half of the dollars traded\nare in positions held\nlonger than {fmt(mn)}", 0.97 * ym)
ja.panel_title(top, "share of positions (blue) and of notional traded (gold) by how long the position was open", size=LB)
ylabel(top, "share per bin, %")
ja.x_caption(top, "time from flat to flat (or a flip), log scale", size=LB)

L = hist(bot, "long", "positions_notional", "actual", fill=False, lw=3)
S = hist(bot, "short", "positions_notional", "model", fill=False, lw=3)
ym2 = 1.3 * max(L.max(), S.max()); axes_style(bot, ym2)
ml, ms = epn["long"]["km"]["p50"], epn["short"]["km"]["p50"]
median_mark(bot, ml, "actual", f"longs: median {fmt(ml)}", 0.97 * ym2)
median_mark(bot, ms, "model", f"shorts: median {fmt(ms)}", 0.97 * ym2, ha="right")
p90l, p90s = epn["long"]["km"]["p90"], epn["short"]["km"]["p90"]
t = bot.text(0.985, 0.62, f"1 in 10 dollars stays\nin a long > {fmt(p90l)},\nin a short > {fmt(p90s)}", transform=bot.transAxes,
             color=ja.C["ink"], fontsize=LB, family=ja.MONO, ha="right", va="top", zorder=20); t._ja_label = True
ja.panel_title(bot, "share of notional traded, long (gold) vs short (blue) positions", size=LB)
ylabel(bot, "share per bin, %")
bot.set_xlabel("time from flat to flat (or a flip), log scale", color=ja.C["muted"], family=ja.MONO, fontsize=LB)

title = f"Half of positions close in {fmt(mc)}; half the money stays {fmt(mn)}+"
ja.finish(fig, title, hl=fmt(mc), subtitle=sub,
          source="Data: Hydromancer Reservoir. Positions rebuilt from fills; closed only; medians Kaplan-Meier.")
ja.save(fig, "out/holding.png")

# ---------------------------------------------------------------- chart 2
fig, ax = ja.figure("wide", "night")
_p = ax.get_position(); _l = 136 / 1536
ax.set_position([_l, _p.y0, _p.x1 - _l, _p.height])
roles = {"maker-heavy": "model", "taker": "actual", "mixed": "faint"}
mx = 0
for g in ("mixed", "maker-heavy", "taker"):
    mx = max(mx, hist(ax, g, "lots_notional", roles[g], fill=False, lw=3 if g != "mixed" else 2.5).max())
axes_style(ax, 1.3 * mx)
lots = R["lots"]
y = 0.97 * 1.3 * mx
for i, g in enumerate(("maker-heavy", "taker", "mixed")):
    r = lots[g]
    t = ax.text(0.985, 0.97 - i * 0.1, f"━━ {g}: median {fmt(r['p50_s'])}, mean {fmt(r['mean_s_qty_weighted'])}",
                transform=ax.transAxes, color=ja.C[roles[g]], fontsize=LB, family=ja.MONO, weight="semibold",
                ha="right", va="top", zorder=20); t._ja_label = True
ja.panel_title(ax, "share of closed notional, each contract matched to the oldest open one (FIFO)", size=LB)
ylabel(ax, "share per bin, %")
ax.set_xlabel("time each dollar was held, log scale", color=ja.C["muted"], family=ja.MONO, fontsize=LB)
mk, tk = lots["maker-heavy"]["p50_s"], lots["taker"]["p50_s"]
ja.finish(fig, f"Makers turn a dollar over in {fmt(mk)}; takers hold it {fmt(tk)}", hl=fmt(mk), subtitle=sub,
          source="Data: Hydromancer Reservoir. Maker-heavy: >= 80% of notional as maker; taker: <= 20%.")
ja.save(fig, "out/holding_types.png")
print("wrote out/holding.png, out/holding_types.png")
