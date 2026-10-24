# Taker-cluster markouts, xyz:SP500, 2026-10-08..21

Run from the repository root, in order:
1. `duckdb < analysis/taker_clusters/takers.sql`        taker notional per address -> takers.csv
2. `.venv/bin/python analysis/taker_clusters/roles.py`   Hyperliquid API userRole + subAccounts for takers >= $1M -> roles.json
3. `.venv/bin/python analysis/taker_clusters/clusters.py` address -> master cluster -> cluster_map.csv
4. `.venv/bin/python analysis/taker_clusters/mk.py`      markouts by cluster, ES session, maker -> mk_res.json, labels_local.json
5. `.venv/bin/python analysis/taker_clusters/plot.py`    chart -> sp500_taker_clusters.png
6. `duckdb < analysis/taker_clusters/verify.sql`         independent recompute (DuckDB ASOF joins) of the T1/others markouts, fees, session and hourly shares

Inputs: data/raw/xyz/fills (Reservoir), data/derived/markout/bbo_t.parquet (best bid/ask per block from touch.py, timed by block_time).
Markout = side * (mid(t+h) - fill px) / fill px, bps, notional-weighted; fill horizon = last book change strictly before the fill;
h > 0 = last change at or before t+h. CI: bootstrap over 1-hour blocks. Gross of fees.
labels_local.json (under data/, gitignored) maps cluster labels to addresses and stays local.
