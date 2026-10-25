"""Independent recompute of the funding chart/caption numbers with plain Python (no pandas).
Inputs only: sp500_funding_api.json, candles.json (no refetch)."""
import json, math, statistics as st, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, "scripts")
import window as WIN          # window end and the list of holiday dates only; the session logic below is separate
D = "data/derived/funding"
NY, CHI = ZoneInfo("America/New_York"), ZoneInfo("America/Chicago")
raw = json.load(open(f"{D}/sp500_funding_api.json"))
H = 3600_000
END = int(datetime.strptime(WIN.API_END, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp() * 1000)
rows = {}
for r in raw:
    hr = r["time"] // H * H                      # print at hour T (floored)
    if hr > END:
        continue
    assert hr not in rows
    rows[hr] = (float(r["fundingRate"]), float(r["premium"]))
hrs = sorted(rows)
assert (hrs[-1] - hrs[0]) // H + 1 == len(hrs)
def session(hr):
    # print at T covers hour starting T-1h; classify by its New York wall clock (ES rules in Chicago time)
    t = datetime.fromtimestamp((hr - H) / 1000, timezone.utc)
    ny, ch = t.astimezone(NY), t.astimezone(CHI)
    d, h, m = ny.weekday(), ny.hour, ny.minute
    closed = (d == 4 and h >= 17) or d == 5 or (d == 6 and h < 18) or (d < 4 and h == 17)
    hol = WIN.ES_HOLIDAYS.get(ch.strftime("%Y-%m-%d"))
    if hol and ch.hour * 60 + ch.minute >= int(hol[:2]) * 60 + int(hol[3:]) and (ch.weekday() == 4 or ch.hour < 17):
        closed = True                             # early halt; Monday holidays reopen at 17:00 Chicago time
    cash = d < 5 and 570 <= h * 60 + m < 960 and ny.strftime("%Y-%m-%d") not in WIN.NYSE_HOLIDAYS
    return "closed" if closed else ("cash" if cash else "other_open")
prem = {h: rows[h][1] * 1e4 for h in hrs}
ses = {h: session(h) for h in hrs}
out = {"n_hours": len(hrs), "first": str(datetime.fromtimestamp(hrs[0]/1000, timezone.utc)), "last": str(datetime.fromtimestamp(hrs[-1]/1000, timezone.utc))}
op = [prem[h] for h in hrs if ses[h] != "closed"]; cl = [prem[h] for h in hrs if ses[h] == "closed"]
out["es_open_median"] = st.median(op); out["es_open_mean"] = st.fmean(op); out["es_open_n"] = len(op)
out["cash_median"] = st.median([prem[h] for h in hrs if ses[h] == "cash"])
out["other_open_median"] = st.median([prem[h] for h in hrs if ses[h] == "other_open"])
out["es_closed_median"] = st.median(cl); out["es_closed_n"] = len(cl); out["es_closed_mean"] = st.fmean(cl)
# alternative: open = not closed AND not daily 17:00 halt only weekends excluded (halt counted as open)
def closed_wkend(hr):
    ny = datetime.fromtimestamp((hr - H) / 1000, timezone.utc).astimezone(NY); d, h = ny.weekday(), ny.hour
    return (d == 4 and h >= 17) or d == 5 or (d == 6 and h < 18)
op2 = [prem[h] for h in hrs if not closed_wkend(h)]
out["alt_open_incl_halt_median"] = st.median(op2); out["alt_open_incl_halt_n"] = len(op2)
# alt: no 1h shift (classify print hour itself)
def ses_noshift(hr):
    return session(hr + H)
op3 = [prem[h] for h in hrs if ses_noshift(h) != "closed"]; out["alt_noshift_open_median"] = st.median(op3)
# alt: open median in the hour-of-week profile (median of medians)
out["overall_median"] = st.median(prem.values())
out["share_neg"] = sum(1 for h in hrs if rows[h][1] < 0) / len(hrs)
cum = sum(rows[h][0] for h in hrs) * 100
out["cum_long_funding_pct"] = cum; out["per_year_pct"] = cum / (len(hrs) / (24 * 365))
out["funding_rule_maxerr"] = max(abs((rows[h][1] + min(max(1e-4 - rows[h][1], -3e-4), 3e-4)) / 16 - rows[h][0]) for h in hrs)
# candles: dedupe keep last
cr = json.load(open(f"{D}/candles.json")); cd = {}
for c in cr:
    if c["t"] <= END: cd[c["t"]] = float(c["o"])
out["candles_raw"] = len(cr); out["candles_dedup"] = len(cd)
# forward 24h return from open of hour T to open of hour T+24
fw = []
for h in hrs:
    if h in cd and h + 24 * H in cd:
        fw.append((h, prem[h], (math.log(cd[h + 24 * H]) - math.log(cd[h])) * 1e4))
out["n_returns"] = len(fw)
# quintiles by rank (pd.qcut equivalent: quantile edges, include lowest)
ps = sorted(p for _, p, _ in fw); n = len(ps)
def q(p):  # linear-interpolated quantile like numpy default
    x = p * (n - 1); i = int(math.floor(x)); return ps[i] + (ps[min(i + 1, n - 1)] - ps[i]) * (x - i)
e1 = q(0.2)
q0 = [r for _, p, r in fw if p <= e1]
out["q0_n"] = len(q0); out["q0_mean_r24"] = st.fmean(q0); out["q0_edge_bps"] = e1
out["q0_median_prem"] = st.median([p for _, p, _ in fw if p <= e1])
# months of q0 contribution
from collections import defaultdict
bym = defaultdict(list)
for h, p, r in fw:
    if p <= e1: bym[datetime.fromtimestamp(h/1000, timezone.utc).strftime("%m")].append(r)
out["q0_by_month"] = {m: [len(v), round(st.fmean(v), 1)] for m, v in sorted(bym.items())}
# daily non-overlapping: 20:00 UTC prints
dd = [(p, r) for h, p, r in fw if datetime.fromtimestamp(h/1000, timezone.utc).hour == 20]
xs, ys = [a for a, _ in dd], [b for _, b in dd]
mx, my = st.fmean(xs), st.fmean(ys)
sxy = sum((a - mx) * (b - my) for a, b in dd); sxx = sum((a - mx) ** 2 for a in xs); syy = sum((b - my) ** 2 for b in ys)
r = sxy / math.sqrt(sxx * syy)
out["daily_n"] = len(dd); out["daily_corr"] = r; out["daily_t"] = r * math.sqrt(len(dd) - 2) / math.sqrt(1 - r * r)
# sensitivity: other UTC hours for the daily test
sens = {}
for hh in range(24):
    dd2 = [(p, r_) for h, p, r_ in fw if datetime.fromtimestamp(h/1000, timezone.utc).hour == hh]
    a = [x for x, _ in dd2]; b = [y for _, y in dd2]
    sens[hh] = round(st.correlation(a, b), 3)
out["daily_corr_by_utc_hour"] = sens
json.dump(out, open("data/checks/funding/recompute.json", "w"), indent=1)
print(json.dumps(out, indent=1))
