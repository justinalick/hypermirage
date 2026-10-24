-- run from the repository root: duckdb -c ".read analysis/concentration/universe.sql"
COPY (SELECT user u, count(DISTINCT block_number) nb, count(*) n
      FROM read_parquet('data/l4/order_statuses/xyz_SP500/*/*.parquet')
      WHERE status IN ('open','canceled','badAloPxRejected','scheduledCancel')
      GROUP BY 1 HAVING count(DISTINCT block_number) >= 200 ORDER BY nb DESC)
TO 'data/derived/concentration/universe.csv';
