#!/usr/bin/env bash
# Scan the working tree and the full git history (every blob and commit message) for addresses,
# credentials, IPs and session links. Extra extended-regex patterns, one per line, can be passed
# in a file kept outside the repository: tools/scan.sh [patterns-file]
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
GENERIC=(
  '0x[0-9a-fA-F]{8,}'                              # addresses and prefixes of them
  'AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}'              # AWS access key IDs
  'aws_secret_access_key[ =]+[A-Za-z0-9/+]{30,}'
  'arn[:]aws[:]'
  '(^|[^0-9.])[0-9]{12}([^0-9.]|$)'                # AWS account IDs
  '([0-9]{1,3}\.){3}[0-9]{1,3}'                    # IPv4
  'BEGIN [A-Z ]*PRIVATE KEY'
  'gh[pousr]_[A-Za-z0-9]{20,}|github[_]pat[_]|xox[bp][-]|sk-[A-Za-z0-9]{20,}'
  'claude[.]ai/code/session|Claude-Session[:]'
)
ALLOW='169\.254\.169\.254'
patterns=("${GENERIC[@]}")
if [[ -n ${1:-} ]]; then
  while IFS= read -r p; do [[ -n $p && $p != \#* ]] && patterns+=("$p"); done < "$1"
fi
re=$(IFS='|'; echo "${patterns[*]}")
{
  git ls-files -z | xargs -0 grep -IHnE -- "$re" 2>/dev/null | sed 's/^/tree: /' || true
  for b in $(git rev-list --all --objects | awk '{print $1}'); do
    [[ $(git cat-file -t "$b") == blob ]] || continue
    git cat-file -p "$b" | grep -IanE -- "$re" | sed "s/^/blob $b: /" || true
  done
  git log --all --format='%H %an <%ae> %s%n%b' | grep -nE -- "$re" | sed 's/^/message: /' || true
} | grep -vE "$ALLOW" > /tmp/scan_hits.$$ || true
if [[ -s /tmp/scan_hits.$$ ]]; then
  echo "SCAN FAILED:" >&2; cut -c1-200 /tmp/scan_hits.$$ >&2; rm -f /tmp/scan_hits.$$; exit 1
fi
rm -f /tmp/scan_hits.$$
echo "scan clean: $(git ls-files | wc -l) tracked files, $(git rev-list --all | wc -l) commits, ${#patterns[@]} patterns"
