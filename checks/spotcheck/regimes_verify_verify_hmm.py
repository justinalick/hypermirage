import sys, os; sys.path.insert(0, "analysis/regimes/verify")
import duckdb as _d
_c = _d.connect
def _conn(*a, **k):
    c = _c(*a, **k); c.execute("SET memory_limit='3GB'; SET threads=2"); return c
_d.connect = _conn
try: _d.default_connection().execute("SET memory_limit='3GB'; SET threads=2")
except Exception: pass
"""Checks of the HMM code in hmm.py against independent references.
1. brute force: enumerate every state path on tiny sequences (with a chain break) -> exact log-likelihood,
   posteriors and best path; compare to forward_backward / viterbi.
2. log-space reference forward-backward (scipy logsumexp, no scaling) on the real data and fitted models.
3. synthetic recovery: simulate a 3-state HMM with known parameters, fit, compare.
Usage: verify_hmm.py [fits.pkl]  (part 2 and EM-monotonicity use the fitted models if given)"""
import itertools, sys
import numpy as np, pandas as pd
from scipy.special import logsumexp
from scipy.stats import multivariate_normal
sys.path.insert(0, "analysis/regimes")
from hmm import emis_logp, forward_backward, viterbi, fit_hmm, order_states, match

rng = np.random.default_rng(42)
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


# 1. brute force
for K in (2, 3):
    T, P = 7, 2
    X = rng.normal(size=(T, P))
    mu = rng.normal(size=(K, P)); cov = np.array([np.eye(P) * rng.uniform(0.5, 2) for _ in range(K)])
    A = rng.dirichlet(np.ones(K), size=K); pi = rng.dirichlet(np.ones(K))
    seg = np.zeros(T, bool); seg[0] = True; seg[4] = True  # chain restarts at t=4
    lb = np.column_stack([multivariate_normal(mu[k], cov[k]).logpdf(X) for k in range(K)])
    paths = np.array(list(itertools.product(range(K), repeat=T)))
    lp = np.empty(len(paths))
    for n, z in enumerate(paths):
        v = 0.0
        for t in range(T):
            v += (np.log(pi[z[t]]) if seg[t] else np.log(A[z[t - 1], z[t]])) + lb[t, z[t]]
        lp[n] = v
    ll_bf = logsumexp(lp)
    post_bf = np.array([[np.exp(logsumexp(lp[paths[:, t] == k]) - ll_bf) for k in range(K)] for t in range(T)])
    _, _, g, ll = forward_backward(lb, np.log(A), np.log(pi), seg)
    check(f"brute-force log-likelihood K={K}", abs(ll - ll_bf) < 1e-9, f"{ll:.10f} vs {ll_bf:.10f}")
    check(f"brute-force posteriors K={K}", np.abs(g - post_bf).max() < 1e-9, f"max diff {np.abs(g - post_bf).max():.2e}")
    vp = viterbi(X, dict(mu=mu, cov=cov, A=A, pi=pi), seg)
    check(f"brute-force Viterbi path K={K}", (vp == paths[lp.argmax()]).all(), f"{vp} vs {paths[lp.argmax()]}")


def ref_fb(lb, A, pi, seg):
    T, K = lb.shape; la = np.empty((T, K)); lbk = np.zeros((T, K)); lA = np.log(A)
    for t in range(T):
        la[t] = (np.log(pi) if seg[t] else logsumexp(la[t - 1][:, None] + lA, axis=0)) + lb[t]
    for t in range(T - 2, -1, -1):
        lbk[t] = 0.0 if seg[t + 1] else logsumexp(lA + (lb[t + 1] + lbk[t + 1])[None], axis=1)
    ends = np.r_[np.where(seg)[0][1:] - 1, T - 1]
    ll = sum(logsumexp(la[e]) for e in ends)
    g = la + lbk; g = np.exp(g - logsumexp(g, axis=1, keepdims=True))
    return ll, g


# 3. synthetic recovery
K, P, T = 3, 4, 20000
mu_t = np.array([[-2, 1, 0, -1], [0.5, -0.5, 0, 0], [1, -0.5, 0.3, 1.5]], float)
cov_t = np.array([np.eye(P) * s for s in (0.3, 0.5, 0.6)])
A_t = np.array([[0.995, 0.003, 0.002], [0.002, 0.97, 0.028], [0.003, 0.03, 0.967]])
z = np.empty(T, int); z[0] = 0
for t in range(1, T):
    z[t] = rng.choice(K, p=A_t[z[t - 1]])
Xs = np.array([rng.multivariate_normal(mu_t[k], cov_t[k]) for k in z])
m = order_states(fit_hmm(Xs, K, seed=0))
o = match(mu_t, m["mu"])
check("synthetic: means recovered", np.abs(m["mu"][o] - mu_t).max() < 0.1, f"max err {np.abs(m['mu'][o] - mu_t).max():.3f}")
check("synthetic: transitions recovered", np.abs(m["A"][o][:, o] - A_t).max() < 0.01,
      f"max err {np.abs(m['A'][o][:, o] - A_t).max():.4f}")
vz = np.argsort(o)[viterbi(Xs, m, np.r_[True, np.zeros(T - 1, bool)])]
check("synthetic: Viterbi accuracy", (vz == z).mean() > 0.97, f"{(vz == z).mean():.4f}")

# 2. reference FB and EM monotonicity on the real fits
if len(sys.argv) > 1:
    Pk = pd.read_pickle(sys.argv[1]); X, seg = Pk["X"], Pk["seg"]
    for K, m in Pk["models"].items():
        lb = emis_logp(X, m["mu"], m["cov"])
        ll_r, g_r = ref_fb(lb, m["A"], m["pi"], seg)
        _, _, g, ll = forward_backward(lb, np.log(m["A"]), np.log(m["pi"]), seg)
        check(f"real data K={K}: scaled vs log-space ll", abs(ll - ll_r) < 1e-6 * abs(ll_r), f"{ll:.4f} vs {ll_r:.4f}")
        check(f"real data K={K}: posteriors", np.abs(g - g_r).max() < 1e-8, f"max diff {np.abs(g - g_r).max():.1e}")
        h = np.array(m["ll_hist"])
        check(f"real data K={K}: EM log-lik never decreases", (np.diff(h) > -1e-6 * abs(h[-1])).all(),
              f"{len(h)} iters, last gain {h[-1] - h[-2]:.2e}")
print("ALL PASS" if ok else "SOME CHECKS FAILED")
