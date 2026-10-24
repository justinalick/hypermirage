import csv, json, time, urllib.request, sys
D = "data/derived/taker_clusters"
def q(body):
    for k in range(4):
        try:
            r = urllib.request.Request("https://api.hyperliquid.xyz/info", json.dumps(body).encode(), {"content-type": "application/json"})
            return json.load(urllib.request.urlopen(r, timeout=15))
        except Exception as e:
            time.sleep(2**k)
    return {"error": True}
rows = [r for r in csv.DictReader(open(f"{D}/takers.csv")) if float(r["tak"]) >= 1e6]
out = {}
for r in rows:
    out[r["address"]] = q({"type": "userRole", "user": r["address"]}); time.sleep(0.35)
masters = {v["data"]["master"] for v in out.values() if v.get("role") == "subAccount"}
masters |= {a for a, v in out.items() if v.get("role") == "user"}
subs = {}
for m in masters:
    subs[m] = q({"type": "subAccounts", "user": m}); time.sleep(0.35)
json.dump({"roles": out, "subs": subs}, open(f"{D}/roles.json", "w"))  # rerun clusters.py after
from collections import Counter
print(Counter(v.get("role") for v in out.values()), len(masters), sum(1 for s in subs.values() if s))
