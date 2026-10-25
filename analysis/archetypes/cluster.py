"""HDBSCAN on standardized account features + UMAP picture + bootstrap ARI + permutation null."""
import numpy as np, pandas as pd, json
from sklearn.cluster import HDBSCAN
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.metrics import adjusted_rand_score
import sys
sys.path.insert(0, "scripts")
import window as WIN
O = "data/derived/archetypes"
f = pd.read_parquet(f"{O}/features.parquet")
f = f[f.n_orders.notna()].reset_index(drop=True)
rest = f.med_rest_s.notna()
X = pd.DataFrame({
 'log_notional': np.log10(f.notional),
 'maker_share': f.maker_share,
 'log_med_order': np.log10(f.med_order_usd),
 'log_cancel_to_fill': np.log10(1 + f.cancel_to_fill.fillna(0).clip(upper=1e4)),
 'log_rest_s': np.log10(0.1 + f.med_rest_s.fillna(f.med_rest_s.median())),
 'log_dist_bps': np.log10(0.1 + f.med_dist_bps.fillna(f.med_dist_bps.median())),
 'has_resting': rest.astype(float),
 'alo_share': f.alo_share, 'frontend_share': f.frontend_share, 'trigger_share': f.trigger_share,
 'builder_share': f.builder_share, 'twap_share': f.twap_share,
 'cash_share': f.cash_share, 'weekend_share': f.weekend_share, 'hour_entropy': f.hour_entropy,
 'days_active': f.days_active/WIN.N_DAYS,
 'markout60': f.markout60_bps.clip(-3, 3),
 'log_turnover': np.log10(f.turnover.clip(lower=0.1)),
 'net_flow_ratio': f.net_flow_ratio,
})
Z = StandardScaler().fit_transform(X)
MCS, MS = 25, 10
def fit(Z):
    return HDBSCAN(min_cluster_size=MCS, min_samples=MS).fit_predict(Z)
lab = fit(Z)
res = {'n_accounts': int(len(f)), 'features': list(X.columns), 'mcs': MCS, 'min_samples': MS}
res['n_clusters'] = int(lab.max()+1); res['noise_share'] = float((lab<0).mean())
# bootstrap: refit on resample, ARI vs full-fit labels on the unique sampled accounts
rng = np.random.default_rng(11); aris=[]; aris_nn=[]; ncl=[]
for _ in range(200):
    idx = np.unique(rng.integers(0, len(Z), len(Z)))
    lb = fit(Z[idx]); ncl.append(int(lb.max()+1))
    aris.append(adjusted_rand_score(lab[idx], lb))
    m = (lab[idx]>=0)&(lb>=0)
    aris_nn.append(adjusted_rand_score(lab[idx][m], lb[m]) if m.sum()>10 else np.nan)
res['boot_ari'] = [float(np.nanpercentile(aris,q)) for q in (5,50,95)]
res['boot_ari_nonnoise'] = [float(np.nanpercentile(aris_nn,q)) for q in (5,50,95)]
res['boot_nclusters'] = {int(k): int(v) for k,v in zip(*np.unique(ncl, return_counts=True))}
# null: permute each column independently (keeps marginals, kills joint structure)
nul=[]
for _ in range(50):
    P = np.column_stack([rng.permutation(Z[:,j]) for j in range(Z.shape[1])])
    lp = fit(P); nul.append((int(lp.max()+1), float((lp<0).mean())))
res['null_nclusters_noise'] = nul[:10]; res['null_mean_nclusters'] = float(np.mean([a for a,_ in nul]))
# hyperparameter sensitivity
sens={}
for mcs in (10,15,25,40,60):
    for ms in (5,10,20):
        l2 = HDBSCAN(min_cluster_size=mcs, min_samples=ms).fit_predict(Z)
        sens[f'{mcs}/{ms}'] = (int(l2.max()+1), round(float((l2<0).mean()),3), round(adjusted_rand_score(lab,l2),3))
res['sensitivity'] = sens
# profiles (medians of raw features), notional share
f['cl'] = lab
tot = f.notional.sum()
prof = f.groupby('cl').agg(n=('a','size'), notional_share=('notional', lambda v: v.sum()/tot),
  maker_share=('maker_share','median'), med_order_usd=('med_order_usd','median'), notional_k=('notional', lambda v: v.median()/1e3),
  cancel_to_fill=('cancel_to_fill','median'), med_rest_s=('med_rest_s','median'), med_dist_bps=('med_dist_bps','median'),
  alo=('alo_share','median'), frontend=('frontend_share','median'), trigger=('trigger_share','median'), builder=('builder_share','median'),
  twap=('twap_share','mean'), cash=('cash_share','median'), weekend=('weekend_share','median'), days=('days_active','median'),
  mk60=('markout60_bps','median'), turnover=('turnover','median'), netflow=('net_flow_ratio','median'))
print(prof.round(3).to_string())
res['profiles'] = prof.reset_index().to_dict('records')
# notional-weighted markout per cluster
f['w60'] = f.markout60_bps*f.notional
res['mk60_nw'] = (f.groupby('cl').w60.sum()/f.groupby('cl').notional.sum()).round(3).to_dict()
import umap
E = umap.UMAP(n_neighbors=30, min_dist=0.15, random_state=3).fit_transform(Z)
pd.DataFrame({'a': f.a, 'cl': lab, 'u1': E[:,0], 'u2': E[:,1], 'notional': f.notional}).to_parquet(f"{O}/labels_local.parquet")
X.assign(cl=lab).to_parquet(f"{O}/X.parquet")
json.dump(res, open(f"{O}/cluster_res.json","w"), indent=1, default=str)
for k in ['n_accounts','n_clusters','noise_share','boot_ari','boot_ari_nonnoise','boot_nclusters','null_mean_nclusters','null_nclusters_noise','mk60_nw']:
    print(k, res[k])
for k,v in sens.items(): print(k, v)
