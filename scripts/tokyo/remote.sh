#!/usr/bin/env bash
# Drive an already-running Tokyo extraction instance from a local machine.
# Launching and terminating instances stays manual (AWS CloudShell: launch.sh / teardown.sh).
#
# usage: scripts/tokyo/remote.sh status
#        scripts/tokyo/remote.sh run <dataset> <YYYYMMDD> [YYYYMMDD_end]   (starts in tmux on the instance)
#        scripts/tokyo/remote.sh pull                                      (rsync extracts here)
#
# Config (never committed): private/tokyo.env with
#   TOKYO_HOST=<instance public IP>         changes every launch; update after launch.sh
#   TOKYO_KEY=~/.ssh/hypermirage_tokyo
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
[[ -f "$ROOT/private/tokyo.env" ]] && source "$ROOT/private/tokyo.env"
: "${TOKYO_HOST:?set TOKYO_HOST in private/tokyo.env (public IP printed by launch.sh)}"
TOKYO_KEY=${TOKYO_KEY:-$HOME/.ssh/hypermirage_tokyo}
SSH=(ssh -i "${TOKYO_KEY/#\~/$HOME}" -o ConnectTimeout=10 -o BatchMode=yes "ubuntu@$TOKYO_HOST")

cmd=${1:-status}; shift || true
case $cmd in
  status)
    "${SSH[@]}" 'set -e
      echo "instance $(uptime -p) (self-terminates MAX_HOURS after launch, default 6h)"
      cd ~/hypermirage/data/l4 2>/dev/null || { echo "no extracts yet"; exit 0; }
      for ds in */; do [[ $ds == logs/ ]] && continue
        for c in "$ds"*/; do [[ -d $c ]] || continue
          for d in "$c"*/; do echo "${d%/}: $(ls "$d"*.parquet 2>/dev/null | wc -l)/24"; done; done; done
      # [.] keeps pgrep from counting this remote shell, whose command line contains the pattern
      echo "running extract jobs: $(pgrep -fc "node_extract[.]py" || true)"
      echo "recent failures: $(grep -l . logs/*.log 2>/dev/null | xargs -r grep -L "\"rows_out\"" | wc -l)"'
    ;;
  run)
    ds=${1:?dataset}; start=${2:?YYYYMMDD}; end=${3:-$2}
    "${SSH[@]}" "cd ~/hypermirage && git pull -q && \
      tmux new-session -d -s extract-$start 'scripts/node_extract_day.sh $ds $start $end 2>&1 | tee -a ~/extract.log' && \
      echo started $ds $start..$end in tmux session extract-$start"
    ;;
  pull)
    # The instance's manifest only covers its own runs, so it is merged into the local one
    # (one entry per dataset/coin/hour, the instance's entry winning) instead of copied over it.
    # Exit 24 (source files vanished) is expected while an extraction is still writing; anything else fails.
    rc=0
    rsync -a --info=stats1 --exclude=/manifest.jsonl -e "ssh -i ${TOKYO_KEY/#\~/$HOME} -o ConnectTimeout=10" \
      "ubuntu@$TOKYO_HOST:hypermirage/data/l4/" "$ROOT/data/l4/" || rc=$?
    if [[ $rc -eq 24 ]]; then echo "note: some files changed during transfer (extraction still running); pull again when done"
    elif [[ $rc -ne 0 ]]; then exit "$rc"; fi
    local_m="$ROOT/data/l4/manifest.jsonl"; remote_m=$(mktemp)
    "${SSH[@]}" 'cat ~/hypermirage/data/l4/manifest.jsonl 2>/dev/null || true' > "$remote_m"
    touch "$local_m"
    awk '{ k = ""
           if (match($0, /"label": *"[^"]*"/))   k = k substr($0, RSTART, RLENGTH)
           if (match($0, /"dataset": *"[^"]*"/)) k = k substr($0, RSTART, RLENGTH)
           if (match($0, /"coin": *"[^"]*"/))    k = k substr($0, RSTART, RLENGTH)
           if (k == "") k = $0
           if (!(k in line)) order[++n] = k
           line[k] = $0 }
         END { for (i = 1; i <= n; i++) print line[order[i]] }' \
      "$local_m" "$remote_m" > "$local_m.tmp" && mv "$local_m.tmp" "$local_m"
    echo "manifest: $(wc -l < "$remote_m") instance entries merged; $(wc -l < "$local_m") total"
    rm -f "$remote_m"
    ;;
  *) echo "usage: $0 status | run <dataset> <YYYYMMDD> [end] | pull" >&2; exit 1 ;;
esac
