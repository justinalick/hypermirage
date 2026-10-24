"""Refit the 2- and 3-state HMM with each alternative depth measure (and with no depth at all) and compare
the decoded paths and session mix with the main fit."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "analysis/regimes")
from hmm import fit_hmm, viterbi, order_states, session, D
from sklearn.metrics import adjusted_rand_score

alt = pd.read_parquet(f"{D}/verify/depth_alt.parquet")
base = {k: pd.read_parquet(f"{D}/states_K{k}.parquet") for k in (2, 3)}
f = base[2][["t", "d10", "log_spread", "abs_imb", "log_rv", "session"]].merge(alt, on="t", how="left")
print("median depth by session, $M (orig full notional | fill-adjusted lower bound | Reservoir L2 20 levels):")
print((f.groupby("session")[["d10", "d10_net", "l2_20lvl"]].median() / 1e6).round(2).to_string())
print("ratio fill-adjusted / orig by session:", (f.groupby("session").d10_net.median() / f.groupby("session").d10.median()).round(3).to_dict())

variants = {"fill-adjusted depth": "d10_net", "Reservoir L2 depth": "l2_20lvl", "no depth feature": None}
for name, col in variants.items():
    g = f.copy()
    feats = ["log_spread", "abs_imb", "log_rv"]
    if col:
        g["log_alt"] = np.log(g[col].clip(lower=1.0)); feats = ["log_alt"] + feats
    ok = g[feats].notna().all(1).to_numpy()
    g = g[ok].reset_index(drop=True)
    X = ((g[feats] - g[feats].mean()) / g[feats].std()).to_numpy()
    seg = np.r_[True, np.diff(g.t.values).astype("timedelta64[m]").astype(int) != 1]
    for K in (2, 3):
        m = fit_hmm(X, K, seed=0, seg=seg)
        # label states by mean spread (thin state has the widest spread), then by vol
        o = np.lexsort((m["mu"][:, feats.index("log_rv")], -m["mu"][:, feats.index("log_spread")]))
        p = np.argsort(o)[viterbi(X, m, seg)]
        b = base[K].state.to_numpy()[ok]
        if K == 2:  # main fit: 0 = thin
            agree = (p == b).mean()
        else:
            agree = np.nan
        mix = pd.crosstab(g.session, p, normalize="index").round(3)
        print(f"\n{name}, K={K}: {len(g)} min, ARI vs main fit {adjusted_rand_score(b, p):.3f}"
              + (f", same label {agree:.4f}" if K == 2 else ""))
        print(mix.to_string())
