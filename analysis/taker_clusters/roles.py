"""Declared roles (userRole, subAccounts) of every account with >= $1M taker notional in the window, from the
Hyperliquid info API via analysis/hl_api.py (throttled, cached across windows). Rerun clusters.py after."""
import csv, json, sys
from collections import Counter
sys.path.insert(0, "analysis")
from hl_api import roles_and_subs
D = "data/derived/taker_clusters"
rows = [r for r in csv.DictReader(open(f"{D}/takers.csv")) if float(r["tak"]) >= 1e6]
out = roles_and_subs([r["address"] for r in rows])
json.dump(out, open(f"{D}/roles.json", "w"))
print(Counter(v.get("role") for v in out["roles"].values()), len(out["subs"]), sum(1 for s in out["subs"].values() if s))
