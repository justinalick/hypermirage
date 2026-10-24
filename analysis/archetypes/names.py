"""Plain-language cluster names and coarse groups from each cluster's median raw features."""
import pandas as pd
def name_clusters(f, lab):
    f = f.assign(cl=lab); g = f[f.cl >= 0].groupby('cl')
    m = g.median(numeric_only=True); tw = g.twap_share.mean()
    names, grp = {}, {}
    for c, r in m.iterrows():
        if r.alo_share > 0.5 and r.maker_share > 0.5:
            names[c] = f"Post-only makers (ALO quotes, {r.med_rest_s:.0f} s median rest)"; grp[c] = 'maker'; continue
        ui = r.builder_share > 0.5
        tags = []
        if tw[c] > 0.3: tags.append("TWAP orders")
        if r.net_flow_ratio > 0.5: tags.append("one-way (net buyers or sellers)")
        if r.med_rest_s > 1000: tags.append("long-resting orders far from touch")
        if r.frontend_share > 0.5: tags.append("front-end market orders")
        if r.trigger_share > 0.3: tags.append("stop / take-profit")
        if r.maker_share > 0.2: tags.append("some making")
        if r.weekend_share > 0.5: tags.append("weekend")
        elif r.cash_share > 0.45: tags.append("US cash hours")
        if r.days_active >= 12: tags.append("daily")
        if r.med_order_usd > 10000: tags.append("large orders")
        elif r.med_order_usd < 300: tags.append("small orders")
        if r.turnover > 120: tags.append("high turnover")
        names[c] = ("Builder takers" if ui else "API takers") + (", " + ", ".join(tags[:3]) if tags else "")
        grp[c] = 'ui' if ui else 'api'
    return names, grp
