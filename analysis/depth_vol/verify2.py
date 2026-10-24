exec(open('verify.py').read().split("print(base.groupby")[0])
c=base[base.g=='closed'].copy()
c['blk']=np.where(c.wk, 'wk'+c.t.dt.isocalendar().week.astype(str), 'break')
print(c.groupby('blk').agg(n=('rv','size'),rv=('rv','median'),d10M=('d10',lambda s:s.median()/1e6),rel=('rel','median')).round(3))
c['rel2']=c.rel-c.groupby('blk').rel.transform('median')
q=pd.qcut(c.rv.rank(method='first'),10,labels=False)
print('closed, demeaned by block: top vs bottom decile',f"{np.expm1(c.rel2[q==9].median()-c.rel2[q==0].median())*100:+.1f}%")
print('decile composition (share wk42) bottom/top', round((c.blk[q==0]=='wk42').mean(),2), round((c.blk[q==9]=='wk42').mean(),2))
for b,gg in c.groupby('blk'):
    q=pd.qcut(gg.rv.rank(method='first'),10,labels=False); print(b,'within-block decile gap',f"{np.expm1(gg.rel[q==9].median()-gg.rel[q==0].median())*100:+.1f}%")
# same for cash/overnight: demean by day
for g in ['cash','overnight']:
    x=base[base.g==g].copy(); x['rel2']=x.rel-x.groupby('day').rel.transform('median')
    q=pd.qcut(x.rv.rank(method='first'),10,labels=False)
    print(g,'demeaned by day',f"{np.expm1(x.rel2[q==9].median()-x.rel2[q==0].median())*100:+.1f}%")
