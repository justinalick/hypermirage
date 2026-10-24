"""@justinalick: the quant graphics kit for matplotlib. (Python cannot import "@", so the module is `justinalick`.)

The punk is the brand. Everything here is cut from it: the palette is its seven
pixels, the grid is its 24 px, the vape is the accent bar, the LED is the one
point a graphic is about.

Quick start
-----------
    import justinalick as ja

    fig, ax = ja.figure("wide", theme="night")            # one chart
    ja.line(ax, x, actual, "actual", label="actual")      # skin / ink
    ja.line(ax, x, model, "model", label="fair")          # slate
    ja.gap(ax, x, model, actual)                          # tint between them
    ja.end_label(ax, x, actual, "4.28% actual", "actual")
    ja.signal(ax, x[-1], actual[-1])                      # the LED, once
    ja.finish(fig, "xyz:JPY shorts overpay 3.3%/yr", hl="3.3%/yr",
              subtitle="USDC-settled USDJPY perp, Dec 2025 to Oct 2026",
              source="Data: Hyperliquid API")
    ja.save(fig, "post.png")

Layouts: ja.figure(size, theme, layout="single" | "stack" | "proof").
    "stack" returns (fig, {"top": ax, "bot": ax}).
    "proof" returns (fig, {"col": Column, "top": ax, "bot": ax}): a derivation
    column on the left and two stacked panels on the right.
Sizes (multiples of 24 px): wide 1536x864 (16:9), tall 1080x1344 (4:5), square 1080x1080.
Themes: night (default), paper, slate (hero cards only, see ja.card).
"""
from pathlib import Path
import textwrap

__version__ = 29   # kit version; ds_export stamps it into the Design System

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
for _f in (HERE / "fonts").glob("*.ttf"):
    font_manager.fontManager.addfont(str(_f))

SANS, MONO, PIXEL = "IBM Plex Sans", "IBM Plex Mono", "Silkscreen"

# The punk, pixel for pixel. Identity colors; never retint.
PUNK = dict(slate="#638596", skin="#DBB180", ink="#000000", grey="#595959",
            brow="#A66E2C", highlight="#F0D6B4", led="#0044FF")

# Themes. Roles, not hues: actual = what happened, model = what theory says,
# ref = a third series, signal = the one LED point, accent = the headline figure.
# tint_* are pre-mixed fills.
THEMES = {
    "night": dict(ground="#212E38", panel="#2A3945", ink="#F7F3EC", muted="#B8C6CE",
                  faint="#8A9BA5", grid="#2D3C47", axis="#3D4E5A", frame="#000000",
                  accent="#DBB180", actual="#DBB180", model="#6CA6D4", ref="#C08A4A", signal="#6B92FF",
                  tint_actual="#414444", tint_model="#2E4253", rod=PUNK["grey"]),
    "paper": dict(ground="#F3EEE6", panel="#FFFFFF", ink="#111111", muted="#4F5E66",
                  faint="#8A949A", grid="#E3DCD0", axis="#CFC6B8", frame="#000000",
                  accent="#8A5A22", actual="#111111", model="#3F6273", ref="#8A5A22", signal="#0044FF",
                  tint_actual="#DCD8D1", tint_model="#E1E0DA", rod=PUNK["grey"]),
    "slate": dict(ground=PUNK["slate"], panel="#57778A", ink="#000000", muted="#16232A",
                  faint="#2E434E", grid="#56778A", axis="#16232A", frame="#000000",
                  accent="#000000", actual="#000000", model=PUNK["highlight"], ref=PUNK["skin"], signal=PUNK["led"],
                  tint_actual="#557281", tint_model="#77909A", rod=PUNK["grey"]),
}
SIZES = {"wide": (1536, 864), "tall": (1080, 1344), "square": (1080, 1080), "story": (1080, 1920),
         "wide_tall": (1536, 1344)}   # wide_tall: desktop width with room for two stacked panels
DPI = 144          # 1 pt = 2 px, so a 24 px grid unit is 12 pt
U = 24             # the punk's grid
C = dict(THEMES["night"])
_state = {"theme": "night", "size": "wide"}


def _rc():
    plt.rcParams.update({
        "font.family": [MONO, SANS, "DejaVu Sans"],     # Plex Mono has no Greek: falls back to Plex Sans
        "font.size": 11,
        "mathtext.fontset": "custom", "mathtext.rm": SANS, "mathtext.it": f"{SANS}:italic",
        "mathtext.bf": f"{SANS}:semibold", "mathtext.sf": SANS, "mathtext.fallback": "stixsans",
        "axes.unicode_minus": True,
        "text.color": C["ink"], "axes.labelcolor": C["muted"],
        "xtick.color": C["muted"], "ytick.color": C["muted"],
        "xtick.labelsize": 10, "ytick.labelsize": 10,
        "xtick.major.size": 0, "ytick.major.size": 0, "xtick.major.pad": 8, "ytick.major.pad": 8,
        "axes.edgecolor": C["axis"], "axes.linewidth": 1, "axes.facecolor": C["ground"],
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": C["grid"], "grid.linewidth": 1,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "axes.axisbelow": True,
        "lines.linewidth": 2.5, "lines.solid_capstyle": "butt", "lines.solid_joinstyle": "miter",
        "legend.frameon": False, "legend.labelcolor": C["ink"], "legend.fontsize": 10,
        "legend.handlelength": 1.5, "legend.handleheight": 0.4,
        "axes.prop_cycle": plt.cycler(color=[C["actual"], C["model"], C["ref"]]),
        "figure.facecolor": C["ground"], "savefig.facecolor": C["ground"],
    })


def theme(name):
    """Switch the active theme (also done by figure())."""
    _state["theme"] = name
    C.clear(); C.update(THEMES[name]); _rc()
    return C


# ---------------------------------------------------------------- LaTeX equations
import hashlib, os, shutil, subprocess, tempfile
import numpy as np

TEX_PREAMBLE = r"\usepackage{amsmath,amssymb}"
_CACHE = Path(os.environ.get("JUSTINALICK_CACHE", Path(tempfile.gettempdir()) / "justinalick-tex"))
HAVE_LATEX = bool(shutil.which("pdflatex") and shutil.which("pdftoppm"))


def tex_image(expr, size=13, color=None, display=True):
    """Typeset `expr` (LaTeX math, no $) with pdflatex in Computer Modern and return an RGBA
    array at the kit's resolution (1 pt = 2 px), colored `color`. Cached by content."""
    from PIL import Image
    color = color or C["ink"]
    key = hashlib.sha1(f"{expr}|{size}|{display}|{TEX_PREAMBLE}".encode()).hexdigest()[:16]
    _CACHE.mkdir(parents=True, exist_ok=True)
    png = _CACHE / f"{key}.png"
    if not png.exists():
        body = rf"$\displaystyle {expr}$" if display else rf"${expr}$"
        doc = (r"\documentclass[border=2pt]{standalone}" + TEX_PREAMBLE + r"\begin{document}"
               + rf"\fontsize{{{size}}}{{{size * 1.2:.1f}}}\selectfont " + body + r"\end{document}")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "e.tex").write_text(doc)
            r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "e.tex"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                err = [l for l in r.stdout.splitlines() if l.startswith("!")]
                raise RuntimeError(f"LaTeX failed on {expr!r}: {err[:2]}")
            subprocess.run(["pdftoppm", "-r", str(DPI * 4), "-gray", "-png", "-singlefile", "e.pdf", "e"],
                           cwd=d, check=True)
            im = Image.open(Path(d) / "e.png").convert("L")
            im = im.resize((max(1, im.width // 4), max(1, im.height // 4)), Image.LANCZOS)
            im.save(png)
    g = np.asarray(Image.open(png).convert("L"), dtype=float) / 255.0
    rgb = matplotlib.colors.to_rgb(color)
    out = np.zeros(g.shape + (4,))
    out[..., :3] = rgb
    out[..., 3] = 1 - g
    return out


# ---------------------------------------------------------------- canvas
def _px_axes(fig, x, y, w, h):
    """Axes from a top-left pixel box."""
    W, H = fig.get_size_inches() * DPI
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])


class Column:
    """A text column for derivations, notes and results. Units are px from the top-left.
    Lines stack downward; every method returns the column so calls chain."""

    STEP, EQ, NOTE, RESULT = 11.5, 13, 10, 14

    def __init__(self, fig, x, y, w, h):
        self.fig, self.x, self.y0, self.y, self.w, self.h = fig, x, y, y, w, h
        self.W, self.H = fig.get_size_inches() * DPI
        self.r = fig.canvas.get_renderer()

    def _text(self, x, s, **kw):
        t = self.fig.text(x / self.W, 1 - self.y / self.H, s, va="top", **kw)
        self.y += t.get_window_extent(self.r).height
        return t

    def _wrap(self, text, maxw, **kw):
        probe = self.fig.text(0, 0, "", **kw)
        lines, cur = [], ""
        for word in text.split():
            trial = (cur + " " + word).strip()
            probe.set_text(trial)
            if probe.get_window_extent(self.r).width > maxw and cur:
                lines.append(cur); cur = word
            else:
                cur = trial
        lines.append(cur); probe.remove()
        return "\n".join(lines)

    def space(self, px=U / 2):
        self.y += px; return self

    def step(self, n, text):
        """Numbered step header: the number in mono, the move in sans."""
        if self.y > self.y0:
            self.space(U * 0.6)
        self.fig.text(self.x / self.W, 1 - (self.y + 1) / self.H, str(n), va="top", family=MONO,
                      fontsize=self.STEP, color=C["faint"], weight="medium")
        self._text(self.x + 24, text, family=SANS, fontsize=self.STEP, color=C["muted"], weight="medium")
        return self.space(6)

    def _img(self, arr, cx):
        """Place an RGBA array with its top at self.y, centered on x = cx (px)."""
        h, w = arr.shape[:2]
        self.fig.figimage(arr, xo=int(cx - w / 2), yo=int(self.H - self.y - h), origin="upper", zorder=3)
        self.y += h

    def eq(self, tex, size=None, indent=24, center=True):
        """One line of display math. With LaTeX installed it is typeset in Computer Modern and
        centered in the column (underbraces, \\dfrac, everything); otherwise mathtext in Plex Sans."""
        size = size or self.EQ
        if HAVE_LATEX:
            cx = self.x + indent + (self.w - indent) / 2 if center else None
            arr = tex_image(tex, size=size * 1.1)
            room = self.w - indent
            if arr.shape[1] > room:                     # never overflow: step down until it fits
                arr = tex_image(tex, size=size * 1.1 * room / arr.shape[1] * 0.98)
            self._img(arr, cx if center else self.x + indent + arr.shape[1] / 2)
        else:
            self._text(self.x + indent, f"${tex}$", fontsize=size, color=C["ink"])
        return self.space(6)

    def note(self, text, size=None, indent=24, color=None):
        """A sentence beside the math, wrapped to the column."""
        kw = dict(family=SANS, fontsize=size or self.NOTE)
        self._text(self.x + indent, self._wrap(text, self.w - indent, **kw), color=color or C["muted"],
                   linespacing=1.4, **kw)
        return self.space(4)

    def result(self, tex, caption=""):
        """The boxed result: panel fill, 4 px ink border, square. Ink, not a series color, so the box
        reads as the conclusion rather than part of a chart."""
        self.space(U * 0.6)
        top = self.y
        self.space(10)
        if HAVE_LATEX:
            self._img(tex_image(tex, size=self.RESULT * 1.1), self.x + self.w / 2)
        else:
            self._text(self.x + 20, f"${tex}$", fontsize=self.RESULT, color=C["ink"])
        if caption:
            self.space(8)
            t = self.fig.text((self.x + self.w / 2) / self.W, 1 - self.y / self.H, caption, va="top",
                              ha="center", family=SANS, fontsize=self.NOTE, color=C["muted"])
            self.y += t.get_window_extent(self.r).height
        self.space(12)
        self.fig.add_artist(Rectangle((self.x / self.W, 1 - self.y / self.H), self.w / self.W,
                                      (self.y - top) / self.H, transform=self.fig.transFigure,
                                      fc=C["panel"], ec=C[RESULT_BORDER], lw=4, zorder=0))
        return self

    def callout(self, label, text, role="ink", size=None):
        """A labeled paragraph ('fix', 'config'). The label is mono in the role color:
        ink for fix, faint for config. Never signal: the LED is the chart marker and the vape tip only."""
        size = size or self.NOTE
        self.space(U * 0.45)
        lab = self.fig.text(self.x / self.W, 1 - (self.y + 4) / self.H, label, va="top", family=MONO,  # +4: align mono cap height with sans
                            fontsize=size, color=C[role], weight="semibold")
        lw = 7 * size * 2 * 0.6                      # fixed 7-char label column keeps callouts aligned
        kw = dict(family=SANS, fontsize=size)
        self._text(self.x + lw, self._wrap(text, self.w - lw, **kw), color=C["ink"], linespacing=1.4, **kw)
        return self

    @property
    def bottom(self):
        return self.y


def figure(size="wide", theme_name="night", layout="single", theme=None):
    """New figure on the brand canvas.
    layout "single" -> (fig, ax); "stack" -> (fig, {top, bot}); "proof" -> (fig, {col, top, bot});
    "pair" -> (fig, {top, bot}): two panels with their own x axes, equal height, a 140 px gap for the
    top panel's ticks, an x caption (ja.x_caption) and the bottom panel title. Use on "wide_tall"."""
    globals()["theme"](theme or theme_name)
    _state["size"] = size
    w, h = SIZES[size]
    fig = plt.figure(figsize=(w / DPI, h / DPI), dpi=DPI, facecolor=C["ground"])
    top, bottom = 7 * U, 2 * U + 16            # header band (title + byline), footer band (source line)
    left, right = 2 * U + 40, 2 * U            # room for y tick labels
    if layout == "single":                    # leaves room for a panel title and an x label
        return fig, _px_axes(fig, left, top + 28, w - left - right, h - top - 28 - bottom - 72)
    if layout == "stack":
        avail = h - top - bottom - 24
        a = _px_axes(fig, left, top + 28, w - left - right, int(avail * 0.42) - 28)
        b = _px_axes(fig, left, top + int(avail * 0.42) + 56, w - left - right, int(avail * 0.58) - 56)
        a.tick_params(labelbottom=False)
        return fig, {"top": a, "bot": b}
    if layout == "proof":
        colw = int(w * 0.47)
        col = Column(fig, 2 * U, top - 8, colw - 2 * U, h - top - bottom + 8)
        x0 = colw + 2 * U + 40
        avail = h - top - bottom - 24
        a = _px_axes(fig, x0, top + 28, w - x0 - right, int(avail * 0.42) - 28)
        b = _px_axes(fig, x0, top + int(avail * 0.42) + 56, w - x0 - right, int(avail * 0.58) - 56)
        a.tick_params(labelbottom=False)
        return fig, {"col": col, "top": a, "bot": b}
    if layout == "pair":
        y0 = top + 48
        ph = (h - bottom - 96 - y0 - 140) // 2
        a = _px_axes(fig, left, y0, w - left - right, ph)
        b = _px_axes(fig, left, y0 + ph + 140, w - left - right, ph)
        return fig, {"top": a, "bot": b}
    raise ValueError(layout)


# ---------------------------------------------------------------- marks
def line(ax, x, y, role="actual", **kw):
    """A series in its role color. Roles: actual, model, ref."""
    kw.setdefault("lw", 2.5)
    return ax.plot(x, y, color=C[role], **kw)


def gap(ax, x, lo, hi, role="actual", where=None):
    """Fill between model and actual with the pre-mixed tint (no alpha mud)."""
    return ax.fill_between(x, lo, hi, color=C[f"tint_{role}"], lw=0, zorder=0.5, where=where,
                           interpolate=where is not None)


def zero(ax):
    ax.axhline(0, color=C["faint"], lw=1, zorder=1)


def _knockout():
    """Ground-colored backing so a label reads over fills, grids and lines."""
    return dict(boxstyle="square,pad=0.22", fc=C["ground"], ec="none")


def end_label(ax, x, y, text, role="actual", dy=10, bold=True, size=11):
    """Direct label at the last point, right-aligned inside the axes, on a knockout."""
    xs, ys = list(x), list(y)
    t = ax.annotate(text, (xs[-1], ys[-1]), xytext=(-10, dy), textcoords="offset points",
                    ha="right", color=C[role], fontsize=size, family=MONO,
                    weight="semibold" if bold else "regular", bbox=_knockout(), zorder=20)
    t._ja_label = True
    return t


def label_at(ax, x, y, text, role="actual", dy=-16, ha="center", size=11):
    """Direct label at a chosen point (when the series end is crowded), on a knockout."""
    t = ax.annotate(text, (x, y), xytext=(0, dy), textcoords="offset points", ha=ha,
                    color=C[role], fontsize=size, family=MONO, weight="semibold",
                    bbox=_knockout(), zorder=20)
    t._ja_label = True
    return t


def note_at(ax, x, y, text, role="ink", size=11):
    """A short in-chart note ("overpaid 2.6 pts"), centered, on a knockout."""
    t = ax.text(x, y, text, ha="center", va="center", color=C[role], fontsize=size, family=MONO,
                bbox=_knockout(), zorder=20)
    t._ja_label = True
    return t


def x_caption(ax, text, size=11):
    """Muted mono caption under the x tick labels, right-aligned (x units, scale)."""
    return ax.annotate(text, (1, 0), xycoords="axes fraction", xytext=(0, -24), textcoords="offset points",
                       ha="right", va="top", family=MONO, fontsize=size, color=C["muted"])


def panel_title(ax, text, size=11):
    """Small mono label above a panel, left-aligned, with units."""
    return ax.text(0, 1.035, text, transform=ax.transAxes, color=C["ink"], fontsize=size,
                   family=MONO, va="bottom")


def signal(ax, x, y, label=None, dx=12, dy=-26, size=11, ms=11, role="ink"):
    """The LED: one black-framed square on the point the post is about. Once per graphic.
    The label takes its series role color (role="actual" for an actual point), never the LED."""
    ax.plot([x], [y], marker="s", ms=ms, mfc=C["signal"], mec=PUNK["ink"], mew=1.5, zorder=10,
            clip_on=False)
    if label:
        t = ax.annotate(label, (x, y), xytext=(dx, dy), textcoords="offset points", color=C[role],
                        fontsize=size, family=MONO, weight="semibold", bbox=_knockout(), zorder=20)
        t._ja_label = True


def pixelate(ax, x, y, step=None, role="actual", lw=8):
    """Hero-only: draw a series as punk pixels (a staircase of flat bars). Never in analysis."""
    import numpy as np
    x, y = np.asarray(x, float), np.asarray(y, float)
    step = step or (y.max() - y.min()) / 12
    q = np.round(y / step) * step
    ax.step(x, q, where="mid", color=C[role], lw=lw, solid_capstyle="butt")


# ---------------------------------------------------------------- frame
def _badge(fig, x, y, px=48):
    img = plt.imread(str(HERE / "assets" / "punk-48.png"))
    fig.add_artist(AnnotationBbox(OffsetImage(img, zoom=px / 48 * 72 / DPI, interpolation="nearest"),
                                  (x, y), xycoords="figure pixels", frameon=False,
                                  box_alignment=(0, 0)))


def vape(fig, x, y_top, length=5 * U):
    """The vape bar: the punk's vape, in its exact pixels (grey #595959 rod, LED #0044FF tip) in every
    theme. 8 px tall. Under a title it runs the title's full width, so the LED lands on the last letter."""
    W, H = fig.get_size_inches() * DPI
    rod = max(length - 8, 8)
    fig.add_artist(Rectangle((x / W, 1 - (y_top + 8) / H), rod / W, 8 / H,
                             transform=fig.transFigure, color=PUNK["grey"], lw=0))
    fig.add_artist(Rectangle(((x + rod) / W, 1 - (y_top + 8) / H), 8 / W, 8 / H,
                             transform=fig.transFigure, color=PUNK["led"], lw=0))   # the punk's own LED, every theme


BYLINE_PX = 144         # the punk in the byline: 6 px per pixel, one grid unit (24 px) from the corner
BYLINE_MARGIN = U
RESULT_BORDER = "ink"    # result box border: neutral and boldest; never a series color

# Where to reach @justinalick: the same handle on both platforms, so graphics show the two
# official marks followed by "@justinalick" once. The URLs are kept here for docs and links.
# Marks live in assets/icons/ (<key>-<theme>.png, else <key>.png), taken unmodified from each
# platform's brand page; without a file the row falls back to a pixel key-cap ("X", "TG").
CONTACTS = [("x", "X", "x.com/justinalick"), ("telegram", "TG", "t.me/justinalick")]


def _marker(fig, key, label, x, yc, size=22):
    """One contact marker, left edge x, vertically centered on yc (figure px)."""
    W, H = fig.get_size_inches() * DPI
    icons = HERE / "assets" / "icons"
    icon = icons / f"{key}-{_state['theme']}.png"
    if not icon.exists():
        icon = icons / f"{key}.png"
    if icon.exists():
        img = plt.imread(str(icon))
        fig.add_artist(AnnotationBbox(OffsetImage(img, zoom=size / img.shape[0] * 72 / DPI),
                                      (x, yc - size / 2), xycoords="figure pixels", frameon=False,
                                      box_alignment=(0, 0)))
    else:
        fig.add_artist(Rectangle((x / W, (yc - size / 2) / H), size / W, size / H,
                                 transform=fig.transFigure, fc=C["ink"], ec="none"))
        fig.text((x + size / 2) / W, (yc - 0.5) / H, label, family=PIXEL, weight="bold",
                 fontsize=7 if len(label) > 1 else 9, color=C["ground"], ha="center", va="center")


def handle_row(fig, x, yc, align="right", size=14, icon=26, gap=8):
    """The contact line: X mark, Telegram mark, then @justinalick in Plex Mono SemiBold.
    One handle for both platforms, so it is written once. `x` is the right edge (align="right")
    or the left edge (align="left"); `yc` is the vertical center, both in figure px.
    Returns (left, right) of the row."""
    W, H = fig.get_size_inches() * DPI
    r = fig.canvas.get_renderer()
    probe = fig.text(0, 0, "@justinalick", fontsize=size, family=MONO, weight="semibold")
    tw = probe.get_window_extent(r).width; probe.remove()
    n = len(CONTACTS)
    total = n * icon + (n - 1) * gap + 12 + tw
    left = x - total if align == "right" else x
    for i, (key, label, _) in enumerate(CONTACTS):
        _marker(fig, key, label, left + i * (icon + gap), yc, size=icon)
    fig.text((left + n * icon + (n - 1) * gap + 12) / W, yc / H, "@justinalick", fontsize=size,
             family=MONO, weight="semibold", color=C["ink"], ha="left", va="center")
    return left, left + total


def byline(fig, corner="top-right", px=BYLINE_PX):
    """The contact line (X, Telegram, @justinalick) and the punk. Top-right by default: read
    right after the headline, and the corner that survives screenshots and crops.
    Returns the left edge of the block (px)."""
    W, H = fig.get_size_inches() * DPI
    if corner == "top-right":
        m = BYLINE_MARGIN
        x_img, y_img = W - m - px, H - m - px                    # figure px, bottom-left origin
        _badge(fig, x_img, y_img, px)
        left, _ = handle_row(fig, x_img - 20, y_img + px / 2)
        return left
    _badge(fig, 2 * U, U + 4, 48)                                     # legacy bottom-left badge
    handle_row(fig, 2 * U + 62, U + 28, align="left", size=12, icon=20)
    return W


def finish(fig, title, subtitle="", source="", hl=None, hl_role="accent", ax=None, corner="top-right"):
    """Header (title, optional highlighted figure, subtitle, vape bar), byline (punk + handle,
    top-right), source line (bottom-left) and the 4 px ink frame. `hl` is a substring of the
    title set in its role color. The title shrinks to stay clear of the byline."""
    W, H = fig.get_size_inches() * DPI
    r = fig.canvas.get_renderer()
    X, Y = 2 * U, 2 * U + 34
    limit = byline(fig, corner) - 2 * U - X
    size = 25

    def width(txt, fs):
        t = fig.text(0, 0, txt, fontsize=fs, family=SANS, weight="semibold")
        w_ = t.get_window_extent(r).width; t.remove(); return w_
    while width(title, size) > limit and size > 18:
        size -= 0.5
    space = width("a a", size) - width("aa", size)
    if hl and hl in title:
        a, b = title.split(hl, 1)
        x = X
        for part, col in ((a, C["ink"]), (hl, C[hl_role]), (b, C["ink"])):
            if not part:
                continue
            lead = space if part.startswith(" ") else 0
            fig.text((x + lead) / W, 1 - Y / H, part.strip(), fontsize=size, family=SANS,
                     weight="semibold", color=col, va="baseline")
            x += lead + width(part.strip(), size) + (space if part.endswith(" ") else 0)
    else:
        fig.text(X / W, 1 - Y / H, title, fontsize=size, family=SANS, weight="semibold",
                 color=C["ink"], va="baseline")
    if subtitle:
        fig.text(X / W, 1 - (Y + 34) / H, subtitle, fontsize=12.5, family=SANS, color=C["muted"],
                 va="baseline")
    vape(fig, X, Y + 52, length=width(title, size))          # full title width, LED on the last letter
    if source:
        sx, ha = (X, "left") if corner == "top-right" else (W - X, "right")
        fig.text(sx / W, (U + 4) / H, source, fontsize=10, family=MONO, color=C["muted"],
                 ha=ha, va="baseline")
    fig.add_artist(Rectangle((0, 0), 1, 1, transform=fig.transFigure, fill=False,
                             ec=C["frame"], lw=4, zorder=100))
    return fig


# ---------------------------------------------------------------- phone
PHONE = dict(title=34, subtitle=16, panel=16, tick=15, label=17, eq=18, result=20, note=15,
             step=16, source=13.5, handle=18, icon=34, punk=144)


class Phone:
    """Portrait 4:5 (1080 x 1344) for reading full screen in X and Telegram on a phone. Built top
    to bottom: header() -> chart() -> col (result, notes) -> footer(). The canvas shows at about
    1:1 device pixels on a phone, so nothing that carries information goes below 13.5 pt.

        P = ja.Phone("night")
        P.header("xyz:JPY shorts overpay 3.3%/yr in funding", hl="3.3%/yr", subtitle="...")
        ax = P.chart(420, "cumulative paid by shorts  % of notional")
        P.col.result(r"f=...", "f < 0 means shorts pay").callout("fix", "...")
        P.footer("Data: ..."); ja.save(P.fig, "phone.png")
    """

    def __init__(self, theme_name="night", size="tall"):
        theme(theme_name)
        self.W, self.H = SIZES[size]
        self.fig = plt.figure(figsize=(self.W / DPI, self.H / DPI), dpi=DPI, facecolor=C["ground"])
        self.r = self.fig.canvas.get_renderer()
        self.y = U                                   # cursor, px from top
        self.col = None

    def _w(self, txt, **kw):
        t = self.fig.text(0, 0, txt, **kw); w = t.get_window_extent(self.r).width; t.remove(); return w

    def header(self, title, hl=None, hl_role="accent", subtitle=""):
        """Byline row (marks, handle, punk) on top, then the title wrapped to full width, the
        subtitle, and the vape bar under the longest title line."""
        W, H, fig, X = self.W, self.H, self.fig, 2 * U
        px = PHONE["punk"]
        x_img, y_img = W - U - px, H - U - px
        _badge(fig, x_img, y_img, px)
        handle_row(fig, x_img - 24, y_img + px / 2, size=PHONE["handle"], icon=PHONE["icon"], gap=10)
        self.y = U + px + 20
        tk = dict(fontsize=PHONE["title"], family=SANS, weight="semibold")
        words = title.replace(hl, hl.replace(" ", "\0")).split() if hl else title.split()
        lines, cur = [], ""
        for w_ in words:
            trial = (cur + " " + w_).strip()
            if self._w(trial.replace("\0", " "), **tk) > W - 2 * X and cur:
                lines.append(cur); cur = w_
            else:
                cur = trial
        lines.append(cur)
        space = self._w("a a", **tk) - self._w("aa", **tk)
        widest = 0
        for ln in lines:
            ln = ln.replace("\0", " ")
            x = X
            segs = [(ln, C["ink"])]
            if hl and hl in ln:
                a_, b_ = ln.split(hl, 1)
                segs = [(a_, C["ink"]), (hl, C[hl_role]), (b_, C["ink"])]
            for part, col in segs:
                if not part:
                    continue
                lead = space if part.startswith(" ") else 0
                fig.text((x + lead) / W, 1 - self.y / H, part.strip(), color=col, va="top", **tk)
                x += lead + self._w(part.strip(), **tk) + (space if part.endswith(" ") else 0)
            widest = max(widest, x - X)
            self.y += PHONE["title"] * 2 * 1.18
        if subtitle:
            self.y += 6
            sk = dict(fontsize=PHONE["subtitle"], family=SANS)
            words, lines, cur = subtitle.split(), [], ""
            for w_ in words:
                trial = (cur + " " + w_).strip()
                if self._w(trial, **sk) > W - 2 * X and cur:
                    lines.append(cur); cur = w_
                else:
                    cur = trial
            lines.append(cur)
            t = fig.text(X / W, 1 - self.y / H, "\n".join(lines), color=C["muted"], va="top",
                         linespacing=1.3, **sk)
            self.y += t.get_window_extent(self.r).height
        self.y += 18
        vape(fig, X, self.y, length=widest)
        self.y += 8 + 32
        return self

    def chart(self, height, title=None, left=2 * U + 56):
        """An axes of `height` px at the cursor, with a panel title and phone-size ticks."""
        if title:
            self.fig.text(2 * U / self.W, 1 - self.y / self.H, title, family=MONO,
                          fontsize=PHONE["panel"], color=C["ink"], va="top")
            self.y += PHONE["panel"] * 2 + 14
        ax = _px_axes(self.fig, left, self.y, self.W - left - 2 * U, height)
        ax.tick_params(labelsize=PHONE["tick"])
        for line in ax.get_xticklabels() + ax.get_yticklabels():
            line.set_fontsize(PHONE["tick"])
        self.y += height + PHONE["tick"] * 2 + 28            # room for x tick labels
        self.column()
        return ax

    def column(self):
        """A full-width Column at the cursor with phone sizes (made by chart(); call directly
        for a derivation that comes before any chart)."""
        self.col = Column(self.fig, 2 * U, self.y, self.W - 4 * U, self.H - self.y - 3 * U)
        self.col.STEP, self.col.EQ, self.col.NOTE, self.col.RESULT = (PHONE["step"], PHONE["eq"],
                                                                     PHONE["note"], PHONE["result"])
        return self.col

    def rule(self, gap=U):
        """Hairline between sections; moves the cursor below the column if one is open."""
        if self.col is not None:
            self.y = self.col.y
        self.y += gap
        self.fig.add_artist(Rectangle((2 * U / self.W, 1 - self.y / self.H), (self.W - 4 * U) / self.W,
                                      1 / self.H, transform=self.fig.transFigure, fc=C["axis"], ec="none"))
        self.y += gap
        return self

    def footer(self, source=""):
        if source:
            self.fig.text(2 * U / self.W, (U + 4) / self.H, source, fontsize=PHONE["source"],
                          family=MONO, color=C["muted"], va="baseline")
        self.fig.add_artist(Rectangle((0, 0), 1, 1, transform=self.fig.transFigure, fill=False,
                                      ec=C["frame"], lw=4, zorder=100))
        return self.fig


def card(size="wide", kicker="", headline="", number="", number_role="accent", body="",
         source="", theme_name="slate"):
    """Hero card: thread covers, announcements, the one big number. The punk at full size."""
    theme(theme_name)
    w, h = SIZES[size]
    fig = plt.figure(figsize=(w / DPI, h / DPI), dpi=DPI, facecolor=C["ground"])
    W, H = w, h
    # the punk, 16 px per pixel when wide, flush to the bottom-right like the avatar crop
    side = {"wide": 16, "square": 12, "tall": 14}[size] * 24
    img = plt.imread(str(HERE / "assets" / "punk-24.png"))
    fig.add_artist(AnnotationBbox(OffsetImage(img, zoom=side / 24 * 72 / DPI, interpolation="nearest"),
                                  (W - 2 * U, 0), xycoords="figure pixels", frameon=False,
                                  box_alignment=(1, 0)))
    x = 2 * U
    if kicker:
        fig.text(x / W, 1 - 3 * U / H, kicker.upper(), family=PIXEL, fontsize=12, color=C["ink"],
                 va="baseline")
    if number:
        fig.text(x / W, 1 - (H * 0.50) / H, number, family=SANS, weight="semibold", fontsize=72,
                 color=C[number_role], va="baseline")
    if headline:
        chars = int((W - side - 5 * U) / (24 * 2 * 0.52))      # stay clear of the punk
        fig.text(x / W, 1 - (H * 0.50 + 64) / H, "\n".join(textwrap.wrap(headline, chars)), family=SANS,
                 weight="semibold", fontsize=24, color=C["ink"], va="top", linespacing=1.15)
    if body:
        fig.text(x / W, (4 * U + 16) / H, body, family=SANS, fontsize=12.5, color=C["muted"],
                 va="baseline")                                  # clears the contact line
    if kicker:                                                  # the kicker gets the same full-width bar
        kt = fig.text(0, 0, kicker.upper(), family=PIXEL, fontsize=12)
        kw_ = kt.get_window_extent(fig.canvas.get_renderer()).width; kt.remove()
        vape(fig, x, 3 * U + 16, length=kw_)
    handle_row(fig, x, 2 * U + 30, align="left")
    if source:
        fig.text(x / W, (U - 4) / H, source, fontsize=10, family=MONO, color=C["muted"],
                 va="baseline")
    fig.add_artist(Rectangle((0, 0), 1, 1, transform=fig.transFigure, fill=False,
                             ec=C["frame"], lw=4, zorder=100))
    return fig


def check(fig, strict=False):
    """Legibility check. Every direct label must clear every data line by 3 px and every other
    label. Returns a list of problems; save() prints them, or raises when strict=True."""
    import numpy as np
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    problems, boxes = [], []
    for ax in fig.axes:
        labels = [t for t in ax.texts if getattr(t, "_ja_label", False)]
        lines = [l for l in ax.get_lines() if l.get_linewidth() >= 1.5 and len(l.get_xdata()) > 1]
        for t in labels:
            bb = t.get_window_extent(r).expanded(1.0, 1.0).padded(3)
            boxes.append((t.get_text(), bb))
            for l in lines:
                xy = l.get_transform().transform_path(l.get_path()).vertices   # display px; handles dates
                xy = xy[np.isfinite(xy).all(axis=1)]
                if len(xy) < 2:
                    continue
                # densify segments so a line crossing the box between samples is caught
                fine = np.concatenate([np.linspace(xy[i], xy[i + 1], 6) for i in range(len(xy) - 1)])
                hit = (fine[:, 0] > bb.x0) & (fine[:, 0] < bb.x1) & (fine[:, 1] > bb.y0) & (fine[:, 1] < bb.y1)
                if hit.any():
                    problems.append(f"label '{t.get_text()}' crosses a data line")
                    break
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][1].overlaps(boxes[j][1]):
                problems.append(f"labels '{boxes[i][0]}' and '{boxes[j][0]}' overlap")
    if problems and strict:
        raise ValueError("legibility check failed: " + "; ".join(problems))
    return problems


def save(fig, path, strict=False):
    """Save at brand resolution after the legibility check (warnings printed; strict raises)."""
    for p_ in check(fig, strict=strict):
        print(f"[@justinalick check] {Path(str(path)).name}: {p_}")
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


theme("night")


# ---------------------------------------------------------------- profile assets
def x_avatar(path, px=400):
    """X / Telegram avatar: the punk at 16 px per pixel on its own slate, nearest-neighbor."""
    from PIL import Image
    src = Image.open(HERE / "assets" / "punk-24.png").convert("RGB")
    scale = px // 24
    big = src.resize((24 * scale, 24 * scale), Image.NEAREST)
    out = Image.new("RGB", (px, px), PUNK["slate"])
    out.paste(big, ((px - big.width) // 2, px - big.height))
    out.save(path)
    return path


def bot_avatar(path, px=1080):
    """@justinalick_bot avatar: the vape bar alone on the night ground. Never the punk: a bot
    wearing the punk reads as Justin himself in a chat list. The LED is the signal, and the bot is a
    signal channel. Rod 24 x 3 grid units with a 3-unit LED tip, centered; every edge on the 24 px grid."""
    from PIL import Image, ImageDraw
    if px % U:
        raise ValueError("bot_avatar px must be a multiple of the 24 px grid")
    out = Image.new("RGB", (px, px), THEMES["night"]["ground"])
    d = ImageDraw.Draw(out)
    w, h, tip = 24 * U, 3 * U, 3 * U
    x0, y0 = (px - w) // 2, (px - h) // 2
    d.rectangle([x0, y0, x0 + w - tip - 1, y0 + h - 1], fill=PUNK["grey"])
    d.rectangle([x0 + w - tip, y0, x0 + w - 1, y0 + h - 1], fill=PUNK["led"])
    out.save(path)
    return path


# The canary: 23 x 16 punk pixels, facing right, perched on the vape bar. Keys are punk tokens.
CANARY_KEY = {"K": "ink", "S": "skin", "H": "highlight", "B": "brow", "G": "grey", "L": "led"}
CANARY = (
    "..............KKKK.....",
    ".............KSSSSK....",
    "............KSSSSSSK...",
    "............KSSSSKSSK..",
    "...........KSSSSSSSSBBK",
    "..........KSSSSSSSSSKK.",
    "......KKKKSSSSSSSSSK...",
    ".....KSSSSSSSSSHHHHK...",
    "....KSBBBBBBSSSHHHHHK..",
    "...KSBBBBBBBBSSHHHHHK..",
    "..KBBKBBBBBBBSSHHHHK...",
    ".KBBK.KBBBBBSSSHHHK....",
    "KBBK....KKSSSSSSSK.....",
    "KKK.......KKKKKKK......",
    "............K.K........",
    "...GGGGGGGGGGGGGGGGGGL.",
)


def canary_avatar(path, px=1080):
    """Canary bot avatar: a pixel canary in punk colors perched on the vape bar, night ground.
    Not the punk, so it never reads as Justin; the perch keeps it in the bot family with
    bot_avatar. One sprite pixel = one 24 px grid unit, nearest-neighbor, centered on the grid.
    The punk palette has no yellow, so the bird is skin, highlight and brow (a gold canary)."""
    from PIL import Image, ImageDraw
    if px % U:
        raise ValueError("canary_avatar px must be a multiple of the 24 px grid")
    n, w, h = px // U, len(CANARY[0]), len(CANARY)
    if n < w + 8:
        raise ValueError("canary_avatar px too small to keep the bird inside Telegram's circle")
    out = Image.new("RGB", (px, px), THEMES["night"]["ground"])
    d = ImageDraw.Draw(out)
    x0, y0 = (n - w) // 2 * U, (n - h) // 2 * U
    for j, row in enumerate(CANARY):
        for i, c in enumerate(row):
            if c != ".":
                x, y = x0 + i * U, y0 + j * U
                d.rectangle([x, y, x + U - 1, y + U - 1], fill=PUNK[CANARY_KEY[c]])
    out.save(path)
    return path


def export_design_system(check=False):
    """Regenerate the Design System's kit-owned files into build/ds/ (see justinalick/ds_export.py)."""
    from . import ds_export
    return ds_export.export(check=check)


def x_header(path, theme_name="night"):
    """Legacy X header (superseded by x_header_tails, the live banner). 1500x500: dot grid, a pixel smile in skin, the LED at its minimum.
    The bottom-left is left clear for the avatar overlap."""
    import numpy as np
    theme(theme_name)
    W, H = 1500, 500
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=C["ground"])
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    g = np.arange(12, W, U); gy = np.arange(12, H, U)
    X, Y = np.meshgrid(g, gy)
    ax.scatter(X.ravel(), Y.ravel(), s=1.2, c=C["grid"], marker="s", lw=0)
    # pixel smile: an SVI-like curve quantized to the 24 px grid, drawn as flat bars
    x = np.arange(0, W + U, U)
    k = (x - W * 0.62) / W * 2.2
    y = 330 - 150 * (np.sqrt(k ** 2 + 0.03) - 0.17 + 0.35 * k * (k < 0) * -1)
    y = np.clip(np.round(y / U) * U, U * 3, H - U * 2)
    for xi, yi in zip(x, y):
        ax.add_patch(Rectangle((xi - U / 2, yi - 10), U, 20, color=C["actual"], lw=0))
    run = np.flatnonzero(y == y.max()); i = int(run[len(run) // 2])   # middle of the flat bottom
    ax.add_patch(Rectangle((x[i] - 12, y[i] - 12), 24, 24, fc=C["signal"], ec=PUNK["ink"], lw=2, zorder=5))
    fig.savefig(path, dpi=DPI, facecolor=C["ground"])
    plt.close(fig)
    return path


HEADER_TAILS = {   # ground, fat tail (dashed by default), normal (solid)
    "slate_led_tail": (PUNK["slate"], PUNK["led"], PUNK["ink"]),   # default and live banner: LED fat tail, ink normal; the LED marks the thesis
    "slate_led": (PUNK["slate"], PUNK["ink"], PUNK["led"]),       # vape LED for the normal
    "slate_skin_norm": (PUNK["slate"], PUNK["ink"], PUNK["skin"]),
    "black": ("#000000", PUNK["skin"], PUNK["slate"]),            # alternate: melts into X Lights Out
    "slate": (PUNK["slate"], PUNK["ink"], PUNK["highlight"]),     # alternate: ink fat tail, highlight normal
    "night": ("#212E38", PUNK["skin"], "#B8C6CE"),
    "ink":   ("#111A20", "#F7F3EC", PUNK["skin"]),
    "slate_skin": (PUNK["slate"], PUNK["highlight"], "#1E2A31"),
}

def x_header_tails(path, variant="slate_led_tail", contact=True, contact_pt=20, contact_icon=40,
                   fat_lw=4.0, normal_lw=2.6, fat_dashed=True, icons=False, corner="bottom-right",
                   shape="standard", vape_bar=True, base=360, top=180):
    """X header 1500x500: the standard normal (solid ink) against the standard Cauchy (dashed LED),
    both true densities with location 0 and scale 1, the textbook pair. The Cauchy peak is 80% of
    the normal's and its tails sit visibly above the flat normal at the edges. One scale factor maps
    density to px, so nothing is rescaled per curve. shape="peak" restores the old same-peak sketch."""
    import numpy as np
    ground, fat_c, norm_c = HEADER_TAILS[variant]
    theme("slate" if variant.startswith("slate") else "night")   # sets ink and the icon set for the ground
    W, H = 1500, 500
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=ground)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    x = np.linspace(0, W, 3001)
    if shape == "standard":
        z = (x - W / 2) / 165
        normal = np.exp(-z ** 2 / 2) / np.sqrt(2 * np.pi); fat = 1 / (np.pi * (1 + z ** 2))
        k = (base - top) / normal.max()                       # normal peak at y = top
        y_norm, y_fat = base - k * normal, base - k * fat
    else:
        z = (x - W / 2) / 160; base, amp = 400, 200
        y_norm, y_fat = base - amp * np.exp(-z ** 2 / 2), base - amp / (1 + (z / 0.95) ** 2)
    dlw = fat_lw if fat_dashed else normal_lw
    dash = dict(dashes=(9.8 / dlw, 7.8 / dlw))                # dash length fixed in pt, not scaled by weight
    solid = dict(solid_capstyle="butt")
    ax.plot(x, y_norm, color=norm_c, lw=normal_lw, **(solid if fat_dashed else dash))
    ax.plot(x, y_fat, color=fat_c, lw=fat_lw, **(dash if fat_dashed else solid))
    if contact:   # top-right contact line, sized to stay legible when X shrinks the banner on phones
        # X's phone app shows a 2.5:1 window (about 125 px cropped each side), puts the status bar over
        # the top 25% and two floating buttons at right, 40 to 62% down. Bottom-right inside the crop is
        # the one corner that is clear on phone and desktop.
        safe_right = W - 125 - U
        if corner == "bottom-right":
            xr, yc = safe_right, 62                           # yc from the bottom, figure px
        else:
            xr, yc = W - 2 * U, H - 2 * U - contact_icon / 2
        if icons:
            handle_row(fig, xr, yc, size=contact_pt, icon=contact_icon, gap=12)
        else:                          # handle only: the banner sits on X, so the marks add nothing
            t = fig.text(xr / W, yc / H, "@justinalick", fontsize=contact_pt,
                         family=MONO, weight="semibold", color=C["ink"], ha="right", va="center")
            if vape_bar:               # the title bar under the handle: full handle width, LED on the last letter
                bb = t.get_window_extent(fig.canvas.get_renderer())
                vape(fig, bb.x0, H - bb.y0 + 12, length=bb.width)
    fig.savefig(path, dpi=DPI, facecolor=ground)
    plt.close(fig)
    return path


# ---------------------------------------------------------------- reports
REPORT_PT = dict(tick=8, label=8.5, panel=8.5)   # placed at 100% in a 10 pt document


def report_figure(width_in=6.85, height_in=2.5, theme_name="paper", print_mode=False):
    """A chart for the PDF report class, drawn at the size it is placed (no scaling), so 8.5 pt
    labels print at 8.5 pt. Paper theme; print_mode=True uses a white ground to match the
    class's `print` option. Returns (fig, ax). Save with save_report_figure."""
    theme(theme_name)
    if print_mode:
        C["ground"] = "#FFFFFF"
    _rc()
    plt.rcParams.update({"xtick.labelsize": REPORT_PT["tick"], "ytick.labelsize": REPORT_PT["tick"],
                         "xtick.major.pad": 4, "ytick.major.pad": 4, "lines.linewidth": 1.4,
                         "grid.linewidth": 0.6, "axes.linewidth": 0.6, "pdf.fonttype": 42})
    fig = plt.figure(figsize=(width_in, height_in), dpi=DPI, facecolor=C["ground"])
    ax = fig.add_axes([0.06, 0.13, 0.92, 0.80], facecolor=C["ground"])
    return fig, ax


def save_report_figure(fig, path, strict=False):
    """Vector PDF (fonts embedded) for \\Figure in the report class. Runs the legibility check."""
    check(fig, strict=strict)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def build_report(tex_path):
    """Compile a report with XeLaTeX (twice, for page X of Y). Returns the PDF path."""
    import subprocess
    tex_path = Path(tex_path).resolve()
    for _ in range(2):
        r = subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
                           cwd=tex_path.parent, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stdout[-3000:])
    return tex_path.with_suffix(".pdf")
