"""xyz:SP500 order flow imbalance, @justinalick night. Data loading copied from
analysis/ofi/plot.py (ofi_res.json, gap_res.json)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import numpy as np, matplotlib; matplotlib.use("Agg")
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

O = "data/derived/ofi"
r = json.load(open(f"{O}/ofi_res.json")); g = json.load(open(f"{O}/gap_res.json"))
HZ = ["1", "5", "10", "30", "60", "300"]; xl = ["1s", "5s", "10s", "30s", "1m", "5m"]; x = np.arange(len(HZ))
h = r["h"]

fig, ax0 = ja.figure("wide", "night"); ax0.remove()
LB = 11
L, pw, gapx = 120, 600, 144
a = ja._px_axes(fig, L, 216, pw, 504)
b = ja._px_axes(fig, L + pw + gapx, 216, pw, 504)


def txt(ax, x, y, s, role, ha="left", va="center", bold=True, **kw):
    """Unboxed direct label (counted by ja.check)."""
    t = ax.text(x, y, s, ha=ha, va=va, color=ja.C[role], fontsize=LB, family=ja.MONO,
                weight="semibold" if bold else "regular", zorder=20, **kw)
    t._ja_label = True
    return t
for ax in (a, b):
    ax.set_xticks(x, xl); ax.set_xlim(-0.3, len(HZ) - 0.7)
pct = FuncFormatter(lambda v, _: f"{v:.0f}%")

# left: same bin
hh = HZ[:5]; xi = x[:5]
med = [100 * h[k]["cont_halfhour_r2_median"] for k in hh]
lo = [100 * h[k]["cont_halfhour_r2_iqr"][0] for k in hh]; hi = [100 * h[k]["cont_halfhour_r2_iqr"][1] for k in hh]
pooled = [100 * h[k]["cont_ofi_r2"] for k in HZ]
ti = [100 * h[k]["cont_ti_r2"] for k in HZ]
ja.gap(a, xi, lo, hi)
ja.line(a, xi, med, "actual", lw=3, marker="o", ms=6)
ja.line(a, x, pooled, "model", lw=2.5, marker="o", ms=5)
ja.line(a, x, ti, "muted", lw=2.5, marker="o", ms=5)
rth, off = 100 * h["10"]["cont_ofi_r2_rth"], 100 * h["10"]["cont_ofi_r2_off"]
a.plot([2, 2], [off, rth], color=ja.C["model"], lw=1.2, ls=(0, (2, 2)), zorder=3)
a.plot([2, 2], [off, rth], ls="none", marker="D", ms=7, mfc=ja.C["ground"], mec=ja.C["model"], mew=1.8, zorder=5)
AT = WIN.IS_ATLAS                                   # the atlas keeps its hand-placed label heights
txt(a, 1.86 if AT else 2.14, rth, f"10s cash {rth:.0f}%", "model", ha="right" if AT else "left")
txt(a, 2.16 if AT else 2, 16.2 if AT else off - 4.5, f"10s other {off:.0f}%", "model", ha="left" if AT else "center")
a.set_ylim(*ja.fit(0, 75, hi + pooled + [rth], 3)); a.set_yticks([0, 20, 40, 60]); a.yaxis.set_major_formatter(pct)
txt(a, 4.14, med[-1], f"OFI, 30-min refit\n{med[0]:.0f}% to {med[-1]:.0f}%", "actual", linespacing=1.3)
txt(a, 5, 11.6 if AT else max(pooled[3:]) + 4.5, "OFI / depth, pooled", "model", ha="right")
txt(a, 5, 2.6 if AT else ti[-1] - 6, "taker volume alone", "muted", ha="right")
ja.panel_title(a, "same bin: mid return on OFI  (shade = IQR)", size=LB)
AX = dict(color=ja.C["muted"], family=ja.MONO, fontsize=LB)
a.set_xlabel("bin length", **AX); a.set_ylabel("R², same bin, %", **AX)

# right: next bin, out of sample
ja.zero(b)
CLIP = -3
CLIP_HI = np.inf if AT else 3.2                     # long windows have a few outlier days above the key
for i, k in enumerate(HZ):
    dv = np.array(h[k]["oos_ofi_r2_days"]) * 100
    jit = np.linspace(-0.18, 0.18, len(dv))
    b.scatter(x[i] + jit, np.clip(dv, CLIP, CLIP_HI), s=16, color=ja.C["faint"], zorder=2, lw=0)
oos = [100 * h[k]["oos_ofi_r2"] for k in HZ]
lag = [100 * h[k]["oos_lagret_r2"] for k in HZ]
ja.line(b, x, lag, "model", lw=2.5, ls=(0, (5, 3)), marker="o", ms=5, zorder=3)
ja.line(b, x, oos, "actual", lw=3, marker="o", ms=6, zorder=4)
TOP = 4.0 if AT else 4.6
b.set_ylim(CLIP - 0.3, TOP); b.set_yticks([-3, -2, -1, 0, 1, 2, 3])
b.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}%" if v else "0%"))
ja.signal(b, 0, oos[0], label=f"{oos[0]:.1f}% at 1s", dx=14, dy=10, size=LB, ms=0, role="actual")  # LED hidden on request; label kept
txt(b, -0.25, TOP - 0.24, f"lagged OFI, {h['1']['oos_days']} test days pooled", "actual")
txt(b, -0.25, TOP - 0.68, "lagged mid return only", "model")
txt(b, 5.25, TOP - 0.68, "dots: test days", "faint", ha="right")
ja.note_at(b, 2.5, -2.55, f"1s with a 1s delay: {100 * g['1s_gap1000ms']:.1f}%", role="muted", size=LB)
ja.panel_title(b, "next bin: out of sample, vs a zero forecast", size=LB)
b.set_xlabel("bin length", **AX); b.set_ylabel("out-of-sample R², %", **AX)

WIN.expect("OFI out-of-sample R2 at 1s, %", round(oos[0], 1), 1.3)
ja.finish(fig, f"Order flow explains moves but forecasts only {oos[0]:.1f}% at 1s", hl=f"{oos[0]:.1f}%",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {WIN.label()}, {h['1']['n_bins']:,} one-second bins",
          source="Data: Hydromancer Reservoir / node data. Gross of spread/fees. OOS walk-forward by day. " + ("Dots clip at -3%." if AT else "Dots clip at -3% and +3.2%."))
ja.save(fig, "out/ofi.png")
