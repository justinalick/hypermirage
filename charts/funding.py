"""xyz:SP500 premium and funding, five panels, @justinalick night.
Data loading copied from analysis/funding/funding_premium.py (public API files, no refetch)."""
import json, sys, warnings; warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, "charts")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.dates as md
from matplotlib.ticker import FuncFormatter
import justinalick as ja
sys.path.insert(0, "scripts")
import window as WIN

D = Path("data/derived/funding")
INTEREST, CLAMP, DIV = 1e-4, 3e-4, 16
END = pd.Timestamp(WIN.API_END, tz="UTC")


def load_funding():
    f = pd.DataFrame(json.load(open(D / "sp500_funding_api.json")))
    f["t"] = pd.to_datetime(f.time, unit="ms", utc=True).dt.floor("h")
    f = f[f.t <= END].copy()
    assert not f.t.duplicated().any()
    f["fund"] = f.fundingRate.astype(float)
    f["prem"] = f.premium.astype(float)
    f["prem_bps"] = f.prem * 1e4
    f["ny"] = (f.t - pd.Timedelta(hours=1)).dt.tz_convert("America/New_York")
    return f.set_index("t")


def load_candles():
    c = pd.DataFrame(json.load(open(D / "candles.json")))
    c["t"] = pd.to_datetime(c.t, unit="ms", utc=True)
    c = c.drop_duplicates("t", keep="last").set_index("t").sort_index()
    return c[c.index <= END][["o", "c"]].astype(float)


def ny_session(ny):
    """Session of the hour starting at ny, read from the scripts/window.py clock at the hour's start."""
    es = WIN.es_state(ny)
    return np.where(es != "open", "es_closed", np.where(WIN.cash(ny), "cash", "es_open_other"))


def forward_returns(f, c):
    d = f.join(c, how="inner")
    o = c.o
    for h in (24,):
        later = o.reindex(d.index + pd.Timedelta(hours=h)).to_numpy()
        d[f"r{h}"] = (np.log(later) - np.log(d.o.to_numpy())) * 1e4
    return d


f = load_funding(); c = load_candles()
f["session"] = ny_session(f.ny)
d = forward_returns(f, c).dropna(subset=["r24"])
d["q"] = pd.qcut(d.prem_bps, 5, labels=False)
d["month"] = d.index.strftime("%m %b")
lo_band, hi_band = (INTEREST - CLAMP) * 1e4, (INTEREST + CLAMP) * 1e4     # flat-funding band, -2 to +4 bps
zero_fund = -CLAMP * 1e4                                                  # shorts paid below -3 bps
open_med = f.prem_bps[f.session != "es_closed"].median()
closed = f[f.session == "es_closed"]

# ---------------------------------------------------------------- canvas: 1536 x 1536, own axes
ja.SIZES["sq1536"] = (1536, 1536)
fig, ax0 = ja.figure("sq1536", "night"); ax0.remove()
LB = 11
L, R = 120, 48
W = 1536 - L - R
pw = (W - 144) // 2
A = ja._px_axes(fig, L, 216, W, 360)
B = ja._px_axes(fig, L, 696, pw, 288)
Cx = ja._px_axes(fig, L + pw + 144, 696, pw, 288)
Dq = ja._px_axes(fig, L, 1104, pw, 288)
E = ja._px_axes(fig, L + pw + 144, 1104, pw, 288)
def axlab(ax, xl, yl):
    ax.set_xlabel(xl, color=ja.C["muted"], family=ja.MONO, fontsize=LB)
    ax.set_ylabel(yl, color=ja.C["muted"], family=ja.MONO, fontsize=LB)


bps = FuncFormatter(lambda v, _: f"{v:+.0f}" if v else "0")

# A: premium by hour of week (New York time)
fw = f[~f.ny.dt.strftime("%Y-%m-%d").isin(list(WIN.ES_HOLIDAYS))]   # regular weeks: holidays left out
how = fw.ny.dt.day_of_week * 24 + fw.ny.dt.hour
g = fw.prem_bps.groupby(how)
med = g.median()
A.axhspan(lo_band, hi_band, color=ja.C["panel"], lw=0, zorder=0)
for day in range(5):
    A.axvspan(day * 24 + 9.5, day * 24 + 16, color=ja.C["tint_model"], lw=0, zorder=0.2)
ja.gap(A, med.index, g.quantile(0.25), g.quantile(0.75))
ja.zero(A)
ja.line(A, med.index, med.values, "actual", lw=2.5)
A.set_xlim(0, 168); A.set_ylim(*ja.fit(-6.5, 4.5, np.r_[g.quantile(0.25), g.quantile(0.75)], 0.5)); A.set_yticks([-6, -4, -2, 0, 2, 4]); A.yaxis.set_major_formatter(bps)
A.set_xticks([i * 24 + 12 for i in range(7)]); A.set_xticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
A.grid(False, axis="x")
def key_row(ax, items, size=LB, gap=3):
    """Colored text row, right-aligned on the panel-title baseline (no boxes)."""
    cw = 0.6 * size                                   # Plex Mono advance, pt
    off = 0
    for text, role in reversed(items):
        ax.annotate(text, (1, 1.035), xycoords="axes fraction", xytext=(-off, 0), textcoords="offset points",
                    ha="right", va="bottom", color=ja.C[role], fontsize=size, family=ja.MONO, weight="semibold")
        off += (len(text) + gap) * cw


key_row(A, [("US cash hours", "model"), ("flat-funding band -2 to +4", "faint")])
ja.note_at(A, 6 * 24 - 8, -5.4, f"ES closed: median {closed.prem_bps.median():+.2f} bps, {len(closed):,} h", size=LB).set_bbox(None)
t = ja.label_at(A, 18.5, 1.0, "17:00 ET halt", role="muted", dy=0, ha="left", size=LB); t.set_bbox(None); t.set_weight("regular")
k = 2 * 24 + 4                                    # Wed 04:00 ET, a typical ES-open hour
ja.signal(A, k, med.loc[k], label=f"{f[f.session != 'es_closed'].prem_bps.median():+.1f} bps median while ES trades", dx=4, dy=-44, size=LB, ms=0, role="actual")  # LED hidden on request; label kept
ja.panel_title(A, "when: median by hour of week, IQR shaded", size=LB)
axlab(A, "day of week, New York time", "premium to oracle, bps")

# B: daily median premium
dm = f.prem_bps.resample("D").median()
B.axhspan(lo_band, hi_band, color=ja.C["panel"], lw=0, zorder=0)
B.bar(dm.index, dm, width=1, color=np.where(dm < zero_fund, ja.C["actual"], ja.C["faint"]), lw=0, zorder=2)
ja.zero(B)
B.set_ylim(*ja.fit(-12, 4.5, dm, 1)); B.set_yticks([-10, -5, 0]); B.yaxis.set_major_formatter(bps)
B.xaxis.set_major_locator(md.MonthLocator(bymonth=[4, 6, 8, 10])); B.xaxis.set_major_formatter(md.DateFormatter("%b"))
t = ja.label_at(B, pd.Timestamp("2026-08-20", tz="UTC"), -11.1, f"below {zero_fund:.0f} bps: shorts paid", "actual", dy=0, size=LB); t.set_bbox(None)
ja.panel_title(B, f"daily median premium  ({(f.prem < 0).mean():.0%} of hours < 0)", size=LB)
axlab(B, "date, 2026", "median premium, bps")

# C: cumulative funding for a constant 1x long
cf = f.fund.cumsum() * 100
years = len(f) / (24 * 365)
# the window's own hours: a print at hour T settles the hour ending at T
inwin = (f.index > pd.Timestamp(WIN.T0, tz="UTC")) & (f.index <= pd.Timestamp(WIN.T1, tz="UTC"))
print(f"funding paid by a constant 1x long, window hours only ({inwin.sum()} prints): {f.fund[inwin].sum() * 100:+.3f}%")
ja.zero(Cx)
ja.line(Cx, cf.index, cf.values, "actual", lw=2.5)
Cx.set_ylim(*ja.fit(-1.3, 0.15, cf, 0.1)); Cx.set_yticks([-1.2, -0.8, -0.4, 0]); Cx.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}%"))
Cx.xaxis.set_major_locator(md.MonthLocator(bymonth=[4, 6, 8, 10])); Cx.xaxis.set_major_formatter(md.DateFormatter("%b"))
ja.end_label(Cx, cf.index, cf.values, f"long received {-cf.iloc[-1]:.2f}%, about {-cf.iloc[-1] / years:.1f}%/yr", "actual", dy=14, size=LB)
ja.panel_title(Cx, "funding paid by a constant 1x long", size=LB)
axlab(Cx, "date, 2026", "funding paid, cum. %")

# D: next-24h return by premium quintile
gq = d.groupby("q").agg(p=("prem_bps", "median"), r=("r24", "mean"), se=("r24", lambda s: s.std() / np.sqrt(len(s))))
Dq.bar(range(5), gq.r, color=[ja.C["actual"]] + [ja.C["faint"]] * 4, width=0.6, zorder=2)
Dq.errorbar(range(5), gq.r, yerr=2 * gq.se * np.sqrt(24), fmt="none", ecolor=ja.C["muted"], elinewidth=1.2, capsize=0, zorder=3)
ja.zero(Dq)
Dq.set_xticks(range(5)); Dq.set_xticklabels([f"{p:+.1f}" for p in gq.p]); Dq.grid(False, axis="x")
_e = 2 * gq.se * np.sqrt(24)
Dq.set_ylim(*ja.fit(-28, 62, np.r_[gq.r - _e, gq.r + _e], 4)); Dq.set_yticks([-20, 0, 20, 40]); Dq.yaxis.set_major_formatter(bps)
ja.label_at(Dq, 0.35, gq.r.iloc[0] + 3, f"{gq.r.iloc[0]:+.0f} bps", "actual", dy=0, ha="left", size=LB)
ja.note_at(Dq, 2.8, 50, "bars: 2 SE, widened for overlap", role="faint", size=LB)
ja.panel_title(Dq, "deepest fifth next 24h: up on average...", size=LB)
axlab(Dq, "premium quintile, median bps", "mean 24h return, bps")

# E: deepest-discount fifth by month vs all hours
months = sorted(d.month.unique())
q0 = d[d.q == 0].groupby("month").agg(r=("r24", "mean"), n=("r24", "size")).reindex(months)
base = d.groupby("month").r24.mean().reindex(months)
x = np.arange(len(months))
daily = d[d.index.hour == 20]
corr = np.corrcoef(daily.prem_bps, daily.r24)[0, 1]
tstat = corr * np.sqrt(len(daily) - 2) / np.sqrt(1 - corr * corr)
E.bar(x - 0.19, q0.r, 0.36, color=ja.C["actual"], zorder=2)
E.bar(x + 0.19, base, 0.36, color=ja.C["faint"], zorder=2)
ja.zero(E)
E.set_xticks(x); E.set_xticklabels([m[3:] for m in months]); E.grid(False, axis="x")
ehi = ja.fit(-45, 165, np.r_[q0.r, base], 15)[1]
E.set_ylim(ja.fit(-45, 165, np.r_[q0.r, base], 10)[0], ehi); E.set_yticks([0, 50, 100, 150]); E.yaxis.set_major_formatter(bps)
for txt_, role_, x_ in (("deepest fifth", "actual", 1.6), ("all hours", "faint", 4.25)):
    t = ja.label_at(E, x_, ehi - 55, txt_, role_, dy=0, ha="left", size=LB); t.set_bbox(None); t.set_va("center")
ja.note_at(E, 4.3, ehi - 17, f"daily test: corr {corr:.2f}, t {tstat:.2f}, n {len(daily)}", size=LB)
# months that contribute most of the deepest fifth's summed 24h return (positive months only)
contrib = (q0.r * q0.n).clip(lower=0).dropna()
contrib = contrib / contrib.sum()
top = contrib.sort_values(ascending=False)
lead = list(top.index[:(top.cumsum() < 0.6).sum() + 1])
mname = lambda m: pd.Timestamp(f"2026-{m[:2]}-01").strftime("%b")
print("funding panel E: deepest-fifth return share by month", contrib.round(2).to_dict())
if WIN.IS_ATLAS:
    etitle = "...but mostly from Mar and Apr"          # the published panel title
elif len(lead) <= 2:
    etitle = f"...but mostly from {' and '.join(mname(m) for m in sorted(lead))}"
else:
    etitle = f"...in {int((q0.r > base).sum())} of {len(months)} months"
ja.panel_title(E, etitle, size=LB)
axlab(E, f"month, 2026; {len(d):,} h from {d.index.min():%b} {d.index.min().day}", "mean 24h return, bps")

span = f"{f.index.min():%b} {f.index.min().day} to {f.index.max():%b} {f.index.max().day}, {f.index.max().year}"
WIN.expect("funding: median premium while ES trades (bps)", round(open_med, 1), -3.2, tol=0.05)
ja.finish(fig, f"xyz:SP500 trades about {-open_med:.0f} bps under oracle while ES is open", hl=f"about {-open_med:.0f} bps",
          subtitle=f"xyz:SP500 perp on Hyperliquid, {span}, {len(f):,} funding hours",
          source=f"Data: Hyperliquid public API (fundingHistory, 1h candles), {span}. No ES prices.")
ja.save(fig, "out/funding.png")
