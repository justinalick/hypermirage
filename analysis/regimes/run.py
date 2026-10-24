"""Fit GMM + HMM regimes, select K, stability checks. xyz:SP500 2026-10-08..21, 1-min bins."""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "analysis/regimes")
from hmm import *

f = pd.read_parquet(f"{D}/features.parquet").sort_values("t").reset_index(drop=True)
# trailing 5-min realized vol (60 x 5s returns); 1-min RV is 0 in 7% of minutes
rv2 = (f.rv_ann ** 2).rolling(5, min_periods=5).mean()
f["rv5"] = np.sqrt(rv2)
f["log_depth"] = np.log(f.d10)
f["log_spread"] = np.log(f.spread_bps)
f["log_rv"] = np.log(f.rv5.clip(lower=f.rv5[f.rv5 > 0].quantile(0.005)))
f = f.dropna(subset=FEATS).reset_index(drop=True)
print("minutes used:", len(f), "rv5==0:", (f.rv5 == 0).sum())
mu0, sd0 = f[FEATS].mean(), f[FEATS].std()
X = ((f[FEATS] - mu0) / sd0).to_numpy()
seg = np.r_[True, np.diff(f.t.values).astype("timedelta64[m]").astype(int) != 1]
f["session"] = session(f.t)

res = {"n_minutes": len(f), "bic": {}, "gmm_bic": {}}
models = {}
for K in range(2, 7):
    m = order_states(fit_hmm(X, K, seed=0, seg=seg))
    models[K] = m
    res["bic"][K] = m["bic"]; res["gmm_bic"][K] = m["gmm"].bic(X)
    print(K, "HMM BIC", round(m["bic"]), "GMM BIC", round(m["gmm"].bic(X)), "iters", m["iters"], flush=True)

# stability per K: seeds and week halves
half = (f.t < "2026-10-15").to_numpy()
stab = {}
for K in range(2, 7):
    ref = models[K]; pref = viterbi(X, ref, seg)
    seeds = []
    for s in (1, 2):
        m = order_states(fit_hmm(X, K, seed=s, seg=seg)); seeds.append(adjusted_rand_score(pref, viterbi(X, m, seg)))
    halves = []
    for msk in (half, ~half):
        sg = seg[msk].copy(); sg[0] = True
        m = order_states(fit_hmm(X[msk], K, seed=0, seg=sg))
        halves.append(dict(ari_full=adjusted_rand_score(pref, viterbi(X, m, seg)),
                           diag=np.diag(m["A"]).round(4).tolist(), mu=m["mu"].round(2).tolist()))
    stab[K] = dict(seed_ari=np.round(seeds, 3).tolist(), half_ari=[round(h["ari_full"], 3) for h in halves], halves=halves)
    print(K, "seed ARI", stab[K]["seed_ari"], "half ARI", stab[K]["half_ari"], flush=True)
res["stability"] = stab
pd.to_pickle(dict(models=models, f=f, X=X, seg=seg, mu0=mu0, sd0=sd0), f"{D}/fits.pkl")
json.dump(res, open(f"{D}/fit_summary.json", "w"), indent=1, default=float)
