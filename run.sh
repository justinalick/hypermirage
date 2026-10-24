#!/usr/bin/env bash
# Rebuild the xyz:SP500 plot atlas (2026-10-08 to 2026-10-21 UTC) from Reservoir fills and node order statuses.
#
#   ./run.sh fetch                 Reservoir fills and 1m L2 for the window (requester pays, about 5 GB)
#   ./run.sh pipeline              per-day order lifecycles and book replay (needs data/l4/order_statuses)
#   ./run.sh analysis [topic ...]  derived tables; topics below, default all
#   ./run.sh charts                atlas charts -> out/
#   ./run.sh checks [name ...]     independent recomputes; default all
#   ./run.sh headline              print headline numbers next to the atlas values
#   ./run.sh all                   pipeline, analysis, charts, headline (fetch and node data not included)
#
# Topics: survival concentration markouts funding cancels heatmap depth_vol vol_spread impact metaorders ofi
#         taker_clusters archetypes regimes queue
# Run from anywhere; everything is relative to the repository root. Heavy steps run one at a time
# under a lock file so two shells do not compete for memory.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}
DUCKDB=${DUCKDB:-duckdb}
DAYS=(20261008 20261009 20261010 20261011 20261012 20261013 20261014 20261015 20261016 20261017 20261018 20261019 20261020 20261021)
iso() { echo "${1:0:4}-${1:4:2}-${1:6:2}"; }
for d in chart_cache concentration cancels offhours heatmap depth_vol impact metaorder_shapes ofi taker_clusters \
         archetypes regimes queue funding markout/rerun vol_spread; do mkdir -p "data/derived/$d"; done
mkdir -p data/tmp data/checks/spotcheck data/checks/funding data/checks/queue/work data/checks/cancels/work out
LOCK=${LOCK:-data/tmp/heavy.lock}
heavy() { echo "+ $*" >&2; flock "$LOCK" "$@"; }
sql() { heavy "$DUCKDB" -c ".read $1"; }

need() { for f in "$@"; do [[ -e $f ]] || { echo "missing input: $f (run the step that builds it first)" >&2; exit 1; }; done; }

fetch() {
  scripts/fetch.sh xyz fills "$(iso "${DAYS[0]}")" "$(iso "${DAYS[-1]}")"
  scripts/fetch.sh xyz book:SP500 "$(iso "${DAYS[0]}")" "$(iso "${DAYS[-1]}")"
}

pipeline() {
  for d in "${DAYS[@]}"; do
    need "data/l4/order_statuses/xyz_SP500/$d" "data/raw/xyz/fills/$(iso "$d").parquet" "data/raw/xyz/book_1m/SP500/$(iso "$d").parquet"
    heavy "$PY" scripts/lifecycle.py --day "$d" --fills "data/raw/xyz/fills/$(iso "$d").parquet"
    heavy "$PY" scripts/touch.py --day "$d" --check-book "data/raw/xyz/book_1m/SP500/$(iso "$d").parquet"
  done
}

bbo_t() { [[ -s data/derived/markout/bbo_t.parquet ]] || { mkdir -p data/derived/markout/rerun; sql analysis/markout/rerun/prep_bbo_t.sql; }; }
offhours() { [[ -s data/derived/offhours/offhours_depth_minutes.parquet ]] || heavy "$PY" analysis/offhours/offhours_depth.py; }
ofi_l1() { [[ -d data/derived/ofi/l1 && $(ls data/derived/ofi/l1 | wc -l) -ge ${#DAYS[@]} ]] || heavy "$PY" analysis/ofi/l1.py "${DAYS[@]}"; }
impact_tables() { [[ -s data/derived/impact/orders.parquet ]] || topic_impact; }

topic_survival() { heavy "$PY" charts/survival_cache.py; }
topic_concentration() {
  sql analysis/concentration/universe.sql
  "$PY" analysis/concentration/roles.py          # public Hyperliquid info API, declared sub-accounts only
  heavy "$PY" charts/concentration_cache.py
}
topic_markouts() {
  bbo_t
  heavy "$PY" analysis/markout/rerun/markout2.py
  heavy "$PY" analysis/markout/rerun/dist.py
}
topic_funding() {
  # fetch_api.py pulls from the public API up to now; the atlas used the pull of 2026-10-23.
  [[ -s data/derived/funding/sp500_funding_api.json ]] || "$PY" analysis/funding/fetch_api.py
  "$PY" analysis/funding/funding_premium.py
}
topic_cancels() {
  heavy "$PY" analysis/cancels/amends.py "${DAYS[@]}"
  sql analysis/cancels/amends_sum.sql
  ofi_l1
  heavy "$PY" analysis/cancels/latency2.py "${DAYS[@]}"
  sql analysis/cancels/rates.sql
}
topic_heatmap() {
  heavy "$PY" analysis/heatmap/depth_check.py data/derived/heatmap
  "$PY" analysis/heatmap/heatmap_depth.py out/heatmap_v1.png
}
topic_depth_vol() { offhours; heavy "$PY" analysis/depth_vol/prep2.py; }
topic_vol_spread() {
  offhours
  heavy "$PY" analysis/vol_spread/spread_minutes.py
  heavy "$PY" analysis/vol_spread/vol_spread.py
}
topic_impact() {
  bbo_t
  heavy "$PY" analysis/impact/build.py
  heavy "$PY" analysis/impact/fit.py
  heavy "$PY" analysis/impact/robust.py
  heavy "$PY" analysis/impact/bookwalk.py
}
topic_metaorders() {
  impact_tables
  heavy "$PY" analysis/metaorder_shapes/build.py
  heavy "$PY" analysis/metaorder_shapes/cluster.py
  heavy "$PY" analysis/metaorder_shapes/impact.py
}
topic_ofi() { ofi_l1; heavy "$PY" analysis/ofi/ofi.py; heavy "$PY" analysis/ofi/gap.py; }
topic_taker_clusters() {
  bbo_t
  heavy "$DUCKDB" < analysis/taker_clusters/takers.sql
  "$PY" analysis/taker_clusters/roles.py         # public Hyperliquid info API, declared sub-accounts only
  "$PY" analysis/taker_clusters/clusters.py
  heavy "$PY" analysis/taker_clusters/mk.py
}
topic_archetypes() {
  bbo_t
  for s in features cluster cluster_umap clusterwise plot3d; do heavy "$PY" "analysis/archetypes/$s.py"; done
}
topic_regimes() {
  offhours; ofi_l1
  heavy "$PY" analysis/regimes/features.py
  heavy "$PY" analysis/regimes/run.py
  for k in 2 3; do heavy "$PY" analysis/regimes/analyze.py "$k"; done
}
topic_queue() {
  heavy "$PY" analysis/queue_replay.py "${DAYS[@]}"
  heavy "$DUCKDB" data/derived/queue/queue.duckdb < analysis/queue_fill.sql
  "$PY" analysis/queue_km.py
}

TOPICS=(survival concentration markouts funding cancels heatmap depth_vol vol_spread impact metaorders ofi taker_clusters archetypes regimes queue)
analysis() { for t in "${@:-${TOPICS[@]}}"; do echo "== analysis: $t" >&2; "topic_$t"; done; }

CHARTS=(survival concentration markouts markouts_violin funding cancels_1 cancels_2 cancels_3 heatmap depth_week depth_vol vol_spread impact
        metaorder ofi taker_markouts archetypes_v2 regimes queue_fill)
charts() { for c in "${CHARTS[@]}"; do echo "== chart: $c" >&2; "$PY" "charts/$c.py"; done; }

CHECKS=(spotcheck funding queue cancels vol_spread)
check_spotcheck() {
  for f in checks/spotcheck/*.py; do
    case $f in *regimes_verify_verify_hmm.py) heavy "$PY" "$f" data/derived/regimes/fits.pkl ;; *) heavy "$PY" "$f" ;; esac
  done
}
check_vol_spread() { heavy "$PY" checks/vol_spread/check_vol_spread.py; }
check_funding() { "$PY" checks/funding/recompute.py; }
check_queue() {
  heavy "$PY" checks/queue/extract.py
  heavy "$PY" checks/queue/fifo_replay.py 20261008 -- 20261009 20261010
  heavy "$PY" checks/queue/fifo_replay.py 20261011 20261012 -- 20261013 20261014
  heavy "$PY" checks/queue/recompute.py
}
check_cancels() {
  heavy "$PY" checks/cancels/orders.py "${DAYS[@]}"
  heavy "$PY" checks/cancels/amends_v.py "${DAYS[@]}"
  heavy "$PY" checks/cancels/latency_v.py "${DAYS[@]}"
  heavy "$PY" checks/cancels/latency_v.py --all "${DAYS[@]}"
  sql checks/cancels/rates_v.sql
  "$PY" checks/cancels/summarize.py
}
checks() { for c in "${@:-${CHECKS[@]}}"; do echo "== check: $c" >&2; "check_$c"; done; }

headline() { "$PY" analysis/headline.py; }

cmd=${1:-}; shift || true
case $cmd in
  fetch|pipeline|charts|headline) "$cmd" ;;
  analysis|checks) "$cmd" "$@" ;;
  all) pipeline; analysis; charts; headline ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
