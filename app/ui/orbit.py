"""Orbit: the picker shown when you tap the shortcut.

Tools circle on one orbit and formats on the other. Point at one and the
drift stops, the option leans toward the pointer, and a small card on the
side says what it does. Holds up to ~20 options before adding a "More" planet,
so new tools and converters can keep joining without a redesign.

Built to stay smooth on low-end laptops:
- planets, hub, orbits and the side card are drawn once into pixmaps, so a
  frame is a handful of blits;
- the frame clock runs only while something moves (60 fps for motion, 30 fps
  for the slow idle drift) and stops completely when everything is still;
- motion is time-based, so a late frame never makes anything jump or crawl;
- Windows' "Show animations" setting (Accessibility) turns the motion off.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ..catalog import Offer
from . import theme
from .fx import display_family

# ---------------------------------------------------------------- what each option does (short on purpose)

BLURBS = {
    "compress.image": "Pick a size, see the quality first",
    "image.jpg": "Smaller photo that opens anywhere",
    "image.png": "Lossless, keeps transparency",
    "image.webp": "Small and sharp, made for the web",
    "image.pdf": "One page per picture",
    "image.pdf_combined": "All the pictures in one PDF",
    "image.heic": "Small files, full photo quality",
    "image.avif": "The smallest modern photo format",
    "image.ico": "A Windows icon, 16 to 256 px",
    "image.tiff": "Lossless, for print and archives",
    "image.gif": "Simple animation, 256 colors",
    "image.bmp": "Plain, uncompressed bitmap",
    "image.tga": "Uncompressed, for games and 3D",
    "ocr.txt": "Copy the words out of a picture or scan",
    "ocr.pdf": "Make a scan searchable",
    "archive.zip": "Pack everything into one .zip",
    "archive.extract": "Unpack into a new folder",
    "archive.tozip": "Repack as a standard ZIP",
    "pdf.compress": "Smaller PDF, same pages",
    "pdf.pages": "Keep or remove pages",
    "pdf.lock": "Needs a password to open",
    "pdf.unlock": "Removes the password",
    "pdf.numbers": "Numbers on every page",
    "pdf.watermark": "Text stamped on every page",
    "pdf.rotate": "Turn pages the right way up",
    "pdf.merge": "Join the PDFs in folder order",
    "pdf.png": "Each page as a PNG image",
    "pdf.jpg": "Each page as a JPG image",
    "pdf.txt": "All the text, without layout",
    "pdf.split": "One PDF per page",
    "doc.pdf": "Looks exactly like it does in Office",
    "doc.docx": "Modern Word document",
    "doc.doc": "Older Word, for older apps",
    "doc.odt": "OpenDocument, for LibreOffice",
    "doc.rtf": "Simple formatted text",
    "doc.txt": "Just the words",
    "doc.xlsx": "Modern Excel workbook",
    "doc.xls": "Older Excel, for older apps",
    "doc.csv": "First sheet as plain values",
    "doc.ods": "OpenDocument spreadsheet",
    "doc.pptx": "Modern PowerPoint",
    "doc.ppt": "Older PowerPoint",
    "doc.odp": "OpenDocument slides",
    "doc.png": "Each slide as a PNG image",
    "doc.jpg": "Each slide as a JPG image",
    "data.xlsx": "Opens straight in Excel",
    "data.json": "Rows as a list of records",
    "data.csv": "A table that opens anywhere",
    "data.tidy": "Indented and easy to read",
    "data.minify": "Smallest, without spaces",
    "textdoc.pdf": "A clean A4 document",
    "textdoc.html": "A web page",
    "textdoc.docx": "Edit it in Word",
}

TOOL_ENGINES = {"compress", "archive", "ocr"}


def is_tool(o: Offer) -> bool:
    t = o.target
    return t.engine in TOOL_ENGINES or bool(t.suffix) or t.ask or t.combine or t.key == "pdf.split"


def blurb(o: Offer) -> str:
    return BLURBS.get(o.target.key) or f"Save as {o.target.label}"


def out_name(o: Offer) -> str:
    """The name the new file (or folder) will get, for the side card."""
    if not o.sources:
        return ""
    t, src, n = o.target, o.sources[0], len(o.sources)
    if t.folder:
        return f"{src.stem} ({t.folder})"
    try:
        from ..toolbox import output_ext

        ext = output_ext(t, src, {op.key: op.default for op in o.options})
    except Exception:
        ext = t.ext if t.ext != "*" else src.suffix
    if t.combine:
        stem = f"{src.stem} and {n - 1} more" if n > 1 else src.stem
        return stem + t.suffix + ext
    name = src.stem + t.suffix + ext
    return name + (f"  +{n - 1} more" if n > 1 else "")


CAUTIONS = ("become white", "become hard", "scaled down", "padded", "only the text", "can't be recovered",
            "dithered", " lost", "removed", "not kept")


def real_warning(o: Offer) -> str:
    """The first note that is a real caution (something is lost or can't be undone).
    Plain notes like "uses the first row as field names" don't get the amber dot."""
    import re

    for w in o.warnings:
        for sentence in re.split(r"(?<=[.!?])\s+", w):
            if any(c in sentence.lower() for c in CAUTIONS):
                return sentence  # just the cautionary sentence, not the whole note
    return ""


def animations_enabled() -> bool:
    """Windows' Settings > Accessibility > Visual effects > Animation effects."""
    try:
        import ctypes

        v = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(v), 0):  # SPI_GETCLIENTAREAANIMATION
            return bool(v.value)
    except Exception:
        pass
    return True


# ---------------------------------------------------------------- springs

class Spring:
    """A damped spring toward ``t``. ``step`` returns True while it is still moving."""

    __slots__ = ("v", "t", "vel")

    def __init__(self, v: float):
        self.v = self.t = float(v)
        self.vel = 0.0

    def snap(self, v: float | None = None) -> None:
        if v is not None:
            self.t = v
        self.v, self.vel = self.t, 0.0

    def step(self, dt: float, k: float, d: float, motion: bool = True) -> bool:
        if not motion:
            moved = self.v != self.t
            self.v, self.vel = self.t, 0.0
            return moved
        if abs(self.t - self.v) < 1e-3 and abs(self.vel) < 1e-3:
            self.v, self.vel = self.t, 0.0
            return False
        n = int(dt / 0.008) + 1  # sub-steps keep stiff springs stable on slow frames
        h = dt / n
        for _ in range(n):
            self.vel += (k * (self.t - self.v) - d * self.vel) * h
            self.v += self.vel * h
        return True


class _Planet:
    __slots__ = ("r", "sw", "s", "a", "mx", "my", "delay", "ring", "base", "x", "y", "hx", "hy", "ang")

    def __init__(self, ring: int, base: float, delay: float):
        self.ring, self.base, self.delay = ring, base, delay
        self.r, self.sw, self.s, self.a = Spring(0), Spring(140), Spring(0.4), Spring(0)
        self.mx, self.my = Spring(0), Spring(0)
        self.x = self.y = self.hx = self.hy = self.ang = 0.0


def _font(px: float, weight=QFont.Weight.Normal, display=False, mono=False) -> QFont:
    if mono:
        f = QFont("Cascadia Mono")
        f.setStyleHint(QFont.StyleHint.Monospace)
        if not QFontMetrics(f).inFont("a"):
            f = QFont("Consolas")
    else:
        f = QFont(display_family() if display else theme.FONT)
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(weight)
    return f


def warm_fonts() -> None:
    """Load the picker's fonts once, at startup: the first text drawn in a new
    font costs ~25 ms, which would otherwise land on the first hover."""
    pm = QPixmap(8, 8)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    for f in (_font(12, QFont.Weight.DemiBold, display=True), _font(19, QFont.Weight.Bold, display=True),
              _font(12.5), _font(11), _font(11, mono=True), _font(9.5, QFont.Weight.Bold, mono=True),
              _font(10.5, QFont.Weight.DemiBold)):
        p.setFont(f)
        p.drawText(0, 6, "Ag→1")
        QFontMetrics(f).horizontalAdvance("Ag→1")
    p.end()


def _alpha(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlphaF(max(0.0, min(1.0, a)))
    return out


# ---------------------------------------------------------------- the widget

class OrbitView(QWidget):
    activated = Signal(int)  # index into self.items
    options_requested = Signal(int)
    hovered = Signal(int)  # -1 = none

    MAX_SCALE = 1.16
    DRIFT_SECONDS = 6.0

    def __init__(self, offers: list[Offer], center_title: str, card_side: str = "right", scale: float = 1.0,
                 parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)  # we paint every pixel: parents can skip
        self.motion = animations_enabled()
        self.center_title = center_title
        self.side = card_side
        k = scale
        self.D, self.HUB, self.GAP = 72 * k, 108 * k, 14 * k
        self.CARD_W, self.CARD_GAP = round(218 * k + 10 * (1 - k)), round(22 * k)
        self._layout(list(offers))
        self.hover = -1
        self.inside = False
        self.kbd = False
        self._exit: dict | None = None
        self._t = 0.0
        self.rot = [0.0, 0.0]
        self.speed = Spring(1.0 if self.motion else 0.0)
        self.ring_a = Spring(0.0)
        self.hub_s = Spring(0.75)
        # side card
        self.card_a, self.card_y, self.card_dx = Spring(0), Spring(0), Spring(0)
        self.card_pix: QPixmap | None = None
        self.card_old: QPixmap | None = None
        self.card_mix = 1.0
        self._cards: dict[int, QPixmap] = {}
        self._planet_pix: dict[tuple[int, bool], QPixmap] = {}
        self._hub_pix: dict[int, QPixmap] = {}
        self._rings_pix: QPixmap | None = None
        self._warm = list(range(len(self.items)))[::-1]  # pre-drawn after the opening, first planet first
        self._dpr = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._last = time.perf_counter()

    # ------------------------------------------------------------ layout
    def _cap(self, r: float) -> int:
        return max(1, int(2 * math.pi * r / (self.D + 10)))

    def _layout(self, offers: list[Offer]) -> None:
        """Smaller group (tools or formats) on the inner orbit, the rest outside."""
        D, HUB, GAP = self.D, self.HUB, self.GAP
        r_in = HUB / 2 + D / 2 + GAP
        r_out = r_in + D * 1.18 + GAP  # room for a hovered (scaled-up) planet between the orbits
        tools = [o for o in offers if is_tool(o)]
        fmts = [o for o in offers if not is_tool(o)]
        groups = sorted([g for g in (tools, fmts) if g], key=len)
        cap_in, cap_out = self._cap(r_in), self._cap(r_out)
        rings: list[list[Offer | None]]
        if not groups:
            rings = [[]]
        elif len(groups) == 1 or len(offers) <= 4:
            allg = tools + fmts
            if len(allg) <= cap_in:
                rings = [allg]
            else:
                k = min(cap_in, round(len(allg) * cap_in / (cap_in + cap_out)))
                rings = [allg[:k], allg[k:]]
        else:
            g1, g2 = groups
            rings = [list(g1[:cap_in]), list(g2) + list(g1[cap_in:])]
        last_cap = cap_in if len(rings) == 1 else cap_out
        if len(rings[-1]) > last_cap:
            rings[-1] = rings[-1][: last_cap - 1] + [None]
        if len(rings) == 1:
            m = len(rings[0])
            self.radii = [max(r_in, m * (D + 12) / (2 * math.pi))]
        else:
            self.radii = [r_in, r_out]
        self.items: list[Offer | None] = []
        self.ps: list[_Planet] = []
        order = 0
        for ri, ring in enumerate(rings):
            m = max(1, len(ring))
            for j, o in enumerate(ring):
                base = -90 + j * 360 / m + (180 / m if ri == 1 else 0)
                self.items.append(o)
                self.ps.append(_Planet(ri, base, 0.03 + order * 0.028))
                order += 1
        self.hidden_count = len(offers) - sum(1 for o in self.items if o is not None)
        self.E = self.radii[-1] + D * 0.6 + 16  # orbit half-size, with room for hover scale and the magnet
        S = 2 * self.E
        self.ox = (self.CARD_W + self.CARD_GAP) if self.side == "left" else 0
        self.setFixedSize(QSize(int(S + self.CARD_GAP + self.CARD_W) + 4, int(S)))

    def orbit_center(self) -> QPointF:
        return QPointF(self.ox + self.E, self.E)

    # ------------------------------------------------------------ pixmap caches
    def _check_dpr(self) -> float:
        dpr = self.devicePixelRatioF()
        if dpr != self._dpr:
            self._dpr = dpr
            self._planet_pix.clear()
            self._hub_pix.clear()
            self._cards.clear()
            self._rings_pix = None
        return dpr

    def _new_pix(self, w: float, h: float) -> QPixmap:
        pm = QPixmap(max(1, math.ceil(w * self._dpr)), max(1, math.ceil(h * self._dpr)))
        pm.setDevicePixelRatio(self._dpr)
        pm.fill(Qt.GlobalColor.transparent)
        return pm

    @staticmethod
    def _painter(pm: QPixmap) -> QPainter:
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        return p

    def _planet_size(self) -> float:
        return self.D * self.MAX_SCALE + 12

    def _planet_pixmap(self, i: int, on: bool) -> QPixmap:
        key = (i, on)
        pm = self._planet_pix.get(key)
        if pm is not None:
            return pm
        L = self._planet_size()
        pm = self._new_pix(L, L)
        p = self._painter(pm)
        c = QPointF(L / 2, L / 2)
        R = self.D / 2 * self.MAX_SCALE
        o = self.items[i]
        if on:
            p.setPen(QPen(_alpha(theme.ACCENT, 0.30), 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, R + 4, R + 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ACCENT)
            p.drawEllipse(c, R, R)
        else:
            pen = QPen(theme.LINE if o is not None else theme.DIM, 1.2)
            if o is None:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(theme.SURFACE2)
            p.drawEllipse(c, R - 0.6, R - 0.6)
        text_c = theme.ON_ACCENT if on else theme.TEXT
        label = "More" if o is None else o.target.label
        lines, f = self._fit_label(label, R * 2 * 0.78)
        fm = QFontMetrics(f)
        lh = fm.height() * 0.92
        top = c.y() - (len(lines) * lh) / 2 + 5 * self.D / 72
        # small type mark above the label: filled = tool, ring = format
        dot_y = top - 7 * self.D / 72
        if o is None:
            sub = f"+{self.hidden_count}"
            p.setFont(_font(10 * self.D / 72, QFont.Weight.DemiBold))
            p.setPen(theme.ON_ACCENT if on else theme.DIM)
            p.drawText(QRectF(c.x() - R, top + lh * len(lines) - 2, 2 * R, 16), Qt.AlignmentFlag.AlignHCenter, sub)
        elif is_tool(o):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ON_ACCENT if on else theme.ACCENT)
            p.drawEllipse(QPointF(c.x(), dot_y), 3.0, 3.0)
        else:
            p.setPen(QPen(theme.ON_ACCENT if on else theme.DIM, 1.3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(c.x(), dot_y), 2.8, 2.8)
        p.setFont(f)
        p.setPen(text_c)
        for k, line in enumerate(lines):
            w = fm.horizontalAdvance(line)
            p.drawText(QPointF(c.x() - w / 2, top + fm.ascent() * 0.92 + k * lh), line)
        if o is not None and real_warning(o):
            wc = QPointF(c.x() + R * 0.70, c.y() - R * 0.70)
            p.setPen(QPen(theme.BG, 2))
            p.setBrush(theme.WARN)
            p.drawEllipse(wc, 4.5, 4.5)
        p.end()
        self._planet_pix[key] = pm
        return pm

    def _fit_label(self, label: str, max_w: float) -> tuple[list[str], QFont]:
        k = self.D / 72
        for px in (13.5, 12.5, 11.5):
            f = _font(px * k, QFont.Weight.DemiBold, display=True)
            fm = QFontMetrics(f)
            if fm.horizontalAdvance(label) <= max_w:
                return [label], f
            if " " in label:
                a, b = label.split(" ", 1)
                if max(fm.horizontalAdvance(a), fm.horizontalAdvance(b)) <= max_w:
                    return [a, b], f
        f = _font(11 * k, QFont.Weight.DemiBold, display=True)
        return [QFontMetrics(f).elidedText(label, Qt.TextElideMode.ElideRight, int(max_w))], f

    def _hub_pixmap(self) -> QPixmap:
        pm = self._hub_pix.get(self.hover)
        if pm is not None:
            return pm
        H = self.HUB
        pm = self._new_pix(H + 4, H + 4)
        p = self._painter(pm)
        c = QPointF((H + 4) / 2, (H + 4) / 2)
        p.setPen(QPen(theme.LINE, 1.2))
        p.setBrush(theme.SURFACE)
        p.drawEllipse(c, H / 2, H / 2)
        k = self.D / 72
        f = _font(12.5 * k, QFont.Weight.Bold, display=True)
        fm = QFontMetrics(f)
        title = fm.elidedText(self.center_title, Qt.TextElideMode.ElideMiddle, int(H - 22 * k))
        p.setFont(f)
        p.setPen(theme.TEXT)
        p.drawText(QPointF(c.x() - fm.horizontalAdvance(title) / 2, c.y() - 2 * k), title)
        if 0 <= self.hover < len(self.items):
            o = self.items[self.hover]
            sub = "show all" if o is None else f"→ {o.target.label}"
            col = theme.ACCENT
        else:
            sub, col = "pick one", theme.DIM
        f = _font(10.5 * k, QFont.Weight.DemiBold)
        fm = QFontMetrics(f)
        sub = fm.elidedText(sub, Qt.TextElideMode.ElideRight, int(H - 26 * k))
        p.setFont(f)
        p.setPen(col)
        p.drawText(QPointF(c.x() - fm.horizontalAdvance(sub) / 2, c.y() + 15 * k), sub)
        p.end()
        self._hub_pix[self.hover] = pm
        return pm

    def _rings_pixmap(self) -> QPixmap:
        if self._rings_pix is not None:
            return self._rings_pix
        S = 2 * self.E
        pm = self._new_pix(S, S)
        p = self._painter(pm)
        c = QPointF(self.E, self.E)
        for ri, r in enumerate(self.radii):
            pen = QPen(_alpha(theme.TEXT, 0.16 if theme.DARK else 0.20), 1.3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setDashPattern([0.1, 5.5] if ri == len(self.radii) - 1 else [3, 6])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r, r)
        p.end()
        self._rings_pix = pm
        return pm

    def _card_pixmap(self, i: int) -> QPixmap:
        pm = self._cards.get(i)
        if pm is not None:
            return pm
        o = self.items[i]
        W, pad = self.CARD_W, 14
        inner = W - 2 * pad
        f_tag = _font(9.5, QFont.Weight.Bold, mono=True)
        f_tag.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        f_title = _font(19, QFont.Weight.Bold, display=True)
        f_body = _font(12.5)
        f_meta = _font(11, mono=True)
        f_small = _font(11)
        if o is None:
            tag, title, cap, text = "LIST", "More", "", f"See all {self.hidden_count + 1} options and search them"
            meta, warn, hint = "", "", "Or just start typing"
        else:
            tag = "TOOL" if is_tool(o) else "FORMAT"
            title, cap, text = o.target.label, o.caption, blurb(o)
            meta = out_name(o)
            warn = real_warning(o)
            hint = "Asks for details first" if o.target.ask else ("Right-click for options" if o.options else "")
        fm_body = QFontMetrics(f_body)
        body_lines = self._wrap(text, fm_body, inner, 2)
        h = pad + 13 + 6 + 24 + 6 + len(body_lines) * (fm_body.height() + 1)
        if meta:
            h += 10 + 15
        warn_lines = self._wrap(warn, QFontMetrics(f_small), inner - 14, 2) if warn else []
        if warn_lines:
            h += 8 + len(warn_lines) * (QFontMetrics(f_small).height())
        if hint:
            h += 8 + 15
        h += pad
        pm = self._new_pix(W + 2, h + 2)
        p = self._painter(pm)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(QRectF(0.5, 0.5, W, h), 12, 12)
        y = pad
        # tag + caption chip
        p.setFont(f_tag)
        p.setPen(theme.ACCENT if tag == "TOOL" else theme.DIM)
        p.drawText(QRectF(pad, y, inner, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tag)
        if cap:
            fc = _font(10.5, QFont.Weight.DemiBold)
            fmc = QFontMetrics(fc)
            cap = fmc.elidedText(cap, Qt.TextElideMode.ElideRight, int(inner * 0.62))
            cw = fmc.horizontalAdvance(cap) + 14
            r = QRectF(pad + inner - cw, y - 3, cw, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.SURFACE2)
            p.drawRoundedRect(r, 10, 10)
            p.setFont(fc)
            p.setPen(theme.DIM)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, cap)
        y += 13 + 6
        p.setFont(f_title)
        p.setPen(theme.TEXT)
        fmt = QFontMetrics(f_title)
        p.drawText(QPointF(pad, y + fmt.ascent()), fmt.elidedText(title, Qt.TextElideMode.ElideRight, inner))
        y += 24 + 6
        p.setFont(f_body)
        p.setPen(_alpha(theme.TEXT, 0.82))
        for line in body_lines:
            p.drawText(QPointF(pad, y + fm_body.ascent()), line)
            y += fm_body.height() + 1
        if meta:
            y += 10
            p.setFont(f_meta)
            fmm = QFontMetrics(f_meta)
            p.setPen(theme.ACCENT)
            p.drawText(QPointF(pad, y + fmm.ascent()), "→")
            p.setPen(theme.DIM)
            p.drawText(QPointF(pad + 16, y + fmm.ascent()),
                       fmm.elidedText(meta, Qt.TextElideMode.ElideMiddle, inner - 16))
            y += 15
        if warn_lines:
            y += 8
            fms = QFontMetrics(f_small)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.WARN)
            p.drawEllipse(QPointF(pad + 4, y + fms.height() / 2), 3.5, 3.5)
            p.setFont(f_small)
            p.setPen(theme.WARN)
            for line in warn_lines:
                p.drawText(QPointF(pad + 14, y + fms.ascent()), line)
                y += fms.height()
        if hint:
            y += 8
            p.setFont(f_small)
            p.setPen(_alpha(theme.DIM, 0.9))
            p.drawText(QPointF(pad, y + QFontMetrics(f_small).ascent()), hint)
        p.end()
        self._cards[i] = pm
        return pm

    @staticmethod
    def _wrap(text: str, fm: QFontMetrics, width: int, max_lines: int) -> list[str]:
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if fm.horizontalAdvance(trial) <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[: max_lines - 1] + [fm.elidedText(" ".join(lines[max_lines - 1:]), Qt.TextElideMode.ElideRight, width)]
        return lines

    # ------------------------------------------------------------ clock
    def showEvent(self, e):
        super().showEvent(e)
        self._t = 0.0
        hub_r = self.HUB / 2 * 0.6
        for p in self.ps:
            p.r.snap(hub_r)
            p.sw.snap(140 if self.motion else 0)
            p.s.snap(0.4 if self.motion else 1)
            p.a.snap(0 if self.motion else 1)
        self.ring_a.snap(0 if self.motion else 1)
        self.hub_s.snap(0.75 if self.motion else 1)
        self._wake()

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def _wake(self) -> None:
        if not self._timer.isActive():
            self._last = time.perf_counter()
            self._timer.start(16)

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = min(0.05, max(0.0, now - self._last))
        self._last = now
        self._t += dt
        m = self.motion
        busy = False
        ex = self._exit
        # The drift stops when you point at the orbit, and by itself after a few seconds,
        # so a popup left open goes back to using no CPU at all.
        still = self.hover >= 0 or self.inside or self.kbd or ex is not None or not m or self._t > self.DRIFT_SECONDS
        self.speed.t = 0.0 if still else 1.0
        busy |= self.speed.step(dt, 38, 12, m)
        if m:
            self.rot[0] -= dt * 11 * self.speed.v
            self.rot[1] += dt * 7 * self.speed.v
        drifting = self.speed.v > 0.003
        self.ring_a.t = 0.0 if ex else 1.0
        busy |= self.ring_a.step(dt, 120, 20, m)
        self.hub_s.t = 1.08 if ex else 1.0
        busy |= self.hub_s.step(dt, 220, 16, m)
        c = self.orbit_center()
        for i, p in enumerate(self.ps):
            if self._t < p.delay and ex is None:
                busy = True
                continue
            rr = self.radii[p.ring]
            h = i == self.hover
            if ex is not None:
                if i == ex["i"]:
                    p.r.t, p.s.t, p.a.t, p.mx.t, p.my.t = 0.0, 1.2, 0.0, 0.0, 0.0
                else:
                    p.r.t, p.s.t, p.a.t = rr * 1.45, 0.8, 0.0
            else:
                p.r.t, p.sw.t = rr, 0.0
                p.s.t = 1.12 if h else 1.0
                p.a.t = 1.0 if (self.hover < 0 or h) else 0.62
            chosen = ex is not None and i == ex["i"]
            busy |= p.r.step(dt, 90 if chosen else 120, 14, m)
            busy |= p.sw.step(dt, 60, 12, m)
            busy |= p.s.step(dt, 260, 18, m)
            busy |= p.a.step(dt, 30 if chosen else 180, 11 if chosen else 22, m)
            busy |= p.mx.step(dt, 220, 17, m)
            busy |= p.my.step(dt, 220, 17, m)
            a = math.radians(p.base + self.rot[p.ring] + p.sw.v)
            p.ang = a
            p.hx, p.hy = c.x() + math.cos(a) * p.r.v, c.y() + math.sin(a) * p.r.v
            p.x, p.y = p.hx + p.mx.v, p.hy + p.my.v
        # side card follows the hovered planet
        if self.hover >= 0 and ex is None:
            pm = self.card_pix
            ch = pm.height() / self._dpr if pm is not None else 120
            self.card_y.t = max(4.0, min(self.height() - ch - 4, self.ps[self.hover].y - ch / 2))
            self.card_a.t = 1.0
        else:
            self.card_a.t = 0.0
        busy |= self.card_y.step(dt, 210, 22, m)
        busy |= self.card_a.step(dt, 260, 26, m)
        busy |= self.card_dx.step(dt, 260, 22, m)
        if self.card_mix < 1.0:
            self.card_mix = min(1.0, self.card_mix + dt / 0.12) if m else 1.0
            busy = True
        if ex is not None:
            ex["t"] += dt
            busy = True
            if ex["t"] >= ex["dur"] and not ex.get("fired"):
                ex["fired"] = True
                QTimer.singleShot(0, ex["done"])
        self.update()
        # Pre-draw one hover image per quiet frame, so hovering never draws on the spot.
        if self._warm and self._t > 0.5 and ex is None:
            self._check_dpr()
            i = self._warm.pop()
            self._planet_pixmap(i, True)
            self._card_pixmap(i)
            busy = True if self._warm else busy
        if not (busy or drifting):
            self._timer.stop()
            return
        want = 16 if busy else 33  # idle drift doesn't need 60 fps
        if self._timer.interval() != want:
            self._timer.setInterval(want)

    # ------------------------------------------------------------ painting
    def paintEvent(self, _):
        self._check_dpr()
        p = QPainter(self)
        p.fillRect(self.rect(), theme.BG)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = self.orbit_center()
        ra = max(0.0, min(1.0, self.ring_a.v))
        if ra > 0.01:
            p.setOpacity(ra)
            p.drawPixmap(QPointF(c.x() - self.E, c.y() - self.E), self._rings_pixmap())
            # comet trails show the drift direction; they fade as the orbits stop
            sp = self.speed.v
            if sp > 0.02:
                p.setPen(Qt.PenStyle.NoPen)
                for i, pl in enumerate(self.ps):
                    if pl.a.v < 0.05:
                        continue
                    direction = 1.0 if pl.ring == 0 and len(self.radii) == 2 else -1.0
                    rr = pl.r.v + self.D / 2 + 5
                    for k in range(1, 5):
                        a = pl.ang + direction * k * 0.05
                        p.setBrush(_alpha(theme.ACCENT, 0.42 * sp * pl.a.v * (1 - k / 5)))
                        p.drawEllipse(QPointF(c.x() + math.cos(a) * rr, c.y() + math.sin(a) * rr), 2.2 - k * 0.3, 2.2 - k * 0.3)
            if 0 <= self.hover < len(self.ps):
                pl = self.ps[self.hover]
                ang = math.atan2(pl.y - c.y(), pl.x - c.x())
                d = math.hypot(pl.x - c.x(), pl.y - c.y())
                r0, r1 = self.HUB / 2 + 3, d - self.D / 2 * pl.s.v - 3
                if r1 > r0:
                    p.setPen(QPen(_alpha(theme.ACCENT, 0.85 * ra), 2))
                    p.drawLine(QPointF(c.x() + math.cos(ang) * r0, c.y() + math.sin(ang) * r0),
                               QPointF(c.x() + math.cos(ang) * r1, c.y() + math.sin(ang) * r1))
        # planets (the hovered one last, on top)
        L = self._planet_size()
        order = [i for i in range(len(self.ps)) if i != self.hover] + ([self.hover] if self.hover >= 0 else [])
        for i in order:
            pl = self.ps[i]
            a = max(0.0, min(1.0, pl.a.v))
            if a < 0.01:
                continue
            pm = self._planet_pixmap(i, i == self.hover)
            size = L * pl.s.v / self.MAX_SCALE
            p.setOpacity(a)
            p.drawPixmap(QRectF(pl.x - size / 2, pl.y - size / 2, size, size), pm, QRectF(pm.rect()))
        # hub
        hub = self._hub_pixmap()
        hs = (self.HUB + 4) * self.hub_s.v
        p.setOpacity(1.0 if self._exit is None else max(0.0, 1 - self._exit["t"] / self._exit["dur"]))
        p.drawPixmap(QRectF(c.x() - hs / 2, c.y() - hs / 2, hs, hs), hub, QRectF(hub.rect()))
        # side card + leader line
        ca = max(0.0, min(1.0, self.card_a.v))
        if ca > 0.01 and self.card_pix is not None and 0 <= self.hover < len(self.ps):
            pl = self.ps[self.hover]
            cw = self.CARD_W
            right = self.side == "right"
            cx = (2 * self.E + self.CARD_GAP if right else 0) + self.card_dx.v
            cy = self.card_y.v
            ch = self.card_pix.height() / self._dpr
            edge_x = cx if right else cx + cw
            px = pl.x + (1 if right else -1) * (self.D / 2 * pl.s.v + 2)
            p.setOpacity(ca)
            p.setPen(QPen(_alpha(theme.ACCENT, 0.55), 1.4))
            ly = max(cy + 14, min(cy + ch - 14, pl.y))
            p.drawLine(QPointF(px, pl.y), QPointF(edge_x, ly))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ACCENT)
            p.drawEllipse(QPointF(edge_x, ly), 3, 3)
            if self.card_old is not None and self.card_mix < 1:
                p.setOpacity(ca * (1 - self.card_mix))
                p.drawPixmap(QPointF(cx, cy), self.card_old)
            p.setOpacity(ca * (self.card_mix if self.card_old is not None else 1))
            p.drawPixmap(QPointF(cx, cy), self.card_pix)
        p.end()

    # ------------------------------------------------------------ interaction
    def set_hover(self, i: int) -> None:
        if i == self.hover:
            return
        prev = self.hover
        self.hover = i
        if i >= 0:
            self._check_dpr()
            new = self._card_pixmap(i)
            if prev >= 0 and self.card_a.v > 0.05:
                self.card_old, self.card_mix = self.card_pix, 0.0
            else:  # appearing: start next to the planet, slide in from the orbit side
                ch = new.height() / self._dpr
                self.card_y.snap(max(4.0, min(self.height() - ch - 4, self.ps[i].y - ch / 2)))
                self.card_dx.snap(-12 if self.side == "right" else 12)
                self.card_dx.t = 0
                self.card_old, self.card_mix = None, 1.0
            self.card_pix = new
        self.hovered.emit(i)
        self._wake()

    def _nearest(self, pos: QPointF) -> int:
        best, bd = -1, 1e9
        for i, pl in enumerate(self.ps):
            d = math.hypot(pl.hx - pos.x(), pl.hy - pos.y())
            if d < bd:
                best, bd = i, d
        return best if bd <= self.D * 0.62 else -1

    def mouseMoveEvent(self, e):
        if self._exit is not None:
            return
        pos = e.position()
        c = self.orbit_center()
        inside = math.hypot(pos.x() - c.x(), pos.y() - c.y()) < self.E
        self.kbd = False
        if inside != self.inside:
            self.inside = inside
        i = self._nearest(pos)
        self.set_hover(i)
        for k, pl in enumerate(self.ps):
            if k == i:
                pl.mx.t = max(-14.0, min(14.0, (pos.x() - pl.hx) * 0.3))
                pl.my.t = max(-14.0, min(14.0, (pos.y() - pl.hy) * 0.3))
            else:
                pl.mx.t = pl.my.t = 0.0
        self._wake()

    def leaveEvent(self, _):
        self.inside = False
        for pl in self.ps:
            pl.mx.t = pl.my.t = 0.0
        if not self.kbd:
            self.set_hover(-1)
        self._wake()

    def mouseReleaseEvent(self, e):
        if self._exit is not None:
            return
        i = self._nearest(e.position())
        if i < 0:
            return
        if e.button() == Qt.MouseButton.RightButton:
            self.options_requested.emit(i)
        elif e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(i)

    def keyPressEvent(self, e: QKeyEvent):
        n = len(self.items)
        k = e.key()
        if n and k in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Up):
            step = 1 if k in (Qt.Key.Key_Right, Qt.Key.Key_Down) else -1
            self.kbd = True
            self.set_hover((self.hover + step) % n if self.hover >= 0 else (0 if step > 0 else n - 1))
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.hover >= 0:
            self.activated.emit(self.hover)
        elif k == Qt.Key.Key_Menu and self.hover >= 0:
            self.options_requested.emit(self.hover)
        else:
            e.ignore()

    def play_exit(self, i: int, done) -> None:
        """The chosen planet falls into the hub while the others fly out; then ``done``."""
        if not self.motion or not self.isVisible():
            done()
            return
        self._exit = {"i": i, "t": 0.0, "dur": 0.2, "done": done}
        self.card_a.t = 0.0
        self._wake()
