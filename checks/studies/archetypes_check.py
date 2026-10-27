"""Check of the archetype stability numbers (analysis/archetypes/cluster_umap.py, clusterwise.py; chart
charts/archetypes_v2.py), plus the null comparison the analysis does not make.
(a) Real accounts: the 30 bootstrap refits of clusterwise.py are rerun with the same resamples and seeds (UMAP with a
    fixed random_state and HDBSCAN are deterministic, so the refit labels are those of the analysis run; they are not
    saved by the analysis). Each cluster's best-match Jaccard per refit is computed from a contingency table
    (np.bincount over label pairs, |A u B| = |A| + |B| - |A n B|) instead of the per-cluster Python set loop, and
    compared with data/derived/archetypes/jaccard.npy entry by entry; then the number of clusters with mean Jaccard
    >= 0.7 (the page: 16 of 32). The cluster count of a fresh fit on the full data is also compared with labB.npy.
(b) Shuffled data: the column-permuted matrix of clusterwise.py (seed 9) is clustered with the same pipeline (seed 0;
    the page: 11 clusters, compared with plotdata.npz), then put through the same 30-refit test (same resample
    indices and seeds as the real run) and the same Jaccard code. The number of shuffled clusters with mean Jaccard
    >= 0.7 is printed with their sizes. This is the null comparison for (a); it has no published number, so it does
    not fail the check.
Refit labels are cached in data/derived/archetypes/stability_refits.npz together with a hash of the inputs; a cache
whose hash does not match (new features, new labels) is refit. HM_REFIT=1 forces the refits. A full refit is 62 UMAP
fits of about one minute each, run in 3 worker processes. Exit code 1 if (a) or the shuffled cluster count disagrees
with the saved analysis output (Jaccard entries to 1e-12)."""
import hashlib, json, os, sys, time, warnings
warnings.filterwarnings("ignore")
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
from sklearn.preprocessing import StandardScaler

O = "data/derived/archetypes"
NREF, WORKERS = 30, 3
CACHE = f"{O}/stability_refits.npz"


def pipe(Z, seed):
    import umap
    from sklearn.cluster import HDBSCAN
    E = umap.UMAP(n_components=10, n_neighbors=30, min_dist=0.0, random_state=seed).fit_transform(Z)
    return HDBSCAN(min_cluster_size=25, min_samples=10).fit_predict(E)


def best_jaccard(ref, new):
    """For each cluster k of ref (labels >= 0), the largest Jaccard overlap with any cluster of new (noise excluded)."""
    K = ref.max() + 1; Cn = new.max() + 1
    if Cn <= 0: return np.zeros(K)
    m = (ref >= 0) & (new >= 0)
    N = np.bincount(ref[m] * Cn + new[m], minlength=K * Cn).reshape(K, Cn).astype(float)
    a = np.bincount(ref[ref >= 0], minlength=K).astype(float)[:, None]
    b = np.bincount(new[new >= 0], minlength=Cn).astype(float)[None, :]
    return (N / np.maximum(a + b - N, 1)).max(1)


def main():
    t_start = time.time()
    X = pd.read_parquet(f"{O}/X.parquet").drop(columns="cl")
    Z = StandardScaler().fit_transform(X)
    lab = np.load(f"{O}/labB.npy"); Jsaved = np.load(f"{O}/jaccard.npy")
    lp_saved = np.load(f"{O}/plotdata.npz")["lp"]
    rng2 = np.random.default_rng(9)                                   # the permutation of clusterwise.py
    P = np.column_stack([rng2.permutation(Z[:, j]) for j in range(Z.shape[1])])
    rng = np.random.default_rng(21)                                   # the resamples of clusterwise.py
    IDX = [np.unique(rng.integers(0, len(Z), len(Z))) for _ in range(NREF)]
    key = hashlib.sha256(Z.tobytes() + lab.tobytes() + lp_saved.tobytes()).hexdigest()
    cache = None
    if os.path.exists(CACHE) and os.environ.get("HM_REFIT") != "1":
        c = np.load(CACHE, allow_pickle=True)
        if str(c["key"]) == key: cache = c
    if cache is None:
        jobs = [(Z, 0)] + [(Z[i], 300 + b) for b, i in enumerate(IDX)] + [(P, 0)] + [(P[i], 300 + b) for b, i in enumerate(IDX)]
        with ProcessPoolExecutor(WORKERS) as ex:
            out = list(ex.map(pipe, *zip(*jobs)))
        full, real, pfull, null = out[0], out[1:NREF + 1], out[NREF + 1], out[NREF + 2:]
        np.savez(CACHE, key=key, full=full, pfull=pfull, real=np.array(real, dtype=object), null=np.array(null, dtype=object))
        src = f"refit now ({len(jobs)} fits, {time.time() - t_start:.0f} s)"
    else:
        full, pfull, real, null = cache["full"], cache["pfull"], list(cache["real"]), list(cache["null"])
        src = "refit labels from cache (HM_REFIT=1 to refit)"
    print(f"     {src}")
    ok = True
    def report(good, msg):
        nonlocal ok
        ok &= bool(good)
        print(f"{'OK  ' if good else 'FAIL'} {msg}")

    # (a) real accounts
    report(np.array_equal(full, lab), f"real: fresh fit reproduces labB.npy ({full.max() + 1} clusters, noise {np.mean(full < 0):.1%})")
    J = np.array([best_jaccard(lab[i], l) for i, l in zip(IDX, real)])
    d = np.abs(J - Jsaved).max() if J.shape == Jsaved.shape else np.inf
    report(d <= 1e-12, f"real: best-match Jaccard, {J.shape[0]} refits x {J.shape[1]} clusters, max abs diff vs jaccard.npy {d:.1e}")
    jac = J.mean(0)
    n_ok = int((jac >= 0.7).sum())
    report(n_ok == int((Jsaved.mean(0) >= 0.7).sum()),
           f"real: {n_ok} of {len(jac)} clusters with mean Jaccard >= 0.7 (jaccard.npy {int((Jsaved.mean(0) >= 0.7).sum())}, page: 16 of 32)")
    print(f"     real: accounts in stable clusters {int(np.isin(lab, np.where(jac >= 0.7)[0]).sum()):,} of {len(lab):,}; "
          f"refit cluster counts {sorted(int(l.max() + 1) for l in real)}")

    # (b) shuffled data
    report(np.array_equal(pfull, lp_saved), f"shuffled: fresh fit reproduces plotdata.npz lp ({pfull.max() + 1} clusters, page: 11)")
    Jn = np.array([best_jaccard(pfull[i], l) for i, l in zip(IDX, null)])
    jn = Jn.mean(0)
    sizes = np.bincount(pfull[pfull >= 0])
    order = np.argsort(-sizes)
    print(f"     shuffled: {int((jn >= 0.7).sum())} of {len(jn)} clusters with mean Jaccard >= 0.7 over the same {len(null)} refits; "
          f"refit cluster counts {sorted(int(l.max() + 1) for l in null)}")
    print("     shuffled clusters by size (accounts, mean Jaccard): "
          + ", ".join(f"{sizes[k]}: {jn[k]:.2f}" for k in order))
    print(f"     for comparison, real clusters >= 0.7 by size: "
          + ", ".join(f"{np.sum(lab == k)}: {jac[k]:.2f}" for k in np.argsort(-np.bincount(lab[lab >= 0])) if jac[k] >= 0.7))
    print(f"     runtime {time.time() - t_start:.0f} s")
    print("ALL OK" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
