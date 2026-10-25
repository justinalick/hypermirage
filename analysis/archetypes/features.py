"""Per-account behavior features, xyz:SP500, every day of the run window (scripts/window.py). Universe: >= 30 fills. Writes features.parquet."""
import duckdb, numpy as np, pandas as pd
import sys
sys.path.insert(0, "scripts")
import window as WIN
D = "data"
OUT = f"{D}/derived/archetypes"
con = duckdb.connect()
con.execute(f"""create temp table f as
 select address a, epoch_ns(timestamp::timestamp)::bigint ft, price::double px, size::double sz,
        case when side='buy' then 1 else -1 end s, crossed, order_id, start_position::double sp,
        fee::double fee, (builder is not null and builder<>'') bld, (twap_id is not null and twap_id>0) twap,
        coalesce(is_liquidation,false) liq, extract(hour from timestamp::timestamp) hr, extract(minute from timestamp::timestamp) mi, dayofweek(timestamp::timestamp) dow,
        timestamp::date d
 from read_parquet('{D}/raw/xyz/fills/*.parquet')
 where coin='xyz:SP500' and timestamp >= '{WIN.T0}' and timestamp < '{WIN.T1}'""")
con.execute("create temp table u as select a from f group by 1 having count(*) >= 30")
# session of each fill's minute from the scripts/window.py clock (session edges fall on whole minutes):
# cash = NYSE session, weekend = futures closed (weekends and holiday closures)
mins = con.execute("select distinct ft // 60000000000 mn from f").df()
mins["session"] = WIN.session(pd.to_datetime(mins.mn * 60, unit="s", utc=True))
con.register("fmin", mins)
# fill-based features
ff = con.execute("""
 select a, count(*) n_fills, sum(px*sz) notional,
  sum(px*sz) filter (not crossed)/sum(px*sz) maker_share,
  count(distinct d) days_active,
  sum(px*sz) filter (m.session = 'cash')/sum(px*sz) cash_share,
  sum(px*sz) filter (m.session = 'closed')/sum(px*sz) weekend_share,
  sum(px*sz) filter (bld)/sum(px*sz) builder_share,
  sum(px*sz) filter (twap)/sum(px*sz) twap_share,
  sum(px*sz) filter (liq)/sum(px*sz) liq_share,
  1e4*sum(fee)/sum(px*sz) fee_bps,
  abs(sum(s*px*sz))/sum(px*sz) net_flow_ratio
 from f join u using(a) join fmin m on m.mn = f.ft // 60000000000 group by 1""").df()
# hour-of-day entropy (notional, 24 bins)
h = con.execute("select a, hr, sum(px*sz) v from f join u using(a) group by 1,2").df()
p = h.pivot_table(index='a', columns='hr', values='v', fill_value=0)
p = p.div(p.sum(axis=1), axis=0)
ent = -(p * np.log(p.where(p > 0, 1))).sum(axis=1) / np.log(24)
ff['hour_entropy'] = ff['a'].map(ent)
# order size: median order notional (fills grouped by order_id)
osz = con.execute("""select a, median(v) med_order_usd, quantile_cont(v,0.9) p90_order_usd from
  (select a, order_id, sum(px*sz) v from f join u using(a) group by 1,2) group by 1""").df()
# inventory: turnover = traded size / mean |position| at fills (position after fill)
inv = con.execute("""select a, sum(sz)/nullif(avg(abs(sp + s*sz)),0) turnover,
  avg(abs(sp + s*sz)*px)/1e3 mean_abs_pos_k from f join u using(a) group by 1""").df()
# markouts at 10s and 60s from account side, notional-weighted, vs block-replayed mid
b = con.execute(f"select epoch_ns(t)::bigint t, (best_bid+best_ask)/2 m from '{D}/derived/markout/bbo_t.parquet' where t is not null order by t").fetchnumpy()
bt, bm = b['t'].astype(np.int64), b['m']
x = con.execute("select a, ft, px, sz, s, crossed from f join u using(a)").df()
ft = x.ft.values.astype(np.int64); nt = (x.px*x.sz).values
mk = {}
for hs in (10, 60):
    ih = np.searchsorted(bt, ft + hs*10**9, 'right') - 1
    ok = (ih >= 0) & (ft + hs*10**9 <= bt[-1])
    v = np.where(ok, x.s.values*(bm[np.clip(ih,0,None)] - x.px.values)/x.px.values*1e4, 0.0)
    x[f'w{hs}'] = nt*ok; x[f'xw{hs}'] = v*nt*ok
g = x.groupby('a')[['w10','xw10','w60','xw60']].sum()
# cross-check vs markout2.py: market-wide taker 60s markout should be about +0.12 bps (universe only, so close, not equal)
tk = x.crossed.values
print('check taker 60s bps (universe):', round(float(x.xw60[tk].sum()/x.w60[tk].sum()), 3),
      ' maker 60s:', round(float(x.xw60[~tk].sum()/x.w60[~tk].sum()), 3))
mko = pd.DataFrame({'markout10_bps': g.xw10/g.w10, 'markout60_bps': g.xw60/g.w60}).reset_index()
# lifecycle features (all orders placed by the account). Read one day at a time into an on-disk table so
# memory stays flat over long windows: counts and sums add up over days; the two medians are exact
# (same definition as DuckDB median: mean of the two middle values for an even count), from a sort
# that DuckDB can spill to disk.
import glob, os
TMP = f"{OUT}/lc_tmp.duckdb"
if os.path.exists(TMP): os.remove(TMP)
dk = duckdb.connect(TMP); dk.execute(f"SET memory_limit='4GB'; SET threads=4; SET temp_directory='{OUT}/lc_tmp.spill'")
dk.register("uni", con.execute("select a from u").df())
dk.execute("CREATE TABLE ids AS SELECT a, row_number() OVER (ORDER BY a)::INT id FROM uni")
dk.execute("""CREATE TABLE cnt (id INT, n BIGINT, canc DOUBLE, fill DOUBLE, nd BIGINT, rj BIGINT, alo BIGINT, fe BIGINT, tr BIGINT)""")
dk.execute("CREATE TABLE rest (id INT, v DOUBLE)"); dk.execute("CREATE TABLE dist (id INT, v DOUBLE)")
for p in sorted(glob.glob(f"{D}/derived/lifecycle_touch/xyz_SP500/*.parquet")):
    dk.execute(f"""CREATE OR REPLACE TEMP TABLE l AS SELECT i.id, x.* FROM read_parquet('{p}') x JOIN ids i ON i.a = x.user""")
    dk.execute("""INSERT INTO cnt SELECT id, count(*),
        sum(notional_usd - coalesce(filled_usd,0)) filter (class in ('displayed_pulled','displayed_partial','never_displayed')),
        sum(filled_usd), count(*) filter (class='never_displayed'), count(*) filter (class='rejected'),
        count(*) filter (tif='Alo'), count(*) filter (tif='FrontendMarket'), count(*) filter (is_trigger) FROM l GROUP BY 1""")
    dk.execute("""INSERT INTO rest SELECT id, blocks_rested*ms_per_block/1000 FROM l
                  WHERE class in ('displayed_pulled','displayed_partial','filled') and blocks_rested>0""")
    dk.execute("""INSERT INTO dist SELECT id, abs(dist_bps) FROM l
                  WHERE dist_bps is not null and tif in ('Alo','Gtc') and not is_trigger""")
def med(t):
    return f"""SELECT id, avg(v) {t} FROM (
        SELECT id, v, row_number() OVER (PARTITION BY id ORDER BY v) rn, count(*) OVER (PARTITION BY id) n FROM {t})
      WHERE rn IN ((n + 1) // 2, n // 2 + 1) GROUP BY id"""
lc = dk.execute(f"""
 WITH c AS (SELECT id, sum(n) n, sum(canc) canc, sum(fill) fill, sum(nd) nd, sum(rj) rj, sum(alo) alo, sum(fe) fe, sum(tr) tr
            FROM cnt GROUP BY 1),
      r AS ({med('rest')}), d AS ({med('dist')})
 SELECT i.a, c.n n_orders, c.canc / nullif(c.fill, 0) cancel_to_fill, c.nd / c.n never_displayed_share,
        c.rj / c.n rejected_share, r.rest med_rest_s, c.alo / c.n alo_share, c.fe / c.n frontend_share,
        c.tr / c.n trigger_share, d.dist med_dist_bps
 FROM c JOIN ids i USING (id) LEFT JOIN r USING (id) LEFT JOIN d USING (id)""").df()
dk.close(); os.remove(TMP)
out = ff.merge(osz, on='a', how='left').merge(inv, on='a', how='left').merge(mko, on='a', how='left').merge(lc, on='a', how='left')
out['orders_per_fill'] = out.n_orders / out.n_fills
for c in ['maker_share','cash_share','weekend_share','builder_share','twap_share','liq_share','never_displayed_share',
          'rejected_share','alo_share','frontend_share','trigger_share']:
    out[c] = out[c].fillna(0)
out.to_parquet(f"{OUT}/features.parquet")
print(out.shape); print(out.describe().T.round(3).to_string())
