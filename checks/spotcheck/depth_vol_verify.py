import sys, os; sys.path.insert(0, "analysis/depth_vol")
import duckdb as _d
_c = _d.connect
def _conn(*a, **k):
    c = _c(*a, **k); c.execute("SET memory_limit='3GB'; SET threads=2"); return c
_d.connect = _conn
try: _d.default_connection().execute("SET memory_limit='3GB'; SET threads=2")
except Exception: pass
import duckdb, numpy as np, pandas as pd
import datetime as dt
from zoneinfo import ZoneInfo
sys.path.insert(0, "scripts")
import window as WIN   # holiday dates only; the UTC session rules below are this check's own
if WIN.utc_offset_hours() != -4:
    sys.exit("depth_vol_verify.py: UTC session rules assume US daylight time throughout the window")
_CHI = ZoneInfo("America/Chicago")
_HOL = []
for _d, _hm in WIN.ES_HOLIDAYS.items():   # early halt; Monday holidays reopen 17:00 Chicago, Friday ones run into the weekend
    _day = dt.date.fromisoformat(_d)
    _a = dt.datetime.combine(_day, dt.time(int(_hm[:2]), int(_hm[3:])), _CHI).astimezone(dt.timezone.utc).replace(tzinfo=None)
    _b = dt.datetime.combine(_day, dt.time(16 if _day.weekday() == 4 else 17), _CHI).astimezone(dt.timezone.utc).replace(tzinfo=None)
    _HOL.append((pd.Timestamp(_a), pd.Timestamp(_b)))
def hol_mask(t):
    m_ = np.zeros(len(t), bool)
    for a_, b_ in _HOL: m_ |= ((t >= a_) & (t < b_)).to_numpy()
    return m_
R='.'
con=duckdb.connect(); con.execute("SET TimeZone='UTC'")
m=con.sql(f"select * from '{R}/data/derived/offhours/offhours_depth_minutes.parquet' order by t").df()
print('rows',len(m),'min',m.t.min(),'max',m.t.max(),'dups',m.t.duplicated().sum(),'gaps',(m.t.diff()!=pd.Timedelta('1min')).sum()-1, 'nulls',m.isna().sum().to_dict())
# L2 independent: mid and depth within 2 bps, first block of each minute
import pyarrow.parquet as pq, glob
rows=[]
for f in sorted(glob.glob(f"{R}/data/raw/xyz/book_1m/SP500/*.parquet")):
    for r in pq.read_table(f).to_pylist():
        b=[(float(x['px']),float(x['sz'])) for x in r['bids']]; a=[(float(x['px']),float(x['sz'])) for x in r['asks']]
        if not b or not a: continue
        mid=(b[0][0]+a[0][0])/2
        dl2=sum(p*z for p,z in b if (mid-p)/mid*1e4<=2)+sum(p*z for p,z in a if (p-mid)/mid*1e4<=2)
        reach=min((mid-b[-1][0])/mid*1e4,(a[-1][0]-mid)/mid*1e4)
        rows.append((pd.Timestamp(r['block_time_ms'],unit='ms'),mid,dl2,reach))
l2=pd.DataFrame(rows,columns=['ts','mid','dl2','reach_b'])
l2['t']=l2.ts.dt.floor('min')
print('L2 rows',len(l2),'reach bps median',l2.reach_b.median().round(2), 'dl2 nulls',l2.dl2.isna().sum())
# alignment: replay minute t (last block) vs L2 at t and t+1
for lag in [0,1]:
    j=m.merge(l2.assign(t=l2.t-pd.Timedelta(minutes=lag))[['t','mid']],on='t',suffixes=('','_l2'))
    print('lag',lag,'median |mid diff| bps',(abs(j.mid/j.mid_l2-1)*1e4).median().round(3),'n',len(j))
def build(df,col,win,midcol='mid'):
    df=df.copy(); df['r']=np.log(df[midcol]).diff()*1e4
    df.loc[df.t.diff()!=pd.Timedelta('1min'),'r']=np.nan
    df['rv']=df.r.rolling(win,min_periods=int(win*.8)).std()*np.sqrt(365*1440)/100
    dow=df.t.dt.day_of_week; h=df.t.dt.hour; mm=h*60+df.t.dt.minute
    wk=((dow==4)&(h>=21))|(dow==5)|((dow==6)&(h<22))|hol_mask(df.t)
    cash=(dow<5)&(mm>=810)&(mm<1200)&~wk&~df.t.dt.strftime('%Y-%m-%d').isin(WIN.NYSE_HOLIDAYS); closed=wk|((dow<4)&(h==21))
    df['g']=np.select([cash,closed],['cash','closed'],'overnight')
    df['hod']=h.astype(str)+np.where(wk,'w','d')
    df['rel']=np.log(df[col])-df.groupby('hod')[col].transform(lambda s: np.log(s).median())
    df['day']=df.t.dt.date; df['wk']=wk
    return df.dropna(subset=['rv','rel'])
def gaps(d,label):
    o=[]
    for g,gg in d.groupby('g'):
        q=pd.qcut(gg.rv.rank(method='first'),10,labels=False)
        a=gg.rel[q==9].median()-gg.rel[q==0].median()
        o.append(f"{g} {np.expm1(a)*100:+.1f}%")
    print(label,' | '.join(o))
base=build(m,'d10',15)
print(base.groupby('g').agg(n=('rv','size'),days=('day','nunique')))
gaps(base,'BASE d10 rv15        ')
for w in [5,30,60]: gaps(build(m,'d10',w),f'd10 rv{w}             ')
for c in ['d5','d25']: gaps(build(m,c,15),f'{c} rv15             ')
# independent depth (L2 within 2 bps) and independent mid (L2)
l2m=l2[['t','mid','dl2']].drop_duplicates('t').set_index('t').reindex(pd.date_range(m.t.min(),m.t.max(),freq='min')).rename_axis('t').reset_index()
gaps(build(l2m.dropna(subset=['mid']),'dl2',15),'L2 only: dl2 2bps, L2 vol')
# replay depth, L2-based vol (lagged one minute alignment-agnostic)
mm2=m.merge(l2m[['t','mid']].rename(columns={'mid':'midl2'}),on='t',how='left')
gaps(build(mm2.dropna(subset=['midl2']),'d10',15,'midl2'),'d10, vol from L2 mid ')
# exclude zero-vol minutes
b=base[base.rv>0]; gaps(b,'BASE excl rv=0       ')
print('rv==0 minutes by g',base[base.rv==0].groupby('g').size().to_dict())
# each weekend alone (closed, weekend only)
for k,gg in base[base.wk].groupby(base[base.wk].t.dt.isocalendar().week):
    q=pd.qcut(gg.rv.rank(method='first'),10,labels=False); a=gg.rel[q==9].median()-gg.rel[q==0].median()
    print('weekend iso-week',k,len(gg),f"{np.expm1(a)*100:+.1f}%")
bk=base[(base.g=='closed')&~base.wk]; q=pd.qcut(bk.rv.rank(method='first'),5,labels=False)
print('break hours only (quintiles)',len(bk),f"{np.expm1(bk.rel[q==4].median()-bk.rel[q==0].median())*100:+.1f}%")
# within each cash day
print('cash per day:',[f"{np.expm1(gg.rel[pd.qcut(gg.rv.rank(method='first'),5,labels=False)==4].median()-gg.rel[pd.qcut(gg.rv.rank(method='first'),5,labels=False)==0].median())*100:+.0f}" for _,gg in base[base.g=='cash'].groupby('day')])
# left panel numbers
hr=base.assign(hr=base.t.dt.floor('h')).groupby('hr').agg(d10=('d10','median'),rv=('rv','median'))
hr=hr[hr.rv>0]; print('hours',len(hr),'rho',np.corrcoef(np.log(hr.d10),np.log(hr.rv))[0,1].round(3))
print('session medians d10 $M',(base.groupby('g').d10.median()/1e6).round(2).to_dict(),'rv%',base.groupby('g').rv.median().round(2).to_dict())
