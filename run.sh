#!/usr/bin/env bash
# Rebuild the xyz:SP500 plot atlas from Reservoir fills and node order statuses, for any window of UTC days.
#
#   ./run.sh fetch                 Reservoir fills and 1m L2 for the window (requester pays, about 0.35 GB a day)
#   ./run.sh pipeline              per-day order lifecycles, book replay, top of book and amend pairs
#                                  (needs data/l4/order_statuses; days already built are skipped)
#   ./run.sh analysis [topic ...]  derived tables; topics below, default all
#   ./run.sh charts                atlas charts -> <view>/out/
#   ./run.sh checks [name ...]     independent recomputes; default all
#   ./run.sh headline              print headline numbers next to the atlas values
#   ./run.sh all                   pipeline, analysis, charts, headline (fetch and node data not included)
#
# Window: HM_START and HM_END (UTC days, YYYYMMDD, inclusive); default 20261008 to 20261021, the
# published atlas. Example: HM_START=20260425 HM_END=20261024 ./run.sh all
# Per-day outputs (lifecycles, replayed book, top of book, amend pairs) are shared by every window.
# Everything else runs inside a per-window view, data/derived/runs/<start>_<end>/: the code directories and
# the window's per-day files are links there and every output is written there, so windows never
# overwrite each other and a file glob sees the window's days only. The market clock (CME futures
# and NYSE sessions, daylight saving time, holidays) is in scripts/window.py.
#
# Topics: survival concentration markouts funding cancels heatmap depth_vol vol_spread impact metaorders ofi
#         taker_clusters archetypes regimes queue
# Run from anywhere; everything is relative to the repository root. Heavy steps run one at a time
# under a lock file so two shells do not compete for memory.
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$PWD
PY=${PY:-$ROOT/.venv/bin/python}
DUCKDB=${DUCKDB:-duckdb}
export HM_START=${HM_START:-20261008} HM_END=${HM_END:-20261021}
mapfile -t DAYS < <("$PY" scripts/window.py days)
VIEW=$ROOT/$("$PY" scripts/window.py view)
iso() { echo "${1:0:4}-${1:4:2}-${1:6:2}"; }
mkdir -p data/tmp
LOCK=${LOCK:-$ROOT/data/tmp/heavy.lock}
heavy() { echo "+ $*" >&2; flock "$LOCK" "$@"; }
sql() { heavy "$DUCKDB" -c ".read $1"; }

need() { for f in "$@"; do [[ -e $f ]] || { echo "missing input: $f (run the step that builds it first)" >&2; exit 1; }; done; }
# An output is fresh when it exists and its input has not changed since it was built. The input's fingerprint
# (a day folder: file names and sizes; a file: size and time) is kept next to the output in <output>.in, so inputs
# copied in later with older timestamps (rsync -a keeps the sender's times) still trigger a rebuild.
# Outputs from before fingerprints existed fall back to the timestamp test once and get a fingerprint.
fp() { if [[ -d $1 ]]; then find "$1" -maxdepth 1 -type f ! -name '*.tmp' -printf '%f %s\n' | sort | md5sum | cut -c1-32
       else stat -c '%s %Y' "$1"; fi; }
fresh() { [[ -s $1 ]] || return 1
          if [[ -f $1.in ]]; then [[ $(<"$1.in") == "$(fp "$2")" ]]; else [[ $1 -nt $2 ]] && fp "$2" > "$1.in"; fi; }
stamp() { fp "$2" > "$1.in"; }   # after a build: record the input it was built from

fetch() {
  local a=$(iso "${DAYS[0]}") b e
  while [[ ! $a > $(iso "${DAYS[-1]}") ]]; do   # scripts/fetch.sh takes at most 14 days per call
    e=$(date -u -d "$a + 13 days" +%F); b=$(iso "${DAYS[-1]}"); [[ $e > $b ]] && e=$b
    scripts/fetch.sh xyz fills "$a" "$e"
    scripts/fetch.sh xyz book:SP500 "$a" "$e"
    a=$(date -u -d "$e + 1 day" +%F)
  done
}

pipeline() {
  local d i S=data/derived
  for d in "${DAYS[@]}"; do
    i=$(iso "$d")
    need "data/l4/order_statuses/xyz_SP500/$d" "data/raw/xyz/fills/$i.parquet" "data/raw/xyz/book_1m/SP500/$i.parquet"
    local L4=data/l4/order_statuses/xyz_SP500/$d LC=$S/lifecycle/xyz_SP500/$d.parquet LT=$S/lifecycle_touch/xyz_SP500/$d.parquet
    fresh "$LC" "$L4" || { heavy "$PY" scripts/lifecycle.py --day "$d" --fills "data/raw/xyz/fills/$i.parquet" && stamp "$LC" "$L4"; }
    fresh "$LT" "$LC" ||
      { heavy "$PY" scripts/touch.py --day "$d" --check-book "data/raw/xyz/book_1m/SP500/$i.parquet" && stamp "$LT" "$LC"; }
    fresh "$S/ofi/l1/$d.parquet" "$LC" || { heavy "$PY" analysis/ofi/l1.py "$d" && stamp "$S/ofi/l1/$d.parquet" "$LC"; }
    fresh "$S/cancels/amends_$d.parquet" "$L4" || { heavy "$PY" analysis/cancels/amends.py "$d" && stamp "$S/cancels/amends_$d.parquet" "$L4"; }
  done
}

# The view: links to code and to the window's per-day inputs; real directories for every output.
view() {
  local d i v=$VIEW S=data/derived
  mkdir -p "$v/data/l4/order_statuses/xyz_SP500" "$v/data/raw/xyz/fills" "$v/data/raw/xyz/book_1m/SP500" \
           "$v/$S/lifecycle/xyz_SP500" "$v/$S/lifecycle_touch/xyz_SP500" "$v/$S/bbo/xyz_SP500" "$v/$S/ofi/l1" \
           "$v/$S/funding" "$v/out" "$v/data/tmp"
  for x in analysis charts checks scripts report; do ln -sfn "$ROOT/$x" "$v/$x"; done
  mkdir -p "$ROOT/$S/hl_api"; ln -sfn "$ROOT/$S/hl_api" "$v/$S/hl_api"   # info API cache, shared by windows
  for d in "${DAYS[@]}"; do
    i=$(iso "$d")
    need "$ROOT/$S/lifecycle_touch/xyz_SP500/$d.parquet" "$ROOT/$S/ofi/l1/$d.parquet" "$ROOT/$S/cancels/amends_$d.parquet"
    ln -sfn "$ROOT/data/l4/order_statuses/xyz_SP500/$d" "$v/data/l4/order_statuses/xyz_SP500/$d"
    ln -sf "$ROOT/data/raw/xyz/fills/$i.parquet" "$v/data/raw/xyz/fills/$i.parquet"
    ln -sf "$ROOT/data/raw/xyz/book_1m/SP500/$i.parquet" "$v/data/raw/xyz/book_1m/SP500/$i.parquet"
    for t in lifecycle lifecycle_touch bbo; do ln -sf "$ROOT/$S/$t/xyz_SP500/$d.parquet" "$v/$S/$t/xyz_SP500/$d.parquet"; done
    ln -sf "$ROOT/$S/ofi/l1/$d.parquet" "$v/$S/ofi/l1/$d.parquet"
    mkdir -p "$v/$S/cancels"; ln -sf "$ROOT/$S/cancels/amends_$d.parquet" "$v/$S/cancels/amends_$d.parquet"
  done
  # the public-API pull (funding, 1h candles) covers far more than any window; funding_premium.py selects the window
  for f in sp500_funding_api.json candles.json; do [[ -e $ROOT/$S/funding/$f ]] && ln -sf "$ROOT/$S/funding/$f" "$v/$S/funding/$f"; done
  for d in chart_cache concentration cancels offhours heatmap depth_vol impact metaorder_shapes ofi taker_clusters \
           archetypes regimes queue funding markout/rerun vol_spread; do mkdir -p "$v/$S/$d"; done
  mkdir -p "$v/data/checks/clock" "$v/data/checks/spotcheck" "$v/data/checks/funding" "$v/data/checks/queue/work" "$v/data/checks/cancels/work"
}
inview() { cd "$ROOT"; { flock 9; view; } 9>"$ROOT/data/tmp/view.lock"; cd "$VIEW"; }   # one view build at a time

bbo_t() { [[ -s data/derived/markout/bbo_t.parquet ]] || { mkdir -p data/derived/markout/rerun; heavy "$PY" analysis/markout/rerun/prep_bbo_t.py; }; }
offhours() { [[ -s data/derived/offhours/offhours_depth_minutes.parquet ]] || heavy "$PY" analysis/offhours/offhours_depth.py; }
impact_tables() { [[ -s data/derived/impact/orders.parquet ]] || topic_impact; }

topic_survival() { heavy "$PY" charts/survival_cache.py; }
topic_concentration() {
  heavy "$PY" analysis/concentration/universe.py
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
  heavy "$PY" analysis/cancels/amends_sum.py
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
  heavy "$PY" analysis/impact/bookwalk.py
  heavy "$PY" analysis/impact/robust.py
}
topic_metaorders() {
  impact_tables
  heavy "$PY" analysis/metaorder_shapes/build.py
  heavy "$PY" analysis/metaorder_shapes/cluster.py
  heavy "$PY" analysis/metaorder_shapes/impact.py
}
topic_ofi() { heavy "$PY" analysis/ofi/ofi.py; heavy "$PY" analysis/ofi/gap.py; }
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
  offhours
  heavy "$PY" analysis/regimes/features.py
  heavy "$PY" analysis/regimes/run.py
  for k in 2 3; do heavy "$PY" analysis/regimes/analyze.py "$k"; done
}
topic_queue() {
  heavy "$PY" analysis/queue_replay.py "${DAYS[@]}"
  rm -f data/derived/queue/queue.duckdb
  heavy "$DUCKDB" data/derived/queue/queue.duckdb < analysis/queue_fill.sql
  "$PY" analysis/queue_km.py
}

TOPICS=(survival concentration markouts funding cancels heatmap depth_vol vol_spread impact metaorders ofi taker_clusters archetypes regimes queue)
analysis() { inview; for t in "${@:-${TOPICS[@]}}"; do echo "== analysis: $t" >&2; "topic_$t"; done; }

CHARTS=(metaorder_explainer survival concentration markouts markouts_violin funding cancels_1 cancels_2 cancels_3 heatmap depth_week
        depth_vol vol_spread impact
        metaorder ofi taker_markouts archetypes_v2 regimes queue_fill)
charts() { inview; for c in "${CHARTS[@]}"; do echo "== chart: $c" >&2; "$PY" "charts/$c.py"; done; }

CHECKS=(clock spotcheck funding queue cancels vol_spread)
check_clock() { offhours; "$PY" checks/clock/holidays.py; }   # holiday halts in scripts/window.py vs the replayed book
check_spotcheck() {
  for f in checks/spotcheck/*.py; do
    case $f in *regimes_verify_verify_hmm.py) heavy "$PY" "$f" data/derived/regimes/fits.pkl ;; *) heavy "$PY" "$f" ;; esac
  done
}
check_vol_spread() { heavy "$PY" checks/vol_spread/check_vol_spread.py; }
check_funding() { "$PY" checks/funding/recompute.py; }
check_queue() {
  heavy "$PY" checks/queue/extract.py
  local i n=${#DAYS[@]} k
  if [[ $HM_START == 20261008 && $HM_END == 20261021 ]]; then   # the atlas check: two warm-up + check stretches
    heavy "$PY" checks/queue/fifo_replay.py 20261008 -- 20261009 20261010
    heavy "$PY" checks/queue/fifo_replay.py 20261011 20261012 -- 20261013 20261014
  else   # six stretches spread over the window: one warm-up day, then two check days
    for k in 0 1 2 3 4 5; do
      i=$(( k * (n - 3) / 5 ))
      heavy "$PY" checks/queue/fifo_replay.py "${DAYS[i]}" -- "${DAYS[i + 1]}" "${DAYS[i + 2]}"
    done
  fi
  heavy "$PY" checks/queue/touch_compare.py
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
checks() { inview; for c in "${@:-${CHECKS[@]}}"; do echo "== check: $c" >&2; "check_$c"; done; }

headline() { inview; "$PY" analysis/headline.py; }

cmd=${1:-}; shift || true
case $cmd in
  fetch|pipeline|charts|headline) "$cmd" ;;
  analysis|checks) "$cmd" "$@" ;;
  all) pipeline; analysis; charts; headline ;;
  *) sed -n '2,24p' "$0"; exit 1 ;;
esac
