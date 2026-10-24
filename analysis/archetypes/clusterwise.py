"""Clusterwise stability (Hennig): mean best-match Jaccard per variant-B cluster over bootstrap refits. Also null UMAP for the chart."""
import numpy as np, pandas as pd, json, warnings
warnings.filterwarnings('ignore')
from sklearn.cluster import HDBSCAN
from sklearn.preprocessing import StandardScaler
import umap
O = "data/derived/archetypes"
X = pd.read_parquet(f"{O}/X.parquet").drop(columns='cl')
Z = StandardScaler().fit_transform(X); lab = np.load(f"{O}/labB.npy")
def pipe(Z, seed):
    E = umap.UMAP(n_components=10, n_neighbors=30, min_dist=0.0, random_state=seed).fit_transform(Z)
    return HDBSCAN(min_cluster_size=25, min_samples=10).fit_predict(E)
rng = np.random.default_rng(21); K = lab.max()+1; J = np.zeros((30, K))
for b in range(30):
    idx = np.unique(rng.integers(0, len(Z), len(Z))); lb = pipe(Z[idx], 300+b); lo = lab[idx]
    for k in range(K):
        A = set(np.where(lo==k)[0]); best = 0
        for c in range(lb.max()+1):
            B = set(np.where(lb==c)[0]); best = max(best, len(A&B)/max(1,len(A|B)))
        J[b,k] = best
jac = J.mean(0); np.save(f"{O}/jaccard.npy", J)
print({k: round(float(v),2) for k,v in enumerate(jac)})
rng2 = np.random.default_rng(9)
P = np.column_stack([rng2.permutation(Z[:,j]) for j in range(Z.shape[1])])
lp = pipe(P, 0)
E2 = umap.UMAP(n_neighbors=30, min_dist=0.15, random_state=3).fit_transform(P)
E1 = umap.UMAP(n_neighbors=30, min_dist=0.15, random_state=3).fit_transform(Z)
np.savez(f"{O}/plotdata.npz", E1=E1, E2=E2, lab=lab, lp=lp, jac=jac)
print('null clusters', lp.max()+1, 'noise', (lp<0).mean())
