"""Link preview (og:image / twitter summary_large_image) for the public xyz:SP500 atlas page.
1200 x 630, night theme, so the unfurled link matches the atlas and the post images.
Run: .venv/bin/python charts/og_card.py"""
import sys, textwrap, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "charts")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Rectangle
import justinalick as ja

W, H, U, DPI = 1200, 630, ja.U, ja.DPI
ja.theme("night")
C = ja.C
fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=C["ground"])
r = fig.canvas.get_renderer()
px = lambda x, y: (x / W, 1 - y / H)            # top-left pixel coordinates

# the punk on its own slate, 10 px per source pixel, bottom-right
side = 240
img = plt.imread(str(ja.HERE / "assets" / "punk-24.png"))
fig.add_artist(AnnotationBbox(OffsetImage(img, zoom=side / 24 * 72 / DPI, interpolation="nearest"),
                              (W - 2 * U, 2 * U), xycoords="figure pixels", frameon=False,
                              box_alignment=(1, 0)))

x = 2 * U
kicker = "HYPERMIRAGE"
fig.text(*px(x, 3 * U), kicker, family=ja.PIXEL, fontsize=12, color=C["muted"], va="baseline")
kt = fig.text(0, 0, kicker, family=ja.PIXEL, fontsize=12); kw = kt.get_window_extent(r).width; kt.remove()
ja.vape(fig, x, 3 * U + 14, length=kw)

# headline: the question, "a mirage?" in the accent, wrapped clear of the punk
y0, lh = 6 * U + 30, 64
for i, ln in enumerate(["Is liquidity on", "Hyperliquid's SP500", "perp "]):
    a = fig.text(*px(x, y0 + i * lh), ln, family=ja.SANS, weight="semibold", fontsize=27, color=C["ink"], va="baseline")
aw = a.get_window_extent(r).width
fig.text(*px(x + aw, y0 + 2 * lh), "a mirage?", family=ja.SANS, weight="semibold", fontsize=27,
         color=C["accent"], va="baseline")

# numbers from the run's outputs: orders in the survival sample, metaorder impact vs the book (as in charts/impact.py)
import json, pandas as pd
sys.path.insert(0, "scripts")
import window as WIN
n_orders = json.load(open("data/derived/chart_cache/survival.json"))["meta"]["n"]
cmp = pd.DataFrame(json.load(open("data/derived/impact/robust.json"))["dollar_cmp"])
cmp = cmp[(cmp.Q <= 1.01e6) & (cmp.Q >= 1e3)]; ratio = cmp.obs_meta_i0 / cmp.book_mean
r_lo, r_small = ratio[cmp.Q >= 1e4].min(), ratio[cmp.Q <= 1.01e4].median()
fig.text(*px(x, y0 + 3 * lh - 8), f"Partly. Metaorders move price about {round(r_lo)} to {round(r_small)}x more than the book implies.",
         family=ja.SANS, fontsize=13, color=C["muted"], va="baseline")
fig.text(*px(x, y0 + 3 * lh + 28), f"xyz:SP500  ·  {n_orders / 1e6:.0f}M orders  ·  {WIN.label()}",
         family=ja.MONO, fontsize=10.5, color=C["faint"], va="baseline")
ja.handle_row(fig, x, H - (y0 + 3 * lh + 84), align="left")   # above the domain label X overlays bottom-left
fig.add_artist(Rectangle((0, 0), 1, 1, transform=fig.transFigure, fill=False, ec=C["frame"], lw=4, zorder=100))
fig.savefig("out/og-xyz-sp500-v4.png" if WIN.IS_ATLAS else f"out/og-xyz-sp500-{WIN.DAYS[0]}-{WIN.DAYS[-1]}.png", dpi=DPI, facecolor=C["ground"])
