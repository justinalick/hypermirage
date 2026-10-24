import duckdb, numpy as np, pandas as pd
S='data/derived/depth_vol/'
D='data/derived/offhours/offhours_depth_minutes.parquet'
df=duckdb.sql(f"select * from '{D}' order by t").df()
df['r']=np.log(df.mid).diff()*1e4
df['rv']=df.r.rolling(15,min_periods=12).std()*np.sqrt(365*1440)/100
dow=df.t.dt.day_of_week; h=df.t.dt.hour; mm=h*60+df.t.dt.minute
wk=((dow==4)&(h>=21))|(dow==5)|((dow==6)&(h<22)); brk=(dow<4)&(h==21)
cash=(dow<5)&(mm>=810)&(mm<1200)
df['g']=np.select([cash,wk,brk],['cash','weekend','break'],'overnight')
df['hod']=h.astype(str)+np.where(wk,'w','d')
df['rel']=np.log(df.d10)-df.groupby('hod').d10.transform(lambda s: np.log(s).median())
df['blk']=np.where(wk,'W'+(df.t-pd.to_timedelta((dow-4)%7,unit='D')).dt.strftime('%m%d'),df.t.dt.strftime('%m%d'))
d=df.dropna(subset=['rv']).copy()
d=d[d.g!='break']
d['rel2']=d.rel-d.groupby(['g','blk']).rel.transform('median')
print(d[d.g=='weekend'].groupby('blk').size())
# hourly (left), session at minute 30 of each hour
hr=df.dropna(subset=['rv']).assign(hr=df.t.dt.floor('h'))
mid30=df[df.t.dt.minute==30].set_index(df.t[df.t.dt.minute==30].dt.floor('h')).g.rename('g')
hr=hr.groupby('hr').agg(d10=('d10','median'),rv=('rv','median')).join(mid30).reset_index()
hr['g']=hr.g.replace({'weekend':'closed','break':'closed'}); hr=hr[hr.rv>0]
print('hours',len(hr),'rho',np.corrcoef(np.log(hr.d10),np.log(hr.rv))[0,1].round(3)); hr.to_parquet(S+'hourly2.parquet')
rng=np.random.default_rng(7); out=[]
def dec(gg,key):
    q=pd.qcut(gg.rv.rank(method='first'),10,labels=False)
    b=gg.assign(q=q).groupby('q').agg(rv=('rv','median'),rel=('rel2','median')).reset_index(); b['k']=key; return b,q
for g in ['cash','overnight']:
    gg=d[d.g==g]; b,q=dec(gg,g); gg=gg.assign(q=q.values)
    days=gg.blk.unique(); gs=[];B=[]
    for _ in range(1000):
        s=pd.concat([gg[gg.blk==x] for x in rng.choice(days,len(days))]); m=s.groupby('q').rel2.median(); B.append(m); gs.append(m[9]-m[0])
    B=pd.concat(B,axis=1); b['lo']=B.quantile(.05,axis=1).values; b['hi']=B.quantile(.95,axis=1).values
    print(g,len(gg),len(days),'gap',round(np.expm1(b.rel[9]-b.rel[0])*100,1),'CI',np.round(np.expm1(np.quantile(gs,[.05,.95]))*100,1))
    out.append(b)
for k,gg in d[d.g=='weekend'].groupby('blk'):
    b,_=dec(gg,k); b['lo']=np.nan; b['hi']=np.nan; out.append(b); print(k,len(gg),'gap',round(np.expm1(b.rel[9]-b.rel[0])*100,1))
pd.concat(out).to_parquet(S+'deciles2.parquet')
