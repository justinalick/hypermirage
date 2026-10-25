"""Declared account roles from the Hyperliquid info API (userRole, subAccounts) for the active-account
universe (universe.csv), plus the large takers if analysis/taker_clusters/roles.py has run.
Writes data/derived/concentration/roles.json; charts/concentration_cache.py merges declared sub-accounts with it.
The API answers with today's declared links, which can differ from the ones in force in the study window.
Requests go through analysis/hl_api.py (throttled, cached across windows)."""
import csv, json, os, sys
from collections import Counter
sys.path.insert(0, "analysis")
from hl_api import roles_and_subs
R = "data/derived"
seed = f"{R}/taker_clusters/roles.json"
extra = list(json.load(open(seed))["roles"]) if os.path.exists(seed) else []
uni = [r["u"] for r in csv.DictReader(open(f"{R}/concentration/universe.csv"))]
out = roles_and_subs(sorted(set(uni) | set(extra)))
json.dump(out, open(f"{R}/concentration/roles.json", "w"))
roles = out["roles"]
masters = {v["data"]["master"] for a, v in roles.items() if a in set(uni) and v.get("role") == "subAccount"}
masters |= {a for a in uni if roles[a].get("role") == "user"}
print(Counter(roles[a].get("role") for a in uni), len(masters), sum(1 for m in masters if out["subs"].get(m)))
