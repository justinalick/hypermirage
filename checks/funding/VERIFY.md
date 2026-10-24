# Verify: funding (xyz:SP500 premium and funding, Mar 18 to Oct 23 2026)

Recompute in plain Python (json, statistics, zoneinfo; no pandas, no qcut) from the two cached API files
`data/derived/funding/sp500_funding_api.json` and `candles.json`. Nothing refetched, originals untouched.
Session rule re-implemented independently: each print at hour T covers the hour starting T-1h, classified by
New York wall clock; ES closed = Fri 17:00 to Sun 18:00 ET plus the Mon-Thu 17:00 ET halt hour.

| Number | Original | Recomputed | Match | Method |
|---|---|---|---|---|
| Funding hours | 5,255 | 5,255 (no gaps, no duplicate hours) | yes | hourly floor of API `time` |
| ES-open median premium | -3.2 bps (chart) | -3.160 bps (n 3,610) | yes (rounds to -3.2) | median over hours not ES-closed |
| ES-closed median premium | -0.05 bps | -0.054 bps | yes | median over ES-closed hours |
| ES-closed hours | 1,645 | 1,645 | yes | count |
| Overall median premium | -2.5 bps | -2.499 bps | yes | median of all hours |
| Hours with premium < 0 | 78% | 77.9% | yes | share |
| Cumulative long funding | 0.67% received | -0.672% paid by long (= 0.67% received) | yes | sum of fundingRate x 100 |
| Per year | about 1.1% | 1.12%/yr | yes | cum / (5,255 / 8,760) |
| Funding rule | exact | max error 5e-11 | yes | (p + clamp(1e-4 - p, +-3e-4))/16 |
| Deepest-fifth next-24h return | +27 bps | +26.93 bps (n 996, cutoff -4.28 bps, median -5.3) | yes | lowest 20% of premium (numpy-style quantile edge), log return open T to open T+24h |
| Hours with 24h forward return | 4,978 | 4,978 | yes | candles deduped (5,003 raw -> 5,002), both ends present |
| Daily test corr | -0.10 | -0.1018 | yes | Pearson on 20:00 UTC prints |
| Daily test t | -1.46 | -1.465 | yes | r sqrt(n-2)/sqrt(1-r^2) |
| Daily test n | 207 | 207 | yes | |

## -3.1 vs -3.2

Not a rounding or mean/median slip on the same set; it is a different set of hours.
- -3.2 (chart, current caption) = median over all ES-open hours (cash + other ES hours, 3,610 h) = -3.160.
- -3.1 (earlier text) = median over US cash hours only (09:30-16:00 ET weekdays, 942 h) = -3.121. The v3 note
  states it as "cash -3.1 (942 h) and other ES hours -3.2 (2,668 h)"; the older caption text reused the cash figure.
- Other variants for reference: mean over ES-open hours -3.02; counting the 17:00 ET halt as open -3.12;
  classifying by the print hour without the 1h shift -3.10. The other-ES-hours median alone is -3.17.
- So "-3.2 while ES trades" is correct for the stated definition; "-3.1" is correct only if labelled "US cash hours".

## Minor wording notes (not number errors)
- The page note says "4,978 hourly bars after removing a duplicate". After dedup there are 5,002 hourly candles;
  4,978 is the number of hours with a 24h forward return (the chart's panel E caption says this correctly).
- "+27 bps ... comes from March and April": Mar+Apr contribute about 79% of the deepest-fifth sum; August
  (n 81, +83 bps) contributes most of the rest. "Mostly" is accurate.
- The daily test is mildly sensitive to which UTC hour is sampled (corr -0.21 to +0.04 across the 24 hours);
  20:00 UTC gives -0.10. None is a strong signal.

## Rerun
`.venv/bin/python -P checks/funding/recompute.py` (writes recompute.json)
