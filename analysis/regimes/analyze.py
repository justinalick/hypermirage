"""Describe chosen-K regimes: profiles, transitions, dwell, session mix, clock baseline, per-day stability.
Usage: analyze.py K"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "analysis/regimes")
from hmm import *
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

K = int(sys.argv[1])
P = pd.read_pickle(f"{D}/fits.pkl")
f, X, seg, m = P["f"], P["X"], P["seg"], P["models"][K]
f["state"] = viterbi(X, m, seg)
_, _, g, _ = forward_backward(emis_logp(X, m["mu"], m["cov"]), np.log(m["A"]), np.log(m["pi"]), seg)
f["post_max"] = g.max(1)
f["day"] = f.t.dt.strftime("%m-%d %a")
out = {"K": K, "n_minutes": len(f)}

prof = f.groupby("state").agg(minutes=("t", "size"), depth10_musd=("d10", lambda x: x.median() / 1e6),
                              spread_bps=("spread_bps", "median"), abs_imb=("abs_imb", "median"),
                              rv5_ann_pct=("rv5", lambda x: 100 * x.median()))
prof["share"] = prof.minutes / len(f)
prof["dwell_min_model"] = 1 / (1 - np.diag(m["A"]))
# empirical runs from Viterbi path
run_id = (f.state.diff() != 0).cumsum().rename("run")
runs = f.groupby(run_id).agg(st=("state", "first"), n=("t", "size"))
prof["runs"] = runs.groupby("st").size()
prof["median_run_min"] = runs.groupby("st").n.median()
out["profile"] = prof.round(3).reset_index().to_dict("records")
out["A"] = m["A"].round(4).tolist()
# empirical Viterbi transitions
tr = pd.crosstab(f.state[:-1].values, f.state[1:].values)
out["A_viterbi"] = (tr.div(tr.sum(1), axis=0)).round(4).values.tolist()
out["mean_post_max"] = round(float(f.post_max.mean()), 3)

mix = pd.crosstab(f.session, f.state, normalize="index").round(3)
out["session_mix"] = mix.to_dict("index")
out["session_minutes"] = f.session.value_counts().to_dict()

# clock baseline: how much of the state does the clock alone explain?
f["clock"] = f.session + "|" + f.t.dt.hour.astype(str)
maj = f.groupby("clock").state.agg(lambda s: s.value_counts().idxmax())
out["clock_hour_accuracy"] = round(float((f.clock.map(maj) == f.state).mean()), 3)
maj_s = f.groupby("session").state.agg(lambda s: s.value_counts().idxmax())
out["session_only_accuracy"] = round(float((f.session.map(maj_s) == f.state).mean()), 3)
out["nmi_state_vs_clockhour"] = round(normalized_mutual_info_score(f.clock, f.state), 3)
out["nmi_state_vs_session"] = round(normalized_mutual_info_score(f.session, f.state), 3)
# leave-one-day-out clock baseline (honest)
acc = []
for d in f.day.unique():
    tr_, te = f[f.day != d], f[f.day == d]
    mj = tr_.groupby("clock").state.agg(lambda s: s.value_counts().idxmax())
    acc.append((te.clock.map(mj) == te.state).mean())
out["clock_hour_accuracy_lodo"] = round(float(np.nanmean(acc)), 3)

# per-day state shares within each session (stability across days)
pd_ = pd.crosstab([f.session, f.day], f.state, normalize="index").round(3)
out["per_day_mix"] = {f"{a} | {b}": r.to_dict() for (a, b), r in pd_.iterrows()}

# transitions at session boundaries vs inside sessions
f["sess_change"] = f.session.ne(f.session.shift())
f["st_change"] = f.state.ne(f.state.shift())
win = np.zeros(len(f), bool)
for i in np.where(f.sess_change)[0][1:]:
    win[max(0, i - 5): i + 6] = True
out["switch_rate_per_hr_near_session_edge"] = round(float(f.st_change[win].mean() * 60), 2)
out["switch_rate_per_hr_elsewhere"] = round(float(f.st_change[~win].mean() * 60), 2)
out["switch_rate_by_session_per_hr"] = (f.groupby("session").st_change.mean() * 60).round(2).to_dict()

f.to_parquet(f"{D}/states_K{K}.parquet", index=False)
json.dump(out, open(f"{D}/regimes_K{K}.json", "w"), indent=1, default=float)
print(json.dumps({k: v for k, v in out.items() if k != "per_day_mix"}, indent=1, default=float))
