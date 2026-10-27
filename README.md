# hypermirage

**How much of Hyperliquid's displayed liquidity is real?**

hypermirage is an open research project that measures the reliability of displayed liquidity on
Hyperliquid perpetual markets. It starts with Trade[XYZ]'s S&P 500 perpetual (`xyz:SP500`), a
high-volume HIP-3 market, and follows every limit order through its full life: placed,
modified, filled, or cancelled.

**Read the report:** [justinalick.com/projects/hypermirage](https://justinalick.com/projects/hypermirage/), the illustrated atlas of every result below.

Data partner: **[Hydromancer](https://docs.hydromancer.xyz)**.

By [Justin Alick](https://justinalick.com) ([@justinalick](https://x.com/justinalick)).

Research only; not investment advice. Disclosure: the author holds a long position in the xyz:SP500 perp as of October 2026 and trades it actively; the position may change at any time without notice.

---

## Results: xyz:SP500, 2026-04-25 to 2026-10-24 UTC (183 days)

321.4M displayed orders from 24,103 accounts, replayed block by block (about 70 ms) from node order
statuses and checked against the exchange's one-minute book snapshots. The numbers below were
recomputed with separate code (`checks/`). `./run.sh charts` rebuilds the chart for each result in `out/`.
The first, two-week edition of this atlas covered 2026-10-08 to 2026-10-21; `HM_START=20261008
HM_END=20261021 ./run.sh all` still reproduces it (see Reproduce).

A **metaorder** is one account's run of consecutive taker orders on the same side, with no gap longer
than 5 minutes (liquidations excluded); each order in the run is a child order. Its impact is the mid
0.25 s after its last fill against the mid just before its first.

### Five headline findings

1. **Liquidity runs mostly on the CME clock, not the stock market's.** Median depth within 10 bps of mid is
   $13.7M in US cash hours, $11.4M overnight, $4.6M in the daily futures break (about two
   fifths) and $2.7M while futures are closed. A hidden Markov model finds little beyond that clock:
   session alone matches its two-state split in 93.8% of minutes.
2. **Almost nothing on display ever trades.** 0.23% of $18.9T in displayed notional filled (re-placed
   orders count again). 45% of 382M cancels are the same account replacing an order on the same side in
   the same block, often at a new price.
3. **Short queues fill far more often.** Orders that improve the touch or join behind at most $5k get a
   fill about 16% of the time; orders joining behind more than $250k get one 2.7% of the time.
4. **Small takers are early but still lose after fees.** Takers cross about 0.67 bps from the mid, and
   the mid then moves about that far their way, so they end near zero before fees. Orders under $10k are
   ahead in 72% of hours at 10 s and +0.18 bps at 1 minute, but at 0.89 bps in fees they end about
   0.7 bps underwater.
5. **Metaorders move price far more than the book suggests, and most of it stays.** Impact grows with
   size to the power of about 0.35, and metaorders move the price 2 to 7x more than one sweep of the
   typical displayed book would (a single order of the same size sweeping the top 20 levels at once, with no
   refill, averaged over one-minute snapshots), about 2 to 3.5x from $50k up. For metaorders of $1M or more
   whose account then stops trading for 5 minutes, 85% of the move is still there 5 minutes after the last fill.

### Also measured

- **Month by month.** Cash-hours depth grew from $7.5M in May to $18.1M in July (2.4x) and was $15.6M in
  October; the share of at-touch orders cancelled within 1 s rose from 44% to 70% in June, then 66% in October.
- **Order survival.** Near the touch a quote is usually gone within a second: 60% of orders at or inside
  the touch and 57% of orders up to 1 bp behind it, against 37% of orders more than 5 bps away.
- **Maker concentration and rotation.** The top three maker accounts supply 25.9% of maker volume pooled
  and 36% on the median day; merging declared sub-accounts gives 34.9%. The same few groups lead most
  weeks (top-20 rank correlation 0.93 week to week), and one has ranked first for the last 17 weeks.
- **Volatility widens the spread, not the book, while futures trade.** The most volatile tenth of
  minutes has a median quoted spread 17% wider than the calmest tenth (90% CI +15% to +19%), with depth
  flat (-0.6%). With futures closed, volatile minutes are both wider (+89%) and thinner (-13%).
- **Takers who lead the price keep leading.** Correlating the ten largest taker clusters' 60 s markouts
  month to month, one month predicts the next (r = 0.71 over six month pairs); the largest taker sits near +0.4 bps every month.
- **Funding and the oracle premium.** The perp trades about 3 bps below the oracle only while CME
  futures are open (median -3.2 bps, against -0.05 bps while they are closed). Funding is small next to
  that: over the six months a constant long paid 0.25%; from 2026-03-18 to 2026-10-25 it collected 0.66%,
  about 1.1% a year.

### Null and negative results

- **Depth does not thin in volatile minutes while futures trade.** Across hours depth and volatility
  rise together (correlation of logs +0.43), but relative to each hour's typical depth and its own session that
  day, volatile minutes carry about the same depth
  (-1.8% in cash hours, +0.3% overnight).
- **Order flow describes the move but does not forecast it.** OFI explains about 62% of same-bin price
  moves at 1 minute, but out-of-sample next-bin R-squared is 1.4% at 1 s, 0.5% at 10 s and about zero
  from 1 minute on, far below the half-spread plus fees.
- **Execution shape does not clearly lower cost within an account.** Spread-out metaorders look cheaper across
  traders (-0.29 bps against back-loaded, matched), but comparing an account with itself the gap shrinks
  to -0.13 bps (CI includes zero) and spread out costs 0.20 bps more than front-loaded.
- **Deep discounts to the oracle do not reliably predict a bounce.** The non-overlapping daily test
  gives a correlation of -0.10 over 209 days (t = -1.47).
- **Book regimes reduce to the clock.** A third HMM state only separates calm from active minutes at
  similar depth and is unstable across window halves (ARI 0.86 and 0.42).
- **Trader archetypes are not clearly real.** 16 of 32 clusters are close to stable across refits, but
  the same pipeline on shuffled data (each feature permuted, no real account) finds 11 clusters and 9 of
  them pass the same stability test, so stability alone does not show trader types.

All results describe measured behavior, not intent. An account is an address, not a firm.

## Why this matters

An order book shows depth. Traders, risk engines and market deployers treat that depth as
liquidity they can rely on. But displayed size is only real if it stays there when someone tries
to trade against it.

Three features of HIP-3 markets make this worth measuring carefully:

- **Concentration.** A handful of market makers can supply most of the resting liquidity in a
  builder-deployed market. If they pull quotes at the same time, depth disappears at once.
- **Always-on trading of closed underlyings.** Equity and index perps trade around the clock while
  the reference market is closed for nights and weekends.
- **Full transparency.** Hyperliquid publishes order-level activity, so these questions can be
  answered with data rather than anecdote.

## Principles

- Findings describe measured patterns in aggregate (fill and cancel rates, order lifetimes, distance
  from the touch). They describe behavior, not intent.
- Results are aggregated first. Every result states the date range it covers.

## Data

| Layer | What it contains | What it can show | What it cannot show |
|---|---|---|---|
| [Reservoir](https://docs.hydromancer.xyz/reservoir) (public, requester pays) | Fills with account and order id, 1s candles, top-20 L2 book every minute | Who trades, maker/taker roles, volume, concentration, markouts | Anything about orders that were never filled |
| Node data (Hydromancer) | Order status events, per-order book diffs, L4 book snapshots | Full order lifecycle: placement, cancel, fill, rejects, original size | Intent |

No raw or derived data is redistributed in this repository. Reservoir is a requester-pays S3 bucket:
anyone can reproduce the Reservoir results with their own AWS account. Node data comes from
Hydromancer; see their docs for access. Funding and the oracle premium come from the Hyperliquid public API.

## Data access

**Hydromancer Reservoir** (fills, 1s candles, top-20 L2 every minute). Public S3 bucket
`s3://hydromancer-reservoir` in `ap-northeast-1`, **requester pays**: you need your own AWS account,
and transfer is billed to it (about 350 MB per day of xyz fills). See
[docs.hydromancer.xyz/reservoir](https://docs.hydromancer.xyz/reservoir).

1. Create an AWS account and an IAM user or role allowed `s3:GetObject` and `s3:ListBucket` on the
   `hydromancer-reservoir` bucket and its objects.
2. Configure the AWS CLI (`aws configure`, or set `AWS_PROFILE`).
3. Check access: `aws s3 ls --request-payer requester s3://hydromancer-reservoir/by_dex/xyz/fills/perp/all/ | tail`
4. `./run.sh fetch` downloads the window's fills and SP500 1m L2 with `scripts/fetch.sh` (at most 14 days per
   call, skips files already present, logs bytes to `data/download_log.csv`).

**Node data** (order status events: placement, cancel, fill, reject, original size). Needed for every chart
except funding and maker concentration. For access, see
[Hydromancer](https://docs.hydromancer.xyz). Node output is large (tens of GB per day for all markets), so
extraction runs on a short-lived EC2 instance in the data's region and only the single-market extract is
copied back:

```bash
# AWS CloudShell
bash scripts/tokyo/launch.sh <your-ip> <your-ssh-public-key>
# on the instance (bootstrap asks for your read-only node-data credentials and config)
git clone https://github.com/justinalick/hypermirage && bash hypermirage/scripts/tokyo/bootstrap.sh
cd hypermirage
for r in "20260425 20260525" "20260526 20260625" "20260626 20260726" "20260727 20260826" "20260827 20260926" "20260927 20261024"; do
  scripts/node_extract_day.sh order_statuses $r   # the six-month window, at most 31 days per call
done
# locally: copy the extracts back into data/l4/ (scripts/tokyo/remote.sh pull), then terminate
bash scripts/tokyo/teardown.sh
```

Node-data settings are read from an env file that is never committed (see the header of
`scripts/node_extract_day.sh`). The extract lands in `data/l4/order_statuses/xyz_SP500/<YYYYMMDD>/<H>.parquet`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # versions the atlas was built with
# DuckDB CLI 2.x on PATH as `duckdb` (or set DUCKDB=/path/to/duckdb); `flock` from util-linux
```

16 GB of RAM is enough; heavy steps run one at a time under a lock file.

## Reproduce

```bash
git checkout <commit>                        # optional: the exact code the published page links (shown on the page)
export HM_START=20260425 HM_END=20261024     # the six-month page; leave unset for the two-week first edition
./run.sh fetch        # Reservoir fills + 1m L2 for the window
./run.sh pipeline     # per day: order lifecycles (scripts/lifecycle.py), book replay (scripts/touch.py),
                      # top of book with sizes and same-block amend pairs; days already built are skipped
./run.sh analysis     # all topics, or e.g. ./run.sh analysis survival markouts
./run.sh charts       # PNGs in data/derived/runs/<start>_<end>/out/
./run.sh headline     # headline numbers next to the values printed in the atlas
./run.sh checks       # independent recomputes (different code paths) of the published numbers
```

**Window.** Every step runs on the UTC days from `HM_START` to `HM_END` (YYYYMMDD, inclusive). The published
page is 2026-04-25 to 2026-10-24. The default is 2026-10-08 to 2026-10-21, the window of the two-week atlas, where the scripts assert that the published
numbers come out again. Any other window, for example `HM_START=20260425 HM_END=20261024 ./run.sh all`,
prints its own numbers next to the atlas values instead. Per-day files (lifecycles, replayed book, top of
book, amend pairs) are shared by all windows; everything else is written to a per-window folder,
`data/derived/runs/<start>_<end>/`, which links the window's days and the code, so windows never overwrite
each other and a file glob sees the window's days only.

**Market clock.** Sessions come from `scripts/window.py`, computed in exchange local time, so daylight
saving time is handled: CME equity index futures trade Sunday 17:00 to Friday 16:00 Chicago time with a
daily halt 16:00 to 17:00, the NYSE cash session is 09:30 to 16:00 New York time, and US exchange holidays
are listed with their early CME halt (a Monday holiday reopens at 17:00 Chicago the same day, a Friday
holiday stays closed into the weekend). Futures-closed hours therefore include holiday afternoons, and
hour-of-week charts leave holiday dates out. `./run.sh checks clock` tests each listed halt against the
replayed book (depth within 10 bps falls at the halt). A window with an NYSE holiday that has no CME
schedule in the table is refused. Charts drawn on a UTC hour grid assume one UTC offset across the window
and refuse a window that crosses a daylight saving change.

| Atlas section | Topic | Main scripts | Chart |
|---|---|---|---|
| Order survival | `survival` | `charts/survival_cache.py`, `analysis/survival_viz.py` | `charts/survival.py` |
| Depth vs volatility | `depth_vol` | `analysis/offhours/offhours_depth.py`, `analysis/depth_vol/prep2.py` | `charts/depth_vol.py` |
| Spread vs volatility | `vol_spread` | `analysis/vol_spread/` | `charts/vol_spread.py` |
| Maker concentration | `concentration` | `analysis/concentration/`, `charts/concentration_cache.py` | `charts/concentration.py` |
| Depth by hour and weekday | `heatmap` | `analysis/heatmap/depth_check.py` | `charts/heatmap.py`, `charts/depth_week.py` |
| Fill markouts | `markouts` | `analysis/markout/rerun/` | `charts/markouts.py`, `charts/markouts_violin.py` |
| Funding and the oracle premium | `funding` | `analysis/funding/` | `charts/funding.py` |
| Price impact | `impact` | `analysis/impact/` | `charts/impact.py` |
| Order flow imbalance | `ofi` | `analysis/ofi/` | `charts/ofi.py` |
| Taker markouts by cluster | `taker_clusters` | `analysis/taker_clusters/` | `charts/taker_markouts.py` |
| Metaorder shapes | `metaorders` | `analysis/metaorder_shapes/` | `charts/metaorder.py` |
| Trader archetypes | `archetypes` | `analysis/archetypes/` | `charts/archetypes_v2.py` |
| Book regimes | `regimes` | `analysis/regimes/` | `charts/regimes.py` |
| Queue position and fills | `queue` | `analysis/queue_replay.py`, `analysis/queue_fill.sql`, `analysis/queue_km.py` | `charts/queue_fill.py` |
| Cancels and amends | `cancels` | `analysis/cancels/` | `charts/cancels_1.py` to `charts/cancels_3.py` |
| Impact after completion | `impact_decay` | `analysis/impact_decay/decay.py` | `charts/impact_decay.py` |
| Execution shape and cost | `shape_cost` | `analysis/shape_cost/shape_cost.py` | `charts/shape_cost.py` |
| Month by month | `monthly` | `analysis/monthly/daily.py`, `analysis/monthly/monthly.py` | `charts/monthly.py`, `charts/quotes_monthly.py` |
| Maker rotation | `maker_rotation` | `analysis/maker_rotation/rotation.py` | `charts/maker_rotation.py` |
| Taker markouts by hour of week | `taker_hours` | `analysis/taker_hours/hours.py` | `charts/taker_hours.py` |
| Chain pauses (data quality) | `halts` | `analysis/halts/halts.py` | none |

The last five topics read outputs of earlier ones (impact, metaorders, concentration, taker clusters, survival,
heatmap, spread vs volatility), so run them after those; `./run.sh analysis` keeps that order. `./run.sh checks
studies` recomputes each of them by a separate code path (`checks/studies/`).

`charts/og_card.py` draws the report's link-preview image (1200 x 630) with the window, the order count and
the impact ratio from the run's outputs. The first-version figure scripts kept in `analysis/` (for example
`analysis/impact/plot.py`) describe the atlas window in their text and refuse other windows; `charts/` has
the current version of each.

`report/` holds the published page (`report/index.html`, `report/og-xyz-sp500-v7.png`). `node scripts/build.mjs` builds it into
`dist/` with its security headers for justinalick.com/projects/hypermirage; the build fails if the page would load anything
from another site.

Notes:
- `data/derived/markout/bbo_t.parquet` (replayed best bid and ask with block times) is shared by markouts,
  impact, metaorders, taker clusters and archetypes; the first topic that needs it builds it.
- Spread vs volatility: the +19% headline is the change in the median of the hour- and day-normalized,
  time-weighted spread (top vs bottom volatility decile). The cross-check against exchange L2 snapshots in
  `checks/vol_spread/` compares means, because the snapshot spread is one tick most of the time and its
  median barely moves.
- Maker concentration and taker clusters merge only sub-accounts that are declared on Hyperliquid, read from
  the public info API (`userRole`, `subAccounts`). The API returns current links, so a later run can differ
  slightly from the atlas. Requests go through `analysis/hl_api.py`: about one per second per IP, retried on
  rate limits, and cached in `data/derived/hl_api/` for every window; a request that keeps failing stops
  the run instead of being recorded as an account with no role.
- `analysis/funding/fetch_api.py` pulls from the public API up to the time it runs and merges each pull into
  the saved files, because the 1h candle endpoint only serves the most recent ~5,000 hours. The funding
  analysis uses every print from the first one to the end of the window; the atlas window keeps the end of
  its own pull, made on 2026-10-23.
- The plotting kit in `charts/justinalick/` bundles IBM Plex and Silkscreen, both under the SIL Open Font
  License.

## How the pipeline works

Hyperliquid's node output is large: tens of gigabytes of compressed order-status events per day,
across all markets. `xyz:SP500` is a small share of that.

```
S3 (Tokyo, requester pays)
   │  stream one hour at a time, never stored
   ▼
zstd -dc  ──►  scripts/node_extract.py  ──►  parquet, one coin only
   ▼
scripts/lifecycle.py, scripts/touch.py  ──►  analysis/ (DuckDB / Python)  ──►  charts/
```

Extraction runs on a short-lived EC2 instance in the same AWS region as the data, where transfer
from S3 is free. Only the single-market extract leaves the region.

## Repository layout

```
run.sh       entry point for every step above
scripts/     Reservoir download, node-data extraction (EC2), order lifecycles, book replay
analysis/    derived tables and statistics, one folder per atlas section
charts/      atlas charts (matplotlib) and the plotting kit
checks/      independent recomputes of the published numbers
tools/       scan.sh: checks the tree and history for addresses and credentials
```

## Acknowledgments

Thanks to [Hydromancer](https://docs.hydromancer.xyz) for providing the data and infrastructure
that make order-level research on Hyperliquid possible.

## License

Code is released under the MIT License (see `LICENSE`). Data remains subject to Hydromancer's
terms. Research only; not investment advice. Disclosure: the author holds a long position in the xyz:SP500 perp as of October 2026 and trades it actively; the position may change at any time without notice.
