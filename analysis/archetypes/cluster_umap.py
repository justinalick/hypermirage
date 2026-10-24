"""Variant B: UMAP(10d) -> HDBSCAN. Bootstrap ARI (refit both), and the same pipeline on a column-permuted null."""
import numpy as np, pandas as pd, json, warnings
warnings.filterwarnings('ignore')
from sklearn.cluster import HDBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import adjusted_rand_score
import umap
O = "data/derived/archetypes"
X = pd.read_parquet(f"{O}/X.parquet").drop(columns='cl')
Z = StandardScaler().fit_transform(X)
def pipe(Z, seed):
    E = umap.UMAP(n_components=10, n_neighbors=30, min_dist=0.0, random_state=seed).fit_transform(Z)
    return HDBSCAN(min_cluster_size=25, min_samples=10).fit_predict(E)
lab = pipe(Z, 0)
res = {'n_clusters': int(lab.max()+1), 'noise_share': float((lab<0).mean())}
# seed-only stability (same data)
res['seed_ari'] = [round(adjusted_rand_score(lab, pipe(Z, s)),3) for s in (1,2,3,4,5)]
rng = np.random.default_rng(5); ar=[]; nc=[]
for b in range(40):
    idx = np.unique(rng.integers(0, len(Z), len(Z)))
    lb = pipe(Z[idx], 100+b); nc.append(int(lb.max()+1)); ar.append(adjusted_rand_score(lab[idx], lb))
res['boot_ari'] = [float(np.percentile(ar,q)) for q in (5,25,50,75,95)]
res['boot_nclusters'] = {int(k): int(v) for k,v in zip(*np.unique(nc, return_counts=True))}
nul=[]
for b in range(10):
    P = np.column_stack([rng.permutation(Z[:,j]) for j in range(Z.shape[1])])
    lp = pipe(P, 200+b); nul.append((int(lp.max()+1), round(float((lp<0).mean()),3)))
res['null'] = nul
np.save(f"{O}/labB.npy", lab)
json.dump(res, open(f"{O}/cluster_umap_res.json","w"), indent=1)
print(res)
f = pd.read_parquet(f"{O}/features.parquet"); f = f[f.n_orders.notna()].reset_index(drop=True); f['cl']=lab
tot=f.notional.sum()
print(f.groupby('cl').agg(n=('a','size'), nshare=('notional', lambda v: round(v.sum()/tot,3)), notional_k=('notional', lambda v: v.median()/1e3),
  maker=('maker_share','median'), med_order=('med_order_usd','median'), ctf=('cancel_to_fill','median'), rest_s=('med_rest_s','median'),
  dist=('med_dist_bps','median'), alo=('alo_share','median'), fe=('frontend_share','median'), trig=('trigger_share','median'),
  bld=('builder_share','median'), twap=('twap_share','mean'), cash=('cash_share','median'), wknd=('weekend_share','median'),
  days=('days_active','median'), mk60=('markout60_bps','median'), turn=('turnover','median')).round(2).to_string())
