"""Gaussian HMM (full covariance, scaled Baum-Welch with numba loops, GMM init) on per-minute book features.
Features (z-scored): log depth10, log spread, abs L1 imbalance, log realized vol. Imported by run.py / analyze.py."""
import json
import numpy as np
import pandas as pd
from scipy.special import logsumexp
from scipy.stats import multivariate_normal
from sklearn.mixture import GaussianMixture
from sklearn.metrics import adjusted_rand_score
from numba import njit

D = "data/derived/regimes"
FEATS = ["log_depth", "log_spread", "abs_imb", "log_rv"]


def load():
    f = pd.read_parquet(f"{D}/features.parquet")
    f["log_depth"] = np.log(f.d10)
    f["log_spread"] = np.log(f.spread_bps)
    rv_floor = f.rv_ann[f.rv_ann > 0].quantile(0.01)
    f["log_rv"] = np.log(f.rv_ann.clip(lower=rv_floor))
    f = f.dropna(subset=FEATS).reset_index(drop=True)
    return f


def emis_logp(X, mu, cov):
    return np.column_stack([multivariate_normal(mu[k], cov[k], allow_singular=True).logpdf(X) for k in range(len(mu))])


@njit(cache=True)
def _fb(B, A, pi, seg):
    T, K = B.shape
    al = np.empty((T, K)); c = np.empty(T); be = np.empty((T, K))
    for t in range(T):
        v = pi * B[t] if seg[t] else (al[t - 1] @ A) * B[t]
        c[t] = v.sum(); al[t] = v / c[t]
    for t in range(T - 1, -1, -1):
        if t == T - 1 or seg[t + 1]:
            be[t] = 1.0
        else:
            be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
    return al, be, c


def forward_backward(lb, logA, logpi, seg):
    """Scaled forward-backward. lb: (T,K) log emission densities. seg: segment start flags (gaps restart the chain)."""
    A = np.exp(logA); pi = np.exp(logpi)
    mx = lb.max(1, keepdims=True); B = np.exp(lb - mx)
    al, be, c = _fb(B, A, pi, seg.astype(np.bool_))
    ll = np.log(c).sum() + mx.sum()
    g = al * be; g /= g.sum(1, keepdims=True)
    return dict(al=al, be=be, B=B, c=c, A=A), None, g, ll


def fit_hmm(X, K, seed=0, n_iter=500, tol=1e-7, seg=None):
    T, P = X.shape
    seg = np.zeros(T, bool) if seg is None else seg.copy()
    seg[0] = True
    gm = GaussianMixture(K, covariance_type="full", random_state=seed, n_init=3).fit(X)
    mu, cov = gm.means_.copy(), gm.covariances_.copy()
    A = np.full((K, K), 0.05 / (K - 1)); np.fill_diagonal(A, 0.95)
    pi = np.full(K, 1 / K)
    prev = -np.inf; hist = []
    for it in range(n_iter):
        lb = emis_logp(X, mu, cov)
        fb, _, g, ll = forward_backward(lb, np.log(A), np.log(pi), seg)
        hist.append(ll)
        # xi summed over t (skip transitions into segment starts); scaled form
        nxt = np.where(~seg[1:])[0]
        w1 = fb["B"][nxt + 1] * fb["be"][nxt + 1] / fb["c"][nxt + 1][:, None]
        xi = A * (fb["al"][nxt].T @ w1)
        A = xi / xi.sum(1, keepdims=True)
        pi = g[seg].mean(0) + 1e-8; pi /= pi.sum()
        w = g.sum(0)
        mu = (g.T @ X) / w[:, None]
        for k in range(K):
            d = X - mu[k]
            cov[k] = (g[:, k, None] * d).T @ d / w[k] + 1e-6 * np.eye(P)
        if ll - prev < tol * abs(ll):
            break
        prev = ll
    n_par = K * P + K * P * (P + 1) / 2 + K * (K - 1) + (K - 1)
    return dict(mu=mu, cov=cov, A=A, pi=pi, ll=ll, bic=-2 * ll + n_par * np.log(T), iters=it + 1, gmm=gm, ll_hist=hist)


@njit(cache=True)
def _viterbi(lb, logA, logpi, seg):
    T, K = lb.shape
    d = np.empty((T, K)); bp = np.zeros((T, K), np.int64)
    for t in range(T):
        if seg[t] or t == 0:
            d[t] = logpi + lb[t]
        else:
            for j in range(K):
                best = -np.inf; arg = 0
                for i in range(K):
                    v = d[t - 1, i] + logA[i, j]
                    if v > best:
                        best = v; arg = i
                d[t, j] = best + lb[t, j]; bp[t, j] = arg
    path = np.empty(T, np.int64)
    for t in range(T - 1, -1, -1):
        if t == T - 1 or seg[t + 1]:
            path[t] = np.argmax(d[t])
        else:
            path[t] = bp[t + 1, path[t + 1]]
    return path


def viterbi(X, m, seg):
    lb = emis_logp(X, m["mu"], m["cov"])
    s = seg.astype(np.bool_).copy(); s[0] = True
    return _viterbi(lb, np.log(m["A"]), np.log(m["pi"]), s)


def order_states(m):
    """relabel states by mean log depth (0 = thinnest)."""
    o = np.argsort(m["mu"][:, 0])
    m["mu"], m["cov"], m["A"], m["pi"] = m["mu"][o], m["cov"][o], m["A"][o][:, o], m["pi"][o]
    return m


def match(mu_ref, mu):
    from scipy.optimize import linear_sum_assignment
    c = ((mu_ref[:, None] - mu[None]) ** 2).sum(-1)
    return linear_sum_assignment(c)[1]


def session(ts):
    """UTC session labels, same definition as offhours/depth_vol threads (ES: Sun 22:00 - Fri 21:00 UTC, break 21:00 Mon-Thu)."""
    dow = ts.dt.dayofweek  # Mon=0
    m = ts.dt.hour * 60 + ts.dt.minute
    h = ts.dt.hour
    wk = ((dow == 4) & (h >= 21)) | (dow == 5) | ((dow == 6) & (h < 22))
    cash = (dow <= 4) & (m >= 810) & (m < 1200)
    brk = (dow <= 3) & (h == 21)
    return np.select([wk, cash, brk], ["futures closed (wknd)", "US cash", "ES daily break"], "ES overnight")
