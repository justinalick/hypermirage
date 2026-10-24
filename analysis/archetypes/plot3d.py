"""Interactive 3-D UMAP (real vs shuffled null) as a self-contained HTML page. No addresses are written."""
import numpy as np, pandas as pd, json, warnings, sys
warnings.filterwarnings('ignore')
from sklearn.preprocessing import StandardScaler
import umap
O = "data/derived/archetypes"; sys.path.insert(0, O)
from names import name_clusters
f = pd.read_parquet(f"{O}/features.parquet"); f = f[f.n_orders.notna()].reset_index(drop=True)
X = pd.read_parquet(f"{O}/X.parquet").drop(columns='cl'); Z = StandardScaler().fit_transform(X)
d = np.load(f"{O}/plotdata.npz"); lab, lp, jac = d['lab'], d['lp'], d['jac']
rng2 = np.random.default_rng(9)
P = np.column_stack([rng2.permutation(Z[:, j]) for j in range(Z.shape[1])])
E = umap.UMAP(n_components=3, n_neighbors=30, min_dist=0.15, random_state=3).fit_transform(Z)
EP = umap.UMAP(n_components=3, n_neighbors=30, min_dist=0.15, random_state=3).fit_transform(P)
NAME, GRP = name_clusters(f, lab); tot = f.notional.sum()
rows = []
for i in range(len(f)):
    c = int(lab[i]); r = f.iloc[i]
    rows.append([round(float(E[i,0]),3), round(float(E[i,1]),3), round(float(E[i,2]),3), c,
      GRP.get(c, 'noise'), NAME.get(c, 'Unassigned (noise)'), round(float(jac[c]),2) if c >= 0 else None,
      round(float(np.log10(r.notional)),2), round(float(r.maker_share),2), round(float(r.med_order_usd)),
      round(float(r.markout60_bps),2), int(r.days_active)])
null = [[round(float(EP[i,0]),3), round(float(EP[i,1]),3), round(float(EP[i,2]),3), int(lp[i])] for i in range(len(f))]
summ = {g: [int((np.array([GRP.get(c,'noise') for c in lab]) == g).sum()),
            round(100*f.notional[np.array([GRP.get(c,'noise') for c in lab]) == g].sum()/tot)] for g in ['maker','api','ui','noise']}
json.dump({'rows': rows, 'null': null, 'summ': summ, 'nnull': int(lp.max()+1), 'n': len(f)}, open(f"{O}/plot3d_data.json", "w"))
tpl = open("analysis/archetypes/plot3d_template.html").read()
open(f"{O}/sp500_archetypes_3d.html", "w").write(tpl.replace("/*DATA*/null", json.dumps({'rows': rows, 'null': null, 'summ': summ, 'nnull': int(lp.max()+1), 'n': len(f)})))
print('wrote', len(rows))
