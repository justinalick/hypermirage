"""Position holding time, xyz:SP500, every day of the run window (scripts/window.py). Writes data/derived/holding/holding.json.

Positions come from Reservoir fills: each fill carries the account's position before it (start_position), so
the position after it is start_position + signed size and nothing has to be assumed about the window's start.
Two measures:
  episodes  one account's position from flat (or a flip) to flat (or the next flip). Episodes that were
            already open at the window start are left out (their open time is unknown); episodes still open
            at the end are right-censored and handled with Kaplan-Meier. Split by account type and by the
            episode's peak notional; also weighted by notional traded inside the episode.
  lots      first-in first-out lots: every contract closed is matched to the oldest open contract of the
            same account, giving how long each dollar of position was held, notional-weighted. This is the
            measure that fits market makers, whose position rarely returns to exactly zero.
Account type: maker share of the account's window notional, >= 80% maker-heavy, <= 20% taker, else mixed.
Open-interest view (Little's law): time-averaged |position| / contracts closed per second. Unlike the lot
mean it counts inventory that sits for weeks, so it is the average age weighted by open interest rather than
by turnover. No account is named in the output."""
import json, os, sys
import duckdb, numba, numpy as np
sys.path.insert(0, "scripts")
import window as WIN

O = "data/derived/holding"
os.makedirs(O, exist_ok=True)
NS = 1_000_000_000
EPS = 1e-9
con = duckdb.connect(); con.execute("SET memory_limit='6GB'; SET threads=4")
SRC = f"read_parquet('data/raw/xyz/fills/*.parquet')"
cols = set(con.execute(f"DESCRIBE SELECT * FROM {SRC}").df().column_name)
tie = next((c for c in ("tid", "trade_id", "block_number", "hash") if c in cols), None)
print("fill columns:", sorted(cols)); print("tie-break within an account's millisecond:", tie)
con.execute(f"""CREATE TEMP TABLE f AS
 SELECT address a, epoch_ns(timestamp::TIMESTAMP)::BIGINT t, {tie + ',' if tie else ''} price::DOUBLE px,
        (CASE WHEN side='buy' THEN 1 ELSE -1 END) * size::DOUBLE d, start_position::DOUBLE sp, crossed,
        coalesce(is_liquidation, false) liq
 FROM {SRC} WHERE coin='xyz:SP500' AND timestamp >= '{WIN.T0}' AND timestamp < '{WIN.T1}'""")
con.execute("""CREATE TEMP TABLE acct AS SELECT a, sum(px*abs(d)) FILTER (WHERE NOT crossed) / sum(px*abs(d)) mk
               FROM f GROUP BY 1""")
con.execute("""CREATE TEMP TABLE acct2 AS SELECT a, row_number() OVER (ORDER BY a) - 1 aid,
               CASE WHEN mk >= 0.8 THEN 0 WHEN mk <= 0.2 THEN 2 ELSE 1 END typ FROM acct""")
TYPES = ["maker-heavy", "mixed", "taker"]
x = con.execute(f"""SELECT aid, typ, t, px, d, sp, crossed, liq FROM f JOIN acct2 USING (a)
                    ORDER BY aid, t{', ' + tie if tie else ''}""").fetchnumpy()
aid, typ, t, px, d, sp = (np.ascontiguousarray(x[k]) for k in ("aid", "typ", "t", "px", "d", "sp"))
crossed = np.ascontiguousarray(x["crossed"]).astype(np.bool_); liq = np.ascontiguousarray(x["liq"]).astype(np.bool_)
typ = typ.astype(np.int8); aid = aid.astype(np.int64)
T0 = int(np.datetime64(WIN.T0, "ns").astype(np.int64)); T1 = int(np.datetime64(WIN.T1, "ns").astype(np.int64))
n = len(t); n_acct = int(aid.max()) + 1
print(f"{n:,} fills, {n_acct:,} accounts, {WIN.span()}")

# lot hold-time histogram: bin 0 is < 1 ms, then 40 log bins per decade from 1 ms to 10^8 s
BPD, LO = 40, -3.0
NB = 1 + int((8 - LO) * BPD) + 1


@numba.njit(cache=True)
def hbin(ns):
    s = ns / 1e9
    if s < 1e-3:
        return 0
    b = 1 + int((np.log10(s) - LO) * BPD)
    return min(b, NB - 1)


@numba.njit(cache=True)
def sgn(v):
    return 0 if abs(v) < EPS else (1 if v > 0 else -1)


@numba.njit(cache=True)
def run(aid, typ, t, px, d, sp, crossed, liq, T0, T1):
    n = len(t)
    # episodes: open time (-1 = opened before the window), close time (-1 = still open), peak notional,
    # traded notional, maker notional, fills, account, opened/closed by liquidation, chain-break flag
    e_open = np.empty(n + 1, np.int64); e_close = np.empty(n + 1, np.int64); e_peak = np.zeros(n + 1)
    e_vol = np.zeros(n + 1); e_mk = np.zeros(n + 1); e_n = np.zeros(n + 1, np.int64); e_a = np.empty(n + 1, np.int64)
    e_liq = np.zeros(n + 1, np.int8); e_brk = np.zeros(n + 1, np.bool_); e_side = np.zeros(n + 1, np.int8)
    ne = 0
    # lots
    q_t = np.empty(n + 1, np.int64); q_q = np.empty(n + 1)
    hist = np.zeros((3, 2, NB)); hq = np.zeros((3, 2, 2))   # [type, long/short]: notional-weighted hold histogram; qty, qty*hold_s
    cens_left = np.zeros(3); cens_right = np.zeros(3); closed_nt = np.zeros(3)
    little_inv = np.zeros(3); little_out = np.zeros(3)     # contract-seconds held; contracts closed
    breaks = 0
    i = 0
    while i < n:
        a = aid[i]; ty = typ[i]
        j = i
        while j < n and aid[j] == a:
            j += 1
        cur = -1; head = i; tail = i; pos = sp[i]; qs = sgn(pos)
        # position held before the first fill in the window
        little_inv[ty] += abs(sp[i]) * (t[i] - T0) / 1e9
        if qs != 0:
            q_t[tail] = -1; q_q[tail] = abs(pos); tail += 1
            cur = ne; e_open[ne] = -1; e_close[ne] = -1; e_a[ne] = a; e_side[ne] = qs; ne += 1
        for k in range(i, j):
            s0 = sp[k]; s1 = s0 + d[k]
            if abs(s1) < EPS:
                s1 = 0.0
            if abs(s0 - pos) > 1e-6 * max(1.0, abs(pos)):   # position changed outside the fills seen here
                breaks += 1
                if cur >= 0:
                    e_brk[cur] = True; e_close[cur] = t[k]; cur = -1
                head = tail
                if sgn(s0) != 0:
                    q_t[tail] = -1; q_q[tail] = abs(s0); tail += 1
                    cur = ne; e_open[ne] = -1; e_close[ne] = -1; e_a[ne] = a; e_side[ne] = sgn(s0); ne += 1
            g0 = sgn(s0); g1 = sgn(s1)
            notl = abs(d[k]) * px[k]
            # ---- episodes
            if g0 != 0 and g1 != g0:                     # reduces through zero: close (and maybe reopen)
                part = abs(s0) / abs(d[k])
                e_vol[cur] += notl * part; e_n[cur] += 1
                if not crossed[k]:
                    e_mk[cur] += notl * part
                if liq[k]:
                    e_liq[cur] |= 2
                e_close[cur] = t[k]; cur = -1
            if g1 != 0 and g1 != g0:                     # opens from flat or flips
                cur = ne; e_open[ne] = t[k]; e_close[ne] = -1; e_a[ne] = a; e_side[ne] = g1
                part = abs(s1) / abs(d[k])
                e_vol[ne] += notl * part; e_n[ne] += 1
                if not crossed[k]:
                    e_mk[ne] += notl * part
                if liq[k]:
                    e_liq[ne] |= 1
                ne += 1
            elif g1 != 0 and cur >= 0:                   # same side, add or reduce
                e_vol[cur] += notl; e_n[cur] += 1
                if not crossed[k]:
                    e_mk[cur] += notl
            if cur >= 0:
                e_peak[cur] = max(e_peak[cur], abs(s1) * px[k])
            # ---- lots (FIFO)
            red = 0.0
            sd = 0 if g0 > 0 else 1                      # lots being closed are long (0) or short (1)
            if g0 != 0 and g1 != g0:
                red = abs(s0)
            elif g0 != 0 and abs(s1) < abs(s0):
                red = abs(s0) - abs(s1)
            while red > EPS and head < tail:
                m = min(red, q_q[head])
                if q_t[head] < 0:
                    cens_left[ty] += m * px[k]
                else:
                    h = t[k] - q_t[head]
                    hist[ty, sd, hbin(h)] += m * px[k]
                    hq[ty, sd, 0] += m; hq[ty, sd, 1] += m * h / 1e9
                closed_nt[ty] += m * px[k]; little_out[ty] += m
                q_q[head] -= m; red -= m
                if q_q[head] <= EPS:
                    head += 1
            add = 0.0
            if g1 != 0 and g1 != g0:
                add = abs(s1)
            elif g1 != 0 and abs(s1) > abs(s0):
                add = abs(s1) - abs(s0)
            if add > EPS:
                q_t[tail] = t[k]; q_q[tail] = add; tail += 1
            # inventory until the next fill of this account (or the window end)
            tn = t[k + 1] if k + 1 < j else T1
            little_inv[ty] += abs(s1) * (tn - t[k]) / 1e9
            pos = s1
        for h in range(head, tail):
            cens_right[ty] += q_q[h] * px[j - 1]
        i = j
    return (e_open[:ne], e_close[:ne], e_peak[:ne], e_vol[:ne], e_mk[:ne], e_n[:ne], e_a[:ne], e_liq[:ne], e_brk[:ne], e_side[:ne],
            hist, hq, cens_left, cens_right, closed_nt, little_inv, little_out, breaks)


(e_open, e_close, e_peak, e_vol, e_mk, e_n, e_a, e_liq, e_brk, e_side, hist, hq, cens_left, cens_right, closed_nt,
 little_inv, little_out, breaks) = run(aid, typ, t, px, d, sp, crossed, liq, T0, T1)
acct_typ = np.zeros(n_acct, np.int8); acct_typ[aid] = typ
e_typ = acct_typ[e_a]
print(f"chain breaks (start_position not equal to the previous fill's end): {breaks:,}")


def fmt(s):
    if s is None or not np.isfinite(s):
        return "n/a"
    for u, v in (("d", 86400), ("h", 3600), ("min", 60), ("s", 1)):
        if s >= v:
            return f"{s / v:.3g} {u}"
    return f"{s * 1000:.3g} ms"


def km(dur, done, w=None):
    """Kaplan-Meier survival of durations with right censoring (done=False), optionally weighted."""
    w = np.ones(len(dur)) if w is None else w
    o = np.lexsort((~done, dur)); dur, done, w = dur[o], done[o], w[o]
    at_risk = w.sum() - np.concatenate(([0.0], np.cumsum(w)[:-1]))
    ev = np.where(done, w, 0.0)
    s = np.cumprod(1 - np.where(at_risk > 0, ev / at_risk, 0.0))
    return dur, s


def surv(dur, s, x):
    k = np.searchsorted(dur, x, side="right")
    return 1.0 if k == 0 else float(s[k - 1])


def km_q(dur, s, q):
    k = np.searchsorted(-s, -(1 - q), side="left")   # first time survival <= 1 - q
    return float(dur[k]) if k < len(dur) else float("inf")


def rmst(dur, s, cap):
    x = np.concatenate(([0.0], dur)); y = np.concatenate(([1.0], s))
    x = np.minimum(x, cap); return float(np.sum(np.diff(np.append(x, cap)) * y))


def wq(v, w, q):
    o = np.argsort(v); v, w = v[o], w[o]; c = np.cumsum(w)
    return float(v[np.searchsorted(c, q * c[-1])])


QS = (0.10, 0.25, 0.50, 0.75, 0.90, 0.99)
CAP = 30 * 86400.0
inwin = e_open >= 0
ok = inwin & ~e_brk
done = e_close >= 0
dur = np.where(done, e_close - e_open, T1 - e_open) / NS
win_s = (T1 - T0) / NS


def episode_stats(m, weight=None):
    if m.sum() == 0:
        return None
    dd, dn = dur[m], done[m]
    w = None if weight is None else weight[m]
    kd, ks = km(dd, dn, w)
    closed = dd[dn]
    r = {"episodes": int(m.sum()), "accounts": int(len(np.unique(e_a[m]))), "still_open_share": float(1 - dn.mean()),
         "km": {f"p{int(q * 100)}": km_q(kd, ks, q) for q in QS},
         "km_mean_capped_30d_s": rmst(kd, ks, min(CAP, float(kd.max()))),
         "km_share_over_1d": surv(kd, ks, 86400.0), "km_share_over_7d": surv(kd, ks, 7 * 86400.0)}
    if weight is None and len(closed):
        r["closed_only"] = {"median_s": float(np.median(closed)), "mean_s": float(closed.mean())}
        # one vote per account: each account's median episode, then the median across accounts
        per = {}
        for a_, v in zip(e_a[m][dn], closed):
            per.setdefault(a_, []).append(v)
        r["median_of_account_medians_s"] = float(np.median([np.median(v) for v in per.values()]))
        cnt = np.bincount(e_a[m]); r["top_account_episode_share"] = float(cnt.max() / cnt.sum())
    return r


SIZE = [(0, 1e3, "< $1k"), (1e3, 1e4, "$1k-10k"), (1e4, 1e5, "$10k-100k"), (1e5, 1e6, "$100k-1M"), (1e6, np.inf, ">= $1M")]
out = {"window": f"{WIN.T0} to {WIN.T1} (UTC, end exclusive), {WIN.span()}", "fills": int(n), "accounts": int(n_acct),
       "account_types": {TYPES[k]: int((acct_typ == k).sum()) for k in range(3)}, "chain_breaks": int(breaks),
       "episodes_opened_before_window": int((~inwin).sum()), "episodes_with_chain_break": int((inwin & e_brk).sum()),
       "episodes": {}, "episodes_notional_weighted": {}, "lots": {}}
out["episodes"]["all"] = episode_stats(ok)
out["episodes_notional_weighted"]["all"] = episode_stats(ok, e_vol)
for k in range(3):
    out["episodes"][TYPES[k]] = episode_stats(ok & (e_typ == k))
    out["episodes_notional_weighted"][TYPES[k]] = episode_stats(ok & (e_typ == k), e_vol)
for sv, lab in ((1, "long"), (-1, "short")):
    out["episodes"][lab] = episode_stats(ok & (e_side == sv))
    out["episodes_notional_weighted"][lab] = episode_stats(ok & (e_side == sv), e_vol)
    for k in (0, 2):
        out["episodes"][f"{TYPES[k]}, {lab}"] = episode_stats(ok & (e_typ == k) & (e_side == sv))
for lo, hi, lab in SIZE:
    out["episodes"]["peak " + lab] = episode_stats(ok & (e_peak >= lo) & (e_peak < hi))
    out["episodes"]["taker, peak " + lab] = episode_stats(ok & (e_typ == 2) & (e_peak >= lo) & (e_peak < hi))
out["episodes_liquidation_closed_share"] = float(((e_liq & 2) > 0)[ok & done].mean())

edges = np.concatenate(([0.0], 10 ** (LO + np.arange(NB) / BPD)))   # bin b covers [edges[b], edges[b+1])


def lot_stats(h, qq, cl, cr, ct, li, lo_):
    tot = h.sum()
    if tot == 0:
        return None
    c = np.cumsum(h) / tot
    r = {"closed_notional_usd": float(ct), "measured_share": float(tot / ct) if ct else None,
         "opened_before_window_share_of_closed": float(cl / ct) if ct else None,
         "open_at_end_usd": float(cr)}
    r.update({f"p{int(q * 100)}_s": float(edges[min(np.searchsorted(c, q) + 1, NB)]) for q in QS})
    r["mean_s_qty_weighted"] = float(qq[1] / qq[0]) if qq[0] else None
    r["open_interest_mean_s"] = float(li / lo_) if lo_ else None
    r["avg_abs_position_contracts"] = float(li / win_s)
    return r


for k in range(3):
    out["lots"][TYPES[k]] = lot_stats(hist[k].sum(0), hq[k].sum(0), cens_left[k], cens_right[k], closed_nt[k], little_inv[k], little_out[k])
out["lots"]["all"] = lot_stats(hist.sum((0, 1)), hq.sum((0, 1)), cens_left.sum(), cens_right.sum(), closed_nt.sum(),
                               little_inv.sum(), little_out.sum())
# by side: censoring and open-interest terms are not split by side, so only the measured distribution is reported
for sd, lab in ((0, "long"), (1, "short")):
    for k, g in ((None, "all"), (0, TYPES[0]), (2, TYPES[2])):
        h_ = hist[:, sd].sum(0) if k is None else hist[k, sd]
        q_ = hq[:, sd].sum(0) if k is None else hq[k, sd]
        out["lots"][f"{g}, {lab}"] = lot_stats(h_, q_, 0.0, 0.0, h_.sum(), 0.0, 0.0)
json.dump(out, open(f"{O}/holding.json", "w"), indent=1)

# ---- printout
print(f"\n{out['window']}; {n:,} fills; accounts {out['account_types']}")
print(f"episodes with unknown open time, opened before the window or after a chain break (excluded): {out['episodes_opened_before_window']:,}; "
      f"with a chain break (excluded): {out['episodes_with_chain_break']:,}")
print("\nEPISODES (flat to flat or flip), Kaplan-Meier, count-weighted")
print(f"{'group':28s} {'episodes':>9s} {'accts':>6s} {'open@end':>8s} {'p10':>9s} {'p25':>9s} {'median':>9s} {'p75':>9s} "
      f"{'p90':>9s} {'mean<=30d':>9s} {'acct-med':>9s} {'top1':>5s} {'>1d':>6s} {'>7d':>6s}")
for g, r in out["episodes"].items():
    if r:
        k_ = r["km"]
        print(f"{g:28s} {r['episodes']:9,d} {r['accounts']:6,d} {r['still_open_share']:8.1%} {fmt(k_['p10']):>9s} "
              f"{fmt(k_['p25']):>9s} {fmt(k_['p50']):>9s} {fmt(k_['p75']):>9s} {fmt(k_['p90']):>9s} "
              f"{fmt(r['km_mean_capped_30d_s']):>9s} {fmt(r.get('median_of_account_medians_s')):>9s} "
              f"{r.get('top_account_episode_share', 0):5.0%} {r['km_share_over_1d']:6.1%} {r['km_share_over_7d']:6.1%}")
print("\nEPISODES weighted by notional traded inside the episode")
for g, r in out["episodes_notional_weighted"].items():
    if r:
        k_ = r["km"]
        print(f"{g:28s} p25 {fmt(k_['p25']):>9s}  median {fmt(k_['p50']):>9s}  p75 {fmt(k_['p75']):>9s}  "
              f"p90 {fmt(k_['p90']):>9s}  mean<=30d {fmt(r['km_mean_capped_30d_s']):>9s}")
print(f"closed by liquidation: {out['episodes_liquidation_closed_share']:.2%} of closed episodes")
print("\nLOTS (FIFO), notional-weighted hold of each closed contract")
for g, r in out["lots"].items():
    if r:
        print(f"{g:22s} closed ${r['closed_notional_usd'] / 1e9:.2f}B  p10 {fmt(r['p10_s'])}  p25 {fmt(r['p25_s'])}  "
              f"median {fmt(r['p50_s'])}  p75 {fmt(r['p75_s'])}  p90 {fmt(r['p90_s'])}  p99 {fmt(r['p99_s'])}  "
              f"mean {fmt(r['mean_s_qty_weighted'])}  OI-view {fmt(r['open_interest_mean_s'])}  "
              f"pre-window {r['opened_before_window_share_of_closed']:.1%}")
print(f"\nwrote {O}/holding.json")
