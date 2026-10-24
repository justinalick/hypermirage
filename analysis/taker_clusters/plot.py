import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
D = "data/derived/taker_clusters"
r = json.load(open(f"{D}/mk_res.json"))
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
C1, C2, C3 = "#2a78d6", "#eb6834", "#8a8984"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "text.parse_math": False, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF})
fig, ax = plt.subplots(1, 3, figsize=(16, 6.2), dpi=180, gridspec_kw={"width_ratios": [1, 1.15, 1.25]})
fig.subplots_adjust(left=0.05, right=0.985, top=0.78, bottom=0.2, wspace=0.28)
for a in ax:
    for s in ("top", "right"): a.spines[s].set_visible(False)
    a.grid(axis="y", color=GRID, lw=0.8); a.set_axisbelow(True)
H = ["0", "1", "10", "60"]; xl = ["fill", "1s", "10s", "60s"]; x = range(4)
cl = r["clusters"]
def curve(a, d, c, lab, ls="-"):
    m = [d[h][0] for h in H]
    a.fill_between(x, [d[h][1] for h in H], [d[h][2] for h in H], color=c, alpha=0.15, lw=0)
    a.plot(x, m, color=c, lw=2, ls=ls, marker="o", ms=5, label=lab)
a = ax[0]; a.axhline(0, color=INK2, lw=1)
curve(a, cl["T1"], C1, f"Largest taker, T1 ({cl['T1']['n']:,} fills, ${cl['T1']['notional']/1e6:,.0f}M)")
curve(a, cl["All except T1"], C2, f"All other takers ({cl['All except T1']['n']:,} fills, ${cl['All except T1']['notional']/1e6:,.0f}M)")
a.set_xticks(list(x), xl); a.set_xlabel("Time after fill"); a.set_ylabel("Taker markout, bps (maker = minus this)")
a.set_title("T1 flow moves the mid its way", loc="left", fontsize=12, color=INK)
a.legend(frameon=False, loc="lower right", fontsize=8.8, labelcolor=INK2)
# panel 2: top 10 clusters at 10s and 60s
a = ax[1]; a.axhline(0, color=INK2, lw=1)
ks = [f"T{i}" for i in range(1, 11)] + ["T11+ (rest)"]
for j, (h, c, off) in enumerate([("10", C1, -0.17), ("60", C2, 0.17)]):
    for i, k in enumerate(ks):
        d = cl[k][h]; a.plot([i+off]*2, [d[1], d[2]], color=c, lw=2, alpha=0.5)
        a.plot(i+off, d[0], "o", color=c, ms=6, mec=SURF, mew=1.5, label=f"{h}s" if i == 0 else None)
a.set_xticks(range(len(ks)), [k.replace(" (rest)", "") + f"\n{cl[k]['notional']/1e6:,.0f}M" for k in ks], fontsize=8.5)
a.set_xlabel("Taker cluster by taker notional ($), sub-accounts under master")
a.set_title("Per dollar, T1 is not the most adverse taker", loc="left", fontsize=12, color=INK)
a.legend(frameon=False, loc="upper right", fontsize=9, labelcolor=INK2)
# panel 3: T1 share of taker notional by UTC hour, Mon-Fri
a = ax[2]
t1, ot = r["T1_by_utc_hour_weekday"], r["oth_by_utc_hour_weekday"]
sh = [100*t1[h]/(t1[h]+ot[h]) for h in range(24)]
a.axvspan(13.5-0.5, 19.5+0.5, color=C3, alpha=0.08, lw=0)
a.text(16.5, 49.5, "US cash hours", ha="center", fontsize=8.5, color=INK2)
a.bar(range(24), sh, color=[C2 if h == 21 else C1 for h in range(24)], width=0.8)
a.annotate("21 UTC: CME break\n(and Fri close)", (21, sh[21]), (21.6, 45.5), ha="center", fontsize=8.5, color=INK2,
    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
a.set_ylim(0, 52); a.set_xticks(range(0, 24, 3)); a.set_xlabel("UTC hour, Mon to Fri"); a.set_ylabel("T1 share of taker notional, %")
s = r["sessions"]
a.set_title("T1's share of taker volume falls when CME ES is shut", loc="left", fontsize=12, color=INK)
fig.text(0.05, 0.015, f"T1 share by ES state: cash hours {100*s['Cash hours']['T1_share']:.0f}% ({s['Cash hours']['hours']} h), "
       f"ES overnight {100*s['ES overnight']['T1_share']:.0f}% ({s['ES overnight']['hours']} h), "
       f"ES closed {100*s['ES closed']['T1_share']:.0f}% ({s['ES closed']['hours']} h)" + ". T1 pays a lower taker fee than the others (charts/taker_markouts.py).", fontsize=8.5, color=INK2)
m = r["meta"]
fig.text(0.05, 0.93, "xyz:SP500 taker markouts by taker cluster", fontsize=16, weight="bold", color=INK)
fig.text(0.05, 0.875, f"2026-10-08 to 2026-10-21 UTC, {m['n']:,} taker fills, ${m['notional']/1e9:.2f}B taker notional, {m['hours']} hours. "
         "Notional-weighted vs block-replayed mid. 95% CI: bootstrap over 1-hour blocks. Gross of fees. ", fontsize=9.5, color=INK2)
fig.text(0.05, 0.05, f"Cluster = sub-accounts grouped under their master (Hyperliquid API). T1 is {100*m['T1_share']:.0f}% of taker notional. "
         "ES closed = weekends + 21-22 UTC daily break (EDT). Source: Hydromancer Reservoir / node data.", fontsize=8.5, color=INK2)
fig.savefig(f"{D}/sp500_taker_clusters.png")
