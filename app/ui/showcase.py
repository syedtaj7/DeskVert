"""Every conversion, animated: a scrolling gallery where each card acts out what it does.

A PDF shrinks while its size counts down, pages fly together to merge, a scan line turns a
photo of a page into text, a waveform squeezes into an MP3... Cards are grouped by the same
worlds the tour counts live (see universe.gather), so a new kind of file gets its own section,
and a plain card, by itself.

Light by design: one shared 30 fps clock, and only the cards you can see are redrawn.
Nothing moves text by fractions of a pixel (that's what makes painted text shimmer); text
fades in place, and only shapes travel.
"""

from __future__ import annotations

import math
import time
from contextlib import contextmanager

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QScrollArea, QWidget

from . import theme
from .fx import clamp, ease_back, ease_in_out, ease_out, font, mix, paint_check, paint_cursor, phase, with_alpha

LOOP = 5.0  # every card acts out its story in five seconds, then starts again
ART_W, ART_H = 300.0, 150.0  # every story is drawn in this box, then scaled into the card
CARD_W, CARD_H = 304, 228
ART_S = (CARD_W - 20) / ART_W
GAP = 12


def scroll_qss() -> str:
    """A thin scrollbar that matches the look (the tour has no app-wide style sheet)."""
    return (f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: transparent; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}"
            f"QScrollBar::handle:vertical {{ background: {theme.rgba(with_alpha(theme.DIM, 0.45))};"
            f" border-radius: 3px; min-height: 40px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {theme.rgba(theme.DIM)}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}")

COL = {
    "pdf": QColor(222, 62, 62), "doc": QColor(45, 110, 230), "sheet": QColor(26, 148, 88),
    "slides": QColor(230, 104, 30), "image": QColor(40, 150, 225), "audio": QColor(210, 60, 135),
    "video": QColor(118, 88, 216), "data": QColor(18, 146, 156), "sub": QColor(214, 150, 20),
    "book": QColor(160, 98, 52), "map": QColor(36, 150, 84), "model": QColor(86, 108, 140),
    "cad": QColor(28, 120, 196), "font": QColor(128, 78, 206), "mail": QColor(224, 140, 30),
    "zip": QColor(170, 120, 50), "md": QColor(70, 72, 84),
}


def _mono(px: float) -> QFont:
    f = QFont("Consolas")
    f.setPixelSize(int(px))
    return f


# ====================================================================== drawing kit


@contextmanager
def xf(p: QPainter, x: float, y: float, s: float = 1.0, rot: float = 0.0, alpha: float = 1.0,
       sx: float | None = None):
    """Draw around (0, 0), moved/scaled/turned. Scaling with the painter (not the font size)
    keeps text sizes smooth while things grow and shrink."""
    p.save()
    p.translate(x, y)
    if rot:
        p.rotate(rot)
    p.scale(s if sx is None else sx, s)
    p.setOpacity(p.opacity() * clamp(alpha))
    try:
        yield
    finally:
        p.restore()


def rpen(c: QColor, w: float) -> QPen:
    pen = QPen(c, w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


WRAP = int(Qt.AlignmentFlag.AlignTop.value) | int(Qt.TextFlag.TextWordWrap.value)


def _folded(r: QRectF, fold: float) -> QPainterPath:
    path = QPainterPath()
    rad = min(5.0, r.width() * 0.08)
    path.moveTo(r.left() + rad, r.top())
    path.lineTo(r.right() - fold, r.top())
    path.lineTo(r.right(), r.top() + fold)
    path.lineTo(r.right(), r.bottom() - rad)
    path.quadTo(r.right(), r.bottom(), r.right() - rad, r.bottom())
    path.lineTo(r.left() + rad, r.bottom())
    path.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - rad)
    path.lineTo(r.left(), r.top() + rad)
    path.quadTo(r.left(), r.top(), r.left() + rad, r.top())
    return path


def tag(p: QPainter, c: QPointF, text: str, col: QColor, alpha: float = 1.0, px: float = 10.5):
    """A coloured format pill (PDF, JPG...)."""
    if alpha <= 0:
        return
    f = font(px, QFont.Weight.Bold)
    w = QFontMetricsF(f).horizontalAdvance(text) + 14
    r = QRectF(c.x() - w / 2, c.y() - px * 0.95, w, px * 1.9)
    p.save()
    p.setOpacity(p.opacity() * clamp(alpha))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
    p.setPen(QColor(255, 255, 255))
    p.setFont(f)
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
    p.restore()


def swap_tag(p: QPainter, c: QPointF, a: str, ca: QColor, b: str, cb: QColor, k: float):
    if k < 0.5:
        tag(p, c, a, ca, 1 - 2 * k)
    else:
        tag(p, c, b, cb, 2 * k - 1)


def lines(p: QPainter, r: QRectF, col: QColor, n: int = 4, widths=(1.0, 0.82, 0.92, 0.6, 0.75), h: float = 4.0,
          gap: float | None = None):
    gap = gap if gap is not None else (r.height() - n * h) / max(1, n - 1)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    for i in range(n):
        w = r.width() * widths[i % len(widths)]
        p.drawRoundedRect(QRectF(r.left(), r.top() + i * (h + gap), w, h), h / 2, h / 2)


def landscape(p: QPainter, r: QRectF, col: QColor = COL["image"], radius: float = 5.0):
    """A little photo: sky, sun, two hills."""
    p.save()
    clip = QPainterPath()
    clip.addRoundedRect(r, radius, radius)
    p.setClipPath(clip)
    p.fillRect(r, mix(col, QColor(255, 255, 255), 0.55))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 214, 92))
    p.drawEllipse(QPointF(r.left() + r.width() * 0.72, r.top() + r.height() * 0.3), r.height() * 0.12,
                  r.height() * 0.12)
    hill = QPainterPath()
    hill.moveTo(r.left(), r.bottom())
    hill.lineTo(r.left(), r.top() + r.height() * 0.72)
    hill.quadTo(r.left() + r.width() * 0.3, r.top() + r.height() * 0.38, r.left() + r.width() * 0.6, r.top()
                + r.height() * 0.74)
    hill.lineTo(r.left() + r.width() * 0.6, r.bottom())
    p.setBrush(mix(col, QColor(20, 40, 60), 0.15))
    p.drawPath(hill)
    hill2 = QPainterPath()
    hill2.moveTo(r.left() + r.width() * 0.35, r.bottom())
    hill2.quadTo(r.left() + r.width() * 0.7, r.top() + r.height() * 0.5, r.right(), r.top() + r.height() * 0.66)
    hill2.lineTo(r.right(), r.bottom())
    p.setBrush(mix(col, QColor(10, 30, 50), 0.35))
    p.drawPath(hill2)
    p.restore()
    p.setPen(QPen(with_alpha(theme.TEXT, 0.12), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r, radius, radius)


def page(p: QPainter, r: QRectF, col: QColor, label: str = "", body: str = "lines", tint: float = 0.0):
    """A document: folded corner, its content, and a format pill."""
    fold = r.width() * 0.26
    path = _folded(r, fold)
    p.setPen(QPen(with_alpha(theme.TEXT, 0.16), 1))
    p.setBrush(mix(theme.SURFACE, col, 0.06 + tint))
    p.drawPath(path)
    tri = QPainterPath()
    tri.moveTo(r.right() - fold, r.top())
    tri.lineTo(r.right() - fold, r.top() + fold)
    tri.lineTo(r.right(), r.top() + fold)
    tri.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(with_alpha(col, 0.4))
    p.drawPath(tri)
    inner = QRectF(r.left() + r.width() * 0.14, r.top() + r.height() * 0.16, r.width() * 0.6, r.height() * 0.46)
    if body == "lines":
        lines(p, inner, with_alpha(theme.TEXT, 0.22), 4, h=max(2.0, r.height() * 0.045))
    elif body == "image":
        landscape(p, QRectF(inner.left(), inner.top(), r.width() * 0.72, inner.height()), col, 3)
    elif body == "grid":
        p.setPen(QPen(with_alpha(col, 0.7), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        g = QRectF(inner.left(), inner.top(), r.width() * 0.72, inner.height())
        p.drawRect(g)
        for k in (1, 2):
            p.drawLine(QPointF(g.left() + g.width() * k / 3, g.top()), QPointF(g.left() + g.width() * k / 3, g.bottom()))
            p.drawLine(QPointF(g.left(), g.top() + g.height() * k / 3), QPointF(g.right(), g.top() + g.height() * k / 3))
    elif body == "slides":
        g = QRectF(inner.left(), inner.top(), r.width() * 0.72, inner.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(col, 0.25))
        p.drawRoundedRect(g, 2, 2)
        p.setBrush(with_alpha(col, 0.8))
        p.drawRect(QRectF(g.left() + 4, g.top() + 4, g.width() * 0.5, 3))
    if label:
        tag(p, QPointF(r.center().x(), r.bottom() - r.height() * 0.16), label, col, px=max(8.0, r.width() * 0.15))


def arrow(p: QPainter, x1: float, x2: float, y: float, t: float, alpha: float = 1.0):
    """A dashed arrow with a dot running along it."""
    if alpha <= 0:
        return
    p.save()
    p.setOpacity(p.opacity() * alpha)
    pen = QPen(with_alpha(theme.TEXT, 0.25), 1.4, Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(x1, y), QPointF(x2 - 4, y))
    p.setPen(QPen(with_alpha(theme.TEXT, 0.35), 1.6))
    p.drawLine(QPointF(x2 - 7, y - 4), QPointF(x2 - 2, y))
    p.drawLine(QPointF(x2 - 7, y + 4), QPointF(x2 - 2, y))
    k = (t * 0.9) % 1.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.ACCENT)
    p.drawEllipse(QPointF(x1 + (x2 - 8 - x1) * k, y), 2.6, 2.6)
    p.restore()


def text(p: QPainter, r: QRectF, s: str, px: float = 12, weight=QFont.Weight.DemiBold, color: QColor | None = None,
         align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, alpha: float = 1.0):
    if alpha <= 0:
        return
    p.save()
    p.setOpacity(p.opacity() * clamp(alpha))
    p.setFont(font(px, weight))
    p.setPen(color or theme.TEXT)
    p.drawText(r, align, s)
    p.restore()


def size_text(kb: float) -> str:
    if kb >= 1000:
        return f"{kb / 1024:.1f} MB"
    return f"{kb:.0f} KB"


def log_mix(a: float, b: float, k: float) -> float:
    return a * (b / a) ** k


def done(p: QPainter, t: float, at: float, c: QPointF, size: float = 22):
    k = phase(t, at, at + 0.6)
    if k > 0:
        paint_check(p, c, size, ease_out(k))


# ====================================================================== the stories
# Each one paints a 300 x 150 scene for time t (0..LOOP) and loop number n.


def a_img_convert(p, t, n, card):
    targets = card.cycle or ["JPG", "PNG", "WEBP", "AVIF"]
    tgt = targets[n % len(targets)]
    flip = phase(t, 1.2, 2.0)
    sx = max(0.03, abs(math.cos(math.pi * flip)))
    with xf(p, 100, 66, 1.0, sx=sx):
        landscape(p, QRectF(-56, -40, 112, 80), COL["image"] if flip < 0.5 else mix(COL["image"], theme.ACCENT, 0.25))
    tag(p, QPointF(100, 128), "HEIC" if flip < 0.5 else tgt, COL["image"] if flip < 0.5 else theme.ACCENT)
    # where it can go: every target the picker offers for pictures (read live)
    for i, name in enumerate(targets[:4]):
        on = name == tgt and flip >= 0.5
        r = QRectF(196, 22 + i * 28, 82, 22)
        p.setPen(QPen(theme.ACCENT if on else with_alpha(theme.TEXT, 0.14), 1.2))
        p.setBrush(theme.ACCENT if on else theme.SURFACE)
        p.drawRoundedRect(r, 11, 11)
        text(p, r, name, 10.5, QFont.Weight.Bold, theme.ON_ACCENT if on else theme.TEXT, Qt.AlignmentFlag.AlignCenter)
    arrow(p, 162, 192, 66, t, 1 - phase(t, 2.0, 2.4))


def a_img_form(p, t, n, card):
    k = ease_in_out(phase(t, 0.6, 2.5))
    with xf(p, 82, 72, 1 - 0.18 * k):
        landscape(p, QRectF(-36, -48, 72, 96))
    # a size meter falling below the form's limit
    meter = QRectF(178, 18, 16, 112)
    p.setPen(QPen(with_alpha(theme.TEXT, 0.14), 1))
    p.setBrush(theme.TRACK)
    p.drawRoundedRect(meter, 8, 8)
    kb = log_mix(2900, 46, k)
    frac = clamp(math.log(kb / 20) / math.log(2900 / 20))
    fill = QRectF(meter.left(), meter.bottom() - meter.height() * frac, meter.width(), meter.height() * frac)
    p.setPen(Qt.PenStyle.NoPen)
    under = kb <= 50
    p.setBrush(theme.SUCCESS if under else mix(theme.ACCENT, COL["pdf"], 0.3))
    p.drawRoundedRect(fill, 8, 8)
    limit_y = meter.bottom() - meter.height() * clamp(math.log(50 / 20) / math.log(2900 / 20))
    p.setPen(QPen(theme.TEXT, 1.4, Qt.PenStyle.DashLine))
    p.drawLine(QPointF(meter.left() - 8, limit_y), QPointF(meter.right() + 8, limit_y))
    text(p, QRectF(204, limit_y - 9, 90, 18), "limit 50 KB", 10, QFont.Weight.DemiBold, theme.DIM)
    text(p, QRectF(204, 22, 90, 22), size_text(kb), 17, QFont.Weight.Bold)
    text(p, QRectF(204, 44, 90, 16), "200 × 230 px" if k > 0.5 else "3000 × 4000 px", 10, QFont.Weight.Normal, theme.DIM)
    done(p, t, 2.6, QPointF(268, 96))


def a_img_resize(p, t, n, card):
    k = ease_in_out(phase(t, 0.8, 2.4))
    w, h = 170 - 80 * k, 112 - 53 * k
    r = QRectF(24, 20, w, h)
    landscape(p, r)
    p.setPen(QPen(theme.ACCENT, 1.4, Qt.PenStyle.DashLine))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(r.adjusted(-3, -3, 3, 3))
    p.setPen(QPen(theme.ACCENT, 1.4))
    p.setBrush(theme.SURFACE)
    for pt in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
        p.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))
    if t < 2.8:
        paint_cursor(p, QPointF(r.right() + 2, r.bottom() + 2), 0.9)
    px = (4032 - (4032 - 1600) * k, 3024 - (3024 - 1200) * k)
    text(p, QRectF(206, 34, 90, 20), f"{px[0]:.0f} ×", 15, QFont.Weight.Bold)
    text(p, QRectF(206, 54, 90, 20), f"{px[1]:.0f} px", 15, QFont.Weight.Bold)
    text(p, QRectF(206, 80, 90, 16), size_text(log_mix(3900, 420, k)), 11, QFont.Weight.Normal, theme.DIM)
    done(p, t, 2.6, QPointF(220, 116))


def a_img_rotate(p, t, n, card):
    k = ease_back(phase(t, 0.9, 1.9), 1.2)
    with xf(p, 110, 75, 1.0, rot=-90 + 90 * k):
        landscape(p, QRectF(-56, -38, 112, 76))
    # the turn arrow
    a = phase(t, 0.4, 1.9)
    if 0 < a < 1:
        p.setPen(QPen(with_alpha(theme.ACCENT, math.sin(math.pi * a)), 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(42, 7, 136, 136), 60 * 16, -int(70 * 16 * a))
    text(p, QRectF(200, 50, 96, 22), "Turned right", 13, QFont.Weight.Bold, alpha=phase(t, 1.8, 2.2))
    text(p, QRectF(200, 72, 96, 18), "No quality lost", 10.5, QFont.Weight.Normal, theme.DIM, alpha=phase(t, 2.0, 2.4))
    done(p, t, 2.2, QPointF(214, 108))


def a_img_clean(p, t, n, card):
    landscape(p, QRectF(26, 34, 108, 80))
    labels = ["GPS 18.52° N", "Camera model", "Taken 09:41"]
    for i, lab in enumerate(labels):
        cut = phase(t, 1.0 + i * 0.4, 1.9 + i * 0.4)
        y = 30 + i * 36 + 60 * ease_in_out(cut) ** 2
        a = 1 - cut
        r = QRectF(176, y, 104, 24)
        p.save()
        p.setOpacity(p.opacity() * a)
        if cut == 0:
            p.setPen(QPen(with_alpha(theme.TEXT, 0.3), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(134, 74), QPointF(r.left(), r.center().y()))
        p.setPen(QPen(with_alpha(COL["pdf"], 0.5), 1))
        p.setBrush(mix(theme.SURFACE, COL["pdf"], 0.08))
        p.drawRoundedRect(r, 6, 6)
        text(p, r.adjusted(8, 0, 0, 0), lab, 10.5, QFont.Weight.DemiBold)
        p.restore()
    k = phase(t, 2.7, 3.2)
    text(p, QRectF(176, 58, 120, 22), "Nothing hidden", 13, QFont.Weight.Bold, alpha=k)
    done(p, t, 2.7, QPointF(160, 69), 20)


def a_img_stitch(p, t, n, card):
    k = ease_in_out(phase(t, 0.7, 2.2))
    for i in range(3):
        sx, sy = 40 + i * 62, 75
        ex, ey = 236, 33 + i * 42
        x, y = sx + (ex - sx) * k, sy + (ey - sy) * k
        g = 4 * (1 - phase(t, 2.2, 2.6))  # the gaps close
        r = QRectF(x - 24, y - 21 + (i - 1) * -g * 0, 48, 42 - g)
        p.setPen(QPen(with_alpha(COL["image"], 0.6), 1))
        p.setBrush(mix(theme.SURFACE, COL["image"], 0.22 + 0.1 * i))
        p.drawRoundedRect(r, 3, 3)
        lines(p, QRectF(r.left() + 6, r.top() + 7, r.width() - 12, r.height() - 16), with_alpha(theme.TEXT, 0.25), 3,
              h=3)
    m = phase(t, 2.5, 2.9)
    if m > 0:
        p.setPen(QPen(with_alpha(theme.ACCENT, m), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(210, 10, 52, 130), 4, 4)
        text(p, QRectF(20, 56, 160, 22), "3 screenshots", 13, QFont.Weight.Bold, alpha=m)
        text(p, QRectF(20, 78, 160, 18), "one long image", 11, QFont.Weight.Normal, theme.DIM, alpha=m)


def a_ocr(p, t, n, card):
    r = QRectF(22, 12, 100, 126)
    with xf(p, r.center().x(), r.center().y(), 1.0, rot=-3):
        rr = QRectF(-50, -63, 100, 126)
        p.setPen(QPen(with_alpha(theme.TEXT, 0.12), 1))
        p.setBrush(mix(theme.SURFACE, QColor(180, 170, 150), 0.18))
        p.drawRect(rr)
        scan = ease_in_out(phase(t, 0.5, 2.6))
        for i in range(7):
            y = -50 + i * 15
            seen = (y + 63) / 126 < scan
            p.setPen(QPen(with_alpha(theme.TEXT, 0.75 if seen else 0.22), 2.2 if seen else 3.2))
            w = 70 - (i * 13) % 30
            if seen:
                p.drawLine(QPointF(-40, y), QPointF(-40 + w, y))
            else:  # a blurry photo of text
                path = QPainterPath(QPointF(-40, y))
                for k in range(1, 9):
                    path.lineTo(QPointF(-40 + w * k / 8, y + (1.4 if k % 2 else -1.4)))
                p.drawPath(path)
        if 0 < scan < 1:
            y = -63 + 126 * scan
            p.setPen(QPen(theme.ACCENT, 2))
            p.drawLine(QPointF(-56, y), QPointF(56, y))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(theme.ACCENT, 0.12))
            p.drawRect(QRectF(-50, y - 14, 100, 14))
    # the text it found, appearing as the line passes
    found = ["Invoice 2611", "Asha Traders", "Total  4,200", "Due  12 Nov"]
    box = QRectF(150, 18, 134, 114)
    p.setPen(QPen(with_alpha(theme.TEXT, 0.14), 1))
    p.setBrush(theme.SURFACE)
    p.drawRoundedRect(box, 8, 8)
    for i, s in enumerate(found):
        a = phase(t, 0.8 + i * 0.45, 1.1 + i * 0.45)
        p.setFont(_mono(11))
        p.setPen(with_alpha(theme.TEXT, a))
        p.drawText(QRectF(box.left() + 10, box.top() + 10 + i * 22, box.width() - 14, 20),
                   Qt.AlignmentFlag.AlignVCenter, s)
    text(p, QRectF(box.left() + 10, box.bottom() - 18, 120, 14), "copy · search", 9.5, QFont.Weight.DemiBold,
         theme.ACCENT, alpha=phase(t, 2.7, 3.0))


def a_pdf_compress(p, t, n, card):
    k = ease_in_out(phase(t, 0.6, 2.4))
    with xf(p, 86, 74, 1 - 0.34 * k):
        page(p, QRectF(-38, -50, 76, 100), COL["pdf"], "PDF")
    squeeze = phase(t, 0.5, 2.5)
    if 0 < squeeze < 1:
        a = math.sin(math.pi * squeeze)
        off = 66 - 22 * k
        p.setPen(rpen(with_alpha(theme.ACCENT, a), 2.4))
        for side in (-1, 1):
            x = 86 + side * off
            for dy in (-14, 0, 14):
                p.drawLine(QPointF(x + side * 8, 74 + dy - 6), QPointF(x, 74 + dy))
                p.drawLine(QPointF(x + side * 8, 74 + dy + 6), QPointF(x, 74 + dy))
    kb = log_mix(4300, 380, k)
    text(p, QRectF(170, 28, 120, 28), size_text(kb), 22, QFont.Weight.Bold)
    bar = QRectF(172, 62, 104, 6)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.TRACK)
    p.drawRoundedRect(bar, 3, 3)
    p.setBrush(theme.SUCCESS if k > 0.98 else theme.ACCENT)
    p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(6.0, bar.width() * kb / 4300), bar.height()), 3, 3)
    text(p, QRectF(172, 74, 120, 16), "pages stay sharp", 10.5, QFont.Weight.Normal, theme.DIM)
    done(p, t, 2.5, QPointF(184, 112))
    text(p, QRectF(200, 102, 90, 20), "−91 %", 14, QFont.Weight.Bold, theme.SUCCESS, alpha=phase(t, 2.6, 3.0))


def a_pdf_merge(p, t, n, card):
    k = ease_in_out(phase(t, 0.6, 2.0))
    starts = [(50, 70, -8), (150, 70, 0), (250, 70, 8)]
    shades = [0.0, 0.08, 0.16]
    for i, (x, y, rot) in enumerate(starts):
        tx, ty = 150 + (i - 1) * 5, 66 + (i - 1) * 5
        with xf(p, x + (tx - x) * k, y + (ty - y) * k, 1.0 - 0.06 * k, rot=rot * (1 - k)):
            page(p, QRectF(-30, -40, 60, 80), COL["pdf"], "" if i < 2 else ("1 PDF" if k > 0.95 else "PDF"),
                 tint=shades[i])
    m = phase(t, 2.2, 2.6)
    tag(p, QPointF(232, 30), "3 files → 1", theme.ACCENT, m)
    text(p, QRectF(0, 124, 300, 18), "in the order you chose", 10, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=m)


def a_pdf_split(p, t, n, card):
    k = ease_back(phase(t, 0.8, 2.0), 1.1)
    for i in range(3):
        tx = 60 + i * 90
        x = 150 + (tx - 150) * k
        with xf(p, x + (i - 1) * 4 * (1 - k), 70 + (i - 1) * 4 * (1 - k), 1.0, rot=(i - 1) * 6 * (1 - k)):
            page(p, QRectF(-30, -40, 60, 80), COL["pdf"], f"p{i + 1}" if k > 0.9 else ("" if i < 2 else "PDF"))
    text(p, QRectF(0, 120, 300, 20), "every page, its own file", 10.5, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 2.1, 2.5))


def a_pdf_images(p, t, n, card):
    page(p, QRectF(26, 22, 72, 96), COL["pdf"], "PDF")
    for i in range(3):
        k = ease_out(phase(t, 0.7 + i * 0.45, 1.5 + i * 0.45))
        if k <= 0:
            continue
        sx, sy = 62, 66
        ex, ey = 150 + i * 50, 58
        x, y = sx + (ex - sx) * k, sy + (ey - sy) * k - math.sin(math.pi * k) * 22
        with xf(p, x, y, 0.5 + 0.5 * k):
            landscape(p, QRectF(-22, -28, 44, 56), mix(COL["image"], COL["pdf"], 0.25 * i))
        tag(p, QPointF(ex, 104), "PNG", COL["image"], phase(t, 1.5 + i * 0.45, 1.8 + i * 0.45))


def a_pdf_protect(p, t, n, card):
    lock = ease_out(phase(t, 2.0, 2.4))
    page(p, QRectF(48, 16, 86, 116), COL["pdf"], "PDF", tint=0.1 * lock)
    drop = ease_back(phase(t, 0.5, 1.2), 1.4)
    y = -30 + 100 * drop
    c = QPointF(91, y)
    shut = ease_in_out(phase(t, 1.5, 2.0))
    p.setPen(rpen(theme.TEXT, 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    lift = 9 * (1 - shut)
    p.drawArc(QRectF(c.x() - 12, c.y() - 28 - lift, 24, 30), 0, 180 * 16)
    p.drawLine(QPointF(c.x() + 12, c.y() - 13 - lift), QPointF(c.x() + 12, c.y() - 6 + 0 * lift))
    p.drawLine(QPointF(c.x() - 12, c.y() - 13 - lift), QPointF(c.x() - 12, c.y() - 13 - lift + 6))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(mix(theme.ACCENT, theme.TEXT, 0.25) if shut > 0.98 else theme.TEXT)
    p.drawRoundedRect(QRectF(c.x() - 19, c.y() - 8, 38, 30), 6, 6)
    p.setBrush(theme.SURFACE)
    p.drawEllipse(QPointF(c.x(), c.y() + 5), 3.5, 3.5)
    text(p, QRectF(160, 46, 130, 22), "Password set", 14, QFont.Weight.Bold, alpha=lock)
    text(p, QRectF(160, 68, 130, 18), "AES-256 encryption", 10.5, QFont.Weight.Normal, theme.DIM, alpha=lock)
    done(p, t, 2.3, QPointF(172, 104))


def a_pdf_numbers(p, t, n, card):
    for i in range(3):
        x = 58 + i * 92
        page(p, QRectF(x - 34, 14, 68, 92), COL["pdf"], "")
        k = ease_back(phase(t, 0.6 + i * 0.35, 1.0 + i * 0.35))
        if k > 0:
            with xf(p, x, 96, k):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.ACCENT)
                p.drawEllipse(QPointF(0, 0), 9, 9)
                text(p, QRectF(-9, -9, 18, 18), str(i + 1), 10, QFont.Weight.Bold, theme.ON_ACCENT,
                     Qt.AlignmentFlag.AlignCenter)
    w = phase(t, 1.9, 2.5)
    if w > 0:
        with xf(p, 150, 58, 1.0, rot=-14, alpha=w * 0.6):
            p.setFont(font(28, QFont.Weight.Black))
            p.setPen(COL["pdf"])
            p.drawText(QRectF(-150, -20, 300, 40), Qt.AlignmentFlag.AlignCenter, "D R A F T")
    text(p, QRectF(0, 122, 300, 20), "numbers and a watermark on every page", 10, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 2.4, 2.8))


def a_office_pdf(p, t, n, card):
    src = [("DOC", "doc", "lines"), ("XLS", "sheet", "grid"), ("PPT", "slides", "slides")][n % 3]
    k = ease_in_out(phase(t, 0.5, 2.6))
    x = 50 + 200 * k
    turned = clamp((x - 128) / 44)
    ring = QPointF(150, 66)
    p.setPen(QPen(with_alpha(theme.ACCENT, 0.22), 5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(ring, 46, 46)
    col = mix(COL[src[1]], COL["pdf"], turned)
    with xf(p, x, 66, 1.0):
        page(p, QRectF(-30, -40, 60, 80), col, src[0] if turned < 0.5 else "PDF", src[2])
    p.setPen(rpen(theme.ACCENT, 5))
    p.drawArc(QRectF(ring.x() - 46, ring.y() - 46, 92, 92), -60 * 16, 120 * 16)  # front of the ring
    text(p, QRectF(0, 122, 300, 20), "your own Office does it, so the layout is exact", 10, QFont.Weight.DemiBold,
         theme.DIM, Qt.AlignmentFlag.AlignCenter)


def a_ebook(p, t, n, card):
    c = QPointF(84, 70)
    p.setPen(QPen(with_alpha(theme.TEXT, 0.18), 1))
    p.setBrush(mix(theme.SURFACE, COL["book"], 0.08))
    left = QRectF(c.x() - 62, c.y() - 42, 60, 84)
    right = QRectF(c.x() + 2, c.y() - 42, 60, 84)
    p.drawRect(left)
    p.drawRect(right)
    lines(p, left.adjusted(8, 12, -8, -36), with_alpha(theme.TEXT, 0.2), 4, h=3)
    lines(p, right.adjusted(8, 12, -8, -36), with_alpha(theme.TEXT, 0.2), 4, h=3)
    p.setBrush(COL["book"])
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(QRectF(c.x() - 64, c.y() + 42, 128, 5))
    for f in range(2):  # two pages turn
        k = phase(t, 0.4 + f * 0.8, 1.1 + f * 0.8)
        if 0 < k < 1:
            sx = math.cos(math.pi * k)
            with xf(p, c.x(), c.y(), 1.0, sx=sx):
                p.setPen(QPen(with_alpha(theme.TEXT, 0.2), 1))
                p.setBrush(mix(theme.SURFACE, COL["book"], 0.14))
                p.drawRect(QRectF(0, -42, 60, 84))
    arrow(p, 156, 198, 70, t, phase(t, 1.8, 2.1))
    m = ease_back(phase(t, 2.0, 2.5))
    if m > 0:
        with xf(p, 242, 70, m):
            page(p, QRectF(-34, -46, 68, 92), COL["pdf"], "PDF")
    text(p, QRectF(196, 124, 100, 18), "ready to print", 10, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 2.5, 2.9))


def a_sheet_csv(p, t, n, card):
    k = ease_in_out(phase(t, 1.2, 1.9))
    g = QRectF(28, 18, 244, 100)
    rows, cols = 4, 3
    vals = [["Name", "City", "Paid"], ["Asha", "Pune", "4200"], ["Ravi", "Delhi", "1350"], ["Mei", "Goa", "980"]]
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(with_alpha(COL["sheet"], 0.16 * (1 - k)))
    p.drawRect(QRectF(g.left(), g.top(), g.width(), g.height() / rows))
    p.setPen(QPen(with_alpha(COL["sheet"], 0.55 * (1 - k)), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(g)
    for c in range(1, cols):
        x = g.left() + g.width() * c / cols
        p.drawLine(QPointF(x, g.top()), QPointF(x, g.bottom()))
    for r in range(1, rows):
        y = g.top() + g.height() * r / rows
        p.drawLine(QPointF(g.left(), y), QPointF(g.right(), y))
    p.setFont(_mono(12))
    for r in range(rows):
        y = g.top() + g.height() * r / rows
        cell_h = g.height() / rows
        # grid layout fades into comma-separated lines, in place
        p.setPen(with_alpha(theme.TEXT, clamp(1 - 2 * k)))
        for c in range(cols):
            p.drawText(QRectF(g.left() + g.width() * c / cols + 10, y, g.width() / cols - 12, cell_h),
                       Qt.AlignmentFlag.AlignVCenter, vals[r][c])
        p.setPen(with_alpha(theme.TEXT, clamp(2 * k - 1)))
        p.drawText(QRectF(g.left() + 10, y, g.width() - 12, cell_h), Qt.AlignmentFlag.AlignVCenter, ",".join(vals[r]))
    swap_tag(p, QPointF(118, 134), "XLSX", COL["sheet"], "CSV", theme.ACCENT, k)
    text(p, QRectF(150, 124, 140, 20), "every value exact", 10, QFont.Weight.DemiBold, theme.DIM, alpha=k)


def a_json_yaml(p, t, n, card):
    left = QRectF(12, 12, 138, 112)
    right = QRectF(160, 12, 128, 112)
    for r in (left, right):
        p.setPen(QPen(with_alpha(theme.TEXT, 0.14), 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, 8, 8)
    js = ["{", ' "name": "Asha",', ' "city": "Pune",', ' "pets": 2', "}"]
    ym = ["name: Asha", "city: Pune", "pets: 2"]
    p.setFont(_mono(11))
    cur = int(phase(t, 0.6, 2.4) * 3.999)
    active = 0.6 <= t < 2.6
    for i, s in enumerate(js):
        y = left.top() + 10 + i * 19
        if active and i == cur + 1:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(theme.ACCENT, 0.16))
            p.drawRoundedRect(QRectF(left.left() + 4, y, left.width() - 8, 18), 4, 4)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(left.left() + 8, y, left.width() - 10, 18), Qt.AlignmentFlag.AlignVCenter, s)
    for i, s in enumerate(ym):
        a = phase(t, 0.8 + i * 0.6, 1.1 + i * 0.6)
        p.setPen(with_alpha(theme.TEXT, a))
        p.drawText(QRectF(right.left() + 10, right.top() + 29 + i * 19, right.width() - 12, 18),
                   Qt.AlignmentFlag.AlignVCenter, s)
    tag(p, QPointF(81, 136), "JSON", COL["data"])
    tag(p, QPointF(224, 136), "YAML", theme.ACCENT, phase(t, 2.4, 2.8))


def a_contacts(p, t, n, card):
    people = [("Asha", "98201 44120"), ("Ravi", "99870 12001"), ("Mei", "90040 77310")]
    k = ease_in_out(phase(t, 0.9, 2.3))
    for i, (name, num) in enumerate(people):
        sx, sy = 24 + i * 92, 14
        ex, ey = 24, 36 + i * 30
        x, y = sx + (ex - sx) * k, sy + (ey - sy) * k
        w = 80 + (252 - 80) * k
        h = 54 - 28 * k
        r = QRectF(x, y, w, h)
        p.setPen(QPen(with_alpha(theme.TEXT, 0.14), 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, 6, 6)
        av = QPointF(r.left() + 14, r.top() + (14 if k < 0.5 else h / 2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(COL["data"], 0.7))
        p.drawEllipse(av, 8, 8)
        text(p, QRectF(r.left() + 28, r.top() + 4, 50, 18), name, 11, QFont.Weight.DemiBold, alpha=1 - 2 * k)
        text(p, QRectF(r.left() + 30, r.top(), 220, h), f"{name}, {num}, {name.lower()}@mail.com", 10.5,
             QFont.Weight.Normal, alpha=2 * k - 1)
    swap_tag(p, QPointF(150, 134), "VCF", COL["data"], "CSV", theme.ACCENT, k)


def a_audio(p, t, n, card):
    k = ease_in_out(phase(t, 0.8, 2.6))
    sweep = 20 + 190 * k
    for i in range(34):
        x = 20 + i * 5.6
        env = math.sin(math.pi * (i + 0.5) / 34) ** 0.7
        h = 6 + 46 * env * (0.45 + 0.55 * abs(math.sin(i * 0.9 + t * 4.2)))
        done_ = x < sweep
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.ACCENT if done_ else with_alpha(COL["audio"], 0.7))
        w = 2.4 if done_ else 3.4
        p.drawRoundedRect(QRectF(x - w / 2, 66 - h / 2, w, h), w / 2, w / 2)
    mb = log_mix(42, 3.9, k)
    text(p, QRectF(216, 34, 84, 26), f"{mb:.1f} MB", 17, QFont.Weight.Bold)
    swap_tag(p, QPointF(244, 76), "WAV", COL["audio"], "MP3", theme.ACCENT, k)
    text(p, QRectF(0, 116, 300, 20), "same length, checked to the second", 10, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter)


def a_video_sound(p, t, n, card):
    strip = QRectF(14, 16, 272, 50)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(mix(theme.TEXT, COL["video"], 0.25))
    p.drawRoundedRect(strip, 4, 4)
    off = (t * 34) % 54
    p.save()
    p.setClipRect(strip)
    for i in range(7):
        x = strip.left() - off + i * 54
        p.setBrush(mix(COL["video"], QColor(255, 255, 255), 0.3 + 0.1 * (i % 3)))
        p.drawRect(QRectF(x + 6, strip.top() + 10, 42, 30))
        p.setBrush(theme.SURFACE)
        for hx in range(3):
            p.drawRect(QRectF(x + 8 + hx * 16, strip.top() + 3, 6, 4))
            p.drawRect(QRectF(x + 8 + hx * 16, strip.bottom() - 7, 6, 4))
    p.restore()
    k = ease_in_out(phase(t, 0.8, 2.6))
    edge = 14 + 272 * k
    for i in range(48):
        x = 18 + i * 5.6
        if x > edge:
            break
        h = 4 + 26 * abs(math.sin(i * 0.7 + t * 3.0)) * (0.5 + 0.5 * math.sin(i * 0.23) ** 2)
        p.setBrush(theme.ACCENT)
        p.drawRoundedRect(QRectF(x - 1.3, 100 - h / 2, 2.6, h), 1.3, 1.3)
    tag(p, QPointF(40, 136), "MP4", COL["video"])
    tag(p, QPointF(260, 136), "MP3", theme.ACCENT, phase(t, 2.4, 2.8))
    text(p, QRectF(70, 128, 160, 18), "picture left out, sound kept", 10, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 1.0, 1.4))


def a_subtitles(p, t, n, card):
    screen = QRectF(14, 12, 150, 88)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(28, 30, 36))
    p.drawRoundedRect(screen, 6, 6)
    cues = [(0.3, 1.6, "Where are we going?"), (1.9, 3.2, "Somewhere new."), (3.5, 4.6, "Bring snacks!")]
    for a, b, s in cues:
        if a <= t < b:
            text(p, QRectF(screen.left(), screen.bottom() - 26, screen.width(), 20), s, 10.5, QFont.Weight.DemiBold,
                 QColor(255, 255, 255), Qt.AlignmentFlag.AlignCenter)
    line = QRectF(14, 112, 150, 6)
    p.setBrush(theme.TRACK)
    p.drawRoundedRect(line, 3, 3)
    for a, b, _ in cues:
        p.setBrush(with_alpha(COL["sub"], 0.8))
        p.drawRoundedRect(QRectF(line.left() + line.width() * a / LOOP, line.top(), line.width() * (b - a) / LOOP, 6),
                          3, 3)
    p.setBrush(theme.TEXT)
    p.drawRect(QRectF(line.left() + line.width() * t / LOOP - 1, line.top() - 5, 2, 16))
    code = QRectF(176, 12, 112, 106)
    p.setPen(QPen(with_alpha(theme.TEXT, 0.14), 1))
    p.setBrush(theme.SURFACE)
    p.drawRoundedRect(code, 8, 8)
    k = phase(t, 1.4, 2.2)
    p.setFont(_mono(10))
    p.setPen(with_alpha(theme.ACCENT, k))
    p.drawText(QRectF(code.left() + 8, code.top() + 8, 100, 16), Qt.AlignmentFlag.AlignVCenter, "WEBVTT")
    for i, (stamp_a, stamp_b) in enumerate((("00:01,200", "00:01.200"), ("00:04,800", "00:04.800"))):
        y = code.top() + 30 + i * 36
        p.setPen(with_alpha(theme.TEXT, clamp(1 - 2 * k)))
        p.drawText(QRectF(code.left() + 8, y, 104, 16), Qt.AlignmentFlag.AlignVCenter, stamp_a)
        p.setPen(with_alpha(theme.TEXT, clamp(2 * k - 1)))
        p.drawText(QRectF(code.left() + 8, y, 104, 16), Qt.AlignmentFlag.AlignVCenter, stamp_b)
        lines(p, QRectF(code.left() + 8, y + 19, 80, 3), with_alpha(theme.TEXT, 0.2), 1, h=3)
    swap_tag(p, QPointF(206, 134), "SRT", COL["sub"], "VTT", theme.ACCENT, k)
    text(p, QRectF(226, 126, 70, 16), "timings kept", 9.5, QFont.Weight.DemiBold, theme.DIM, alpha=k)


def a_markdown(p, t, n, card):
    left = QRectF(12, 14, 128, 106)
    right = QRectF(160, 14, 128, 106)
    p.setPen(QPen(with_alpha(theme.TEXT, 0.14), 1))
    p.setBrush(theme.SURFACE)
    p.drawRoundedRect(left, 8, 8)
    raw = ["# Trip notes", "- **Pack** light", "- Book *hotel*", "- Call Ravi"]
    p.setFont(_mono(10.5))
    cur = int(phase(t, 0.6, 2.6) * 3.999)
    for i, s in enumerate(raw):
        y = left.top() + 12 + i * 22
        if 0.6 <= t < 2.8 and i == cur:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(theme.ACCENT, 0.16))
            p.drawRoundedRect(QRectF(left.left() + 4, y - 1, left.width() - 8, 20), 4, 4)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(left.left() + 8, y, left.width() - 10, 18), Qt.AlignmentFlag.AlignVCenter, s)
    page(p, right, COL["pdf"], "", "none")
    a0 = phase(t, 0.7, 1.0)
    text(p, QRectF(right.left() + 12, right.top() + 10, 110, 22), "Trip notes", 15, QFont.Weight.Bold, alpha=a0)
    items = [("Pack", " light", QFont.Weight.Bold), ("Book ", "hotel", QFont.Weight.Normal), ("Call Ravi", "", None)]
    for i, (a, b, wt) in enumerate(items):
        al = phase(t, 1.2 + i * 0.5, 1.5 + i * 0.5)
        y = right.top() + 40 + i * 20
        p.save()
        p.setOpacity(p.opacity() * al)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.TEXT)
        p.drawEllipse(QPointF(right.left() + 16, y + 9), 2, 2)
        f1 = font(11, wt or QFont.Weight.Normal)
        if i == 1:
            f2 = font(11)
            f2.setItalic(True)
        else:
            f2 = font(11)
        p.setFont(f1)
        p.setPen(theme.TEXT)
        w1 = QFontMetricsF(f1).horizontalAdvance(a)
        p.drawText(QRectF(right.left() + 24, y, 100, 18), Qt.AlignmentFlag.AlignVCenter, a)
        p.setFont(f2)
        p.drawText(QRectF(right.left() + 24 + w1, y, 100, 18), Qt.AlignmentFlag.AlignVCenter, b)
        p.restore()
    tag(p, QPointF(76, 136), "MD", COL["md"])
    tag(p, QPointF(224, 136), "PDF", COL["pdf"], phase(t, 2.6, 3.0))


def a_mail(p, t, n, card):
    env = QRectF(30, 58, 120, 76)
    open_ = ease_in_out(phase(t, 0.4, 1.0))
    rise = ease_out(phase(t, 1.0, 1.8))
    fly = ease_in_out(phase(t, 2.0, 2.8))
    edge = QPen(with_alpha(theme.TEXT, 0.18), 1)

    def letter():
        lx = env.center().x() + (238 - env.center().x()) * fly
        ly = env.top() + 46 - 52 * rise
        with xf(p, lx, ly, 1.0):
            page(p, QRectF(-36, -40, 72, 84), COL["pdf"] if fly > 0.5 else COL["mail"],
                 "PDF" if fly > 0.5 else "", "lines")

    p.setPen(edge)
    p.setBrush(mix(theme.SURFACE, COL["mail"], 0.25))
    p.drawRect(env)
    if fly <= 0:  # still inside: only the part above the pocket shows
        p.save()
        p.setClipRect(QRectF(0, 0, 300, env.top() + 20))
        letter()
        p.restore()
    front = QPainterPath()
    front.moveTo(env.left(), env.top() + 20)
    front.lineTo(env.center().x(), env.top() + 50)
    front.lineTo(env.right(), env.top() + 20)
    front.lineTo(env.right(), env.bottom())
    front.lineTo(env.left(), env.bottom())
    front.closeSubpath()
    p.setPen(edge)
    p.setBrush(mix(theme.SURFACE, COL["mail"], 0.32))
    p.drawPath(front)
    flap = QPainterPath()
    flap.moveTo(env.left(), env.top())
    flap.lineTo(env.center().x(), env.top() + 44 * (1 - 2 * open_))
    flap.lineTo(env.right(), env.top())
    flap.closeSubpath()
    p.setBrush(mix(theme.SURFACE, COL["mail"], 0.45))
    p.drawPath(flap)
    if fly > 0:
        letter()
    tag(p, QPointF(90, 142), "EML", COL["mail"])
    text(p, QRectF(196, 124, 100, 18), "printable, searchable", 9.5, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 2.7, 3.1))


def a_map(p, t, n, card):
    area = QRectF(12, 10, 276, 118)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(mix(theme.SURFACE, COL["map"], 0.08))
    p.drawRoundedRect(area, 8, 8)
    p.setBrush(with_alpha(COL["map"], 0.16))
    p.drawRoundedRect(QRectF(40, 20, 60, 40), 6, 6)
    p.drawRoundedRect(QRectF(196, 74, 70, 44), 6, 6)
    p.setPen(QPen(with_alpha(theme.TEXT, 0.08), 6))
    p.drawLine(QPointF(12, 88), QPointF(288, 60))
    p.drawLine(QPointF(150, 10), QPointF(170, 128))
    pts = [(30, 110), (70, 96), (96, 70), (140, 74), (170, 46), (214, 40), (246, 58), (268, 30)]
    path = QPainterPath(QPointF(*pts[0]))
    for a, b in zip(pts[1::2], pts[2::2]):
        path.quadTo(QPointF(*a), QPointF(*b))
    k = ease_in_out(phase(t, 0.4, 2.4))
    steps = 60
    draw = QPainterPath(path.pointAtPercent(0))
    for i in range(1, int(steps * k) + 1):
        draw.lineTo(path.pointAtPercent(i / steps))
    p.setPen(rpen(theme.ACCENT, 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(draw)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.ACCENT)
    p.drawEllipse(path.pointAtPercent(0), 4, 4)
    pin = ease_back(phase(t, 2.4, 2.8))
    if pin > 0:
        end = path.pointAtPercent(1)
        with xf(p, end.x(), end.y(), pin):
            pp = QPainterPath()
            pp.moveTo(0, 0)
            pp.cubicTo(-12, -14, -9, -26, 0, -26)
            pp.cubicTo(9, -26, 12, -14, 0, 0)
            p.setBrush(COL["pdf"])
            p.drawPath(pp)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(0, -17), 3.5, 3.5)
    tag(p, QPointF(40, 140), "GPX", COL["map"])
    tag(p, QPointF(92, 140), "KML", theme.ACCENT, phase(t, 2.4, 2.8))
    text(p, QRectF(120, 132, 176, 16), "every point kept", 10, QFont.Weight.DemiBold, theme.DIM, alpha=phase(t, 2.6, 3.0))


def a_model3d(p, t, n, card):
    c = QPointF(110, 62)
    ang = t * 0.9
    tilt = 0.5
    s = 30
    verts = []
    for x in (-1, 1):
        for y in (-1, 1):
            for z in (-1, 1):
                xr = x * math.cos(ang) - z * math.sin(ang)
                zr = x * math.sin(ang) + z * math.cos(ang)
                yr = y * math.cos(tilt) - zr * math.sin(tilt)
                zz = y * math.sin(tilt) + zr * math.cos(tilt)
                f = 3.2 / (3.2 + zz)
                verts.append((QPointF(c.x() + xr * s * f, c.y() + yr * s * f), zz))
    faces = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    shade = phase(t, 1.6, 2.4)
    if shade > 0:
        order = sorted(faces, key=lambda f: -sum(verts[i][1] for i in f))
        for k, f in enumerate(order):
            path = QPainterPath(verts[f[0]][0])
            for i in f[1:]:
                path.lineTo(verts[i][0])
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(mix(COL["model"], QColor(255, 255, 255), 0.15 * k), shade))
            p.drawPath(path)
    p.setPen(QPen(with_alpha(theme.ACCENT, 1 - 0.6 * shade), 1.6))
    for a, b in ((0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)):
        p.drawLine(verts[a][0], verts[b][0])
    for i, name in enumerate(("OBJ", "PLY", "GLB", "PNG")):
        tag(p, QPointF(232, 28 + i * 28), name, theme.ACCENT if i == n % 4 else COL["model"],
            phase(t, 0.8 + i * 0.2, 1.1 + i * 0.2))
    tag(p, QPointF(110, 136), "STL", COL["model"])


def a_cad(p, t, n, card):
    paper = phase(t, 2.6, 3.2)
    area = QRectF(12, 10, 186, 128)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(mix(mix(QColor(20, 50, 90), COL["cad"], 0.2), theme.SURFACE, paper))
    p.drawRoundedRect(area, 6, 6)
    ink = mix(QColor(200, 230, 255), theme.TEXT, paper)
    if paper < 1:
        p.setPen(QPen(with_alpha(QColor(255, 255, 255), 0.07 * (1 - paper)), 1))
        for x in range(22, 198, 14):
            p.drawLine(QPointF(x, 10), QPointF(x, 138))
        for y in range(20, 138, 14):
            p.drawLine(QPointF(12, y), QPointF(198, y))
    segs = [((30, 30), (180, 30)), ((180, 30), (180, 118)), ((180, 118), (30, 118)), ((30, 118), (30, 30)),
            ((110, 30), (110, 80)), ((110, 96), (110, 118)), ((30, 74), (80, 74))]
    total = sum(math.dist(a, b) for a, b in segs)
    k = ease_in_out(phase(t, 0.3, 2.3)) * total
    p.setPen(rpen(ink, 2))
    for a, b in segs:
        d = math.dist(a, b)
        if k <= 0:
            break
        f = min(1.0, k / d)
        p.drawLine(QPointF(*a), QPointF(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        k -= d
    door = phase(t, 2.2, 2.6)
    if door > 0:
        p.setPen(QPen(ink, 1.2, Qt.PenStyle.DashLine))
        p.drawArc(QRectF(94, 64, 32, 32), 90 * 16, int(-90 * 16 * door))
    for i, name in enumerate(("SVG", "PDF", "PNG")):
        tag(p, QPointF(248, 40 + i * 32), name, theme.ACCENT if i == n % 3 else COL["cad"],
            phase(t, 2.6 + i * 0.15, 2.9 + i * 0.15))
    tag(p, QPointF(248, 134), "DXF", COL["cad"])


def a_vector(p, t, n, card):
    c = QPointF(100, 72)
    edge = 30 + 140 * ease_in_out(phase(t, 0.8, 2.6))
    shape = QPainterPath()
    shape.addEllipse(QPointF(c.x() - 16, c.y()), 40, 40)
    star = QPainterPath()
    for i in range(10):
        r = 36 if i % 2 == 0 else 15
        a = -math.pi / 2 + i * math.pi / 5
        pt = QPointF(c.x() + 24 + r * math.cos(a), c.y() + 8 + r * math.sin(a))
        (star.moveTo if i == 0 else star.lineTo)(pt)
    star.closeSubpath()
    p.save()
    p.setClipRect(QRectF(edge, 0, 300, 150))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(with_alpha(COL["font"], 0.55))
    p.drawPath(shape)
    p.setBrush(theme.ACCENT)
    p.drawPath(star)
    p.restore()
    cell = 7.0
    p.setPen(Qt.PenStyle.NoPen)
    x = 30.0
    while x < edge:
        y = 20.0
        while y < 130:
            ctr = QPointF(x + cell / 2, y + cell / 2)
            if star.contains(ctr):
                p.setBrush(theme.ACCENT)
                p.drawRect(QRectF(x, y, cell - 0.6, cell - 0.6))
            elif shape.contains(ctr):
                p.setBrush(with_alpha(COL["font"], 0.55))
                p.drawRect(QRectF(x, y, cell - 0.6, cell - 0.6))
            y += cell
        x += cell
    if edge < 170:
        p.setPen(QPen(with_alpha(theme.TEXT, 0.4), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(edge, 18), QPointF(edge, 132))
    swap_tag(p, QPointF(232, 50), "SVG", COL["font"], "PNG", theme.ACCENT, phase(t, 2.4, 2.8))
    text(p, QRectF(196, 70, 100, 18), "any size you like", 10, QFont.Weight.DemiBold, theme.DIM, alpha=phase(t, 2.6, 3))


def a_font(p, t, n, card):
    k = ease_out(phase(t, 0.5, 1.5))
    base, xh, cap = 96.0, 66.0, 40.0
    p.setPen(QPen(with_alpha(theme.ACCENT, 0.5), 1, Qt.PenStyle.DashLine))
    for y in (base, xh, cap):
        p.drawLine(QPointF(16, y), QPointF(16 + 168 * k, y))
    f = QFont("Georgia")
    f.setPixelSize(74)
    p.setFont(f)
    p.setPen(theme.TEXT)
    p.drawText(QRectF(16, 18, 170, 100), Qt.AlignmentFlag.AlignCenter, "Ag")
    m = phase(t, 1.8, 2.4)
    swap_tag(p, QPointF(234, 40), "TTF", COL["font"], "WOFF", theme.ACCENT, m)
    text(p, QRectF(194, 60, 104, 18), "for websites", 10.5, QFont.Weight.DemiBold, theme.DIM, alpha=m)
    f2 = QFont("Georgia")
    f2.setPixelSize(12)
    p.save()
    p.setOpacity(p.opacity() * phase(t, 2.4, 2.9))
    p.setFont(f2)
    p.drawText(QRectF(16, 118, 280, 20), Qt.AlignmentFlag.AlignVCenter, "The quick brown fox jumps over the lazy dog")
    p.restore()


def a_zip(p, t, n, card):
    box = QRectF(206, 70, 76, 58)
    lid = ease_in_out(phase(t, 2.3, 2.7))
    kinds = [("image", "image"), ("doc", "lines"), ("pdf", "lines"), ("sheet", "grid")]
    for i, (col, body) in enumerate(kinds):
        k = ease_in_out(phase(t, 0.4 + i * 0.35, 1.2 + i * 0.35))
        sx, sy = 30 + i * 44, 40
        ex, ey = box.center().x(), box.top() + 18
        x, y = sx + (ex - sx) * k, sy + (ey - sy) * k - math.sin(math.pi * k) * 30
        if k < 1:
            with xf(p, x, y, 1 - 0.5 * k):
                page(p, QRectF(-16, -21, 32, 42), COL[col], "", body)
    p.setPen(QPen(with_alpha(theme.TEXT, 0.2), 1))
    p.setBrush(mix(theme.SURFACE, COL["zip"], 0.3))
    p.drawRect(box)
    with xf(p, box.left(), box.top(), 1.0, rot=-70 * (1 - lid)):
        p.setBrush(mix(theme.SURFACE, COL["zip"], 0.45))
        p.drawRect(QRectF(0, -8, box.width(), 8))
    tag(p, QPointF(box.center().x(), box.center().y() + 6), "ZIP", COL["zip"], lid)
    text(p, QRectF(18, 92, 180, 20), "4 files  ·  2.1 MB → 0.9 MB", 11, QFont.Weight.DemiBold, alpha=phase(t, 2.6, 3))


def a_unzip(p, t, n, card):
    box = QRectF(20, 70, 76, 58)
    lid = ease_in_out(phase(t, 0.3, 0.8))
    p.setPen(QPen(with_alpha(theme.TEXT, 0.2), 1))
    p.setBrush(mix(theme.SURFACE, COL["zip"], 0.3))
    kinds = [("image", "image"), ("doc", "lines"), ("pdf", "lines"), ("sheet", "grid"), ("audio", "lines"),
             ("slides", "slides")]
    for i, (col, body) in enumerate(kinds):
        k = ease_out(phase(t, 0.8 + i * 0.25, 1.6 + i * 0.25))
        if k <= 0:
            continue
        sx, sy = box.center().x(), box.top() + 10
        ex, ey = 140 + (i % 3) * 52, 38 + (i // 3) * 58
        x, y = sx + (ex - sx) * k, sy + (ey - sy) * k - math.sin(math.pi * k) * 26
        with xf(p, x, y, 0.5 + 0.5 * k):
            page(p, QRectF(-17, -23, 34, 46), COL[col], "", body)
    p.setPen(QPen(with_alpha(theme.TEXT, 0.2), 1))
    p.setBrush(mix(theme.SURFACE, COL["zip"], 0.3))
    p.drawRect(box)
    with xf(p, box.left(), box.top(), 1.0, rot=-70 * lid):
        p.setBrush(mix(theme.SURFACE, COL["zip"], 0.45))
        p.drawRect(QRectF(0, -8, box.width(), 8))
    tag(p, QPointF(box.center().x(), box.center().y() + 6), "7Z", COL["zip"])
    text(p, QRectF(20, 26, 90, 18), "into a folder", 10.5, QFont.Weight.DemiBold, theme.DIM, alpha=phase(t, 2.4, 2.8))


def a_generic(p, t, n, card):
    """For any kind of file without its own story yet: in, through Tapshift, out."""
    src = card.src or "FILE"
    outs = card.cycle or ["NEW"]
    out = outs[n % len(outs)]
    k = ease_in_out(phase(t, 0.6, 2.4))
    with xf(p, 70 + 160 * k, 66, 1.0):
        page(p, QRectF(-30, -40, 60, 80), mix(COL["md"], theme.ACCENT, k), src if k < 0.5 else out[:6])
    p.setPen(QPen(with_alpha(theme.ACCENT, 0.3), 6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(150, 66), 40, 40)


STORIES = {name[2:]: fn for name, fn in globals().items() if name.startswith("a_")}

# (world, story, title, caption). Worlds come from universe.gather(); a world with no story
# here still gets a card (the generic one), so new kinds of files always show up.
CARDS = [
    ("pictures", "img_convert", "Any photo, any format", "iPhone HEIC to JPG, PNG, WEBP, AVIF and more."),
    ("pictures", "img_form", "Photo under 50 KB", "Exact size and pixels for upload forms."),
    ("pictures", "img_resize", "Resize", "Smaller pictures for mail and chat."),
    ("pictures", "img_rotate", "Turn and flip", "Sideways photos, fixed for good."),
    ("pictures", "img_clean", "Remove hidden info", "Location, camera and dates, stripped out."),
    ("pictures", "img_stitch", "Stitch screenshots", "Several pictures become one long image."),
    ("pictures", "ocr", "Read text from a picture", "Photos of pages become text you can copy."),
    ("pdf", "pdf_compress", "Compress a PDF", "Smaller for mail and portals."),
    ("pdf", "pdf_merge", "Merge PDFs", "Several files, one document."),
    ("pdf", "pdf_split", "Split pages", "Every page becomes its own file."),
    ("pdf", "pdf_images", "Pages as pictures", "Each page saved as PNG or JPG."),
    ("pdf", "pdf_protect", "Lock with a password", "Strong encryption; unlock again any time."),
    ("pdf", "pdf_numbers", "Page numbers and watermarks", "Stamped on every page."),
    ("office", "office_pdf", "Word, Excel, PowerPoint to PDF", "DOCX, XLSX and PPTX, as PDF."),
    ("ebooks", "ebook", "E-books to PDF", "EPUB, MOBI, FB2 and comics."),
    ("data", "sheet_csv", "Sheets to CSV", "Spreadsheets to plain, portable text."),
    ("data", "json_yaml", "JSON, YAML, TOML, XML", "Data files, rewritten line by line."),
    ("data", "contacts", "Contacts to a sheet", "vCard files become rows you can sort."),
    ("sound", "audio", "WAV to MP3", "Music and recordings, a tenth of the size."),
    ("sound", "video_sound", "Sound from a video", "Keep just the audio of a clip."),
    ("subtitles", "subtitles", "Subtitles, any format", "SRT, VTT, ASS and more."),
    ("text", "markdown", "Markdown to a document", "Notes become a clean PDF or web page."),
    ("mail", "mail", "Saved e-mails to PDF", "EML and MHTML, printable and searchable."),
    ("maps", "map", "GPS tracks", "GPX, KML, GeoJSON and more."),
    ("models", "model3d", "3D models", "STL, OBJ, PLY, glTF, plus a picture of it."),
    ("drawings", "cad", "CAD plans", "DXF drawings to SVG, PDF or PNG."),
    ("drawings", "vector", "Vector to picture", "SVG and AI artwork as PNG."),
    ("fonts", "font", "Fonts", "Desktop fonts to web fonts and back."),
    ("archives", "zip", "Pack into ZIP or 7Z", "Many files, one small archive."),
    ("archives", "unzip", "Unpack anything", "ZIP, 7Z, RAR, TAR, opened in place."),
]


def _short_formats(labels: list[str]) -> list[str]:
    """Format-like labels (JPG, PNG...) out of a world's actions, as the picker names them."""
    out = [s for s in labels if s.isupper() and 2 <= len(s) <= 5]
    return out or labels[:4]


# ====================================================================== widgets


class ShowCard(QWidget):
    """One animated card. Paints itself; the gallery decides when it needs a new frame."""

    def __init__(self, story, title: str, caption: str, offset: float, cycle=None, src: str = "", parent=None):
        super().__init__(parent)
        self.story, self.title, self.caption, self.offset = story, title, caption, offset
        self.cycle, self.src = cycle or [], src
        self.now = 0.0
        self.hot = False
        self.setFixedSize(QSize(CARD_W, CARD_H))
        self.f_title = font(14, QFont.Weight.DemiBold)
        self.f_cap = font(12)

    def enterEvent(self, _):
        self.hot = True
        self.update()

    def leaveEvent(self, _):
        self.hot = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(theme.ACCENT if self.hot else theme.LINE, 1.4 if self.hot else 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, theme.RADIUS_CARD, theme.RADIUS_CARD)
        art = QRectF(10, 10, ART_W * ART_S, ART_H * ART_S)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.BG)
        p.drawRoundedRect(art, 8, 8)
        tt = self.now + self.offset
        n, t = int(tt // LOOP), tt % LOOP
        p.save()
        p.setClipRect(art)
        p.translate(art.topLeft())
        p.scale(ART_S, ART_S)
        # a soft fade between loops, so the restart never jumps
        p.setOpacity(ease_out(phase(t, 0.0, 0.3)) * (1 - ease_in_out(phase(t, LOOP - 0.45, LOOP))))
        try:
            self.story(p, t, n, self)
        except Exception:  # noqa: BLE001 - one broken drawing must not break the tour
            pass
        p.restore()
        p.setFont(self.f_title)
        p.setPen(theme.TEXT)
        y = art.bottom()
        p.drawText(QRectF(14, y + 8, CARD_W - 28, 22), Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setFont(self.f_cap)
        p.setPen(theme.DIM)
        p.drawText(QRectF(14, y + 32, CARD_W - 28, 36), WRAP, self.caption)
        p.end()


class Gallery(QWidget):
    """Sections (one per world) of cards, flowed into as many columns as fit."""

    def __init__(self, worlds, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.sections: list[tuple[QLabel, list[ShowCard]]] = []
        by_world: dict[str, list] = {}
        for w, story, title, cap in CARDS:
            by_world.setdefault(w, []).append((story, title, cap))
        k = 0
        for world in worlds:
            entries = by_world.get(world.key) or [("generic", world.title, world.tagline)]
            head = QLabel(f"<b>{world.title}</b> &nbsp;<span style='color:{theme.rgba(theme.DIM)}'>"
                          f"{len(world.exts)} file types in · {len(world.actions)} ways out</span>", self)
            head.setFont(font(15))
            head.setStyleSheet(f"color: {theme.rgba(theme.TEXT)}; background: transparent;")
            cards = []
            for story, title, cap in entries:
                card = ShowCard(STORIES.get(story, a_generic), title, cap, offset=(k * 0.61) % LOOP,
                                cycle=_short_formats(world.actions), src=(world.exts or ["FILE"])[0], parent=self)
                cards.append(card)
                k += 1
            self.sections.append((head, cards))

    @property
    def cards(self) -> list[ShowCard]:
        return [c for _, cs in self.sections for c in cs]

    def flow(self, width: int) -> None:
        cols = max(1, (width + GAP) // (CARD_W + GAP))
        x0 = max(0, (width - (cols * CARD_W + (cols - 1) * GAP)) // 2)
        y = 0
        for head, cards in self.sections:
            head.setGeometry(x0, y + 8, width - x0, 26)
            y += 42
            for i, c in enumerate(cards):
                c.move(x0 + (i % cols) * (CARD_W + GAP), y + (i // cols) * (CARD_H + GAP))
            y += ((len(cards) + cols - 1) // cols) * (CARD_H + GAP) + 6
        self.setFixedSize(width, y + 10)


class Showcase(QScrollArea):
    """The scrolling gallery. One 30 fps clock; only cards on screen are redrawn."""

    FPS = 30

    def __init__(self, worlds, parent=None):
        super().__init__(parent)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(scroll_qss())
        self.viewport().setAutoFillBackground(False)
        self.gallery = Gallery(worlds)
        self.setWidget(self.gallery)
        self.setWidgetResizable(False)
        self.verticalScrollBar().setSingleStep(40)
        self._t0 = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / self.FPS))
        self.timer.timeout.connect(self._tick)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.gallery.flow(self.viewport().width())

    def start(self):
        self._t0 = time.perf_counter()
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def _tick(self):
        now = time.perf_counter() - self._t0
        top = self.verticalScrollBar().value()
        bottom = top + self.viewport().height()
        for c in self.gallery.cards:
            c.now = now
            y = c.y()
            if y + CARD_H > top and y < bottom:  # on screen: draw the next frame
                c.update()
