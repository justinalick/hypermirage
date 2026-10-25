"""Compare own-replay entry position / queue-ahead bucket with the original replay, per check day
(every day fifo_replay.py checked, from its data/checks/queue/work/touch_<day>.parquet)."""
import glob, re, duckdb
c = duckdb.connect(); c.execute("SET memory_limit='2GB'; SET threads=2")
B = "CASE WHEN {p}=0 THEN 0 WHEN {a}<=5000 THEN 1 WHEN {a}<=25000 THEN 2 WHEN {a}<=100000 THEN 3 WHEN {a}<=250000 THEN 4 ELSE 5 END"
for p in sorted(glob.glob("data/checks/queue/work/touch_*.parquet")):
    d = re.search(r"touch_(\d{8})", p).group(1)
    r = c.execute(f"""SELECT count(*), count(m.oid), avg((m.pos=o.pos)::INT),
        avg((({B.format(p='m.pos', a='m.ahead_sz*o.px')}) = ({B.format(p='o.pos', a='coalesce(o.ahead_sz,0)*o.px')}))::INT)
      FROM 'data/derived/queue/{d}.parquet' o LEFT JOIN '{p}' m USING(oid)
      WHERE o.pos < 2""").fetchone()
    print(d, "orig touch orders", r[0], "found in mine", r[1], "same pos", round(r[2], 4), "same bucket", round(r[3], 4))
