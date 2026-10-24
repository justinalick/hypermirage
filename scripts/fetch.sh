#!/usr/bin/env bash
# usage: scripts/fetch.sh <dex> <fills|candles|book:COIN> <start YYYY-MM-DD> [end YYYY-MM-DD]
set -euo pipefail
DEX=$1; KIND=$2; START=$3; END=${4:-$3}
MAX_DAYS=14
BUCKET=s3://hydromancer-reservoir
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
n=$(( ( $(date -d "$END" +%s) - $(date -d "$START" +%s) ) / 86400 + 1 ))
(( n >= 1 )) || { echo "end is before start"; exit 1; }
(( n <= MAX_DAYS )) || { echo "refusing $n days (max $MAX_DAYS per call)."; exit 1; }
d=$START
while [[ "$d" < "$END" || "$d" == "$END" ]]; do
  case $KIND in
    fills)   key="by_dex/$DEX/fills/perp/all/date=$d/fills.parquet";       out="$ROOT/data/raw/$DEX/fills/$d.parquet" ;;
    candles) key="by_dex/$DEX/candles/1s/date=$d/candles.parquet";         out="$ROOT/data/raw/$DEX/candles_1s/$d.parquet" ;;
    book:*)  coin=${KIND#book:}
             key="by_dex/$DEX/orderbook/1m/perps/date=$d/$coin.parquet";   out="$ROOT/data/raw/$DEX/book_1m/$coin/$d.parquet" ;;
    *) echo "unknown kind: $KIND"; exit 1 ;;
  esac
  if [[ -s "$out" ]]; then
    echo "skip (exists): $out"
  else
    mkdir -p "$(dirname "$out")"
    if aws s3 cp --only-show-errors --request-payer requester "$BUCKET/$key" "$out"; then
      bytes=$(stat -c %s "$out")
      echo "$(date -u +%FT%TZ),$DEX,$KIND,$d,$bytes" >> "$ROOT/data/download_log.csv"
      echo "got $out ($((bytes/1048576)) MB)"
    else
      echo "missing or failed: $key"
    fi
  fi
  d=$(date -I -d "$d + 1 day")
done
awk -F, '{s+=$5} END {printf "cumulative downloaded: %.2f GB (~$%.2f egress)\n", s/1e9, s/1e9*0.11}' "$ROOT/data/download_log.csv"
