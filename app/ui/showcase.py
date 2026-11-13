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
from .fx import (STILL_T, clamp, ease_back, ease_in_out, ease_out, font, mix, motion_ok, paint_check, paint_cursor,
                 phase, with_alpha)

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


# ---------------------------------------------------------------- from the browser (1.12)
# A small effects kit for these stories: soft shadows give depth, a glow sits behind each result,
# ripples and sparkles mark the moment something arrives, particles carry things along. All cheap
# shapes (no blur), so a page of cards stays light.

_INK = QColor(12, 16, 32)


_SHADOWS: dict = {}
_SHADOW_PAD = 12


def _shadow_pixmap(w: int, h: int, radius: int):
    """A soft shadow drawn once (faint rounded layers, offset down), reused every frame."""
    from PySide6.QtGui import QPixmap

    key = (w, h, radius)
    pm = _SHADOWS.get(key)
    if pm is None:
        if len(_SHADOWS) > 96:  # sizes that change while growing: don't keep them all
            _SHADOWS.clear()
        pad = _SHADOW_PAD
        pm = QPixmap((w + 2 * pad) * 2, (h + 2 * pad) * 2)
        pm.setDevicePixelRatio(2)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setPen(Qt.PenStyle.NoPen)
        r = QRectF(pad, pad, w, h)
        for k in range(4):
            g = 1.0 + k * 1.8
            q.setBrush(with_alpha(_INK, 0.075))
            q.drawRoundedRect(r.adjusted(-g * 0.6, 1 + k * 0.9, g * 0.6, 2 + g + k * 0.9), radius + g, radius + g)
        q.end()
        _SHADOWS[key] = pm
    return pm


def soft_shadow(p, r: QRectF, radius: float = 7.0, depth: float = 1.0):
    """A soft shadow under a card or window (depth 0..1.5: how high it floats)."""
    if depth <= 0.02:
        return
    pm = _shadow_pixmap(max(1, round(r.width())), max(1, round(r.height())), round(radius))
    pad = _SHADOW_PAD
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setOpacity(p.opacity() * min(1.0, depth / 1.5))
    p.drawPixmap(QRectF(r.left() - pad, r.top() - pad, r.width() + 2 * pad, r.height() + 2 * pad), pm,
                 QRectF(0, 0, pm.width(), pm.height()))
    p.restore()


_GLOWS: dict = {}


def glow(p, c: QPointF, radius: float, col: QColor, a: float = 1.0):
    """A soft coloured light behind something (a radial fade drawn once per size and colour, then reused)."""
    if a <= 0.01:
        return
    from PySide6.QtGui import QBrush, QPixmap, QRadialGradient

    r = max(4, round(radius))
    key = (r, col.rgba())
    pm = _GLOWS.get(key)
    if pm is None:
        if len(_GLOWS) > 48:
            _GLOWS.clear()
        pm = QPixmap(2 * r, 2 * r)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QRadialGradient(QPointF(r, r), r)
        g.setColorAt(0.0, with_alpha(col, 0.30))
        g.setColorAt(0.5, with_alpha(col, 0.11))
        g.setColorAt(1.0, with_alpha(col, 0.0))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QBrush(g))
        q.drawEllipse(QPointF(r, r), r, r)
        q.end()
        _GLOWS[key] = pm
    p.save()
    p.setOpacity(p.opacity() * clamp(a))
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawPixmap(QRectF(c.x() - radius, c.y() - radius, 2 * radius, 2 * radius), pm,
                 QRectF(0, 0, pm.width(), pm.height()))
    p.restore()


def ripple(p, c: QPointF, t: float, at: float, col: QColor, r0: float = 18, r1: float = 46, dur: float = 0.7):
    """A ring that spreads out and fades: something just landed."""
    k = phase(t, at, at + dur)
    if not 0 < k < 1:
        return
    e = ease_out(k)
    p.save()
    p.setPen(QPen(with_alpha(col, 0.55 * (1 - k)), 2.2 * (1 - k) + 0.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, r0 + (r1 - r0) * e, r0 + (r1 - r0) * e)
    p.restore()


def _star(p, c: QPointF, r: float, col: QColor):
    path = QPainterPath()
    inner = r * 0.3
    for i in range(8):
        a = -math.pi / 2 + i * math.pi / 4
        d = r if i % 2 == 0 else inner
        pt = QPointF(c.x() + math.cos(a) * d, c.y() + math.sin(a) * d)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawPath(path)


def sparkles(p, c: QPointF, t: float, at: float, col: QColor | None = None, n: int = 6, spread: float = 40,
             turn: float = 0.0):
    """Little stars that burst out and twinkle away."""
    col = col or theme.ACCENT
    p.save()
    for i in range(n):
        k = phase(t, at + i * 0.035, at + 0.65 + i * 0.035)
        if not 0 < k < 1:
            continue
        a = turn + i * 2 * math.pi / n + (0.35 if i % 2 else 0)
        d = spread * (0.45 + 0.55 * ease_out(k)) * (0.75 + 0.25 * ((i * 7) % 4) / 3)
        pt = QPointF(c.x() + math.cos(a) * d, c.y() + math.sin(a) * d)
        size = (3.2 + (i % 3)) * math.sin(math.pi * k)
        _star(p, pt, size, mix(col, QColor(255, 210, 90), 0.45 if i % 3 == 0 else 0.0))
    p.restore()


def bob(t: float, at: float, amp: float = 1.6, speed: float = 1.1) -> float:
    """A gentle float, once something has landed."""
    k = phase(t, at, at + 0.5)
    return -amp * k * math.sin((t - at) * speed * 2 * math.pi)


def pop(t: float, at: float, dur: float = 0.5) -> float:
    return ease_back(phase(t, at, at + dur), 1.8)


def flow(p, a: QPointF, b: QPointF, t: float, start: float, end: float, col: QColor, n: int = 5,
         lift: float = 18, size: float = 2.6):
    """Particles travelling from a to b along a gentle arc, each with a short tail."""
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    span = end - start
    for i in range(n):
        s0 = start + i * span * 0.12
        for tail in range(3):
            s = phase(t - tail * 0.045, s0, s0 + span * 0.55)
            if not 0 < s < 1:
                continue
            e = ease_in_out(s)
            x = a.x() + (b.x() - a.x()) * e
            y = a.y() + (b.y() - a.y()) * e - lift * math.sin(math.pi * e) * (1 if i % 2 else 0.6)
            p.setBrush(with_alpha(col, (0.9 - tail * 0.3) * math.sin(math.pi * s) + 0.1))
            p.drawEllipse(QPointF(x, y), size * (1 - tail * 0.25), size * (1 - tail * 0.25))
    p.restore()


def chip(p, c: QPointF, label: str, col: QColor, k: float, on: bool = False, r: float = 11):
    """A round format choice, as in the picker (pops in with k)."""
    if k <= 0:
        return
    with xf(p, c.x(), c.y(), k):
        if on:
            glow(p, QPointF(0, 0), r * 2.2, col, 0.9)
        p.setPen(QPen(with_alpha(col, 0.5), 1) if not on else Qt.PenStyle.NoPen)
        p.setBrush(col if on else theme.SURFACE)
        p.drawEllipse(QPointF(0, 0), r, r)
        text(p, QRectF(-r, -r, 2 * r, 2 * r), label, 6.2 if len(label) > 3 else 7, QFont.Weight.Bold,
             QColor(255, 255, 255) if on else col, Qt.AlignmentFlag.AlignCenter)


_BROWSERS: dict = {}


def _browser(p, r: QRectF, address: str = "example.org", alpha: float = 1.0, lift: float = 1.0):
    """A small browser window with depth: shadow, tab, address pill, white page (drawn once, then reused)."""
    from PySide6.QtGui import QPixmap

    p.save()
    p.setOpacity(p.opacity() * alpha)
    soft_shadow(p, r, 8, lift)
    w, h = round(r.width()), round(r.height())
    key = (w, h, address, theme.SURFACE.name(), theme.TEXT.name(), theme.SUCCESS.name())
    pm = _BROWSERS.get(key)
    if pm is None:
        if len(_BROWSERS) > 32:
            _BROWSERS.clear()
        pm = QPixmap((w + 2) * 3, (h + 2) * 3)  # 3x: sharp when the card is scaled up
        pm.setDevicePixelRatio(3)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        _browser_body(q, QRectF(1, 1, w, h), address)
        q.end()
        _BROWSERS[key] = pm
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawPixmap(QRectF(r.left() - 1, r.top() - 1, w + 2, h + 2), pm, QRectF(0, 0, pm.width(), pm.height()))
    p.restore()


def _browser_body(p, r: QRectF, address: str):
    p.setPen(QPen(with_alpha(theme.TEXT, 0.14), 1))
    p.setBrush(theme.SURFACE)
    p.drawRoundedRect(r, 8, 8)
    p.setPen(Qt.PenStyle.NoPen)
    bar = mix(theme.SURFACE, theme.TEXT, 0.07)
    p.setBrush(bar)
    top = QPainterPath()
    top.addRoundedRect(QRectF(r.left(), r.top(), r.width(), 22), 8, 8)
    top.addRect(QRectF(r.left(), r.top() + 12, r.width(), 10))
    p.drawPath(top.simplified())
    for k, c in enumerate((QColor(240, 96, 86), QColor(242, 190, 70), QColor(84, 192, 96))):
        p.setBrush(c)
        p.drawEllipse(QPointF(r.left() + 10 + k * 9, r.top() + 11), 2.7, 2.7)
    pill = QRectF(r.left() + 42, r.top() + 5, r.width() - 52, 12)
    p.setBrush(theme.SURFACE)
    p.drawRoundedRect(pill, 6, 6)
    p.setPen(QPen(theme.SUCCESS, 1.1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(pill.left() + 5, pill.top() + 2.3, 5, 5), 0, 180 * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.SUCCESS)
    p.drawRoundedRect(QRectF(pill.left() + 4.4, pill.top() + 5, 6.2, 4.6), 1, 1)
    text(p, pill.adjusted(15, 0, 0, 0), address, 7.5, QFont.Weight.Normal, theme.DIM)


def _keys(p, x: float, y: float, on: float, t: float = 0.0, at: float = -9.0, show: float = 1.0):
    """Ctrl + Shift keycaps; they light up and ripple when pressed (show fades them in and out)."""
    from .fx import paint_keycap

    if show <= 0.01:
        return
    with xf(p, x, y + 4 * (1 - ease_out(show)), 0.42, alpha=show):
        glow(p, QPointF(91, 24), 110, theme.ACCENT, 0.6 * on)
        paint_keycap(p, QRectF(0, 0, 80, 46), "Ctrl", on, on)
        paint_keycap(p, QRectF(90, 0, 92, 46), "Shift", on, on)
    ripple(p, QPointF(x + 38, y + 10), t, at, theme.ACCENT, 10, 44, 0.6)


def _circle(p, c: QPointF, k: float, hot: float, t: float):
    """The "drop to convert" circle: pops in, breathes, its dashed ring turns; fills when something's over it."""
    if k <= 0:
        return
    breathe = 1 + 0.03 * math.sin(t * 2 * math.pi * 1.1)
    with xf(p, c.x(), c.y(), ease_back(k, 1.6) * breathe):
        glow(p, QPointF(0, 0), 54, theme.ACCENT, 0.5 + 0.5 * hot)
        p.setPen(QPen(theme.ACCENT, 2))
        p.setBrush(mix(theme.SURFACE, theme.ACCENT, hot))
        p.drawEllipse(QPointF(0, 0), 30, 30)
        ink = mix(theme.ACCENT, theme.ON_ACCENT, hot)
        p.save()
        p.rotate(t * 60)
        pen = QPen(ink, 1.6)
        pen.setDashPattern([3, 3])
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0, 0), 24, 24)
        p.restore()
        p.setPen(rpen(ink, 2.2))
        dy = 2 * math.sin(t * 2 * math.pi * 1.4) * (1 - hot)
        p.drawLine(QPointF(0, -10 + dy), QPointF(0, 4 + dy))
        p.drawPolyline([QPointF(-5, -1 + dy), QPointF(0, 5 + dy), QPointF(5, -1 + dy)])
        p.drawPolyline([QPointF(-9, 6), QPointF(-9, 10), QPointF(9, 10), QPointF(9, 6)])
    for i in range(2):  # calling rings
        ring = ((t * 0.8 + i * 0.5) % 1.0)
        p.setPen(QPen(with_alpha(theme.ACCENT, 0.35 * (1 - ring) * k * (1 - hot)), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, 30 + 16 * ring, 30 + 16 * ring)


def a_web_drag(p, t, n, card):
    lift = ease_out(phase(t, 0.35, 0.6))
    _browser(p, QRectF(10, 14, 168, 118), "photos.example.org")
    lines(p, QRectF(116, 48, 50, 48), with_alpha(theme.TEXT, 0.2), 5, h=3)
    pic = QRectF(24, 46, 82, 58)
    p.save()
    p.setOpacity(p.opacity() * (1 - 0.45 * lift * (t < 2.4)))
    landscape(p, pic)
    p.restore()
    _keys(p, 42, 116, ease_out(phase(t, 0.7, 0.95)) * (1 - phase(t, 3.2, 3.5)), t, 0.75)
    zone = QPointF(242, 72)
    hot = ease_out(phase(t, 1.85, 2.05))
    _circle(p, zone, phase(t, 0.9, 1.3) * (1 - phase(t, 2.55, 2.85)), hot, t)
    ripple(p, zone, t, 2.05, theme.ACCENT, 26, 58, 0.6)
    move = ease_in_out(phase(t, 0.6, 2.0))
    sx, sy = 65, 75
    x = sx + (zone.x() - sx) * move
    y = sy + (zone.y() - sy) * move - 22 * math.sin(math.pi * move)
    if t < 2.35:
        for g in range(3):  # a faint trail of ghosts behind the dragged picture
            m2 = ease_in_out(phase(t - 0.06 * (g + 1), 0.6, 2.0))
            if 0 < m2 < 1:
                gx = sx + (zone.x() - sx) * m2
                gy = sy + (zone.y() - sy) * m2 - 22 * math.sin(math.pi * m2)
                with xf(p, gx, gy, 0.66, alpha=0.12 * (3 - g)):
                    landscape(p, QRectF(-30, -22, 60, 44))
        with xf(p, x, y, 0.7 + 0.08 * lift, rot=-6 * math.sin(math.pi * move), alpha=0.95):
            soft_shadow(p, QRectF(-30, -22, 60, 44), 5, 1.4 * lift)
            landscape(p, QRectF(-30, -22, 60, 44))
        paint_cursor(p, QPointF(x + 12, y + 10), 0.8)
    bloom = phase(t, 2.6, 3.2)
    if bloom > 0:
        with xf(p, zone.x(), zone.y(), ease_back(phase(t, 2.6, 2.95), 1.5)):
            soft_shadow(p, QRectF(-36, -36, 72, 72), 36, 1.0)
            p.setPen(QPen(theme.LINE, 1))
            p.setBrush(theme.SURFACE)
            p.drawEllipse(QPointF(0, 0), 36, 36)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(theme.ACCENT, 0.12))
            p.drawEllipse(QPointF(0, 0), 9, 9)
        for k, (lab, col) in enumerate((("JPG", theme.ACCENT), ("PNG", COL["image"]), ("PDF", COL["pdf"]),
                                         ("WEBP", COL["data"]))):
            a = -math.pi / 2 + k * math.pi / 2
            out = 23 * ease_out(phase(t, 2.7 + k * 0.07, 3.1 + k * 0.07))
            c = QPointF(zone.x() + math.cos(a) * out, zone.y() + math.sin(a) * out)
            chip(p, c, lab, col, pop(t, 2.7 + k * 0.07, 0.4), on=(k == 0 and t > 3.4), r=10)
        sparkles(p, QPointF(zone.x(), zone.y() - 23), t, 3.45, theme.ACCENT, 5, 20)


def a_web_table(p, t, n, card):
    _browser(p, QRectF(8, 14, 150, 116), "en.example.org/wiki")
    g = QRectF(18, 42, 130, 80)
    sel = ease_in_out(phase(t, 0.3, 1.1))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(with_alpha(theme.ACCENT, 0.16))
    p.drawRoundedRect(QRectF(g.left() - 2, g.top() - 2, g.width() + 4, (g.height() + 4) * sel), 3, 3)
    p.setBrush(with_alpha(theme.TEXT, 0.06))
    p.drawRect(QRectF(g.left(), g.top(), g.width(), 20))
    p.setPen(QPen(with_alpha(theme.TEXT, 0.18), 1))
    for r in range(5):
        p.drawLine(QPointF(g.left(), g.top() + r * 20), QPointF(g.right(), g.top() + r * 20))
    for c in range(4):
        p.drawLine(QPointF(g.left() + c * g.width() / 3, g.top()), QPointF(g.left() + c * g.width() / 3, g.bottom()))
    for r in range(4):
        lines(p, QRectF(g.left() + 6, g.top() + 8 + r * 20, 30, 3), with_alpha(theme.TEXT, 0.4 if r else 0.6), 1, h=3)
        lines(p, QRectF(g.left() + 50, g.top() + 8 + r * 20, 24, 3), with_alpha(theme.TEXT, 0.32), 1, h=3)
        lines(p, QRectF(g.left() + 94, g.top() + 8 + r * 20, 20, 3), with_alpha(theme.TEXT, 0.32), 1, h=3)
    sheet = QRectF(206, 28, 84, 92)
    # the cells fly across, one after another
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(10):
        s = phase(t, 1.1 + i * 0.07, 1.65 + i * 0.07)
        if not 0 < s < 1:
            continue
        e = ease_in_out(s)
        a = QPointF(g.left() + 20 + (i % 3) * 43, g.top() + 10 + (i // 3) * 20)
        b = QPointF(sheet.left() + 14 + (i % 3) * 28, sheet.top() + 22 + (i // 3) * 15)
        x = a.x() + (b.x() - a.x()) * e
        y = a.y() + (b.y() - a.y()) * e - 26 * math.sin(math.pi * e)
        p.setBrush(with_alpha(COL["sheet"], 0.25 + 0.6 * math.sin(math.pi * s)))
        p.drawRoundedRect(QRectF(x - 8, y - 4, 16, 8), 2, 2)
    p.restore()
    k = pop(t, 1.2, 0.45)
    if k > 0:
        f = bob(t, 2.6)
        glow(p, sheet.center(), 70, COL["sheet"], phase(t, 2.2, 2.7))
        with xf(p, sheet.center().x(), sheet.center().y() + f, k):
            r = QRectF(-sheet.width() / 2, -sheet.height() / 2, sheet.width(), sheet.height())
            soft_shadow(p, r, 4, 1.2)
            p.setPen(QPen(with_alpha(COL["sheet"], 0.55), 1))
            p.setBrush(theme.SURFACE)
            p.drawRoundedRect(r, 4, 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(COL["sheet"])
            p.drawRoundedRect(QRectF(r.left(), r.top(), r.width(), 14), 4, 4)
            p.drawRect(QRectF(r.left(), r.top() + 8, r.width(), 6))
            p.setPen(QPen(with_alpha(COL["sheet"], 0.3), 1))
            for i in range(1, 6):
                p.drawLine(QPointF(r.left(), r.top() + 14 + i * 13), QPointF(r.right(), r.top() + 14 + i * 13))
            for c in (1, 2):
                p.drawLine(QPointF(r.left() + c * r.width() / 3, r.top() + 14), QPointF(r.left() + c * r.width() / 3, r.bottom()))
            fill = phase(t, 1.5, 2.3) * 5.99
            for i in range(min(5, int(fill))):
                lines(p, QRectF(r.left() + 5, r.top() + 19 + i * 13, 18, 3), COL["sheet"], 1, h=3)
                lines(p, QRectF(r.left() + 33, r.top() + 19 + i * 13, 14, 3), with_alpha(theme.TEXT, 0.4), 1, h=3)
                lines(p, QRectF(r.left() + 61, r.top() + 19 + i * 13, 12, 3), with_alpha(theme.TEXT, 0.4), 1, h=3)
            tag(p, QPointF(0, r.bottom() + 12), "XLSX", COL["sheet"], phase(t, 2.2, 2.5))
        sparkles(p, QPointF(sheet.right() - 6, sheet.top() + 4), t, 2.3, COL["sheet"], 6, 30)


def a_web_clip(p, t, n, card):
    _browser(p, QRectF(8, 14, 150, 116), "recipes.example.org")
    sel = phase(t, 0.2, 1.1)
    widths = [118, 128, 96, 124, 110, 70, 100]
    for r in range(7):
        y = 42 + r * 11
        w = widths[r]
        if r < 5 and sel * 5 > r:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(theme.ACCENT, 0.22))
            p.drawRoundedRect(QRectF(16, y - 3, w * min(1.0, sel * 5 - r) + 4, 9), 2, 2)
        lines(p, QRectF(18, y, w, 3), with_alpha(theme.TEXT, 0.3 if r else 0.62), 1, h=3 if r else 4)
    if sel < 1:  # the text cursor sweeping the selection
        r = min(4, int(sel * 5))
        x = 18 + widths[r] * min(1.0, sel * 5 - r)
        p.setPen(rpen(theme.TEXT, 1.2))
        p.drawLine(QPointF(x, 38 + r * 11), QPointF(x, 47 + r * 11))
    _keys(p, 194, 2, ease_out(phase(t, 1.2, 1.4)) * (1 - phase(t, 1.9, 2.1)), t, 1.25,
          show=phase(t, 0.95, 1.15) * (1 - phase(t, 2.2, 2.45)))
    hub = QPointF(232, 74)
    picker = phase(t, 1.5, 1.8) * (1 - phase(t, 2.7, 2.95))
    if picker > 0:
        with xf(p, hub.x(), hub.y(), ease_back(picker, 1.4)):
            soft_shadow(p, QRectF(-38, -38, 76, 76), 38, 0.9)
            p.setPen(QPen(theme.LINE, 1))
            p.setBrush(theme.SURFACE)
            p.drawEllipse(QPointF(0, 0), 38, 38)
        for k, (lab, col) in enumerate((("PDF", COL["pdf"]), ("Word", COL["doc"]), ("TXT", COL["md"]))):
            a = -math.pi / 2 + k * 2 * math.pi / 3
            c = QPointF(hub.x() + math.cos(a) * 22, hub.y() + math.sin(a) * 22)
            chip(p, c, lab, col, pop(t, 1.6 + k * 0.08, 0.4) * min(1.0, picker * 1.5), on=(k == 0 and t > 2.3), r=11)
        if 2.0 < t < 2.7:
            paint_cursor(p, QPointF(hub.x() + 4, hub.y() - 18), 0.75)
    k = pop(t, 2.8, 0.5)
    if k > 0:
        f = bob(t, 3.3)
        glow(p, QPointF(246, 70), 62, COL["pdf"], phase(t, 2.9, 3.3))
        with xf(p, 246, 70 + f, k):
            soft_shadow(p, QRectF(-34, -46, 68, 92), 5, 1.2)
            page(p, QRectF(-34, -46, 68, 92), COL["pdf"], "", "none")
            lines(p, QRectF(-25, -34, 42, 28), with_alpha(theme.TEXT, 0.35), 5, h=3)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ACCENT)
            p.drawRoundedRect(QRectF(-25, 4, 36, 3), 1.5, 1.5)
            tag(p, QPointF(0, 28), "PDF", COL["pdf"])
        sparkles(p, QPointF(270, 30), t, 3.0, COL["pdf"], 6, 28)
        text(p, QRectF(196, 126, 100, 16), "with the source link", 9, QFont.Weight.DemiBold, theme.DIM,
             Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 3.2, 3.6))


def a_web_page(p, t, n, card):
    shrink = ease_in_out(phase(t, 1.0, 1.9))
    with xf(p, 92 - 26 * shrink, 74, 1 - 0.3 * shrink):
        _browser(p, QRectF(-80, -60, 160, 120), "news.example.org/story")
        landscape(p, QRectF(-70, -32, 60, 40))
        lines(p, QRectF(-2, -30, 70, 48), with_alpha(theme.TEXT, 0.25), 6, h=3)
        lines(p, QRectF(-70, 16, 138, 34), with_alpha(theme.TEXT, 0.25), 4, h=3)
    _keys(p, 196, 112, ease_out(phase(t, 0.3, 0.5)) * (1 - phase(t, 0.9, 1.1)), t, 0.35,
          show=phase(t, 0.05, 0.25) * (1 - phase(t, 1.2, 1.45)))
    flash = phase(t, 0.75, 1.15)
    if 0 < flash < 1:  # the camera flash
        p.save()
        p.setOpacity(p.opacity() * (1 - flash) * (0.75 if theme.BG.lightness() >= 128 else 0.3))
        p.fillRect(QRectF(0, 0, 300, 150), QColor(255, 255, 255))
        p.restore()
    k = pop(t, 1.7, 0.5)
    if k > 0:
        glow(p, QPointF(226, 72), 80, theme.ACCENT, 0.7 * phase(t, 1.9, 2.4))
        fan = ease_out(phase(t, 2.0, 2.6))
        with xf(p, 206 - 6 * fan, 72 + bob(t, 2.6), k, rot=-6 * fan):
            soft_shadow(p, QRectF(-26, -48, 52, 96), 5, 1.2)
            page(p, QRectF(-26, -48, 52, 96), COL["pdf"], "PDF", "lines")
        with xf(p, 252 + 6 * fan, 72 + bob(t, 2.8, 1.6, 0.9), pop(t, 2.0, 0.5), rot=5 * fan):
            r = QRectF(-17, -58, 34, 116)
            soft_shadow(p, r, 4, 1.2)
            p.setPen(QPen(with_alpha(theme.TEXT, 0.16), 1))
            p.setBrush(theme.SURFACE)
            p.drawRoundedRect(r, 4, 4)
            landscape(p, QRectF(-13, -52, 26, 18), radius=2)
            lines(p, QRectF(-13, -28, 26, 70), with_alpha(theme.TEXT, 0.25), 10, h=2.5)
            tag(p, QPointF(0, 50), "PNG", COL["image"])
        sparkles(p, QPointF(232, 22), t, 2.4, theme.ACCENT, 7, 30)


_QR_CACHE: dict = {}


def _qr_pixmap(sym, size: int):
    from PySide6.QtGui import QPixmap

    if "pm" not in _QR_CACHE:
        pm = QPixmap(size * 2, size * 2)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.scale(2, 2)
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(20, 20, 26))
        cell = size / (sym.size + 2)
        for y in range(sym.size):
            for x in range(sym.size):
                if sym.dark[y][x]:
                    q.drawRect(QRectF((x + 1) * cell, (y + 1) * cell, cell + 0.3, cell + 0.3))
        q.end()
        _QR_CACHE["pm"] = pm
    return _QR_CACHE["pm"]


def a_web_qr(p, t, n, card):
    if "sym" not in _QR_CACHE:
        from ..engines.qr import make

        _QR_CACHE["sym"] = make("https://shop.example.org/item/42")
    sym = _QR_CACHE["sym"]
    pill = QRectF(10, 62, 112, 24)
    soft_shadow(p, pill, 12, 0.8)
    p.setPen(QPen(theme.ACCENT, 1.2))
    p.setBrush(theme.SURFACE)
    p.drawRoundedRect(pill, 12, 12)
    p.setPen(rpen(theme.ACCENT, 1.4))  # a link symbol
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(pill.left() + 8, pill.top() + 9, 8, 6), 3, 3)
    p.drawRoundedRect(QRectF(pill.left() + 13, pill.top() + 9, 8, 6), 3, 3)
    text(p, pill.adjusted(26, 0, 0, 0), "shop.example.org", 9, QFont.Weight.DemiBold, theme.ACCENT)
    size = 104
    cell = size / (sym.size + 2)
    ox, oy = 168, 22
    flow(p, QPointF(pill.right(), pill.center().y()), QPointF(ox + 8, oy + size / 2), t, 0.15, 1.2, theme.ACCENT,
         6, 14)
    glow(p, QPointF(ox + size / 2, oy + size / 2), 90, theme.ACCENT, 0.6 * phase(t, 2.9, 3.4))
    with xf(p, ox + size / 2, oy + size / 2 + bob(t, 3.1, 1.2), 1.0):
        base = QRectF(-size / 2 - 5, -size / 2 - 5, size + 10, size + 10)
        soft_shadow(p, base, 7, 1.2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(base, 7, 7)
        diag = (sym.size * 2.0)
        shown = phase(t, 0.5, 1.9) * (diag + 8)  # the code builds itself in a diagonal wave
        if shown >= diag + 6:  # finished: one picture, drawn once
            p.drawPixmap(QRectF(-size / 2, -size / 2, size, size), _qr_pixmap(sym, size),
                         QRectF(0, 0, size * 2, size * 2))
        else:
            p.setBrush(QColor(20, 20, 26))
            for y in range(sym.size):
                for x in range(sym.size):
                    if not sym.dark[y][x]:
                        continue
                    k = clamp((shown - (x + y)) / 6)
                    if k <= 0:
                        continue
                    s = cell * (0.3 + 0.7 * ease_out(k)) + 0.3
                    cx = -size / 2 + (x + 1.5) * cell
                    cy = -size / 2 + (y + 1.5) * cell
                    p.drawRect(QRectF(cx - s / 2, cy - s / 2, s, s))
        scan = phase(t, 2.0, 2.9)
        if 0 < scan < 1:  # the read-back: a glowing band sweeps down
            from PySide6.QtGui import QBrush, QLinearGradient

            y = -size / 2 + size * scan
            g = QLinearGradient(0, y - 12, 0, y + 2)
            g.setColorAt(0, with_alpha(theme.ACCENT, 0.0))
            g.setColorAt(1, with_alpha(theme.ACCENT, 0.35))
            p.setBrush(QBrush(g))
            p.drawRect(QRectF(-size / 2 - 4, y - 12, size + 8, 14))
            p.setPen(QPen(theme.ACCENT, 2))
            p.drawLine(QPointF(-size / 2 - 6, y + 2), QPointF(size / 2 + 6, y + 2))
    done(p, t, 2.95, QPointF(282, 26), 18)
    ripple(p, QPointF(282, 26), t, 3.0, theme.SUCCESS, 9, 26)
    sparkles(p, QPointF(282, 26), t, 3.05, theme.SUCCESS, 5, 20)


def a_web_bigger(p, t, n, card):
    _browser(p, QRectF(8, 14, 130, 112), "art.example.org")
    landscape(p, QRectF(20, 46, 50, 36))
    text(p, QRectF(20, 86, 100, 14), "400 px on screen", 8, QFont.Weight.Normal, theme.DIM)
    grow = ease_in_out(phase(t, 0.8, 2.2))
    w = 50 + 84 * grow
    h = w * 0.72
    r = QRectF(152, 66 - h / 2, w, h)
    glow(p, r.center(), 90, COL["image"], 0.8 * phase(t, 2.0, 2.5))
    soft_shadow(p, r, 5, 0.6 + 0.8 * grow)
    landscape(p, r)
    blocks = 1 - phase(t, 1.4, 2.3)  # the small preview looks blocky; the big one comes out sharp
    if blocks > 0:
        p.save()
        p.setPen(QPen(with_alpha(QColor(255, 255, 255), 0.55 * blocks), 1))
        step = r.width() / 7
        for i in range(1, 7):
            p.drawLine(QPointF(r.left() + i * step, r.top()), QPointF(r.left() + i * step, r.bottom()))
        for j in range(1, 6):
            yy = r.top() + j * r.height() / 6
            p.drawLine(QPointF(r.left(), yy), QPointF(r.right(), yy))
        p.restore()
    label = f"{int(400 + 1200 * grow)} px"
    text(p, QRectF(152, 66 + h / 2 + 4, 140, 16), label, 11, QFont.Weight.Bold,
         theme.ACCENT if grow > 0.98 else theme.TEXT)
    sparkles(p, QPointF(r.right() - 4, r.top() + 4), t, 2.2, COL["image"], 7, 26)
    text(p, QRectF(8, 130, 160, 14), "the biggest the page offers", 8.5, QFont.Weight.DemiBold, theme.DIM,
         alpha=phase(t, 2.2, 2.6))


def a_web_cloud(p, t, n, card):
    c = QPointF(70, 60)
    f = 2.0 * math.sin(t * 2 * math.pi * 0.4)
    if "cloud" not in _QR_CACHE:  # the cloud's outline, made once
        cloud = QPainterPath()
        cloud.addEllipse(QPointF(-24, 8), 20, 16)
        cloud.addEllipse(QPointF(0, -4), 27, 23)
        cloud.addEllipse(QPointF(25, 8), 18, 15)
        cloud.addRoundedRect(QRectF(-40, 6, 80, 18), 9, 9)
        cloud.setFillRule(Qt.FillRule.WindingFill)
        _QR_CACHE["cloud"] = cloud.simplified()
    cloud = _QR_CACHE["cloud"].translated(c.x(), c.y() + f)
    glow(p, QPointF(c.x(), c.y() + 6), 64, COL["doc"], 0.5)
    from PySide6.QtGui import QBrush, QLinearGradient

    g = QLinearGradient(0, c.y() - 28, 0, c.y() + 26)
    g.setColorAt(0, mix(theme.SURFACE, COL["doc"], 0.18))
    g.setColorAt(1, mix(theme.SURFACE, COL["doc"], 0.42))
    p.setPen(QPen(with_alpha(COL["doc"], 0.45), 1.2))
    p.setBrush(QBrush(g))
    p.drawPath(cloud)
    for k2, (name, col) in enumerate((("Drive", QColor(52, 168, 83)), ("Dropbox", QColor(0, 97, 254)),
                                      ("OneDrive", QColor(0, 120, 212)))):
        k = pop(t, 0.1 + k2 * 0.12, 0.4)
        if k > 0:
            cx = 26 + k2 * 46
            with xf(p, cx, 14, k):
                pill = QRectF(-21, -7, 42, 14)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(col, 0.14))
                p.drawRoundedRect(pill, 7, 7)
            text(p, QRectF(cx - 21, 7, 42, 14), name, 7.5, QFont.Weight.Bold, col, Qt.AlignmentFlag.AlignCenter,
                 alpha=k)
    pill = QRectF(18, 104, 104, 20)
    soft_shadow(p, pill, 10, 0.7)
    p.setPen(QPen(COL["doc"], 1))
    p.setBrush(theme.SURFACE)
    p.drawRoundedRect(pill, 10, 10)
    text(p, pill, "shared link", 9, QFont.Weight.DemiBold, COL["doc"], Qt.AlignmentFlag.AlignCenter)
    flow(p, QPointF(100, 64), QPointF(214, 62), t, 0.5, 1.6, COL["doc"], 6, 22)
    k = pop(t, 1.45, 0.5)
    if k > 0:
        glow(p, QPointF(228, 64), 70, COL["pdf"], phase(t, 1.7, 2.2))
        with xf(p, 228, 62 + bob(t, 2.0), k):
            soft_shadow(p, QRectF(-34, -46, 68, 92), 5, 1.2)
            page(p, QRectF(-34, -46, 68, 92), COL["pdf"], "PDF")
        ripple(p, QPointF(228, 62), t, 1.6, COL["pdf"], 30, 64, 0.7)
        sparkles(p, QPointF(258, 22), t, 1.9, COL["pdf"], 6, 24)
    name = "Report Q3.pdf"
    shown = int(len(name) * phase(t, 1.9, 2.6))  # the real name types itself in, from a fixed start
    full = QFontMetricsF(font(10, QFont.Weight.DemiBold)).horizontalAdvance(name)
    text(p, QRectF(228 - full / 2, 120, full + 8, 16), name[:shown], 10, QFont.Weight.DemiBold)


def _folder(p, r: QRectF, open_k: float, back: bool):
    yellow, dark = QColor(246, 196, 72), QColor(226, 168, 44)
    p.setPen(Qt.PenStyle.NoPen)
    if back:
        p.setBrush(dark)
        p.drawRoundedRect(QRectF(r.left(), r.top() - 9, 38, 16), 4, 4)
        p.drawRoundedRect(r, 7, 7)
        return
    front = QPainterPath()
    lean = 10 * open_k
    front.moveTo(r.left() + lean, r.top() + 12 + 6 * open_k)
    front.lineTo(r.right() + lean * 0.4, r.top() + 12 + 6 * open_k)
    front.lineTo(r.right(), r.bottom())
    front.lineTo(r.left(), r.bottom())
    front.closeSubpath()
    p.setBrush(yellow)
    p.drawPath(front)


def a_web_webp(p, t, n, card):
    folder = QRectF(16, 46, 96, 70)
    soft_shadow(p, folder, 7, 0.9)
    _folder(p, folder, 0, back=True)
    drop = phase(t, 0.3, 1.1)
    open_k = math.sin(math.pi * phase(t, 0.6, 1.4))
    e = ease_in_out(drop)
    x = 230 + (64 - 230) * e
    y = 10 + (74 - 10) * e - 30 * math.sin(math.pi * e)
    if drop < 1:
        with xf(p, x, y, 1 - 0.35 * e, rot=-14 * math.sin(math.pi * e)):
            soft_shadow(p, QRectF(-22, -28, 44, 56), 4, 1.0)
            page(p, QRectF(-22, -28, 44, 56), COL["image"], "WEBP", "image")
    else:
        with xf(p, 64, 66, 0.65):
            page(p, QRectF(-22, -28, 44, 56), COL["image"], "WEBP", "image")
    _folder(p, folder, open_k, back=False)
    text(p, QRectF(folder.left(), folder.bottom() + 4, folder.width(), 14), "Downloads", 9, QFont.Weight.DemiBold,
         theme.DIM, Qt.AlignmentFlag.AlignCenter)
    # the JPG twin slides out of the folder, by itself
    out = ease_out(phase(t, 1.6, 2.4))
    if out > 0:
        flow(p, QPointF(112, 70), QPointF(206, 70), t, 1.5, 2.3, theme.ACCENT, 4, 10, 2.2)
        k = pop(t, 2.0, 0.5)
        glow(p, QPointF(232, 70), 64, theme.ACCENT, phase(t, 2.3, 2.8))
        with xf(p, 232, 70 + bob(t, 2.6), k):
            soft_shadow(p, QRectF(-26, -32, 52, 64), 4, 1.2)
            page(p, QRectF(-26, -32, 52, 64), theme.ACCENT, "JPG", "image")
        sparkles(p, QPointF(254, 38), t, 2.3, theme.ACCENT, 6, 24)
        tag(p, QPointF(180, 30), "automatic", with_alpha(theme.SUCCESS, 1.0), phase(t, 2.5, 2.9), px=8.5)
    text(p, QRectF(140, 116, 160, 16), "original kept", 9, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 2.7, 3.1))


def a_web_copied(p, t, n, card):
    _browser(p, QRectF(8, 14, 150, 116), "any app")
    lines(p, QRectF(18, 42, 128, 30), with_alpha(theme.TEXT, 0.2), 3, h=3)
    pic = QRectF(30, 78, 70, 42)
    landscape(p, pic)
    p.save()  # the screen dims while you snip
    dim = phase(t, 0.15, 0.35) * (1 - phase(t, 1.2, 1.4))
    p.setOpacity(p.opacity() * (0.3 if theme.BG.lightness() < 128 else 0.16) * dim)
    p.fillRect(QRectF(8, 14, 150, 116), _INK)
    p.restore()
    snip = ease_in_out(phase(t, 0.3, 1.0))
    r = QRectF(24, 72, 84 * snip, 54 * snip)
    if t < 1.5:
        pen = QPen(theme.ACCENT, 1.6)
        pen.setDashPattern([4, 3])
        pen.setDashOffset(-t * 20)
        p.setPen(pen)
        p.setBrush(with_alpha(theme.ACCENT, 0.08))
        p.drawRect(r)
        if snip < 1:  # the crosshair drawing the snip
            cx, cy = r.right(), r.bottom()
            p.setPen(QPen(theme.TEXT, 1))
            p.drawLine(QPointF(cx - 6, cy), QPointF(cx + 6, cy))
            p.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))
    text(p, QRectF(20, 22, 130, 14), "Win + Shift + S", 8.5, QFont.Weight.Bold, theme.ACCENT,
         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
         alpha=phase(t, 0.3, 0.6) * (1 - phase(t, 1.2, 1.4)))
    lift = ease_in_out(phase(t, 1.3, 2.2))
    if t >= 1.3:  # the snip lifts off and flies to its place
        x = 66 + (232 - 66) * lift
        y = 99 + (80 - 99) * lift - 24 * math.sin(math.pi * lift)
        glow(p, QPointF(232, 80), 70, COL["image"], phase(t, 2.2, 2.7))
        with xf(p, x, y + bob(t, 2.6), 1.0, rot=8 * math.sin(math.pi * lift)):
            soft_shadow(p, QRectF(-42, -27, 84, 54), 5, 1.4)
            p.setPen(QPen(theme.SURFACE, 3))
            p.setBrush(theme.SURFACE)
            p.drawRoundedRect(QRectF(-43, -28, 86, 56), 5, 5)
            landscape(p, QRectF(-40, -25, 80, 50))
    _keys(p, 194, 8, ease_out(phase(t, 1.9, 2.1)) * (1 - phase(t, 2.5, 2.7)), t, 1.95,
          show=phase(t, 1.6, 1.8) * (1 - phase(t, 2.8, 3.0)))
    tag(p, QPointF(232, 130), "Saved as JPG", theme.ACCENT, phase(t, 2.7, 3.0))
    sparkles(p, QPointF(268, 54), t, 2.75, theme.ACCENT, 6, 26)


# ---------------------------------------------------------------- 1.13: more from pages, files and the sound world

def a_web_reader(p, t, n, card):
    _browser(p, QRectF(8, 14, 150, 118), "news.example.org/walk")
    clean = ease_in_out(phase(t, 1.0, 1.8))
    # the clutter: a cookie banner, an ad, a sidebar; it flies away
    for k, (r, col, word) in enumerate(((QRectF(16, 108, 134, 16), QColor(60, 60, 70), "Accept cookies?"),
                                        (QRectF(112, 42, 38, 52), COL["slides"], "AD"),
                                        (QRectF(16, 40, 92, 10), with_alpha(theme.TEXT, 0.25), ""))):
        k2 = clamp(clean * 1.4 - k * 0.2)
        if k2 >= 1:
            continue
        with xf(p, r.center().x() + 60 * ease_in_out(k2) * (1 if k != 2 else -0.4), r.center().y()
                - 20 * k2, 1 - 0.4 * k2, rot=12 * k2, alpha=1 - k2):
            rr = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(rr, 3, 3)
            if word:
                text(p, rr, word, 7.5, QFont.Weight.Bold, QColor(255, 255, 255), Qt.AlignmentFlag.AlignCenter)
    lines(p, QRectF(18, 56, 88 + 40 * clean, 44), with_alpha(theme.TEXT, 0.3), 5, h=3)
    k = pop(t, 2.0, 0.5)
    if k > 0:
        glow(p, QPointF(240, 70), 70, COL["pdf"], phase(t, 2.2, 2.6))
        with xf(p, 240, 70 + bob(t, 2.6), k):
            soft_shadow(p, QRectF(-36, -50, 72, 100), 5, 1.2)
            page(p, QRectF(-36, -50, 72, 100), COL["pdf"], "PDF", "none")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.TEXT)
            p.drawRoundedRect(QRectF(-26, -38, 40, 5), 2, 2)
            lines(p, QRectF(-26, -26, 46, 34), with_alpha(theme.TEXT, 0.3), 6, h=2.6)
        sparkles(p, QPointF(268, 26), t, 2.3, COL["pdf"], 6, 24)
    text(p, QRectF(176, 128, 128, 14), "just the article", 9, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 2.6, 3.0))


def a_web_pictures(p, t, n, card):
    _browser(p, QRectF(8, 14, 150, 118), "travel.example.org")
    spots = [QRectF(18, 42, 60, 38), QRectF(86, 42, 60, 38), QRectF(18, 86, 60, 38), QRectF(86, 86, 60, 38)]
    folder = QRectF(196, 54, 84, 62)
    for k, r in enumerate(spots):
        landscape(p, r, [COL["image"], COL["map"], COL["slides"], COL["video"]][k], 4)
    _folder(p, folder, 0, back=True)
    for k, r in enumerate(spots):  # copies fly into the folder, one after another, at their biggest
        s = phase(t, 0.8 + k * 0.32, 1.5 + k * 0.32)
        if 0 < s < 1:
            e = ease_in_out(s)
            x = r.center().x() + (folder.center().x() - r.center().x()) * e
            y = r.center().y() + (folder.center().y() - 6 - r.center().y()) * e - 30 * math.sin(math.pi * e)
            with xf(p, x, y, 0.8 - 0.3 * e, rot=-10 * math.sin(math.pi * e)):
                soft_shadow(p, QRectF(-30, -19, 60, 38), 4, 1.0)
                landscape(p, QRectF(-30, -19, 60, 38), [COL["image"], COL["map"], COL["slides"], COL["video"]][k], 4)
    _folder(p, folder, math.sin(math.pi * phase(t, 0.9, 2.6)) * 0.6, back=False)
    got = sum(1 for k in range(4) if t > 1.5 + k * 0.32)
    text(p, QRectF(folder.left() - 10, folder.bottom() + 4, folder.width() + 20, 14),
         f"{got} picture{'s' if got != 1 else ''}", 9.5, QFont.Weight.Bold, theme.ACCENT if got == 4 else theme.DIM,
         Qt.AlignmentFlag.AlignCenter)
    sparkles(p, QPointF(folder.right() - 6, folder.top() - 6), t, 2.8, theme.ACCENT, 6, 22)


def a_video_frame(p, t, n, card):
    strip = QRectF(14, 30, 170, 74)
    soft_shadow(p, strip, 6, 1.0)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(28, 28, 34))
    p.drawRoundedRect(strip, 6, 6)
    for k in range(4):  # frames of the film
        landscape(p, QRectF(strip.left() + 8 + k * 40, strip.top() + 14, 36, 46),
                  [COL["image"], COL["map"], COL["slides"], COL["video"]][k], 2)
    p.setBrush(QColor(70, 70, 80))
    for k in range(9):
        p.drawRoundedRect(QRectF(strip.left() + 8 + k * 18, strip.top() + 4, 9, 6), 1.5, 1.5)
        p.drawRoundedRect(QRectF(strip.left() + 8 + k * 18, strip.bottom() - 10, 9, 6), 1.5, 1.5)
    head = strip.left() + 8 + 160 * ease_in_out(phase(t, 0.2, 1.3)) * 0.62
    p.setPen(QPen(theme.ACCENT, 2))
    p.drawLine(QPointF(head, strip.top() - 6), QPointF(head, strip.bottom() + 6))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.ACCENT)
    p.drawEllipse(QPointF(head, strip.top() - 6), 4, 4)
    text(p, QRectF(14, 110, 170, 14), "the middle, 0:42", 9, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 1.2, 1.5))
    flash = phase(t, 1.4, 1.75)
    if 0 < flash < 1:
        glow(p, QPointF(head, strip.center().y()), 40, QColor(255, 255, 255), 1 - flash)
    k = pop(t, 1.7, 0.5)
    if k > 0:
        glow(p, QPointF(246, 70), 66, COL["image"], phase(t, 2.0, 2.4))
        with xf(p, 246, 66 + bob(t, 2.4), k, rot=-4):
            soft_shadow(p, QRectF(-40, -30, 80, 60), 4, 1.3)
            p.setPen(QPen(theme.SURFACE, 3))
            p.setBrush(theme.SURFACE)
            p.drawRoundedRect(QRectF(-41, -31, 82, 62), 4, 4)
            landscape(p, QRectF(-38, -28, 76, 56), COL["slides"], 3)
        tag(p, QPointF(246, 116), "JPG", COL["image"], phase(t, 2.1, 2.4))
        sparkles(p, QPointF(284, 30), t, 2.0, COL["image"], 6, 22)


def a_audio_trim(p, t, n, card):
    col = COL["audio"]
    box = QRectF(20, 40, 260, 60)
    a = 0.22 * ease_in_out(phase(t, 0.5, 1.4))
    b = 1 - 0.3 * ease_in_out(phase(t, 0.8, 1.7))
    squeeze = ease_in_out(phase(t, 2.0, 2.8))
    p.setPen(Qt.PenStyle.NoPen)
    bars = 52
    for i in range(bars):
        x = i / (bars - 1)
        hgt = 6 + 22 * abs(math.sin(i * 0.9) * math.cos(i * 0.31))
        inside = a <= x <= b
        if not inside and squeeze > 0.95:
            continue
        # the kept part spreads out to the full width once the rest is gone
        kx = x + ((x - a) / max(b - a, 0.01) - x) * squeeze if inside else x
        xx = box.left() + box.width() * kx
        p.setBrush(col if inside else with_alpha(theme.TEXT, 0.18 * (1 - squeeze)))
        p.drawRoundedRect(QRectF(xx - 1.6, box.center().y() - hgt / 2, 3.2, hgt), 1.6, 1.6)
    for x, label_ in ((a, "0:30"), (b, "2:15")):
        if squeeze > 0.5:
            break
        hx = box.left() + box.width() * x
        p.setPen(QPen(theme.ACCENT, 2))
        p.drawLine(QPointF(hx, box.top() - 4), QPointF(hx, box.bottom() + 4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.ACCENT)
        p.drawRoundedRect(QRectF(hx - 5, box.top() - 12, 10, 9), 3, 3)
        text(p, QRectF(hx - 24, box.bottom() + 6, 48, 14), label_, 9, QFont.Weight.Bold, theme.ACCENT,
             Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 1.0, 1.4) * (1 - phase(t, 1.9, 2.1)))
    tag(p, QPointF(150, 126), "1:45 kept", col, phase(t, 2.8, 3.1))
    sparkles(p, QPointF(150, 30), t, 2.9, col, 6, 28)


def a_pdf_sign(p, t, n, card):
    with xf(p, 110, 74, 1.0):
        r = QRectF(-56, -64, 112, 128)
        soft_shadow(p, r, 5, 1.0)
        page(p, r, COL["pdf"], "", "none")
        lines(p, QRectF(-44, -50, 80, 50), with_alpha(theme.TEXT, 0.25), 6, h=3)
    line_y = 112
    p.setPen(QPen(with_alpha(theme.TEXT, 0.35), 1))
    p.drawLine(QPointF(108, line_y), QPointF(158, line_y))
    # the signature writes itself
    path = QPainterPath(QPointF(110, line_y - 4))
    pts = [(116, line_y - 16), (121, line_y - 2), (126, line_y - 14), (131, line_y - 3), (137, line_y - 12),
           (142, line_y - 4), (148, line_y - 10), (156, line_y - 6)]
    for x, y in pts:
        path.lineTo(QPointF(x, y))
    draw = phase(t, 0.5, 1.6)
    if draw > 0:
        pen = rpen(QColor(30, 60, 160), 1.8)
        p.save()
        p.setClipRect(QRectF(100, line_y - 24, 8 + 60 * draw, 30))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.restore()
        if draw < 1:  # the pen
            tip = QPointF(108 + 50 * draw, line_y - 8)
            p.setPen(rpen(theme.TEXT, 2.4))
            p.drawLine(tip, QPointF(tip.x() + 12, tip.y() - 16))
    text(p, QRectF(104, line_y + 2, 70, 10), "Signed by Asha Rao", 5.5, QFont.Weight.Normal, theme.DIM,
         alpha=phase(t, 1.6, 1.9))
    arrow(p, 176, 206, 74, t, phase(t, 1.8, 2.1))
    k = pop(t, 2.2, 0.5)
    if k > 0:
        glow(p, QPointF(246, 72), 60, COL["pdf"], phase(t, 2.4, 2.8))
        with xf(p, 246, 72 + bob(t, 2.7), k):
            soft_shadow(p, QRectF(-30, -40, 60, 80), 5, 1.2)
            page(p, QRectF(-30, -40, 60, 80), COL["pdf"], "PDF", "lines")
        done(p, t, 2.6, QPointF(276, 32), 18)
        sparkles(p, QPointF(276, 32), t, 2.7, theme.SUCCESS, 5, 18)


def a_msg(p, t, n, card):
    with xf(p, 66, 70, 1.0 + 0.04 * math.sin(t * 3) * (1 - phase(t, 1.0, 1.2))):
        r = QRectF(-44, -30, 88, 60)
        soft_shadow(p, r, 6, 1.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(16, 110, 190))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(rpen(QColor(255, 255, 255), 2))
        p.drawPolyline([QPointF(-34, -18), QPointF(0, 6), QPointF(34, -18)])
        text(p, QRectF(-44, 12, 88, 14), ".MSG", 9, QFont.Weight.Bold, QColor(255, 255, 255),
             Qt.AlignmentFlag.AlignCenter)
    text(p, QRectF(16, 108, 110, 14), "no Outlook needed", 8.5, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 0.4, 0.8))
    flow(p, QPointF(112, 68), QPointF(206, 68), t, 0.6, 1.6, QColor(16, 110, 190), 5, 16)
    k = pop(t, 1.5, 0.5)
    if k > 0:
        glow(p, QPointF(240, 70), 66, COL["pdf"], phase(t, 1.8, 2.2))
        with xf(p, 240, 68 + bob(t, 2.2), k):
            soft_shadow(p, QRectF(-36, -48, 72, 96), 5, 1.2)
            page(p, QRectF(-36, -48, 72, 96), COL["pdf"], "PDF", "none")
            for i, w in enumerate((30, 40, 26)):  # From / To / Subject
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(theme.TEXT, 0.5))
                p.drawRoundedRect(QRectF(-26, -36 + i * 8, 10, 3), 1.5, 1.5)
                p.setBrush(with_alpha(theme.TEXT, 0.25))
                p.drawRoundedRect(QRectF(-12, -36 + i * 8, w, 3), 1.5, 1.5)
            lines(p, QRectF(-26, -8, 48, 22), with_alpha(theme.TEXT, 0.25), 4, h=2.6)
        tag(p, QPointF(240, 130), "+ attachments", COL["zip"], phase(t, 2.3, 2.6), px=8.5)
        sparkles(p, QPointF(272, 24), t, 2.0, COL["pdf"], 6, 22)


def a_rename(p, t, n, card):
    old = ["IMG_8812.jpg", "DSC0042.jpg", "photo (3).jpg", "IMG_8790.jpg"]
    new = ["2026-11-01 01.jpg", "2026-11-01 02.jpg", "2026-11-02 03.jpg", "2026-11-03 04.jpg"]
    for i in range(4):
        y = 30 + i * 24
        r = QRectF(14, y, 110, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(theme.TEXT, 0.06))
        p.drawRoundedRect(r, 5, 5)
        text(p, r.adjusted(8, 0, 0, 0), old[i], 8.5, QFont.Weight.Normal, theme.DIM)
        s = phase(t, 0.8 + i * 0.25, 1.4 + i * 0.25)
        flow(p, QPointF(126, y + 9), QPointF(168, y + 9), t, 0.7 + i * 0.25, 1.4 + i * 0.25, theme.ACCENT, 2, 4,
             2.0)
        if s > 0:
            k = pop(t, 1.2 + i * 0.25, 0.4)
            with xf(p, 232, y + 9, k):
                rr = QRectF(-62, -9, 124, 18)
                soft_shadow(p, rr, 5, 0.6)
                p.setPen(QPen(with_alpha(theme.ACCENT, 0.5), 1))
                p.setBrush(theme.SURFACE)
                p.drawRoundedRect(rr, 5, 5)
            text(p, QRectF(176, y, 124, 18), new[i], 8.5, QFont.Weight.DemiBold, theme.ACCENT,
                 Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 1.35 + i * 0.25, 1.6 + i * 0.25))
    text(p, QRectF(150, 128, 150, 14), "copies; originals kept", 8.5, QFont.Weight.DemiBold, theme.DIM,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 2.6, 3.0))
    sparkles(p, QPointF(292, 26), t, 2.4, theme.ACCENT, 5, 18)


def a_watch(p, t, n, card):
    folder = QRectF(18, 46, 100, 72)
    soft_shadow(p, folder, 7, 0.9)
    _folder(p, folder, 0, back=True)
    # the folder "watches": a soft pulse around it
    ring = (t * 0.6) % 1.0
    p.setPen(QPen(with_alpha(theme.ACCENT, 0.4 * (1 - ring)), 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(folder.adjusted(-6 * ring - 2, -6 * ring - 10, 6 * ring + 2, 6 * ring + 2), 9, 9)
    for k, (label_, col) in enumerate((("DOCX", COL["doc"]), ("PNG", COL["image"]))):
        at = 0.4 + k * 1.2
        drop = phase(t, at, at + 0.7)
        if drop <= 0:
            continue
        e = ease_in_out(drop)
        x, y = 68 + (k * 10 - 5), 6 + 64 * e
        if drop < 1:
            with xf(p, x, y, 0.62):
                page(p, QRectF(-22, -28, 44, 56), col, label_, "lines")
        out_k = pop(t, at + 0.8, 0.45)
        if out_k > 0:
            flow(p, QPointF(122, 80), QPointF(210, 50 + k * 40), t, at + 0.6, at + 1.1, theme.ACCENT, 3, 8, 2.0)
            with xf(p, 234, 50 + k * 42, out_k * 0.62):
                soft_shadow(p, QRectF(-22, -28, 44, 56), 4, 1.0)
                page(p, QRectF(-22, -28, 44, 56), COL["pdf"], "PDF", "lines")
    _folder(p, folder, 0, back=False)
    text(p, QRectF(folder.left(), folder.bottom() + 4, folder.width(), 14), "Inbox, watched", 8.5,
         QFont.Weight.DemiBold, theme.DIM, Qt.AlignmentFlag.AlignCenter)
    text(p, QRectF(196, 130, 100, 12), "by themselves", 8.5, QFont.Weight.DemiBold, theme.ACCENT,
         Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 2.6, 3.0))


def a_libre(p, t, n, card):
    with xf(p, 62, 72, 1.0):
        soft_shadow(p, QRectF(-34, -46, 68, 92), 5, 1.0)
        page(p, QRectF(-34, -46, 68, 92), COL["doc"], "DOCX", "lines")
    badge = pop(t, 0.5, 0.5)
    if badge > 0:  # no Office: LibreOffice steps in
        with xf(p, 150, 40, badge):
            r = QRectF(-44, -11, 88, 22)
            soft_shadow(p, r, 11, 0.8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(24, 160, 90))
            p.drawRoundedRect(r, 11, 11)
            text(p, r, "LibreOffice", 9, QFont.Weight.Bold, QColor(255, 255, 255), Qt.AlignmentFlag.AlignCenter)
        text(p, QRectF(106, 54, 90, 12), "no Office? fine", 8, QFont.Weight.DemiBold, theme.DIM,
             Qt.AlignmentFlag.AlignCenter, alpha=phase(t, 0.8, 1.2))
    flow(p, QPointF(100, 86), QPointF(204, 76), t, 1.0, 2.0, QColor(24, 160, 90), 5, 14)
    k = pop(t, 1.9, 0.5)
    if k > 0:
        glow(p, QPointF(240, 72), 62, COL["pdf"], phase(t, 2.2, 2.6))
        with xf(p, 240, 72 + bob(t, 2.5), k):
            soft_shadow(p, QRectF(-34, -46, 68, 92), 5, 1.2)
            page(p, QRectF(-34, -46, 68, 92), COL["pdf"], "PDF", "lines")
        sparkles(p, QPointF(270, 28), t, 2.2, COL["pdf"], 6, 22)


STORIES = {name[2:]: fn for name, fn in globals().items() if name.startswith("a_")}

# (world, story, title, caption). Worlds come from universe.gather(); a world with no story
# here still gets a card (the generic one), so new kinds of files always show up.
CARDS = [
    ("web", "web_drag", "Drag from any browser", "Hold Ctrl + Shift while dragging; drop on the circle."),
    ("web", "web_table", "Web tables to Excel", "Select a table on any page and drag it in."),
    ("web", "web_clip", "Clip any text", "Select text on a page, tap Ctrl + Shift: PDF, Word or text."),
    ("web", "web_page", "Save the whole page", "Tap Ctrl + Shift on a browser: PDF or one long picture."),
    ("web", "web_qr", "QR code for any link", "Scan it with a phone; checked by reading it back."),
    ("web", "web_bigger", "Always the biggest picture", "The largest size the page offers, not the preview."),
    ("web", "web_cloud", "Shared links become files", "Google Drive, Dropbox and OneDrive links."),
    ("web", "web_webp", "WEBP downloads to JPG", "Downloaded pictures get a JPG copy, by themselves."),
    ("web", "web_copied", "Screenshots in a tap", "Copy a picture, tap Ctrl + Shift, pick a format."),
    ("web", "web_reader", "Just the article", "A clean PDF: no ads, menus or cookie banners."),
    ("web", "web_pictures", "Every picture on a page", "At their biggest, in one folder; icons left out."),
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
    ("pdf", "pdf_sign", "Sign a PDF", "Your name in handwriting, or a picture of your signature."),
    ("office", "office_pdf", "Word, Excel, PowerPoint to PDF", "DOCX, XLSX and PPTX, as PDF."),
    ("office", "libre", "No Office? LibreOffice", "The free LibreOffice does it when Office isn't there."),
    ("ebooks", "ebook", "E-books to PDF", "EPUB, MOBI, FB2 and comics."),
    ("data", "sheet_csv", "Sheets to CSV", "Spreadsheets to plain, portable text."),
    ("data", "json_yaml", "JSON, YAML, TOML, XML", "Data files, rewritten line by line."),
    ("data", "contacts", "Contacts to a sheet", "vCard files become rows you can sort."),
    ("sound", "audio", "WAV to MP3", "Music and recordings, a tenth of the size."),
    ("sound", "video_sound", "Sound from a video", "Keep just the audio of a clip."),
    ("sound", "video_frame", "A still from a video", "Any moment as a JPG, or nine in one sheet."),
    ("sound", "audio_trim", "Trim a recording", "Keep only the part between two times."),
    ("subtitles", "subtitles", "Subtitles, any format", "SRT, VTT, ASS and more."),
    ("text", "markdown", "Markdown to a document", "Notes become a clean PDF or web page."),
    ("mail", "mail", "Saved e-mails to PDF", "EML and MHTML, printable and searchable."),
    ("mail", "msg", "Outlook .msg to PDF", "Read without Outlook; attachments in a ZIP."),
    ("maps", "map", "GPS tracks", "GPX, KML, GeoJSON and more."),
    ("models", "model3d", "3D models", "STL, OBJ, PLY, glTF, plus a picture of it."),
    ("drawings", "cad", "CAD plans", "DXF drawings to SVG, PDF or PNG."),
    ("drawings", "vector", "Vector to picture", "SVG and AI artwork as PNG."),
    ("fonts", "font", "Fonts", "Desktop fonts to web fonts and back."),
    ("archives", "zip", "Pack into ZIP or 7Z", "Many files, one small archive."),
    ("archives", "unzip", "Unpack anything", "ZIP, 7Z, RAR, TAR, opened in place."),
    ("archives", "rename", "Rename many files", "Tidy names by date or number, as copies."),
    ("archives", "watch", "Watch folders", "Files you drop in are converted by themselves."),
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
        tt = self.now + self.offset if motion_ok() else STILL_T
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
        worlds = sorted(worlds, key=lambda w: w.key != "web")  # the browser features first: the highlight
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
        if motion_ok():
            self.timer.start()
        else:  # Reduce motion: every card shows its result, still
            for c in self.gallery.cards:
                c.update()

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
