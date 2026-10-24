import sys, os; sys.path.insert(0, "analysis/concentration")
import duckdb as _d
_c = _d.connect
def _conn(*a, **k):
    c = _c(*a, **k); c.execute("SET memory_limit='3GB'; SET threads=2"); return c
_d.connect = _conn
try: _d.default_connection().execute("SET memory_limit='3GB'; SET threads=2")
except Exception: pass
"""Independent check of the maker-concentration numbers using Polars (no DuckDB, no SQL).

Recomputes every figure shown on the chart from the raw Reservoir fill files, plus
data-integrity checks, and asserts each against the values the chart printed.
Usage: .venv/bin/python verify_concentration.py
"""
import polars as pl

DAYS = [f"2026-10-{d:02d}" for d in range(8, 22)]

frames = []
for day in DAYS:
    f = (pl.read_parquet(f"data/raw/xyz/fills/{day}.parquet",
                         columns=["coin", "price", "size", "timestamp", "address", "crossed", "trade_id", "order_id"])
         .filter(pl.col("coin") == "xyz:SP500")
         .with_columns(file_day=pl.lit(day)))
    frames.append(f)
f = pl.concat(frames).with_columns(
    usd=pl.col("price").cast(pl.Float64) * pl.col("size").cast(pl.Float64),
    d=pl.col("timestamp").dt.convert_time_zone("UTC").dt.strftime("%Y-%m-%d"),
)

print("== integrity")
coins = pl.concat([pl.read_parquet(f"data/raw/xyz/fills/{d}.parquet", columns=["coin"]) for d in DAYS])
print("coin names containing SP/500:", sorted(c for c in coins["coin"].unique() if "SP" in c or "500" in c))
print("rows whose UTC date differs from the file date:", f.filter(pl.col("d") != pl.col("file_day")).height)
print("null address / price / size:", f.select(pl.col("address").is_null().sum(), pl.col("price").is_null().sum(),
                                               pl.col("size").is_null().sum()).row(0))
print("non-positive notional rows:", f.filter(pl.col("usd") <= 0).height)
legs = f.group_by("trade_id").agg(n=pl.len(), mk=(~pl.col("crossed")).sum(), tk=pl.col("crossed").sum(),
                                  addrs=pl.col("address").n_unique(), usd_min=pl.col("usd").min(),
                                  usd_max=pl.col("usd").max())
print("trades:", legs.height, "| not exactly 1 maker + 1 taker:", legs.filter((pl.col("mk") != 1) | (pl.col("tk") != 1)).height,
      "| same address both legs:", legs.filter(pl.col("addrs") == 1).height,
      "| legs with different notional:", legs.filter((pl.col("usd_max") - pl.col("usd_min")).abs() > 1e-6).height)
dups = f.height - f.unique(["trade_id", "address", "crossed", "order_id"]).height
print("duplicate rows:", dups)
cross_day = f.group_by("trade_id").agg(pl.col("d").n_unique().alias("nd")).filter(pl.col("nd") > 1).height
print("trades whose two legs fall on different days:", cross_day)

mk = f.filter(~pl.col("crossed")).group_by("d", "address").agg(usd=pl.col("usd").sum())
taker_total = f.filter(pl.col("crossed"))["usd"].sum()
maker_total = mk["usd"].sum()
print(f"maker total ${maker_total:,.0f} | taker total ${taker_total:,.0f}")

print("\n== daily (sorted descending, ties broken by address so ranks are deterministic)")
rows = []
for day in DAYS:
    u = mk.filter(pl.col("d") == day).sort(["usd", "address"], descending=[True, False])["usd"].to_list()
    tot = sum(u)
    s = [v / tot for v in u]
    tie3 = len(u) > 3 and abs(u[2] - u[3]) < 1e-6
    rows.append(dict(d=day, vol=tot, makers=len(u), top1=100 * s[0], top3=100 * sum(s[:3]),
                     top10=100 * sum(s[:10]), hhi=1e4 * sum(x * x for x in s), tie_at_3=tie3))
daily = pl.DataFrame(rows)
with pl.Config(tbl_rows=20, float_precision=2):
    print(daily)

tot14 = mk.group_by("address").agg(usd=pl.col("usd").sum()).sort("usd", descending=True)["usd"].to_list()
T = sum(tot14)
pooled = 100 * sum(tot14[:3]) / T
print(f"\n14-day pooled: makers={len(tot14)} top3={pooled:.3f}% top10={100 * sum(tot14[:10]) / T:.3f}% "
      f"HHI={1e4 * sum((v / T) ** 2 for v in tot14):.1f}")
t3 = daily["top3"]
print(f"daily top3: min {t3.min():.2f} max {t3.max():.2f} median {t3.median():.2f} "
      f"volume-weighted {(daily['top3'] * daily['vol']).sum() / daily['vol'].sum():.2f}")

# Values printed by concentration_chart.py (DuckDB) when the PNG was rendered.
chart = {"2026-10-08": (35.1, 17.0, 66.9, 467), "2026-10-09": (38.4, 15.7, 71.0, 364),
         "2026-10-10": (41.9, 14.9, 81.0, 215), "2026-10-11": (39.2, 14.8, 74.9, 265),
         "2026-10-12": (35.5, 12.8, 65.4, 343), "2026-10-13": (35.6, 13.4, 69.3, 374),
         "2026-10-14": (38.0, 17.1, 72.3, 606), "2026-10-15": (41.4, 19.7, 69.4, 514),
         "2026-10-16": (42.3, 19.8, 67.8, 521), "2026-10-17": (45.0, 21.4, 76.8, 285),
         "2026-10-18": (37.7, 16.6, 63.1, 368), "2026-10-19": (45.6, 23.8, 74.4, 456),
         "2026-10-20": (34.3, 16.9, 64.5, 463), "2026-10-21": (41.6, 15.7, 68.7, 437)}
for r in daily.iter_rows(named=True):
    c = chart[r["d"]]
    assert (round(r["top3"], 1), round(r["top1"], 1), round(r["top10"], 1), r["makers"]) == c, (r, c)
assert round(pooled, 1) == 36.0 and len(tot14) == 2201 and legs.height == 612067
assert round(maker_total / 1e9, 2) == 3.10 and abs(maker_total - taker_total) < 1
print("\nALL CHART VALUES MATCH")
