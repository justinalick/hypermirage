"""Independent check of vol_spread.py, in DuckDB SQL, plus a second spread source.

1. Time-weighted spread: recompute per minute directly from the replayed BBO with a different
   method (each quote state weighted by its block duration, assigned by block -> minute via an
   ASOF join on the L2 minute starts), compare with spread_minutes.parquet on a sample day.
2. Gaps: recompute the top vs bottom relative-vol decile gaps (spread and depth, futures open and
   closed) in SQL from the minute tables.
3. Second source: the Reservoir 1m L2 spread (a point sample at each minute start). It is one tick
   92% of the time when futures are open, so its median cannot move; compare means instead: mean
   spread in the top vs bottom relative-vol decile, L2 snapshot vs replay (same minutes).
"""
import datetime as dt, json, sys
from zoneinfo import ZoneInfo
import duckdb, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN          # the window, its holiday list and the outputs to compare; the clock below is separate

R = "data/derived/"
L2 = "data/raw/xyz/book_1m/SP500/*.parquet"
con = duckdb.connect()
con.execute("SET TimeZone='UTC'; SET memory_limit='4GB'")
ok = True
# The UTC session rules below hold in US daylight time (CME 16:00 Chicago = 21:00 UTC).
if WIN.utc_offset_hours() != -4:
    sys.exit("check_vol_spread.py: UTC session rules assume US daylight time throughout the window")
# Holiday closures as UTC intervals: halt at the listed Chicago time; Monday holidays reopen at 17:00 Chicago,
# Friday holidays run into the weekend (16:00 Chicago, where the weekend rule takes over).
CHI = ZoneInfo("America/Chicago")
hol = []
for d, hhmm in WIN.ES_HOLIDAYS.items():
    day = dt.date.fromisoformat(d)
    a = dt.datetime.combine(day, dt.time(int(hhmm[:2]), int(hhmm[3:])), CHI)
    b = dt.datetime.combine(day, dt.time(16 if day.weekday() == 4 else 17), CHI)
    hol.append((a.astimezone(dt.timezone.utc).replace(tzinfo=None), b.astimezone(dt.timezone.utc).replace(tzinfo=None)))
con.register("hol", pd.DataFrame(hol or [(pd.Timestamp(0), pd.Timestamp(0))], columns=["h0", "h1"]))


def check(name, got, want, tol):
    global ok
    good = abs(got - want) <= tol
    ok &= good
    print(f"{'OK  ' if good else 'FAIL'} {name:44s} got {got:+.3f}  expected {want:+.3f}")


# 1. spread on a sample day (mid-window) by a second method
_wd = [d for d in WIN.DATES if d.weekday() < 5]   # a weekday: thin weekend books straddle more minute starts
SAMPLE = _wd[len(_wd) // 2].strftime("%Y%m%d") if not WIN.IS_ATLAS else "20261014"
con.execute(f"""CREATE TABLE b AS SELECT date_trunc('minute', make_timestamp(block_time_ms * 1000))::TIMESTAMP t,
    block_number::BIGINT b0 FROM read_parquet('{L2}')""")
got = con.sql(f"""
WITH q AS (SELECT block::BIGINT blk, (best_ask - best_bid) / ((best_ask + best_bid) / 2) * 1e4 s,
                  lead(block) OVER (ORDER BY block) - block dur
           FROM '{R}bbo/xyz_SP500/{SAMPLE}.parquet' WHERE best_ask > best_bid),
x AS (SELECT b.t, q.s, q.dur FROM q ASOF JOIN b ON b.b0 <= q.blk)
SELECT max(abs(x.tw - s.tw_spread_bps)), median(abs(x.tw - s.tw_spread_bps)), count(*)
FROM (SELECT t, sum(s * dur) / sum(dur) tw FROM x GROUP BY t) x
JOIN '{R}vol_spread/spread_minutes.parquet' s USING (t)""").fetchall()[0]
# method 2 assigns a state that straddles a minute start wholly to its starting minute, so small
# differences are expected; medians should agree closely
check(f"{SAMPLE} spread, median |diff| bps", got[1], 0.0, 0.01)
print(f"     (max |diff| {got[0]:.3f} bps over {got[2]} minutes; straddling states)")

# 2 and 3. decile gaps
base = f"""
WITH a AS (SELECT d.t, d.d10, s.tw_spread_bps sp, s.l2_spread_bps sl2,
                  1e4 * ln(d.mid / lag(d.mid) OVER (ORDER BY d.t)) r
           FROM '{R}offhours/offhours_depth_minutes.parquet' d
           LEFT JOIN '{R}vol_spread/spread_minutes.parquet' s USING (t)),
b AS (SELECT *, stddev_samp(r) OVER w * sqrt(365 * 1440) / 100 rv, count(r) OVER w nr
      FROM a WINDOW w AS (ORDER BY t ROWS BETWEEN 14 PRECEDING AND CURRENT ROW)),
c AS (SELECT *, isodow(t) dw, hour(t) h FROM b WHERE nr >= 12 AND sp IS NOT NULL AND rv > 0),
d0 AS (SELECT c.*, (SELECT min(h0) FROM hol WHERE c.t >= h0 AND c.t < h1) hs FROM c),
d AS (SELECT *, (dw = 5 AND h >= 21) OR dw = 6 OR (dw = 7 AND h < 22) OR hs IS NOT NULL wk FROM d0),
e AS (SELECT *, CASE WHEN wk OR (dw <= 4 AND h = 21) THEN 'closed' ELSE 'open' END es,
             h::VARCHAR || CASE WHEN wk THEN 'w' ELSE 'd' END hod,
             CASE WHEN hs IS NOT NULL AND dw <> 5 THEN 'H' || strftime(hs, '%m%d')
                  WHEN wk THEN 'W' || strftime(coalesce(hs, t - INTERVAL (((dw - 5 + 7) % 7)) DAY), '%m%d')
                  ELSE strftime(t, '%m%d') END dy FROM d),
f AS (SELECT *, ln(rv) - median(ln(rv)) OVER (PARTITION BY hod) xr,
             ln(sp) - median(ln(sp)) OVER (PARTITION BY hod) xs,
             ln(d10) - median(ln(d10)) OVER (PARTITION BY hod) xd,
             ln(sl2) - median(ln(sl2)) OVER (PARTITION BY hod) xl FROM e),
g AS (SELECT *, xr - median(xr) OVER (PARTITION BY es, dy) rr, xs - median(xs) OVER (PARTITION BY es, dy) rs,
             xd - median(xd) OVER (PARTITION BY es, dy) rd, xl - median(xl) OVER (PARTITION BY es, dy) rl FROM f),
q AS (SELECT *, ntile(10) OVER (PARTITION BY es ORDER BY rr, t) - 1 dec FROM g)
SELECT es, count(*),
  100 * (exp(median(rs) FILTER (WHERE dec = 9) - median(rs) FILTER (WHERE dec = 0)) - 1),
  100 * (exp(median(rd) FILTER (WHERE dec = 9) - median(rd) FILTER (WHERE dec = 0)) - 1),
  100 * (avg(sl2) FILTER (WHERE dec = 9) / avg(sl2) FILTER (WHERE dec = 0) - 1),
  100 * (avg(sp) FILTER (WHERE dec = 9) / avg(sp) FILTER (WHERE dec = 0) - 1)
FROM q GROUP BY es ORDER BY es"""
# compare with what vol_spread.py wrote for this window (and, in the atlas window, with the published values)
dec = pd.read_parquet(f"{R}vol_spread/vol_spread_deciles.parquet").sort_values(["es", "q"])
meta = json.load(open(f"{R}vol_spread/vol_spread_meta.json"))
pct = lambda v: 100 * (2.718281828459045 ** v - 1)
want = {es: (meta["n_minutes_by_es"][es], pct(g.sp.iloc[-1] - g.sp.iloc[0]), pct(g.dep.iloc[-1] - g.dep.iloc[0]))
        for es, g in dec.groupby("es")}
if WIN.IS_ATLAS:
    for es, w in {"closed": (6335, 56.8, -19.2), "open": (13787, 18.9, -1.2)}.items():
        check(f"{es}: vol_spread.py output vs published (minutes)", want[es][0], w[0], 1)
        check(f"{es}: vol_spread.py output vs published (spread gap)", want[es][1], w[1], 0.15)
        check(f"{es}: vol_spread.py output vs published (depth gap)", want[es][2], w[2], 0.15)
for es, n, gs, gd, gl, gp in con.sql(base).fetchall():
    check(f"{es}: minutes", n, want[es][0], 1)   # one float-edge minute (rv ~ 0) may differ
    check(f"{es}: spread gap, %", gs, want[es][1], 0.5)
    check(f"{es}: depth gap, %", gd, want[es][2], 0.5)
    check(f"{es}: mean-spread gap, L2 minus replay, pp", gl - gp, 0.0, 12)
    print(f"     {es}: mean spread top vs bottom decile: L2 snapshot {gl:+.1f}%, replay {gp:+.1f}%")
    if es == "open" and WIN.IS_ATLAS:   # README: snapshot cross-check on means, about +22%
        check("open: L2 snapshot mean-spread gap, %", gl, 21.7, 0.5)
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
