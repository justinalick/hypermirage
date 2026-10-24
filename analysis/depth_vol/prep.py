import duckdb, numpy as np, pandas as pd
D='data/derived/offhours/offhours_depth_minutes.parquet'
S='data/derived/depth_vol/'
df=duckdb.sql(f"select * from '{D}' order by t").df()
df['r']=np.log(df.mid).diff()*1e4
df.loc[df.t.diff()!=pd.Timedelta('1min'),'r']=np.nan
ANN=np.sqrt(365*1440)/100  # bps/min -> annualized %
df['rv']=df.r.rolling(15,min_periods=12).std()*ANN
df['rvf']=df.r[::-1].rolling(15,min_periods=12).std()[::-1].shift(-1)*ANN
dow=df.t.dt.day_of_week; h=df.t.dt.hour; mm=h*60+df.t.dt.minute
cash=(dow<5)&(mm>=810)&(mm<1200)
closed=((dow==4)&(h>=21))|(dow==5)|((dow==6)&(h<22))|((dow<4)&(h==21))
df['g']=np.select([cash,closed],['cash','closed'],'overnight')
df['wk']=((dow==4)&(h>=21))|(dow==5)|((dow==6)&(h<22))
df['hod']=h.astype(str)+np.where(df.wk,'w','d')
df['lnd']=np.log(df.d10)
df['rel']=df.lnd-df.groupby('hod').lnd.transform('median')
df['day']=df.t.dt.date
d=df.dropna(subset=['rv']).copy()
d['q']=d.groupby('g').rv.transform(lambda s: pd.qcut(s.rank(method='first'),10,labels=False))
rng=np.random.default_rng(7)
out=[]
for g,gg in d.groupby('g'):
    days=gg.day.unique()
    base=gg.groupby('q').agg(rv=('rv','median'),rel=('rel','median'),n=('rel','size'))
    boots=[]
    for b in range(1000):
        pick=rng.choice(days,len(days))
        s=pd.concat([gg[gg.day==x] for x in pick])
        boots.append(s.groupby('q').rel.median())
    B=pd.concat(boots,axis=1)
    base['lo']=B.quantile(.05,axis=1); base['hi']=B.quantile(.95,axis=1); base['g']=g
    out.append(base.reset_index())
    # top vs bottom decile gap with CI
    gap=(B.loc[9]-B.loc[0]); print(g,len(gg),len(days),'gap pct',round((np.exp(base.rel[9]-base.rel[0])-1)*100,1),
      'CI',round((np.exp(gap.quantile(.05))-1)*100,1),round((np.exp(gap.quantile(.95))-1)*100,1))
    print(base.round(3).to_string())
dec=pd.concat(out); dec.to_parquet(S+'deciles.parquet')
hr=d.assign(hr=d.t.dt.floor('h')).groupby(['hr','g']).agg(d10=('d10','median'),rv=('rv','median')).reset_index()
hr.to_parquet(S+'hourly.parquet')
print('hourly n',len(hr),'corr log',np.corrcoef(np.log(hr.d10),np.log(hr.rv))[0,1])
print('minute corr raw',np.corrcoef(d.lnd,np.log(d.rv))[0,1])
for g,gg in d.groupby('g'):
    x=gg.dropna(subset=['rvf'])
    print(g,'corr rel~log rv trailing',round(np.corrcoef(x.rel,np.log(x.rv))[0,1],3),'forward',round(np.corrcoef(x.rel,np.log(x.rvf))[0,1],3))
# per weekend
c=d[d.g=='closed'].copy(); c['wkid']=(c.t- pd.to_timedelta(((c.t.dt.day_of_week-4)%7),unit='D')).dt.date
for k,gg in c.groupby('wkid'):
    print('closed block',k,len(gg),round(np.corrcoef(gg.rel,np.log(gg.rv))[0,1],3))
print(d.groupby('g').agg(n=('rv','size'),rv=('rv','median'),d10=('d10','median')))
