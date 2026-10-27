-- Replayed top of book (data/derived/ofi/l1) against the exchange's one-minute L2 snapshots, per UTC day of the run
-- window (the run folder links only the window's days): share of snapshots where best bid and ask prices match, where
-- prices and both sizes match exactly, the same per side (mean of bid and ask), and replayed rows with a crossed book.
with r as (select regexp_extract(filename, '(\d{4}-\d{2}-\d{2})\.parquet', 1) dd, block_number::bigint bn, bids[1].px::double rbp, bids[1].sz::double rbs, asks[1].px::double rap, asks[1].sz::double ras from read_parquet('data/raw/xyz/book_1m/SP500/*.parquet', filename=true)),
l as (select * from read_parquet('data/derived/ofi/l1/*.parquet')),
j as (select r.*, l.* from r asof left join l on l.block <= r.bn)
select dd, count(*) n, round(avg((bid_px=rbp and ask_px=rap)::int),3) px_match,
 round(avg((bid_px=rbp and abs(bid_sz-rbs)<1e-6 and ask_px=rap and abs(ask_sz-ras)<1e-6)::int),3) both_sz_exact,
 round((avg((bid_px=rbp and abs(bid_sz-rbs)<1e-6)::int) + avg((ask_px=rap and abs(ask_sz-ras)<1e-6)::int)) / 2,3) side_sz_exact,
 sum((bid_px>=ask_px)::int) crossed from j group by 1 order by 1;
