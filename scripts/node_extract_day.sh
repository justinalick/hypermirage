#!/usr/bin/env bash
# Extract one coin from Hyperliquid node output for a UTC day or a range of days.
# Every (day, hour) file goes into one parallel pool, so more cores = proportionally faster.
#
# usage: scripts/node_extract_day.sh <dataset> <YYYYMMDD> [YYYYMMDD_end]
#   dataset: order_statuses | book_diffs | fills | twap | misc
#   env COIN (default xyz:SP500), JOBS (default: number of cores)
#
# Each hour streams S3 -> zstd -> node_extract.py -> parquet. Nothing raw touches disk.
# Output: data/l4/<dataset>/<coin>/<YYYYMMDD>/<H>.parquet, plus a manifest line per hour.
#
# Config (never committed): private/node.env or ~/.hm-node.env must define
#   HM_NODE_BUCKET   bucket name, no s3:// prefix
#   HM_NODE_PREFIX   key prefix of the raw node datasets
#   HM_NODE_SOURCES  space-separated <dataset>=<source dir>, e.g. "order_statuses=<dir> fills=<dir>"
#
# Cost guard: the source is requester-pays and ~90 GB/day. This script refuses to run unless it
# is on an EC2 instance in ap-northeast-1 (same-region transfer is free). Override with
# ALLOW_EGRESS=1 only for a deliberate one-off, and expect ~$0.11/GB.
set -euo pipefail

DATASET=${1:?dataset}; START=${2:?YYYYMMDD}; END=${3:-$2}; COIN=${COIN:-xyz:SP500}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REGION=ap-northeast-1
JOBS=${JOBS:-$(nproc)}
export AWS_PROFILE=${AWS_PROFILE:-hydromancer}
PY=${PY:-$ROOT/.venv/bin/python}

for f in "$ROOT/private/node.env" "$HOME/.hm-node.env"; do [[ -f $f ]] && source "$f"; done
: "${HM_NODE_BUCKET:?set HM_NODE_BUCKET in private/node.env or ~/.hm-node.env}"
: "${HM_NODE_PREFIX:?set HM_NODE_PREFIX in private/node.env or ~/.hm-node.env}"
: "${HM_NODE_SOURCES:?set HM_NODE_SOURCES in private/node.env or ~/.hm-node.env}"

SRC=""
for pair in $HM_NODE_SOURCES; do [[ ${pair%%=*} == "$DATASET" ]] && SRC=${pair#*=}; done
[[ -n $SRC ]] || { echo "unknown dataset: $DATASET (not in HM_NODE_SOURCES)" >&2; exit 1; }

if [[ "${ALLOW_EGRESS:-0}" != 1 ]]; then
  tok=$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token \
        -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' || true)
  here=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $tok" \
        http://169.254.169.254/latest/meta-data/placement/region || true)
  [[ "$here" =~ ^[a-z]+-[a-z]+-[0-9]+$ ]] || here=""
  if [[ "$here" != "$REGION" ]]; then
    echo "refusing: not on EC2 in $REGION (detected: '${here:-none}'). Downloading this to a" >&2
    echo "non-AWS machine costs ~\$0.11/GB on ~90 GB/day. Set ALLOW_EGRESS=1 to override." >&2
    exit 1
  fi
fi

command -v zstd >/dev/null || { echo "install zstd" >&2; exit 1; }
[[ -x $PY ]] || { echo "python not found at $PY (set PY=...)" >&2; exit 1; }

SLUG=${COIN//:/_}
BASE="$ROOT/data/l4/$DATASET/$SLUG"
MANIFEST="$ROOT/data/l4/manifest.jsonl"
mkdir -p "$BASE" "$ROOT/data/l4/logs"

one_hour() {
  set -o pipefail
  local DAY=$1 h=$2
  local out="$BASE/$DAY/$h.parquet" log="$ROOT/data/l4/logs/$DATASET-$SLUG-$DAY-$h.log"
  mkdir -p "$BASE/$DAY"
  [[ -s $out ]] && { echo "skip $DAY/$h (exists)"; return 0; }
  local key="s3://$HM_NODE_BUCKET/$HM_NODE_PREFIX/$SRC/hourly/$DAY/$h.zst"
  if aws s3 cp "$key" - --request-payer requester --region "$REGION" --only-show-errors \
       | zstd -dc \
       | "$PY" "$ROOT/scripts/node_extract.py" --coin "$COIN" --dataset "$DATASET" \
                 --out "$out" --label "$DAY/$h" 2> "$log"; then
    tail -n 1 "$log" >> "$MANIFEST"
    echo "ok   $DAY/$h $(tail -n 1 "$log" | cut -c1-160)"
  else
    rm -f "$out" "$out.tmp"   # never leave a partial/empty file that a rerun would skip
    echo "FAIL $DAY/$h (see $log)"
  fi
}
export -f one_hour
export BASE MANIFEST ROOT DATASET SLUG HM_NODE_BUCKET HM_NODE_PREFIX SRC REGION COIN PY

days=(); d=$START
while [[ "$d" -le "$END" ]]; do days+=("$d"); d=$(date -u -d "$d + 1 day" +%Y%m%d); done
(( ${#days[@]} <= 31 )) || { echo "refusing ${#days[@]} days in one call (max 31)" >&2; exit 1; }

echo "extract $DATASET $COIN ${days[0]}..${days[-1]} (${#days[@]} days) with $JOBS jobs -> $BASE"
start=$(date +%s)
for d in "${days[@]}"; do for h in $(seq 0 23); do echo "$d $h"; done; done \
  | xargs -P "$JOBS" -L 1 bash -c 'one_hour "$0" "$1"'
total=0
for d in "${days[@]}"; do
  n=$(find "$BASE/$d" -maxdepth 1 -name "*.parquet" 2>/dev/null | wc -l); total=$((total + n))
  echo "  $d: $n/24 hours"
done
echo "done in $(( $(date +%s) - start ))s; $total/$(( ${#days[@]} * 24 )) hour-files"
