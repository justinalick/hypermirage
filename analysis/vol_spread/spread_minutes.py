"""Per-minute time-weighted quoted spread for xyz:SP500, every day of the run window (scripts/window.py).

Minute boundaries: block_number of the first block of each minute in the Reservoir 1m L2 book.
Quote states: replayed best bid/ask per block (data/derived/bbo). Each state lasts until the next
state change; durations are counted in blocks (~70 ms each) and split at minute boundaries.
Output: data/derived/vol_spread/spread_minutes.parquet (t, tw_spread_bps, l2_spread_bps).
"""
import duckdb

R = "."
con = duckdb.connect()
con.execute("SET TimeZone='UTC'; SET memory_limit='4GB'")
con.execute(f"""CREATE TABLE bnd AS
    SELECT make_timestamp(block_time_ms * 1000)::TIMESTAMP ts, block_number::BIGINT b0,
           (asks[1].px::DOUBLE - bids[1].px::DOUBLE) / ((asks[1].px::DOUBLE + bids[1].px::DOUBLE) / 2) * 1e4 l2_spread_bps
    FROM read_parquet('{R}/data/raw/xyz/book_1m/SP500/*.parquet')""")
con.execute("""CREATE TABLE mins AS
    SELECT date_trunc('minute', ts) t, b0, lead(b0) OVER (ORDER BY b0) b1, l2_spread_bps FROM bnd""")
con.execute(f"""CREATE TABLE q AS
    SELECT block::BIGINT b, (best_ask - best_bid) / ((best_ask + best_bid) / 2) * 1e4 s
    FROM read_parquet('{R}/data/derived/bbo/xyz_SP500/*.parquet')
    WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL AND best_ask > best_bid""")
# state segments: every quote change plus every minute start (carrying the prevailing quote)
con.execute("""CREATE TABLE seg AS
    WITH starts AS (
        SELECT m.b0 b, q.s FROM mins m ASOF JOIN q ON q.b <= m.b0
        UNION ALL SELECT b, s FROM q),
    u AS (SELECT DISTINCT ON (b) b, s FROM starts ORDER BY b, s)
    SELECT u.b, u.s, lead(u.b) OVER (ORDER BY u.b) - u.b dur FROM u""")
con.execute(f"""COPY (
    SELECT m.t, sum(seg.s * seg.dur) / sum(seg.dur) tw_spread_bps, any_value(m.l2_spread_bps) l2_spread_bps,
           sum(seg.dur) blocks
    FROM mins m JOIN seg ON seg.b >= m.b0 AND seg.b < m.b1
    WHERE m.b1 IS NOT NULL GROUP BY m.t ORDER BY m.t
) TO '{R}/data/derived/vol_spread/spread_minutes.parquet' (FORMAT parquet)""")
print(con.sql(f"""SELECT count(*) n, min(t), max(t), median(tw_spread_bps), median(l2_spread_bps),
    median(blocks), min(blocks), max(blocks) FROM '{R}/data/derived/vol_spread/spread_minutes.parquet'"""))
