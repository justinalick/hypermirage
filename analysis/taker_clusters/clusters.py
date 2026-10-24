import json, csv
D = "data/derived/taker_clusters"
j = json.load(open(f"{D}/roles.json"))
tak = {r["address"]: float(r["tak"]) for r in csv.DictReader(open(f"{D}/takers.csv"))}
m = {}
for mas, s in j["subs"].items():
    for x in (s or []):
        m[x["subAccountUser"].lower()] = mas.lower()
for a, v in j["roles"].items():
    if v.get("role") == "subAccount": m[a.lower()] = v["data"]["master"].lower()
print("roles None:", sum(1 for a in j['roles'] if j['roles'][a].get('role') is None))
# cluster id
cl = {a: m.get(a, a) for a in tak}
agg = {}
for a, t in tak.items(): agg.setdefault(cl[a], [0,0]); agg[cl[a]][0]+=t; agg[cl[a]][1]+=1
tot = sum(tak.values())
top = sorted(agg.items(), key=lambda x:-x[1][0])[:15]
for i, (c, (t, n)) in enumerate(top): print(f"cluster {i + 1}", round(t/1e6,1), round(t/tot*100,1), n)
multi = {c:v for c,v in agg.items() if v[1]>1}
print("multi-address clusters:", len(multi), "share", round(sum(v[0] for v in multi.values())/tot*100,1))
with open(f"{D}/cluster_map.csv","w") as f:
    f.write("address,cluster\n")
    for a in tak: f.write(f"{a},{cl[a]}\n")
