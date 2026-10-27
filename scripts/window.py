#!/usr/bin/env python3
"""Study window and market clock, shared by run.sh and every analysis, chart and check.

Window: environment variables HM_START and HM_END, UTC days as YYYYMMDD, both inclusive. The
default, 20261008 to 20261021, is the window of the published atlas. run.sh exports both and runs
every step inside a per-window view (data/derived/runs/<start>_<end>/, see run.sh), where the per-day inputs
are links to the shared per-day files, so a file glob sees the window's days and nothing else.

Clock. Everything is computed in exchange local time, so daylight saving time is handled:
  CME Globex equity index futures (ES): open Sunday 17:00 to Friday 16:00 Chicago time, with a daily
  halt 16:00 to 17:00 Monday to Thursday. On the exchange holidays in ES_HOLIDAYS trading halts early
  and reopens at 17:00 Chicago time the same day (Monday holidays) or on Sunday (Friday holidays).
  NYSE cash session: 09:30 to 16:00 New York time on NYSE trading days.
Session labels used throughout:
  cash       NYSE cash session (futures open)
  overnight  futures open, cash session closed
  break      the daily 16:00 to 17:00 Chicago time futures halt, Monday to Thursday
  closed     futures closed: weekends and holiday closures

Usage from the shell: window.py days | iso | start | end | label | view
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

ATLAS = ("20261008", "20261021")
START = os.environ.get("HM_START") or ATLAS[0]
END = os.environ.get("HM_END") or ATLAS[1]

CT, ET = "America/Chicago", "America/New_York"
# ES early halts (Chicago time) on US exchange holidays: date -> halt time. A Monday holiday reopens
# at 17:00 the same day; a Friday holiday stays closed until the Sunday 17:00 open.
ES_HOLIDAYS = {
    "2026-04-03": "08:15",  # Good Friday: shortened session around the 8:30 ET payrolls release; used by the
                            # funding chart only (its public-API series starts before the window).
    "2026-05-25": "12:00",  # Memorial Day
    "2026-06-19": "12:00",  # Juneteenth
    "2026-07-03": "12:00",  # Independence Day (observed)
    "2026-09-07": "12:00",  # Labor Day
}
# NYSE full-day closures. A window that contains one missing from ES_HOLIDAYS is refused, so an
# unchecked holiday cannot pass silently as a normal day.
NYSE_HOLIDAYS = {
    "2025-11-27", "2025-12-25", "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}
NYSE_EARLY_CLOSE = {"2025-11-28": "13:00", "2025-12-24": "13:00", "2026-11-27": "13:00", "2026-12-24": "13:00"}

_d0, _d1 = dt.datetime.strptime(START, "%Y%m%d").date(), dt.datetime.strptime(END, "%Y%m%d").date()
if _d1 < _d0:
    raise SystemExit(f"window: HM_END {END} is before HM_START {START}")
DATES = [_d0 + dt.timedelta(days=i) for i in range((_d1 - _d0).days + 1)]
DAYS = [d.strftime("%Y%m%d") for d in DATES]
ISO = [d.isoformat() for d in DATES]
N_DAYS = len(DAYS)
T0, T1 = ISO[0], (_d1 + dt.timedelta(days=1)).isoformat()   # SQL bounds: t >= T0 AND t < T1
IS_ATLAS = (START, END) == ATLAS
VIEW = f"data/derived/runs/{START}_{END}"
# Public-API series (funding prints, 1h candles) run from their first print to the window's end (a print
# at hour T settles the hour ending at T, so the print at T1 00:00 is the last one). The atlas used the
# pull of 2026-10-23, which ended with the 12:00 UTC print.
API_END = "2026-10-23 12:00" if IS_ATLAS else f"{T1} 00:00"

_missing = sorted(d for d in NYSE_HOLIDAYS if ISO[0] <= d <= ISO[-1] and d not in ES_HOLIDAYS)
if _missing:
    raise SystemExit(f"window: no ES holiday schedule for {', '.join(_missing)}; add it to ES_HOLIDAYS")
# NYSE half days also shorten the futures session; their ES halts are not in ES_HOLIDAYS yet
_early = sorted(d for d in NYSE_EARLY_CLOSE if ISO[0] <= d <= ISO[-1] and d not in ES_HOLIDAYS)
if _early:
    raise SystemExit(f"window: no ES early-halt schedule for the NYSE half days {', '.join(_early)}; add them to ES_HOLIDAYS")
if N_DAYS > 365:
    raise SystemExit("window: longer than a year; block() keys days by month and day")
HOLIDAYS = sorted(d for d in ES_HOLIDAYS if ISO[0] <= d <= ISO[-1])


def label(skip: int = 0) -> str:
    """'Oct 8 to 21, 2026' or 'Apr 25 to Oct 24, 2026'; skip leaves out the first days (a warm-up)."""
    a, b = DATES[skip], DATES[-1]
    if a.year != b.year:
        return f"{a:%b} {a.day}, {a.year} to {b:%b} {b.day}, {b.year}"
    if a.month == b.month:
        return f"{a:%b} {a.day} to {b.day}, {b.year}"
    return f"{a:%b} {a.day} to {b:%b} {b.day}, {b.year}"


def span() -> str:
    """'14 days' or 'six months (183 days)'."""
    return f"{N_DAYS} days" if N_DAYS < 60 else f"{round(N_DAYS / 30.4)} months ({N_DAYS} days)"


def split_day() -> str:
    """First day of the second half of the window (YYYYMMDD), for two-half stability checks."""
    return DAYS[N_DAYS // 2]


def _utc(ts) -> pd.DatetimeIndex:
    ts = pd.DatetimeIndex(pd.to_datetime(ts))
    return ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")


def _ymd(idx) -> np.ndarray:
    """Local calendar date of each timestamp as an integer YYYYMMDD (fast; no string formatting)."""
    return np.asarray(idx.year * 10000 + idx.month * 100 + idx.day)


def _ymd1(d: str) -> int:
    return int(d.replace("-", ""))


def es_state(ts) -> np.ndarray:
    """Per timestamp: 'open', 'break' (daily halt) or 'closed' (weekend, holiday), CME ES."""
    c = _utc(ts).tz_convert(CT)
    dow = np.asarray(c.dayofweek); mins = np.asarray(c.hour * 60 + c.minute)
    date = _ymd(c)
    closed = ((dow == 4) & (mins >= 16 * 60)) | (dow == 5) | ((dow == 6) & (mins < 17 * 60))
    brk = (dow <= 3) & (mins >= 16 * 60) & (mins < 17 * 60)
    for d, hhmm in ES_HOLIDAYS.items():
        h = int(hhmm[:2]) * 60 + int(hhmm[3:])
        on = date == _ymd1(d)
        wd = dt.date.fromisoformat(d).weekday()
        if wd == 4:     # Friday: closed from the halt into the weekend
            closed |= on & (mins >= h)
        else:           # closed from the halt to the 17:00 reopen (which replaces that day's break)
            closed |= on & (mins >= h) & (mins < 17 * 60)
            brk &= ~(on & (mins >= h) & (mins < 17 * 60))
    return np.where(closed, "closed", np.where(brk, "break", "open"))


def cash(ts) -> np.ndarray:
    """True inside the NYSE cash session."""
    n = _utc(ts).tz_convert(ET)
    dow = np.asarray(n.dayofweek); mins = np.asarray(n.hour * 60 + n.minute)
    date = _ymd(n)
    end = np.full(len(n), 16 * 60)
    for d, hhmm in NYSE_EARLY_CLOSE.items():
        end[date == _ymd1(d)] = int(hhmm[:2]) * 60 + int(hhmm[3:])
    return (dow <= 4) & (mins >= 9 * 60 + 30) & (mins < end) & ~np.isin(date, [_ymd1(d) for d in NYSE_HOLIDAYS])


def session(ts) -> np.ndarray:
    """'cash', 'overnight', 'break' or 'closed' per timestamp (see module docstring)."""
    es = es_state(ts)
    return np.where(es == "closed", "closed", np.where(es == "break", "break",
                    np.where(cash(ts), "cash", "overnight")))


def block(ts) -> np.ndarray:
    """Day key for day-level bootstraps and normalizations: the UTC date while futures trade,
    and one key per closure (a weekend, a holiday afternoon), named after the UTC date it starts."""
    u = _utc(ts)
    closed = es_state(u) == "closed"
    s = pd.Series(closed)
    start = s & ~s.shift(1, fill_value=False)
    run = start.cumsum()
    md = pd.Series(np.char.zfill((_ymd(u) % 10000).astype(str), 4))
    first = md.groupby(run.values).transform("first")
    return np.where(closed, "C" + first.values, md.values)


def closed_weeks_grid() -> np.ndarray:
    """7 x 24 UTC hour-of-week mask (Mon..Sun) of futures closed or halted in a regular week, from
    the clock itself. Refuses a window whose Chicago UTC offset changes (DST), where no single UTC
    grid exists."""
    offs = {pd.Timestamp(d, tz=CT).utcoffset() for d in ISO}
    if len(offs) > 1:
        raise SystemExit("window spans a daylight saving change; draw hour-of-week charts in local time")
    wk = pd.date_range("2026-01-05", periods=7 * 24, freq="h", tz="UTC") + pd.Timedelta(minutes=30)
    wk = wk + pd.Timedelta(days=7 * ((pd.Timestamp(ISO[0], tz="UTC") - wk[0]).days // 7))
    st = es_state(wk)
    return (st != "open").reshape(7, 24)


def utc_offset_hours() -> float:
    """New York UTC offset in the window (e.g. -4 for EDT); refuses a window that crosses DST."""
    offs = {pd.Timestamp(d, tz=ET).utcoffset() for d in ISO}
    if len(offs) > 1:
        raise SystemExit("window spans a daylight saving change")
    return offs.pop().total_seconds() / 3600


def atlas_only(replacement: str):
    """For first-version figure scripts whose text describes the atlas window: refuse other windows."""
    if not IS_ATLAS:
        raise SystemExit(f"{sys.argv[0]}: this figure's text and checks describe the Oct 8 to 21, 2026 atlas; "
                         f"for window {START}-{END} use {replacement}")


def expect(name: str, got, want, tol=0.0):
    """Regression guard: in the atlas window, assert that a published value is reproduced; in any
    other window, print the new value next to the atlas one."""
    g = np.atleast_1d(np.asarray(got, float)); w = np.atleast_1d(np.asarray(want, float))
    if IS_ATLAS:
        assert g.shape == w.shape and np.all(np.abs(g - w) <= tol + 1e-12), f"{name}: got {got}, atlas {want}"
    else:
        print(f"[window {START}-{END}] {name}: {got} (atlas window: {want})", file=sys.stderr)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "label"
    out = {"days": "\n".join(DAYS), "iso": "\n".join(ISO), "start": START, "end": END,
           "label": label(), "view": VIEW}.get(cmd)
    if out is None:
        raise SystemExit(__doc__)
    print(out)
