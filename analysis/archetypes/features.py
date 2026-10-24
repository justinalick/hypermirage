"""Per-account behavior features, xyz:SP500, 2026-10-08..21. Universe: >= 30 fills. Writes features.parquet."""
import duckdb, numpy as np, pandas as pd
D = "data"
OUT = f"{D}/derived/archetypes"
con = duckdb.connect()
con.execute(f"""create temp table f as
 select address a, epoch_ns(timestamp::timestamp)::bigint ft, price::double px, size::double sz,
        case when side='buy' then 1 else -1 end s, crossed, order_id, start_position::double sp,
        fee::double fee, (builder is not null and builder<>'') bld, (twap_id is not null and twap_id>0) twap,
        coalesce(is_liquidation,false) liq, extract(hour from timestamp::timestamp) hr, extract(minute from timestamp::timestamp) mi, dayofweek(timestamp::timestamp) dow,
        timestamp::date d
 from read_parquet('{D}/raw/xyz/fills/2026-10-*.parquet')
 where coin='xyz:SP500' and timestamp >= '2026-10-08' and timestamp < '2026-10-22'""")
con.execute("create temp table u as select a from f group by 1 having count(*) >= 30")
# fill-based features
ff = con.execute("""
 select a, count(*) n_fills, sum(px*sz) notional,
  sum(px*sz) filter (not crossed)/sum(px*sz) maker_share,
  count(distinct d) days_active,
  sum(px*sz) filter (hr*60+mi >= 13*60+30 and hr < 20 and dow between 1 and 5)/sum(px*sz) cash_share,
  sum(px*sz) filter (dow=6 or (dow=0 and hr<22) or (dow=5 and hr>=21))/sum(px*sz) weekend_share,
  sum(px*sz) filter (bld)/sum(px*sz) builder_share,
  sum(px*sz) filter (twap)/sum(px*sz) twap_share,
  sum(px*sz) filter (liq)/sum(px*sz) liq_share,
  1e4*sum(fee)/sum(px*sz) fee_bps,
  abs(sum(s*px*sz))/sum(px*sz) net_flow_ratio
 from f join u using(a) group by 1""").df()
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
# lifecycle features (all orders placed by the account)
lc = con.execute(f"""
 select user a, count(*) n_orders,
  sum(notional_usd - coalesce(filled_usd,0)) filter (class in ('displayed_pulled','displayed_partial','never_displayed'))
     / nullif(sum(filled_usd),0) cancel_to_fill,
  count(*) filter (class='never_displayed')/count(*) never_displayed_share,
  count(*) filter (class='rejected')/count(*) rejected_share,
  median(blocks_rested*ms_per_block/1000) filter (class in ('displayed_pulled','displayed_partial','filled') and blocks_rested>0) med_rest_s,
  count(*) filter (tif='Alo')/count(*) alo_share,
  count(*) filter (tif='FrontendMarket')/count(*) frontend_share,
  count(*) filter (is_trigger)/count(*) trigger_share,
  median(abs(dist_bps)) filter (dist_bps is not null and tif in ('Alo','Gtc') and not is_trigger) med_dist_bps
 from read_parquet('{D}/derived/lifecycle_touch/xyz_SP500/*.parquet')
 where user in (select a from u) group by 1""").df()
out = ff.merge(osz, on='a', how='left').merge(inv, on='a', how='left').merge(mko, on='a', how='left').merge(lc, on='a', how='left')
out['orders_per_fill'] = out.n_orders / out.n_fills
for c in ['maker_share','cash_share','weekend_share','builder_share','twap_share','liq_share','never_displayed_share',
          'rejected_share','alo_share','frontend_share','trigger_share']:
    out[c] = out[c].fillna(0)
out.to_parquet(f"{OUT}/features.parquet")
print(out.shape); print(out.describe().T.round(3).to_string())
