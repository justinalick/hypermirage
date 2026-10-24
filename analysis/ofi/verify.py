"""Independent recomputation of key ofi.py numbers (different code path: DuckDB SQL window functions,
bins by integer division, forward-filled mid on a full grid). Compares with ofi_res.json."""
import json, sys, numpy as np, duckdb
O = "data/derived/ofi"
R = json.load(open(f"{O}/ofi_res.json"))["h"]
con = duckdb.connect()
con.execute(f"""CREATE TABLE s AS SELECT t_ns, bid_px bp, bid_sz bs, ask_px ap, ask_sz qa,
  regexp_extract(filename,'(\\d{{8}})',1) d FROM read_parquet('{O}/l1/*.parquet', filename=true) WHERE bid_px < ask_px""")
con.execute("""CREATE TABLE ev AS SELECT t_ns, d, ln((bp+ap)/2) lm, (bs+qa)/2 dep,
  CASE WHEN lag(d) OVER w IS DISTINCT FROM d THEN 0 ELSE
    (CASE WHEN bp >= lag(bp) OVER w THEN bs ELSE 0 END) - (CASE WHEN bp <= lag(bp) OVER w THEN lag(bs) OVER w ELSE 0 END)
  - (CASE WHEN ap <= lag(ap) OVER w THEN qa ELSE 0 END) + (CASE WHEN ap >= lag(ap) OVER w THEN lag(qa) OVER w ELSE 0 END) END e,
  lead(t_ns) OVER w - t_ns dur
  FROM s WINDOW w AS (ORDER BY t_ns, bp, ap)""")
t0 = con.execute("SELECT (min(t_ns)//86400000000000)*86400000000000 FROM ev").fetchone()[0]
out = {}
for h in (1, 10, 60):
    H = h * 10**9
    # per bin: OFI sum, last mid in bin; full grid with forward-filled mid
    con.execute(f"""CREATE OR REPLACE TABLE b AS
      WITH g AS (SELECT range k FROM range(0, {14*86400//h})),
      agg AS (SELECT (t_ns-{t0})//{H} k, sum(e) ofi, arg_max(lm, t_ns) lm_end FROM ev GROUP BY 1)
      SELECT g.k, coalesce(ofi,0) ofi, last_value(lm_end IGNORE NULLS) OVER (ORDER BY g.k ROWS UNBOUNDED PRECEDING) lm_end
      FROM g LEFT JOIN agg USING(k) ORDER BY g.k""")
    # trailing 30-min time-weighted depth: dep weighted by duration, attributed to the state's own bin (approx.)
    con.execute(f"""CREATE OR REPLACE TABLE dd AS
      WITH g AS (SELECT range k FROM range(0, {14*86400//h})),
      a AS (SELECT (t_ns-{t0})//{H} k, sum(dep*coalesce(dur,0)) dw, sum(coalesce(dur,0)) w FROM ev GROUP BY 1),
      f AS (SELECT g.k, coalesce(dw,0) dw, coalesce(w,0) w FROM g LEFT JOIN a USING(k))
      SELECT k, sum(dw) OVER x / nullif(sum(w) OVER x,0) D FROM f
      WINDOW x AS (ORDER BY k ROWS BETWEEN {1800//h} PRECEDING AND 1 PRECEDING)""")
    a = con.execute("""SELECT b.k, ofi, 1e4*(lm_end - lag(lm_end) OVER (ORDER BY b.k)) r, D FROM b JOIN dd USING(k) ORDER BY b.k""").fetchnumpy()
    k, ofi, r, D = a["k"], a["ofi"], a["r"].astype(float), a["D"].astype(float)
    v = np.isfinite(r) & np.isfinite(D) & (D > 0); x = ofi / D
    def fit_r2(X, y):
        Xm = np.c_[np.ones(len(y)), X]; bb = np.linalg.lstsq(Xm, y, rcond=None)[0]; return 1 - ((y - Xm @ bb) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    c = fit_r2(x[v], r[v])
    win = k * h // 1800; rs = []
    for wv in np.unique(win[v]):
        w = v & (win == wv)
        if w.sum() >= 20 and ofi[w].std() > 0 and r[w].std() > 0: rs.append(np.corrcoef(ofi[w], r[w])[0, 1] ** 2)
    y, xk, vv = r[1:], x[:-1], v[1:] & v[:-1]; day = (k[1:] * h) // 86400
    yy, yh = [], []
    for td in range(1, 14):
        tr, te = vv & (day < td), vv & (day == td)
        bb = np.linalg.lstsq(np.c_[np.ones(tr.sum()), xk[tr]], y[tr], rcond=None)[0]; yy.append(y[te]); yh.append(bb[0] + bb[1] * xk[te])
    yy, yh = np.concatenate(yy), np.concatenate(yh); oos = 1 - ((yy - yh) ** 2).sum() / (yy ** 2).sum()
    o = R[str(h)]
    row = {"n_bins": (int(v.sum()), o["n_bins"]), "cont_pooled_r2": (c, o["cont_ofi_r2"]),
           "halfhour_med_r2": (float(np.median(rs)), o.get("cont_halfhour_r2_median")), "oos_r2": (oos, o["oos_ofi_r2"])}
    out[h] = row
    print(h, {kk: (round(a_, 4), None if b_ is None else round(b_, 4)) for kk, (a_, b_) in row.items()}, flush=True)
