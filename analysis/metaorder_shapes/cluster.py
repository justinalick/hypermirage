"""DTW k-medoids on normalized cumulative fill paths (metaorders with >= 4 child orders), with stability checks."""
import json, numpy as np, pandas as pd
from sklearn.metrics import silhouette_score, adjusted_rand_score
import sys
sys.path.insert(0, "scripts")
import window as WIN
O = "data/derived/metaorder_shapes"
M = pd.read_parquet(f"{O}/metaorders_shape.parquet"); C = pd.read_parquet(f"{O}/curves.parquet")
M = M.loc[C.index]; X = C.values; K = X.shape[1]; rng = np.random.default_rng(7)
def dtw(A, B, w):   # banded DTW, L1 cost, rows of A vs rows of B (same count)
    P = len(A); prev = np.full((P, K + 1), np.inf); prev[:, 0] = 0
    for i in range(1, K + 1):
        cur = np.full((P, K + 1), np.inf)
        for j in range(max(1, i - w), min(K, i + w) + 1):
            cur[:, j] = np.abs(A[:, i - 1] - B[:, j - 1]) + np.minimum(np.minimum(prev[:, j - 1], prev[:, j]), cur[:, j - 1])
        prev = cur
    return prev[:, K]
def pdist(S, w, chunk=400_000):
    n = len(S); iu = np.triu_indices(n, 1); d = np.empty(len(iu[0]))
    for s in range(0, len(d), chunk):
        e = slice(s, s + chunk); d[e] = dtw(S[iu[0][e]], S[iu[1][e]], w)
    D = np.zeros((n, n)); D[iu] = d; return D + D.T
def todist(A, Med, w):   # each row of A vs each medoid curve
    return np.stack([dtw(A, np.repeat(m[None], len(A), 0), w) for m in Med], 1)
def kmedoids(D, k, restarts=10):
    best = None
    for r in range(restarts):
        med = [rng.integers(len(D))]
        for _ in range(k - 1):
            p = D[:, med].min(1) ** 2; med.append(rng.choice(len(D), p=p / p.sum()))
        med = np.array(med)
        for _ in range(100):
            lab = D[:, med].argmin(1)
            new = np.array([np.where(lab == c)[0][D[np.ix_(lab == c, lab == c)].sum(1).argmin()] for c in range(k)])
            if set(new) == set(med): break
            med = new
        cost = D[:, med].min(1).sum()
        if best is None or cost < best[0]: best = (cost, med)
    return best[1]
W = 2   # Sakoe-Chiba band: 2 of 20 steps = 10% of the metaorder's duration
N = 3000
si = rng.choice(len(X), N, replace=False); S = X[si]
res = {}
# unconstrained DTW collapses monotone 0->1 paths onto each other; show it
Du = pdist(S[:600], K); Db = pdist(S[:600], W); Deu = np.abs(S[:600, None] - S[None, :600]).sum(2)
res['median_dist_600'] = dict(unconstrained=float(np.median(Du[np.triu_indices(600, 1)])),
                              band10=float(np.median(Db[np.triu_indices(600, 1)])), l1=float(np.median(Deu[np.triu_indices(600, 1)])))
D = pdist(S, W)
res['silhouette'] = {}
meds = {}
for k in range(2, 9):
    med = kmedoids(D, k); meds[k] = med
    res['silhouette'][k] = float(silhouette_score(D, D[:, med].argmin(1), metric='precomputed'))
lab_full = {}
for k in range(2, 6):
    lab_full[k] = todist(X, S[meds[k]], W).argmin(1)
# stability 1: bootstrap the sample, re-cluster, re-assign everything, ARI vs reference
res['ari_boot'] = {}
for k in range(2, 6):
    a = []
    for b in range(20):
        idx = rng.choice(N, N, replace=True); m = kmedoids(D[np.ix_(idx, idx)], k, restarts=5)
        a.append(adjusted_rand_score(lab_full[k], todist(X, S[idx][m], W).argmin(1)))
    res['ari_boot'][k] = [float(np.min(a)), float(np.median(a))]
# stability 2: cluster each half of the window separately (in the two-week atlas: each week), assign
# everything, ARI first-half vs second-half medoids (stored as ari_week)
wk = (M.day.values >= WIN.split_day())
res['ari_week'] = {}; res['ari_ex_top'] = {}; res['ari_l1_kmedoids'] = {}
for half in (0, 1):
    pool = np.where(wk == half)[0]; si2 = rng.choice(pool, 1500, replace=False); D2 = pdist(X[si2], W)
    for k in range(2, 6):
        res['ari_week'].setdefault(k, []).append(todist(X, X[si2][kmedoids(D2, k)], W).argmin(1))
for k in range(2, 6):
    res['ari_week'][k] = float(adjusted_rand_score(*res['ari_week'][k]))
# stability 3: medoids from accounts other than the largest taker only
pool = np.where(~M.top.values)[0]; si3 = rng.choice(pool, 1500, replace=False); D3 = pdist(X[si3], W)
for k in range(2, 6):
    res['ari_ex_top'][k] = float(adjusted_rand_score(lab_full[k], todist(X, X[si3][kmedoids(D3, k)], W).argmin(1)))
# metric check: plain L1 distance k-medoids on the same sample
Dl = np.abs(S[:, None] - S[None]).sum(2)
for k in range(2, 6):
    ml = kmedoids(Dl, k); ll = np.abs(X[:, None] - S[ml][None]).sum(2).argmin(1)
    res['ari_l1_kmedoids'][k] = float(adjusted_rand_score(lab_full[k], ll))
# k-medoids numbers clusters arbitrarily: renumber by mean fill path (area under the curve), so that
# label 0 is the most front-loaded and the last label the most back-loaded (k=3: front-loaded, spread out,
# back-loaded). ARIs above do not depend on the numbering.
order = {}
for k in lab_full:
    area = np.array([X[lab_full[k] == c].mean() for c in range(k)])
    order[k] = np.argsort(-area)
    lab_full[k] = np.argsort(order[k])[lab_full[k]]
res['k3_renumbered_from'] = order[3].tolist()
print("k=3 renumbered from k-medoids labels", order[3].tolist())
print(json.dumps(res, indent=1))
json.dump(res, open(f"{O}/stability.json", "w"), indent=1)
L = pd.DataFrame({f'k{k}': lab_full[k] for k in lab_full}, index=C.index); L.to_parquet(f"{O}/labels.parquet")
np.save(f"{O}/medoid_curves.npy", np.array([S[meds[k]][order[k]] for k in range(2, 6)], dtype=object), allow_pickle=True)
