import sys, os; sys.path.insert(0, "analysis")
import duckdb as _d
_c = _d.connect
def _conn(*a, **k):
    c = _c(*a, **k); c.execute("SET memory_limit='3GB'; SET threads=2"); return c
_d.connect = _conn
try: _d.default_connection().execute("SET memory_limit='3GB'; SET threads=2")
except Exception: pass
"""Independent checks for survival_viz.py (xyz:SP500, Oct 8-21).

1. Rebuild every lifetime from the raw node order statuses for a random sample of orders and
   compare with displayed_blocks and class in the lifecycle table.
2. Recompute dist_bps from best_bid / best_ask / mid and check the distance bucket.
3. Recompute the Kaplan-Meier curves row by row in numpy, in exact milliseconds per day
   (not the pooled ms_per_block), and compare with survival_viz.km() at the headline points.
4. Brute-force textbook Kaplan-Meier on a small subsample vs the vectorised estimator.
5. Naive bounds: share cancelled by t among all orders (lower bound) and among orders that
   ended by cancel or rested past t (upper bound) must bracket the KM estimate.

Usage:
  .venv/bin/python analysis/survival_verify.py
"""

import os
import sys

import duckdb
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import survival_viz as sv  # noqa: E402

ROOT = sv.ROOT
LT = sv.LT
# Outside the two-week atlas the row-level steps would hold every order of the window in memory, so they run on
# twelve days spread evenly over the window (first and last included); the estimator being checked is the same.
_W = os.path.join(ROOT, "scripts"); sys.path.insert(0, _W)
import window as WIN  # noqa: E402
if not WIN.IS_ATLAS and WIN.N_DAYS > 14:
    _days = sorted({WIN.DAYS[round(i * (WIN.N_DAYS - 1) / 11)] for i in range(12)})
    _dir = os.path.join(ROOT, "data/checks/spotcheck/survival_sample")
    os.makedirs(_dir, exist_ok=True)
    for _f in os.listdir(_dir):
        os.remove(os.path.join(_dir, _f))
    for _d in _days:
        os.symlink(os.path.realpath(os.path.join(ROOT, f"data/derived/lifecycle_touch/xyz_SP500/{_d}.parquet")), os.path.join(_dir, f"{_d}.parquet"))
    LT = sv.LT = os.path.join(_dir, "*.parquet")
    print("sample days:", " ".join(_days))
OS = os.path.join(ROOT, "data/l4/order_statuses/xyz_SP500")
CANCEL = ("displayed_pulled", "displayed_partial")
KEEP = ("class IN ('displayed_pulled','displayed_partial','filled','still_open') "
        "AND displayed_blocks > 0 AND dist_bps IS NOT NULL")
POINTS = (0.5, 1.0, 10.0, 60.0, 600.0)


def km_exact(t, ev):
    """Kaplan-Meier on unweighted rows; returns (unique times, survival after each time)."""
    o = np.argsort(t, kind="stable")
    t, ev = t[o], ev[o]
    ut, first, counts = np.unique(t, return_index=True, return_counts=True)
    d = np.add.reduceat(ev.astype(np.int64), first)
    at_risk = len(t) - first
    return ut, np.cumprod(1 - d / at_risk)


def km_textbook(t, ev):
    """Same estimator written as the textbook loop, for small samples."""
    s, out = 1.0, {}
    for u in sorted(set(t)):
        n = sum(1 for x in t if x >= u)
        d = sum(1 for x, e in zip(t, ev) if x == u and e)
        s *= 1 - d / n
        out[u] = s
    return out


def at(ut, s, x):
    i = np.searchsorted(ut, x, side="right") - 1
    return 1.0 if i < 0 else float(s[i])


def main() -> int:
    con = duckdb.connect()
    ok = True

    # 1. Raw-event check on a random sample (one hour file per sampled order)
    print("1. Lifetimes rebuilt from raw order statuses")
    samp = con.execute(f"""
        SELECT left(parse_filename(filename, true), 8) d, oid, class, displayed_blocks
        FROM read_parquet('{LT}', filename = true)
        WHERE {KEEP}
        USING SAMPLE reservoir(300 ROWS) REPEATABLE (7)
    """).fetchall()
    bad = 0
    for d, oid, cls, blocks in samp:
        src = [os.path.join(OS, d, "*.parquet")]  # the lifecycle table is built from this day only
        r = con.execute(f"""
            SELECT min(block_number) FILTER (WHERE status = 'open'), max(block_number),
                   arg_max(status, block_number)
            FROM read_parquet({src}) WHERE oid = {oid}
        """).fetchone()
        b_open, b_last, last = r
        if cls == "still_open":
            continue  # censored at day end, no terminal event to compare
        got = b_last - b_open
        if got != blocks:
            bad += 1
            print(f"   mismatch oid {oid}: table {blocks}, raw {got} ({last})")
    print(f"   {len(samp)} sampled orders, {bad} mismatches")
    ok &= bad == 0

    # 2. Distance buckets
    print("2. Distance from the touch recomputed")
    r = con.execute(f"""
        WITH x AS (
          SELECT dist_bucket, dist_bps,
                 CASE WHEN side = 'B' THEN (best_bid - limit_px) / mid * 1e4
                      ELSE (limit_px - best_ask) / mid * 1e4 END AS d2
          FROM read_parquet('{LT}') WHERE {KEEP})
        SELECT count(*), max(abs(d2 - dist_bps)),
               sum((CASE WHEN d2 < 0 THEN '1' WHEN d2 = 0 THEN '2' WHEN d2 <= 1 THEN '3'
                         WHEN d2 <= 5 THEN '4' WHEN d2 <= 25 THEN '5' ELSE '6' END
                    != left(dist_bucket, 1))::int),
               sum((dist_bps IS NULL)::int)
        FROM x
    """).fetchone()
    print(f"   {r[0]:,} orders, max |diff| {r[1]:.2e} bps, bucket mismatches {r[2]}, null distance {r[3]}")
    ok &= r[2] == 0 and r[3] == 0

    # 3. Row-level KM in exact ms vs the chart's estimator
    print("3. Kaplan-Meier, row level in exact ms vs chart")
    df = con.execute(f"""
        SELECT {sv.GROUP} b, displayed_blocks * ms_per_block AS t_ms,
               class IN {CANCEL} AS ev
        FROM read_parquet('{LT}') WHERE {KEEP}
    """).fetch_df()
    cnt = sv.km(con, "1")
    mspb = con.execute(f"SELECT avg(ms_per_block) FROM read_parquet('{LT}') WHERE {KEEP}").fetchone()[0]
    worst = 0.0
    for b, lab in sv.BUCKETS:
        g = df[df.b == b]
        ut, s = km_exact(g.t_ms.to_numpy(), g.ev.to_numpy())
        row = [f"   {lab:24s}"]
        for p in POINTS:
            a = 1 - at(ut, s, p * 1000)
            c = 1 - sv.surv_at(cnt[b], p * 1000)
            worst = max(worst, abs(a - c))
            row.append(f"{p:g}s {a:.3f}/{c:.3f}")
        print("  ".join(row))
    print(f"   cancelled-by-t, exact vs chart: max abs diff {worst:.4f}")
    ok &= worst < 1e-9

    # 4. Textbook loop on a subsample
    print("4. Textbook KM loop vs vectorised, 3,000-order subsample")
    sub = df.sample(3000, random_state=1)
    t, e = sub.t_ms.to_numpy(), sub.ev.to_numpy()
    ut, s = km_exact(t, e)
    tb = km_textbook(list(t), list(e))
    diff = max(abs(tb[u] - v) for u, v in zip(ut, s))
    print(f"   max abs diff {diff:.2e}")
    ok &= diff < 1e-12

    # 5. Naive bounds at 1s
    print("5. Naive bounds on share cancelled within 1s")
    for b, lab in sv.BUCKETS:
        g = df[df.b == b]
        ut, s = km_exact(g.t_ms.to_numpy(), g.ev.to_numpy())
        k = 1 - at(ut, s, 1000)
        canc = ((g.t_ms <= 1000) & g.ev).sum()
        lo = canc / len(g)
        hi = canc / ((g.t_ms > 1000) | g.ev).sum()
        print(f"   {lab:24s} lower {lo:.3f}  KM {k:.3f}  upper {hi:.3f}")
        ok &= lo - 1e-9 <= k <= hi + 1e-9

    print("\nALL CHECKS PASS" if ok else "\nSOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
