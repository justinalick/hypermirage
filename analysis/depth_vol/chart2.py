import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, FixedLocator, NullLocator
S='data/derived/depth_vol/'
dec=pd.read_parquet(S+'deciles2.parquet'); hr=pd.read_parquet(S+'hourly2.parquet')
SURF='#fcfcfb'; INK='#0b0b0b'; INK2='#52514e'; MUTE='#8a8984'; GRID='#e6e5e1'
COL={'cash':'#2a78d6','overnight':'#eb6834','closed':'#1baf7a'}
LAB={'cash':'US cash hours','overnight':'Overnight (futures open)','closed':'Futures closed (weekend; left also daily break)'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':13,'axes.edgecolor':GRID,'axes.labelcolor':INK2,
  'xtick.color':INK2,'ytick.color':INK2,'axes.facecolor':SURF,'figure.facecolor':SURF})
fig=plt.figure(figsize=(16,9),dpi=100)
axL=fig.add_axes([0.065,0.235,0.40,0.51]); axR=fig.add_axes([0.56,0.235,0.40,0.51])
xt=[1,2,5,10,20,40]
def xfmt(ax):
    ax.set_xscale('log'); ax.xaxis.set_major_locator(FixedLocator(xt)); ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v,_: f'{v:g}%')); ax.set_xlim(0.6,45)
    ax.set_xlabel('Realized volatility, trailing 15 min (annualized)')
    for s in ['top','right']: ax.spines[s].set_visible(False)
    ax.grid(True,color=GRID,lw=0.8); ax.set_axisbelow(True); ax.tick_params(length=0,pad=6)
# LEFT
h=hr[(hr.rv>0)]
for g in ['closed','overnight','cash']:
    x=h[h.g==g]; axL.scatter(x.rv,x.d10/1e6,s=46,color=COL[g],alpha=.85,edgecolor=SURF,lw=1.2,zorder=3)
b=np.polyfit(np.log(h.rv),np.log(h.d10),1); xx=np.geomspace(0.8,45,50)
axL.plot(xx,np.exp(np.polyval(b,np.log(xx)))/1e6,color=INK2,lw=2,ls=(0,(5,4)),zorder=4)
rho=np.corrcoef(np.log(h.rv),np.log(h.d10))[0,1]
axL.text(32,np.exp(np.polyval(b,np.log(32)))/1e6*1.22,f'all hours\nρ = {rho:+.2f}',color=INK2,ha='center',va='bottom',fontsize=12.5)
xfmt(axL); axL.set_yscale('log'); yt=[1,2,5,10,20,40]
axL.yaxis.set_major_locator(FixedLocator(yt)); axL.yaxis.set_minor_locator(NullLocator())
axL.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f'${v:g}M')); axL.set_ylim(0.8,50)
axL.set_ylabel('Depth within ±10 bps of mid (hourly median)')
axL.set_title('Across hours: busier hours are deeper',loc='left',color=INK,fontsize=15,fontweight='bold',pad=12)
# RIGHT
axR.axhline(0,color=MUTE,lw=1.2,zorder=2)
p=lambda v:(np.exp(v)-1)*100
for k,col,ls in [('cash',COL['cash'],'-'),('overnight',COL['overnight'],'-'),('W1009',COL['closed'],(0,(4,3))),('W1016',COL['closed'],'-')]:
    x=dec[dec.k==k].sort_values('q')
    if x.lo.notna().any(): axR.fill_between(x.rv,p(x.lo),p(x.hi),color=col,alpha=.10,lw=0,zorder=1)
    axR.plot(x.rv,p(x.rel),color=col,lw=2.4,ls=ls,zorder=3)
    axR.scatter(x.rv,p(x.rel),s=56,color=col,edgecolor=SURF,lw=2,zorder=4)
xfmt(axR); axR.set_xlim(0.45,45); axR.set_ylim(-22,38)
axR.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f'{v:+.0f}%' if v else '0%'))
axR.set_ylabel('Depth vs. the same day and hour of day')
axR.set_title('Within a day: no consistent drop',loc='left',color=INK,fontsize=15,fontweight='bold',pad=12)
axR.text(37,-5.5,'Cash hours: −4%',color=INK,fontsize=12,ha='right',va='top')
axR.text(17,10.5,'Overnight: +5%',color=INK,fontsize=12,ha='left',va='center')
axR.text(0.55,-13,'Weekend Oct 9–11 (dashed): −9%',color=INK,fontsize=12,ha='left',va='center')
axR.text(2.6,31,'Weekend Oct 16–18: −35%',color=INK,fontsize=12,ha='left',va='center')
# legend row
from matplotlib.lines import Line2D
hs=[Line2D([0],[0],marker='o',color=COL[g],lw=2.4,markersize=9,markeredgecolor=SURF) for g in ['cash','overnight','closed']]
fig.legend(hs,[LAB[g] for g in ['cash','overnight','closed']],loc='upper left',bbox_to_anchor=(0.06,0.845),ncol=3,frameon=False,fontsize=13,labelcolor=INK,handlelength=2.2,columnspacing=2.2)
fig.text(0.065,0.94,'Order book depth follows the clock, not volatility.',fontsize=23,fontweight='bold',color=INK)
fig.text(0.065,0.865,'Hyperliquid xyz:SP500 perp. Across hours, depth and volatility rise together because US trading hours have more of both.\nCompared within the same day and hour, the most volatile minutes carry about the same depth as the calmest. One of two weekends is the exception.',fontsize=13,color=INK2)
foot=('Sample: 20,160 one-minute book snapshots, 2026-10-08 to 2026-10-21 UTC (14 days: 10 weekdays, 2 weekends). Left: 336 hourly medians, colored by session at :30.\n'
 'Depth: displayed bid + ask notional within ±10 bps of mid, from an order-level book replay. Vol: std of 1-min log mid returns, trailing 15 min, annualized (24/7).\n'
 'Right: vol deciles within each session; depth relative to the median for the same UTC hour, then to that day (or weekend). Labels: top vs. bottom decile. Bands: 90% bootstrap over days.\n'
 'Futures closed: Fri 21:00 to Sun 22:00 UTC plus the Mon to Thu 21:00 hour (break hours, 480 min, are left out of the right panel).\n'
 'Source: Hydromancer Reservoir / node data.   @justinalick')
fig.text(0.065,0.02,foot,fontsize=10.5,color=INK2,va='bottom',linespacing=1.5)
fig.text(0.96,0.94,'Source: Hydromancer Reservoir / node data   @justinalick',fontsize=10.5,color=INK2,ha='right',va='bottom',alpha=0)
fig.savefig(S+'depth_vs_vol_v2.png',dpi=100,facecolor=SURF); fig.savefig(S+'depth_vs_vol_v2@2x.png',dpi=200,facecolor=SURF)
fig.savefig(S+'depth_vs_vol_v2.png',dpi=100,facecolor=SURF); fig.savefig(S+'depth_vs_vol_v2@2x.png',dpi=200,facecolor=SURF)
