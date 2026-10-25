"""Check the holiday rows of the market clock (scripts/window.py) against the book itself.

On a CME holiday with an early halt the futures close at the listed Chicago time; the atlas shows that
depth within 10 bps of mid falls when futures close. For every holiday in the window this prints depth in
the hour before the listed halt, the hour after it, and the same hours on the other days with the same
weekday (regular days), and finds the minute of the largest one-hour drop in the holiday's afternoon.
A listed halt is confirmed when the holiday's drop lands within 15 minutes of it and the holiday's
after-halt depth is below half of its before-halt depth while regular days show no such drop.
Input: data/derived/offhours/offhours_depth_minutes.parquet (run the off-hours step first).
Writes data/checks/clock/holidays.json."""
import datetime as dt, json, os, sys
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN

m = pd.read_parquet("data/derived/offhours/offhours_depth_minutes.parquet", columns=["t", "d10"]).sort_values("t")
m["t"] = pd.to_datetime(m.t).dt.tz_localize("UTC") if pd.to_datetime(m.t).dt.tz is None else m.t
m = m.set_index("t").d10
CHI = ZoneInfo("America/Chicago")
out, ok = {}, True
for d in WIN.HOLIDAYS:
    day = dt.date.fromisoformat(d); hh = WIN.ES_HOLIDAYS[d]
    halt = pd.Timestamp(dt.datetime.combine(day, dt.time(int(hh[:2]), int(hh[3:])), CHI)).tz_convert("UTC")
    reopen = None if day.weekday() == 4 else pd.Timestamp(dt.datetime.combine(day, dt.time(17), CHI)).tz_convert("UTC")
    H = pd.Timedelta(hours=1)
    before, after = m[halt - H:halt - pd.Timedelta(minutes=1)].median(), m[halt:halt + H - pd.Timedelta(minutes=1)].median()
    # the same clock minutes on regular days with the same weekday
    reg = [x for x in WIN.ISO if dt.date.fromisoformat(x).weekday() == day.weekday() and x not in WIN.HOLIDAYS]
    rb, ra = [], []
    for x in reg:
        hx = halt + pd.Timedelta(days=(dt.date.fromisoformat(x) - day).days)
        rb.append(m[hx - H:hx - pd.Timedelta(minutes=1)].median()); ra.append(m[hx:hx + H - pd.Timedelta(minutes=1)].median())
    # largest drop: one-hour median before vs after each minute, scanned over the holiday's 14:00-22:00 UTC
    w = m[pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=14):pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=22)]
    pre = m.rolling(60).median(); post = m[::-1].rolling(60).median()[::-1]
    ratio = (post / pre).reindex(w.index)
    t_drop = ratio.idxmin()
    rec = None
    if reopen is not None:
        rb2, ra2 = m[reopen - H:reopen - pd.Timedelta(minutes=1)].median(), m[reopen:reopen + H - pd.Timedelta(minutes=1)].median()
        rec = dict(reopen_utc=str(reopen), before_musd=rb2 / 1e6, after_musd=ra2 / 1e6)
    good = abs((t_drop - halt).total_seconds()) <= 15 * 60 and after < 0.5 * before and np.nanmedian(ra) > 0.7 * np.nanmedian(rb)
    ok &= bool(good)
    out[d] = dict(listed_halt_chicago=hh, halt_utc=str(halt), before_musd=before / 1e6, after_musd=after / 1e6,
                  regular_days=len(reg), regular_before_musd=float(np.nanmedian(rb)) / 1e6, regular_after_musd=float(np.nanmedian(ra)) / 1e6,
                  largest_drop_utc=str(t_drop), drop_minutes_from_listed=(t_drop - halt).total_seconds() / 60,
                  reopen=rec, confirmed=bool(good))
    tail = "" if rec is None else f"; reopen {reopen:%H:%M} UTC: ${rec['before_musd']:.1f}M -> ${rec['after_musd']:.1f}M"
    print(f"{d} halt {hh} Chicago = {halt:%H:%M} UTC: depth ${before / 1e6:.1f}M -> ${after / 1e6:.1f}M "
          f"(regular days {np.nanmedian(rb) / 1e6:.1f} -> {np.nanmedian(ra) / 1e6:.1f}); largest drop at {t_drop:%H:%M} UTC "
          f"({(t_drop - halt).total_seconds() / 60:+.0f} min){tail}  {'CONFIRMED' if good else 'NOT CONFIRMED'}")
os.makedirs("data/checks/clock", exist_ok=True)
json.dump(out, open("data/checks/clock/holidays.json", "w"), indent=1)
print("no holidays in the window" if not WIN.HOLIDAYS else ("ALL HOLIDAY HALTS CONFIRMED" if ok else "SOME HOLIDAY HALTS NOT CONFIRMED"))
sys.exit(0 if ok else 1)
