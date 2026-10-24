"""Cancel reaction of resting near-touch orders to touch moves, xyz:SP500 (sweep-line version).
Event at block t: the OPPOSITE best price moves toward the order (adverse: best ask falls for a bid,
best bid rises for an ask) or away (favorable), with no other best-price change in the 5 blocks before.
Control: random blocks with no best-price change in the 5 blocks before. Exposed orders: open since
<= t-1, still live after t, priced from the own-side best at t-1 to 1 bp behind it.
Outcome: order pulled (cancelled, with or without a partial fill) at block t+k, 1 <= k <= 100. Moves sampled at 30% per day."""
import sys, collections, duckdb, numpy as np, pandas as pd
ROOT = "."
TICK = 0.1
con = duckdb.connect(); con.execute("SET threads=2; SET memory_limit='3GB'")
rng = np.random.default_rng(7)
rows = []
for d in sys.argv[1:]:
    l1 = con.execute(f"SELECT block, bid_px, ask_px FROM '{ROOT}/data/derived/ofi/l1/{d}.parquet' ORDER BY block").df()
    ch = (l1.bid_px.diff() != 0) | (l1.ask_px.diff() != 0)
    px = l1[ch.values].reset_index(drop=True)
    pb, pa = px.bid_px.shift(), px.ask_px.shift()
    gap = px.block.diff()
    ev = []
    for i in np.where((gap > 5).values)[0]:
        if rng.random() > 0.3: continue
        t = int(px.block[i])
        if px.ask_px[i] != pa[i]:
            ev.append((t, "B", "adverse" if px.ask_px[i] < pa[i] else "favorable", min(round(abs(px.ask_px[i]-pa[i])/TICK), 3) if np.isfinite(px.ask_px[i]-pa[i]) else np.nan, pb[i]))
        if px.bid_px[i] != pb[i]:
            ev.append((t, "A", "adverse" if px.bid_px[i] > pb[i] else "favorable", min(round(abs(px.bid_px[i]-pb[i])/TICK), 3) if np.isfinite(px.bid_px[i]-pb[i]) else np.nan, pa[i]))
    # controls: random blocks whose last best-price change is > 5 blocks earlier
    b0, b1 = int(px.block.iloc[1]), int(px.block.iloc[-1])
    ct = rng.integers(b0, b1, 60000)
    j = np.searchsorted(px.block.values, ct, side="right") - 1
    ok = (ct - px.block.values[j]) > 5
    for t, jj in zip(ct[ok], j[ok]):
        side = "B" if rng.random() < 0.5 else "A"
        ev.append((int(t), side, "control", 0, px.bid_px[jj] if side == "B" else px.ask_px[jj]))
    ev = [e for e in ev if np.isfinite(e[4]) and np.isfinite(e[3])]
    ev.sort()
    o = con.execute(f"""SELECT side, limit_px, b_open, b_last, (class IN ('displayed_pulled','displayed_partial')) pulled
      FROM '{ROOT}/data/derived/lifecycle_touch/xyz_SP500/{d}.parquet'
      WHERE class IN ('displayed_pulled','displayed_partial','filled') AND displayed_blocks>0""").df()
    o["tk"] = np.round(o.limit_px / TICK).astype(np.int64)
    opens = o.sort_values("b_open")[["b_open", "b_last", "side", "tk", "pulled"]].to_numpy()
    closes = o.sort_values("b_last")[["b_last", "side", "tk"]].to_numpy()
    act = {"B": collections.defaultdict(list), "A": collections.defaultdict(list)}   # tick -> [(b_last, pulled)]
    cnt = collections.Counter()
    io = 0
    for t, side, kind, mv, best in ev:
        # add orders with b_open <= t-1
        while io < len(opens) and opens[io][0] <= t - 1:
            bo, bl, s, tk, pl = opens[io]
            act[s][tk].append((bl, pl)); io += 1
        bt = int(round(best / TICK)); w = int(np.ceil(best * 1e-4 / TICK))
        rngt = range(bt - w, bt + 1) if side == "B" else range(bt, bt + w + 1)
        for tk in rngt:
            lst = act[side].get(tk)
            if not lst: continue
            keep = [x for x in lst if x[0] > t]          # lazy removal of closed orders
            if len(keep) != len(lst): act[side][tk] = keep
            for bl, pl in keep:
                kk = bl - t
                cnt[(kind, mv, int(kk) if (pl and kk <= 100) else -1)] += 1
    for (kind, mv, kk), n in cnt.items():
        rows.append((d, kind, mv, kk if kk > 0 else None, n))
    print(d, len(ev), sum(cnt.values()), flush=True)
pd.DataFrame(rows, columns=["day", "ev", "mv", "k", "n"]).to_parquet(f"{ROOT}/data/derived/cancels/latency.parquet")
