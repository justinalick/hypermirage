# Order book regimes, xyz:SP500 2026-10-08..21

Run from the repository root with .venv/bin/python (pandas, numpy, scipy, scikit-learn, numba, matplotlib, duckdb):

1. features.py   per-minute features -> features.parquet
                 (inputs: data/derived/offhours/offhours_depth_minutes.parquet, data/derived/ofi/l1/*.parquet)
2. run.py        fits Gaussian HMMs K=2..6, seed and week-half stability -> fits.pkl, fit_summary.json  (~25 min)
                 hmm.py holds the HMM code (Baum-Welch, forward-backward, Viterbi, session labels)
3. analyze.py K  profiles, transitions, session mix, clock baseline -> regimes_K{K}.json, states_K{K}.parquet (run for K=2,3)
4. chart.py      the 4-panel chart -> regimes.png, regimes@2x.png (needs regimes_K2.json, regimes_K3.json, states_K3.parquet)

Checks (verify/):
- duckdb -no-agent < verify/features_check.sql   independent SQL recompute of spread/imbalance/RV
- verify/verify_hmm.py fits.pkl                  brute-force, log-space and synthetic tests of hmm.py
- duckdb -no-agent < verify/session_check.sql    SQL recompute of session mix, medians, clock accuracy
- verify/depth_alt.py then verify/depth_robust.py   refit with fill-adjusted depth, Reservoir L2 depth, no depth
