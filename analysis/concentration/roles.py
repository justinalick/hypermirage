"""Declared account roles from the Hyperliquid info API (userRole, subAccounts) for the active-account
universe (universe.sql), plus the large takers if analysis/taker_clusters/roles.py has run.
Writes data/derived/concentration/roles.json; charts/concentration_cache.py merges declared sub-accounts with it.
The API answers with today's declared links, which can differ from the ones in force in the study window."""
import csv, json, os, time, urllib.request
R = "data/derived"
def q(body):
    for k in range(4):
        try:
            r = urllib.request.Request("https://api.hyperliquid.xyz/info", json.dumps(body).encode(), {"content-type": "application/json"})
            return json.load(urllib.request.urlopen(r, timeout=15))
        except Exception:
            time.sleep(2 ** k)
    return {"error": True}
seed = f"{R}/taker_clusters/roles.json"
old = json.load(open(seed)) if os.path.exists(seed) else {"roles": {}, "subs": {}}
roles, subs = dict(old["roles"]), dict(old["subs"])
uni = [r["u"] for r in csv.DictReader(open(f"{R}/concentration/universe.csv"))]
for a in uni:
    if a not in roles:
        roles[a] = q({"type": "userRole", "user": a}); time.sleep(0.3)
masters = {v["data"]["master"] for a, v in roles.items() if a in uni and v.get("role") == "subAccount"}
masters |= {a for a in uni if roles[a].get("role") == "user"}
for m in masters:
    if m not in subs:
        subs[m] = q({"type": "subAccounts", "user": m}); time.sleep(0.3)
json.dump({"roles": roles, "subs": subs}, open(f"{R}/concentration/roles.json", "w"))
from collections import Counter
print(Counter(roles[a].get("role") for a in uni), len(masters), sum(1 for m in masters if subs.get(m)))
