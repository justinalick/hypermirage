# hypermirage

**How much of Hyperliquid's displayed liquidity is real?**

hypermirage is an open research project that measures the reliability of displayed liquidity on
Hyperliquid perpetual markets. It starts with Trade[XYZ]'s S&P 500 perpetual (`xyz:SP500`), a
high-volume HIP-3 market, and follows every limit order through its full life: placed,
modified, filled, or cancelled.

**Read the report:** [justinalick.com/projects/hypermirage](https://justinalick.com/projects/hypermirage/), the illustrated atlas of every result below.

Data partner: **[Hydromancer](https://docs.hydromancer.xyz)**.

By [Justin Alick](https://justinalick.com) ([@justinalick](https://x.com/justinalick)).

Research only; not investment advice.

---

## Results: xyz:SP500, 2026-10-08 to 2026-10-21 UTC

26.0M displayed orders from 2,914 accounts, replayed block by block (about 70 ms) from node order
statuses and checked against the exchange's one-minute book snapshots. Every number below was
recomputed with separate code. `./run.sh charts` rebuilds the chart for each result in `out/`.

### Five headline findings

1. **Liquidity runs on the CME clock, not the stock market's.** Median depth within 10 bps of mid is
   $15.4M in US cash hours, $13.2M in other futures hours, $4.7M in the daily futures break and $3.4M
   on weekends. A hidden Markov model finds nothing beyond that clock: session alone matches its
   two-state split in 99.5% of minutes.
2. **Almost nothing on display ever trades.** 0.28% of $1.08T in displayed notional filled. Half of 30M
   cancels are the same account replacing an order on the same side in the same block, mostly
   re-centering on a moved touch.
3. **Queue position decides who gets filled.** Orders that improve the touch fill 14.5% of the time;
   orders joining behind more than $250k fill 3.2% of the time.
4. **Small takers are early but still lose after fees.** Takers pay about 0.37 bps to cross, then the
   price follows them. Orders under $10k are ahead in 67% of hours at 10 s, but at 1.13 bps in fees
   they end about 1 bp underwater.
5. **Size moves price far more than the book suggests.** Impact grows with size to the power of about
   0.38, and metaorders move the price 2 to 6 times more than walking the displayed book would.

### Also measured

- **Order survival.** Near the touch a quote is usually gone within a second: 65% of orders at or
  inside the touch and 72% of orders up to 1 bp behind it, against 26% of orders more than 5 bps away.
- **Maker concentration.** The top three maker accounts supply 36.0% of maker volume over the 14 days
  (34% to 46% on single days), and which three changes from day to day. Merging sub-accounts declared
  on Hyperliquid barely changes it (36.1%).
- **Volatility widens the spread, not the book.** Within the same hour of day and the same day, during
  futures hours the most volatile tenth of minutes has a median quoted spread 19% wider than the
  calmest tenth (90% CI +15% to +24%), while depth within 10 bps is flat (-1.2%, 90% CI -4.9% to
  +2.4%). The +19% compares medians of the time-weighted spread; the cross-check against exchange
  snapshots uses means (+22%), since the snapshot spread is one tick most of the time.
- **Funding and the oracle premium.** The perp trades about 3 bps below the oracle only while CME
  futures are open (median -3.2 bps, against -0.05 bps while they are closed). Funding is small next to
  that: a constant long collected 0.67% from 2026-03-18 to 2026-10-23, about 1.1% a year.

### Null and negative results

- **Depth does not thin in volatile minutes.** Across hours depth and volatility rise together, but
  within the same day and hour volatile minutes carry about the same depth (-3.8% in cash hours, +4.8%
  overnight).
- **Order flow describes the move but does not forecast it.** OFI explains up to 57% of same-bin price
  moves at 1 minute, but out-of-sample next-bin R-squared is 1.3% at 1 s and zero or negative from 10 s
  on, far below the half-spread plus fees.
- **Deep discounts to the oracle do not reliably predict a bounce.** The non-overlapping daily test
  gives a correlation of -0.10 over 207 days (t = -1.46).
- **Book regimes reduce to the clock.** A third HMM state is only a volatility label and is unstable
  across week halves.
- **Execution shape barely separates metaorders.** Only a three-way split (front-loaded, spread out,
  back-loaded) is stable; the number of child orders matters more for impact than their timing.
- **Trader archetypes mostly dissolve.** Clusters of accounts largely disappear when tested against
  shuffled data; what remains is one block of fast post-only makers plus a continuum of takers.

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
cd hypermirage && scripts/node_extract_day.sh order_statuses 20261008 20261021
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
./run.sh fetch        # Reservoir fills + 1m L2, 2026-10-08..21
./run.sh pipeline     # per day: scripts/lifecycle.py (one row per order) and scripts/touch.py (book replay)
./run.sh analysis     # all topics, or e.g. ./run.sh analysis survival markouts
./run.sh charts       # PNGs in out/
./run.sh headline     # headline numbers next to the values printed in the atlas
./run.sh checks       # independent recomputes (different code paths) of the published numbers
```

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

`charts/og_card.py` draws the report's link-preview image (1200 x 630); it uses no data.

`report/` holds the published page (`report/index.html`, `report/og-xyz-sp500-v4.png`). `node scripts/build.mjs` builds it into
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
  slightly from the atlas.
- `analysis/funding/fetch_api.py` pulls from the public API up to the time it runs; the atlas used a pull
  made on 2026-10-23, so later pulls extend the sample.
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
terms. Research only; not investment advice.
