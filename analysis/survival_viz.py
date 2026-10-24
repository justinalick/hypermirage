"""Order lifetime survival curves on xyz:SP500, split by distance from the touch at placement.

Kaplan-Meier estimate of the share of displayed orders still resting t seconds after they first
appear in the book. Event = removed by a cancel (classes displayed_pulled, displayed_partial).
Censored = fully filled after resting (filled with displayed_blocks > 0) or still open at the end of
the day window. Excluded: rejected, never_displayed, trigger, pre_existing (no distance), and orders
that filled on arrival, and orders with no measurable distance (no touch on one side).
Lifetime (ms) = displayed_blocks x that day's ms_per_block.

Also checks the replayed touch against the Reservoir 1m L2 book for every day (read-only).

Usage:
  .venv/bin/python analysis/survival_viz.py [--out out/survival_v1.png]
"""
from __future__ import annotations

import argparse
import glob
import os

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.abspath(".")
LT = os.path.join(ROOT, "data/derived/lifecycle_touch/xyz_SP500/*.parquet")

# touch.py buckets merged into four for legibility
GROUP = """CASE WHEN dist_bucket IN ('1 improves touch', '2 at touch') THEN 'a'
                 WHEN dist_bucket = '3 within 1 bp' THEN 'b'
                 WHEN dist_bucket = '4 1-5 bps' THEN 'c' ELSE 'd' END"""
BUCKETS = [
    ("a", "At or inside the touch"),
    ("b", "Up to 1 bp behind"),
    ("c", "1 to 5 bps behind"),
    ("d", "More than 5 bps behind"),
]
# Ordinal blue ramp, light (near the touch) to dark (far)
COLORS = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def book_check(con) -> pd.DataFrame:
    rows = []
    for bbo in sorted(glob.glob(os.path.join(ROOT, "data/derived/bbo/xyz_SP500/*.parquet"))):
        d = os.path.basename(bbo)[:8]
        book = os.path.join(ROOT, f"data/raw/xyz/book_1m/SP500/{d[:4]}-{d[4:6]}-{d[6:]}.parquet")
        if not os.path.exists(book):
            continue
        r = con.execute(f"""
            WITH r AS (SELECT block_number, CAST(bids[1].px AS DOUBLE) r_bid, CAST(asks[1].px AS DOUBLE) r_ask
                       FROM read_parquet('{book}')),
                 b AS (SELECT * FROM read_parquet('{bbo}')),
                 j AS (SELECT r.*, b.best_bid, b.best_ask FROM r ASOF LEFT JOIN b ON b.block <= r.block_number)
            SELECT count(*), avg((best_bid = r_bid)::int), avg((best_ask = r_ask)::int) FROM j
        """).fetchone()
        rows.append((d, *r))
    return pd.DataFrame(rows, columns=["day", "snapshots", "bid_match", "ask_match"])


def km(con, weight: str) -> dict:
    df = con.execute(f"""
        SELECT {GROUP} b, displayed_blocks * ms_per_block t,
               sum(CASE WHEN class IN ('displayed_pulled','displayed_partial') THEN {weight} ELSE 0 END) ev,
               sum({weight}) w, count(*) n
        FROM read_parquet('{LT}')
        WHERE displayed_blocks > 0 AND dist_bps IS NOT NULL
          AND class IN ('displayed_pulled','displayed_partial','filled','still_open')
        GROUP BY 1, 2 ORDER BY 1, 2
    """).df()
    out = {}
    for b, g in df.groupby("b"):
        g = g.sort_values("t")
        at_risk = g["w"][::-1].cumsum()[::-1].to_numpy()
        s = np.cumprod(1 - g["ev"].to_numpy() / at_risk)
        out[b] = (g["t"].to_numpy(), s, int(g["n"].sum()))
    return out


def surv_at(curve, ms):
    t, s, _ = curve
    i = np.searchsorted(t, ms, side="right") - 1
    return 1.0 if i < 0 else float(s[i])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "out/survival_v1.png"))
    args = ap.parse_args()
    con = duckdb.connect()

    chk = book_check(con)
    print(chk.to_string(index=False))
    print(f"book match, all days: bid {chk.bid_match.mean():.3%}  ask {chk.ask_match.mean():.3%}")

    meta = con.execute(f"""
        SELECT count(*) n, count(DISTINCT user) accts, min(placed_ms) p0, max(placed_ms) p1,
               avg(ms_per_block) mspb, sum(notional_usd) usd,
               sum((class IN ('displayed_pulled','displayed_partial'))::int) cancels
        FROM read_parquet('{LT}')
        WHERE displayed_blocks > 0 AND dist_bps IS NOT NULL
          AND class IN ('displayed_pulled','displayed_partial','filled','still_open')
    """).df().iloc[0]
    excl = con.execute(f"SELECT class, count(*) FROM read_parquet('{LT}') GROUP BY 1").fetchall()
    print(meta.to_dict(), excl)
    mspb = float(meta.mspb)

    cnt = km(con, "1")
    usd = km(con, "notional_usd")
    for b, lab in BUCKETS:
        line = [f"{lab:20s} n={cnt[b][2]:>9,}"]
        for sec in (0.5, 1, 10, 60, 600):
            k = sec * 1000
            line.append(f"S({sec}s)={surv_at(cnt[b], k):.3f}/{surv_at(usd[b], k):.3f}")
        print("  ".join(line))

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13})
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=200)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for (b, lab), c in zip(BUCKETS, COLORS):
        t, s, n = cnt[b]
        x = t / 1000
        ax.step(np.r_[x[0] * 0.999, x], np.r_[1.0, s], where="post", color=c, lw=2.2, solid_capstyle="round")
        ax.plot([], [], color=c, lw=2.6, label=f"{lab}  ({n/1e6:.1f}M orders)")
    leg = ax.legend(loc="upper right", frameon=False, fontsize=12, labelcolor=INK, handlelength=1.6,
                    title="Distance from the touch at placement", title_fontsize=12, alignment="left")
    leg.get_title().set_color(INK2)
    ax.set_xscale("log")
    ax.set_xlim(0.06, 3600)
    ax.set_ylim(0, 1.02)
    ticks = [0.1, 1, 10, 60, 600, 3600]
    ax.set_xticks(ticks)
    ax.set_xticklabels(["0.1s", "1s", "10s", "1m", "10m", "1h"])
    ax.minorticks_off()
    ax.set_yticks(np.arange(0, 1.01, 0.25))
    ax.set_yticklabels([f"{v:.0%}" for v in np.arange(0, 1.01, 0.25)])
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, length=0, labelsize=12)
    ax.set_xlabel("Time since the order first appeared in the book (log scale)", color=INK2, fontsize=12)
    ax.set_ylabel("Share of orders still resting", color=INK2, fontsize=12)

    s1 = {b: 1 - surv_at(cnt[b], 1000) for b, _ in BUCKETS}
    fig.text(0.06, 0.955, "Most S&P 500 perp quotes near the touch are cancelled within a second",
             fontsize=17, fontweight="bold", color=INK, ha="left")
    fig.text(0.06, 0.912,
             f"Kaplan-Meier survival of displayed limit orders on Hyperliquid (xyz:SP500). Within 1s, "
             f"{s1['a']:.0%} of orders at or inside the touch\nand {s1['b']:.0%} of those up to 1 bp behind "
             f"are cancelled, against {s1['d']:.0%} of orders more than 5 bps away.",
             fontsize=12, color=INK2, ha="left", va="top", linespacing=1.4)
    fig.text(0.06, 0.826,
             "The touch is the best bid (for buy orders) or best ask (for sell orders) in the block before the "
             "order is placed.\nDistance is the price gap to the touch, in bps of the mid price.",
             fontsize=11, color=INK2, ha="left", va="top", linespacing=1.4, style="italic")
    d0 = pd.to_datetime(meta.p0, unit="ms").strftime("%b %-d")
    d1 = pd.to_datetime(meta.p1, unit="ms").strftime("%b %-d, %Y")
    fig.text(0.06, 0.03,
             f"xyz:SP500, {d0} to {d1} (14 days, UTC). n = {int(meta.n):,} displayed orders from "
             f"{int(meta.accts):,} accounts. Event = cancel; fills and orders open at day end are censored.\n"
             "Excludes rejected orders, orders cancelled in the block they were placed, fills on arrival, and "
             "orders placed before the window.\nTouch replayed block by block from order data; matches the "
             f"independent 1m L2 book at {min(chk.bid_match.mean(), chk.ask_match.mean()):.2%} of snapshots.\n"
             "Source: Hydromancer Reservoir / node data",
             fontsize=9.5, color=MUTED, ha="left", va="bottom", linespacing=1.5)
    fig.subplots_adjust(left=0.08, right=0.80, top=0.74, bottom=0.22)
    fig.savefig(args.out, facecolor=SURF)
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
