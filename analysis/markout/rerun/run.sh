#!/usr/bin/env bash
# Rebuild the markout charts and the independent check. Run from the repository root.
set -euo pipefail
cd .
duckdb -c ".read analysis/markout/rerun/prep_bbo_t.sql"        # 1. timed mid (bbo_t.parquet)
.venv/bin/python analysis/markout/rerun/markout2.py            # 2. markouts + CIs -> markout_res.json
.venv/bin/python analysis/markout/rerun/dist.py                # 3. hourly means -> hourly.json
.venv/bin/python analysis/markout/rerun/plot.py                # 4. line chart -> sp500_markouts.png
.venv/bin/python analysis/markout/rerun/plot_violin2.py        # 5. violins -> sp500_markouts_violin.png
.venv/bin/python analysis/markout/rerun/verify_markouts.py     # 6. independent check -> verify_res.json
