"""xyz:SP500 funding vs premium: data checks, statistics and charts.

Inputs (Hyperliquid public API, fetched by fetch_api.py into this folder):
  sp500_funding_api.json   fundingHistory, one row per funding hour
  candles.json             candleSnapshot 1h, perp trade prices
Outputs: stats printed to stdout, charts written next to this file.

Run: .venv/bin/python analysis/funding/funding_premium.py
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
import window as WIN

HERE = Path("data/derived/funding"); HERE.mkdir(parents=True, exist_ok=True)
WINDOW = (f"{WIN.T0} 01:00", f"{WIN.T1} 00:00")  # funding prints settling the window's hours

# Funding rule, fitted from the data and checked below:
#   hourly funding = (premium + clamp(INTEREST - premium, -CLAMP, +CLAMP)) / DIV
INTEREST, CLAMP, DIV = 1e-4, 3e-4, 16
FLAT = INTEREST / DIV  # 6.25e-6 per hour, paid by longs inside the band


def load_funding():
    f = pd.DataFrame(json.load(open(HERE / "sp500_funding_api.json")))
    # API stamps arrive a few hundred ms after the hour; the print at hour T settles the hour ending T
    f["t"] = pd.to_datetime(f.time, unit="ms", utc=True).dt.floor("h")
    f = f[f.t <= pd.Timestamp(WIN.API_END, tz="UTC")].copy()
    assert not f.t.duplicated().any()
    hours = pd.date_range(f.t.min(), f.t.max(), freq="h")
    assert len(hours) == len(f), "missing funding hours"
    f["fund"] = f.fundingRate.astype(float)
    f["prem"] = f.premium.astype(float)
    f["prem_bps"] = f.prem * 1e4
    f["fund_ann_pct"] = f.fund * 24 * 365 * 100
    # label each print by the New York hour it covers (start of the hour)
    f["ny"] = (f.t - pd.Timedelta(hours=1)).dt.tz_convert("America/New_York")
    return f.set_index("t")


def load_candles():
    c = pd.DataFrame(json.load(open(HERE / "candles.json")))
    c["t"] = pd.to_datetime(c.t, unit="ms", utc=True)
    # pagination overlap returns the boundary bar twice; the later copy is the completed bar
    c = c.drop_duplicates("t", keep="last").set_index("t").sort_index()
    c = c[c.index <= pd.Timestamp(WIN.API_END, tz="UTC")]
    hours = pd.date_range(c.index.min(), c.index.max(), freq="h")
    assert len(hours) == len(c), "missing candle hours"
    return c[["o", "c"]].astype(float)


def check_rule(f):
    pred = (f.prem + np.clip(INTEREST - f.prem, -CLAMP, CLAMP)) / DIV
    err = (pred - f.fund).abs().max()
    print(f"funding rule max abs error: {err:.2e} over {len(f)} hours")
    assert err < 1e-9


def ny_session(ny):
    """Session of the hour starting at ny (scripts/window.py clock, read at the hour's start): es_closed =
    futures closed or in the daily halt (weekends, holiday closures, 17:00-18:00 ET Mon-Thu), cash = NYSE
    session hours, es_open_other = the rest."""
    es = WIN.es_state(ny)
    return np.where(es != "open", "es_closed", np.where(WIN.cash(ny), "cash", "es_open_other"))


def summarize(x):
    return pd.Series(
        dict(
            hours=len(x),
            prem_median_bps=x.prem_bps.median(),
            prem_mean_bps=x.prem_bps.mean(),
            share_prem_negative=(x.prem < 0).mean(),
            share_flat_funding=np.isclose(x.fund, FLAT, rtol=0, atol=1e-12).mean(),
            share_shorts_paid=(x.fund < 0).mean(),
            share_longs_pay_at_discount=((x.fund > 0) & (x.prem < 0)).mean(),
            funding_mean_ann_pct=x.fund_ann_pct.mean(),
            funding_cum_long_pct=x.fund.sum() * 100,
        )
    )


def forward_returns(f, c):
    """Perp log return in bps from the open of hour T (when the T print is known) to the open of hour T+h."""
    d = f.join(c, how="inner")
    o = c.o
    for h in (1, 4, 8, 24):
        later = o.reindex(d.index + pd.Timedelta(hours=h)).to_numpy()
        d[f"r{h}"] = (np.log(later) - np.log(d.o.to_numpy())) * 1e4
    return d


def main():
    f = load_funding()
    c = load_candles()
    check_rule(f)
    f["session"] = ny_session(f.ny)
    pd.set_option("display.width", 200)

    w = f.loc[WINDOW[0] : WINDOW[1]]
    print(f"\nfunding: {f.index.min()} to {f.index.max()}, {len(f)} hours; window {len(w)} hours")
    for name, x in (("full", f), (f"window {WIN.label()}", w)):
        print(f"\n== {name}")
        print(summarize(x).round(4).to_string())
        print(x.groupby("session").apply(summarize).round(3).to_string())

    # hour-of-week profile, Mon-Thu by NY hour (exchange holidays left out of hour-of-week profiles)
    mt = f[(f.ny.dt.day_of_week < 4) & ~f.ny.dt.strftime("%Y-%m-%d").isin(list(WIN.ES_HOLIDAYS))]
    prof = mt.prem_bps.groupby(mt.ny.dt.hour).median()
    print("\nMon-Thu median premium by NY hour:\n" + prof.round(2).to_string())

    d = forward_returns(f, c)
    d = d.dropna(subset=["r24"])
    d["q"] = pd.qcut(d.prem_bps, 5, labels=False)
    print(f"\nreturns sample: {d.index.min()} to {d.index.max()}, {len(d)} hours with a 24h forward return")
    print(d.groupby("q").agg(prem_median=("prem_bps", "median"), n=("r24", "size"),
                             r24_mean=("r24", "mean"), r24_median=("r24", "median")).round(2).to_string())
    daily = d[d.index.hour == 20]
    r = np.corrcoef(daily.prem_bps, daily.r24)[0, 1]
    print(f"non-overlapping daily test (20:00 UTC prints): n={len(daily)}, corr={r:.3f}, t~{r*np.sqrt(len(daily)-2)/np.sqrt(1-r*r):.2f}")
    d["month"] = d.index.strftime("%m %b")
    q0 = d[d.q == 0].groupby("month").agg(n=("r24", "size"), r24=("r24", "mean"))
    q0["all_hours_r24"] = d.groupby("month").r24.mean()
    print(q0.round(1).to_string())

    plot(f, d, prof)


def plot(f, d, prof):
    ink, mut, band, blue, orange = "#3d3d3a", "#8a8980", "#e8e7e1", "#2a78d6", "#eb6834"
    plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": mut, "axes.labelcolor": ink, "xtick.color": mut,
                         "ytick.color": mut, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titlelocation": "left", "axes.titlesize": 10, "axes.titlecolor": ink})
    lo_band, hi_band = (INTEREST - CLAMP) * 1e4, (INTEREST + CLAMP) * 1e4
    zero_fund = -CLAMP * 1e4  # funding crosses zero at -3 bps
    fig = plt.figure(figsize=(12, 11))
    gs = fig.add_gridspec(3, 2, hspace=0.45, wspace=0.22)

    # A: premium by hour of week (NY), every day of the week
    how = f.ny.dt.day_of_week * 24 + f.ny.dt.hour
    g = f.prem_bps.groupby(how)
    a = fig.add_subplot(gs[0, :])
    a.axhspan(lo_band, hi_band, color=band, zorder=0)
    for day in range(5):
        a.axvspan(day * 24 + 9.5, day * 24 + 16, color="#cde2fb", alpha=0.6, zorder=0)
    a.fill_between(g.median().index, g.quantile(0.25), g.quantile(0.75), color=orange, alpha=0.18, lw=0)
    a.plot(g.median().index, g.median(), c=orange, lw=2)
    a.axhline(0, c=mut, lw=0.6)
    a.set_xticks([i * 24 + 12 for i in range(7)])
    a.set_xticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    a.set_xlim(0, 168)
    a.set_ylabel("premium to oracle (bps)")
    a.set_title("A. The discount exists while ES trades: median premium by hour of week (New York time). "
                "Shade = middle 50%, blue = US cash hours,\ngray = flat-funding band. Daily bump = 17:00-18:00 ET "
                f"futures halt (Mon-Thu median {prof.loc[17]:.1f} bps vs about {prof.drop(17).median():.1f} otherwise)")
    a.text(5 * 24 + 20, -5.3, "Fri 17:00 to Sun 18:00 ET\n(futures closed): near zero", fontsize=8.5, color=ink, ha="center")

    # B: daily median premium
    dm = f.prem_bps.resample("D").median()
    b = fig.add_subplot(gs[1, 0])
    b.axhspan(lo_band, hi_band, color=band, zorder=0)
    b.bar(dm.index, dm, width=1, color=np.where(dm < zero_fund, orange, mut), lw=0)
    b.axhline(0, c=mut, lw=0.6)
    b.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    b.set_ylabel("daily median premium (bps)")
    b.set_title(f"B. The perp sat below the oracle on most days\n(orange = below {zero_fund:.0f} bps, where shorts get paid)")

    # C: cumulative funding for a constant 1x long
    cf = f.fund.cumsum() * 100
    years = len(f) / (24 * 365)
    cax = fig.add_subplot(gs[1, 1])
    cax.plot(cf.index, cf, c=blue, lw=2)
    cax.axhline(0, c=mut, lw=0.6)
    cax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    cax.set_ylabel("cumulative funding paid by a 1x long (%)")
    cax.set_title(f"C. Funding barely matters: a constant 1x long since {f.index.min():%b %d}\n"
                  f"received {-cf.iloc[-1]:.2f}% in total, about {-cf.iloc[-1] / years:.1f}%/yr")

    # D: next-24h return by premium quintile; error bars = 2 x SE inflated by sqrt(24) for overlapping windows
    gq = d.groupby("q").agg(p=("prem_bps", "median"), r=("r24", "mean"), se=("r24", lambda s: s.std() / np.sqrt(len(s))))
    e = fig.add_subplot(gs[2, 0])
    e.bar(range(5), gq.r, color=[orange] + [mut] * 4, width=0.6)
    e.errorbar(range(5), gq.r, yerr=2 * gq.se * np.sqrt(24), fmt="none", ecolor=ink, lw=1, capsize=3)
    e.set_xticks(range(5))
    e.set_xticklabels([f"{p:+.1f} bps" for p in gq.p])
    e.axhline(0, c=mut, lw=0.6)
    e.set_xlabel("premium quintile (median of each fifth of hours)")
    e.set_ylabel("mean next-24h perp return (bps)")
    e.set_title("D. Deepest discounts were followed by gains on average...\n(error bars: 2 SE, widened for overlapping 24h windows)")

    # E: deepest-discount quintile by month vs all hours
    months = sorted(d.month.unique())
    q0 = d[d.q == 0].groupby("month").agg(r=("r24", "mean"), n=("r24", "size")).reindex(months)
    base = d.groupby("month").r24.mean().reindex(months)
    x = np.arange(len(months))
    daily = d[d.index.hour == 20]
    corr = np.corrcoef(daily.prem_bps, daily.r24)[0, 1]
    ax = fig.add_subplot(gs[2, 1])
    ax.bar(x - 0.18, q0.r, 0.36, color=orange, label="hours in deepest-discount fifth")
    ax.bar(x + 0.18, base, 0.36, color=mut, label="all hours")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{m[3:]}\nn={0 if np.isnan(n) else int(n)}" for m, n in zip(months, q0.n)])
    ax.axhline(0, c=mut, lw=0.6)
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_ylabel("mean next-24h perp return (bps)")
    ax.set_title(f"E. ...but it doesn't hold up month to month.\nNon-overlapping daily test: corr {corr:.2f}, n={len(daily)}")

    fig.suptitle(f"xyz:SP500 premium and funding, {f.index.min():%b %d} to {f.index.max():%b %d %Y} "
                 f"({len(f):,} funding hours; returns from {d.index.min():%b %d}, {len(d):,} hours)",
                 x=0.01, ha="left", fontsize=11.5, color=ink, y=0.93)
    fig.text(0.01, 0.005, "Source: Hyperliquid public API (fundingHistory, 1h candles). Premium = HL's premium of impact "
             "prices to the deployer oracle. No ES data available. ", fontsize=8, color=mut)
    out = HERE / "sp500_funding_premium_v3.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
