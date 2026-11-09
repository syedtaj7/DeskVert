"""Animation toolkit for Tapshift's windows.

Everything here animates only while it's on screen (timers stop when hidden),
so the tray app still costs nothing while idle.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt,
                            QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QAbstractButton, QGraphicsOpacityEffect, QWidget

from . import theme

# ---------------------------------------------------------------- fonts & easing

_display_family: str | None = None


def display_family() -> str:
    global _display_family
    if _display_family is None:
        fams = set(QFontDatabase.families())
        _display_family = next((f for f in ("Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI")
                                if f in fams), "Segoe UI")
    return _display_family


def font(px: float, weight: QFont.Weight = QFont.Weight.Normal, display: bool = False) -> QFont:
    f = QFont(display_family() if display else theme.FONT)
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(weight)
    return f


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def ease_out(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = clamp(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_back(t: float, s: float = 1.6) -> float:
    t = clamp(t)
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def phase(t: float, start: float, end: float) -> float:
    """0..1 progress of t through [start, end]."""
    if end <= start:
        return 1.0 if t >= end else 0.0
    return clamp((t - start) / (end - start))


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = clamp(t)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


def with_alpha(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlphaF(clamp(a) * c.alphaF())
    return out


def accent_gradient(x1: float, y1: float, x2: float, y2: float) -> QLinearGradient:
    """The accent as a brush. Deliberately flat (one color): no gradients in Tapshift's design."""
    g = QLinearGradient(x1, y1, x2, y2)
    g.setColorAt(0, theme.ACCENT)
    g.setColorAt(1, theme.ACCENT)
    return g


class Clock(QWidget):
    """A widget that repaints at ~60 fps while visible; ``self.t`` is seconds since shown."""

    FPS = 60

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t0 = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / self.FPS))
        self._timer.timeout.connect(self.update)

    @property
    def t(self) -> float:
        return time.perf_counter() - self._t0

    def restart(self):
        self._t0 = time.perf_counter()

    def showEvent(self, e):
        self.restart()
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)


# ---------------------------------------------------------------- background


class Aurora(QWidget):
    """Window backdrop: a calm, flat surface with a hairline edge (no blobs, no gradients)."""

    radius = theme.RADIUS_CARD

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, self.radius, self.radius)
        p.fillPath(path, theme.BG)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


# ---------------------------------------------------------------- logo & text


class AnimatedLogo(Clock):
    """The Tapshift mark drawing itself in once, then holding still."""

    def __init__(self, size: int = 120, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(size, size))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self.width()
        theme.paint_logo(p, QPointF(s / 2, s / 2), s * 0.82, progress=ease_out(self.t / 1.0))
        p.end()
        if self.t > 1.1:
            self._timer.stop()


def paint_wordmark(p: QPainter, rect: QRectF, text: str, f: QFont, align=Qt.AlignmentFlag.AlignCenter):
    """Solid text. For the brand name, "Tap" in the text color and "shift" in the accent."""
    fm = QFontMetricsF(f)
    parts = [(text[:3], theme.TEXT), (text[3:], theme.ACCENT)] if text == "Tapshift" else [(text, theme.TEXT)]
    w = sum(fm.horizontalAdvance(t) for t, _ in parts)
    if align & Qt.AlignmentFlag.AlignLeft:
        x = rect.left()
    elif align & Qt.AlignmentFlag.AlignRight:
        x = rect.right() - w
    else:
        x = rect.center().x() - w / 2
    y = rect.center().y() + (fm.ascent() - fm.descent()) / 2
    p.setFont(f)
    for t, col in parts:
        p.setPen(col)
        p.drawText(QPointF(x, y), t)
        x += fm.horizontalAdvance(t)


class GradientTitle(QWidget):
    """The large wordmark/title (name kept for compatibility; it's solid, not a gradient)."""

    def __init__(self, text: str, px: int = 52, parent=None, align=Qt.AlignmentFlag.AlignCenter):
        super().__init__(parent)
        self.text, self.f, self.align = text, font(px, QFont.Weight.DemiBold, display=True), align
        self.f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 97)
        self.setFixedHeight(int(px * 1.3))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_wordmark(p, QRectF(self.rect()), self.text, self.f, self.align)
        p.end()


# ---------------------------------------------------------------- buttons


class PillButton(QAbstractButton):
    """Rounded button with an animated hover glow. kind: 'primary' | 'ghost'."""

    def __init__(self, text: str, kind: str = "primary", parent=None, min_width: int = 120):
        super().__init__(parent)
        self.setText(text)
        self.kind = kind
        self._hover = 0.0
        self._press = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setMinimumWidth(min_width)
        self.setFont(font(13, QFont.Weight.DemiBold))
        self._anim = QVariantAnimation(self, duration=180, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_hover)

    def sizeHint(self):
        w = QFontMetricsF(self.font()).horizontalAdvance(self.text()) + 44
        return QSize(int(max(self.minimumWidth(), w)), 40)

    def _set_hover(self, v):
        self._hover = float(v)
        self.update()

    def _animate_to(self, v: float):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(v)
        self._anim.start()

    def enterEvent(self, e):
        self._animate_to(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate_to(0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self._press = 1.0
        self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._press = 0.0
        self.update()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Tactile press: the button sinks by 1 px instead of glowing.
        r = QRectF(self.rect()).adjusted(1, 1 + self._press, -1, -1 + self._press)
        radius = theme.RADIUS_CONTROL
        if not self.isEnabled():
            p.setOpacity(0.45)
        if self.kind == "primary":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(mix(theme.ACCENT, theme.ACCENT_HOVER, self._hover))
            p.drawRoundedRect(r, radius, radius)
            p.setPen(theme.ON_ACCENT)
        else:
            p.setPen(QPen(theme.LINE, 1))
            p.setBrush(mix(theme.SURFACE, theme.SURFACE2, self._hover))
            p.drawRoundedRect(r, radius, radius)
            p.setPen(theme.TEXT)
        p.setFont(self.font())
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


class Toggle(QAbstractButton):
    """An animated on/off switch."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(QSize(46, 26))
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=200, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._on_toggled)

    def _set_pos(self, v):
        self._pos = float(v)
        self.update()

    def _on_toggled(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.TRACK)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self._pos > 0:
            p.setOpacity(self._pos)
            p.setBrush(theme.ACCENT)
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            p.setOpacity(1)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setBrush(mix(theme.DIM, theme.ON_ACCENT, self._pos))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        p.end()


class Segmented(QWidget):
    """Options in a pill, with a highlight that slides to the chosen one."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], value: str, parent=None):
        super().__init__(parent)
        self.options = options  # (value, label)
        self.value = value
        self._x = float(self._index(value))
        self._anim = QVariantAnimation(self, duration=240, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_x)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(12, QFont.Weight.DemiBold))
        fm = QFontMetricsF(self.font())
        self._w = max(fm.horizontalAdvance(lbl) for _, lbl in options) + 28
        self.setFixedSize(QSize(int(self._w * len(options) + 8), 36))

    def _index(self, value: str) -> int:
        return next((i for i, (v, _) in enumerate(self.options) if v == value), 0)

    def _set_x(self, v):
        self._x = float(v)
        self.update()

    def set_value(self, value: str, emit: bool = True):
        if value == self.value:
            return
        self.value = value
        self._anim.stop()
        self._anim.setStartValue(self._x)
        self._anim.setEndValue(float(self._index(value)))
        self._anim.start()
        if emit:
            self.changed.emit(value)

    def mousePressEvent(self, e):
        i = int((e.position().x() - 4) // self._w)
        if 0 <= i < len(self.options):
            self.set_value(self.options[i][0])

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        hl = QRectF(4 + self._x * self._w, 4, self._w, r.height() - 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.ACCENT)
        p.drawRoundedRect(hl, hl.height() / 2, hl.height() / 2)
        p.setFont(self.font())
        for i, (_, label) in enumerate(self.options):
            cell = QRectF(4 + i * self._w, 4, self._w, r.height() - 7)
            near = clamp(1 - abs(self._x - i))
            p.setPen(mix(theme.DIM, theme.ON_ACCENT, near))
            p.drawText(cell, Qt.AlignmentFlag.AlignCenter, label)
        p.end()


class StepDots(QWidget):
    """Page indicator: the current page is a stretched, glowing pill."""

    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.count = count
        self._pos = 0.0
        self._anim = QVariantAnimation(self, duration=320, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_pos", float(v)), self.update()))
        self.setFixedSize(QSize(count * 18 + 20, 14))

    def set_index(self, i: int):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(i))
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        x = 2.0
        for i in range(self.count):
            near = clamp(1 - abs(self._pos - i))
            w = 8 + 18 * near
            r = QRectF(x, 3, w, 8)
            if near > 0.02:
                p.setBrush(theme.ACCENT)
                p.setOpacity(0.35 + 0.65 * near)
            else:
                p.setBrush(theme.TRACK)
                p.setOpacity(1)
            p.drawRoundedRect(r, 4, 4)
            p.setOpacity(1)
            x += w + 6
        p.end()


# ---------------------------------------------------------------- small painted pieces


def paint_keycap(p: QPainter, r: QRectF, label: str, pressed: float = 0.0, glow: float = 0.0):
    """A keyboard key. ``pressed`` 0..1 pushes it down, ``glow`` lights it up."""
    depth = 5 * (1 - pressed)
    body = QRectF(r.left(), r.top() + (5 - depth), r.width(), r.height() - 5)
    side = QRectF(body.left(), body.top() + 4, body.width(), body.height() + depth - 4)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.TRACK.darker(140) if theme.DARK else theme.TRACK.darker(115))
    p.drawRoundedRect(side, theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)
    p.setBrush(mix(theme.SURFACE2, theme.ACCENT, glow))
    p.setPen(QPen(mix(theme.LINE, theme.ACCENT, glow), 1))
    p.drawRoundedRect(body, theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)
    p.setPen(mix(theme.TEXT, theme.ON_ACCENT, glow))
    p.setFont(font(min(18, body.height() * 0.36), QFont.Weight.DemiBold))
    p.drawText(body, Qt.AlignmentFlag.AlignCenter, label)


def paint_check(p: QPainter, c: QPointF, size: float, progress: float, color: QColor | None = None,
                ring: bool = True):
    """A check mark in a circle that draws itself in (progress 0..1)."""
    color = color or theme.SUCCESS
    if ring:
        ring_p = clamp(progress * 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(color, 0.18 * ring_p))
        p.drawEllipse(c, size / 2 * ring_p, size / 2 * ring_p)
    tick = clamp(progress * 2 - 0.6)
    if tick <= 0:
        return
    pts = [QPointF(c.x() - size * 0.22, c.y() + size * 0.01), QPointF(c.x() - size * 0.06, c.y() + size * 0.17),
           QPointF(c.x() + size * 0.24, c.y() - size * 0.17)]
    l1 = math.dist((pts[0].x(), pts[0].y()), (pts[1].x(), pts[1].y()))
    l2 = math.dist((pts[1].x(), pts[1].y()), (pts[2].x(), pts[2].y()))
    drawn = tick * (l1 + l2)
    pen = QPen(color, max(2.0, size * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    path = QPainterPath(pts[0])
    if drawn <= l1:
        f = drawn / l1
        path.lineTo(QPointF(pts[0].x() + (pts[1].x() - pts[0].x()) * f, pts[0].y() + (pts[1].y() - pts[0].y()) * f))
    else:
        path.lineTo(pts[1])
        f = (drawn - l1) / l2
        path.lineTo(QPointF(pts[1].x() + (pts[2].x() - pts[1].x()) * f, pts[1].y() + (pts[2].y() - pts[1].y()) * f))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def paint_file_icon(p: QPainter, r: QRectF, kind: str, label: str = ""):
    """A small file illustration. kind: image | doc | sheet | slides | pdf."""
    colors = {"image": (QColor(56, 189, 248), QColor(129, 140, 248)), "doc": (QColor(59, 130, 246), QColor(37, 99, 235)),
              "sheet": (QColor(34, 197, 94), QColor(21, 128, 61)), "slides": (QColor(249, 115, 22), QColor(234, 88, 12)),
              "pdf": (QColor(239, 68, 68), QColor(190, 18, 60))}
    a, b = colors.get(kind, colors["doc"])
    fold = r.width() * 0.28
    path = QPainterPath()
    path.moveTo(r.left() + 6, r.top())
    path.lineTo(r.right() - fold, r.top())
    path.lineTo(r.right(), r.top() + fold)
    path.lineTo(r.right(), r.bottom() - 6)
    path.quadTo(r.right(), r.bottom(), r.right() - 6, r.bottom())
    path.lineTo(r.left() + 6, r.bottom())
    path.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - 6)
    path.lineTo(r.left(), r.top() + 6)
    path.quadTo(r.left(), r.top(), r.left() + 6, r.top())
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, a)
    g.setColorAt(1, b)
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(path, g)
    corner = QPainterPath()
    corner.moveTo(r.right() - fold, r.top())
    corner.lineTo(r.right() - fold, r.top() + fold - 4)
    corner.quadTo(r.right() - fold, r.top() + fold, r.right() - fold + 4, r.top() + fold)
    corner.lineTo(r.right(), r.top() + fold)
    corner.closeSubpath()
    p.fillPath(corner, QColor(255, 255, 255, 90))
    p.setPen(QColor(255, 255, 255))
    if kind == "image":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawEllipse(QPointF(r.left() + r.width() * 0.34, r.top() + r.height() * 0.42), r.width() * 0.08, r.width() * 0.08)
        m = QPainterPath()
        m.moveTo(r.left() + r.width() * 0.18, r.bottom() - r.height() * 0.24)
        m.lineTo(r.left() + r.width() * 0.45, r.top() + r.height() * 0.55)
        m.lineTo(r.left() + r.width() * 0.62, r.top() + r.height() * 0.68)
        m.lineTo(r.left() + r.width() * 0.72, r.top() + r.height() * 0.6)
        m.lineTo(r.right() - r.width() * 0.16, r.bottom() - r.height() * 0.24)
        m.closeSubpath()
        p.fillPath(m, QColor(255, 255, 255, 220))
    if label:
        p.setPen(QColor(255, 255, 255))
        p.setFont(font(max(8, r.width() * 0.2), QFont.Weight.Bold))
        p.drawText(QRectF(r.left(), r.bottom() - r.height() * 0.36, r.width(), r.height() * 0.3),
                   Qt.AlignmentFlag.AlignCenter, label)


def paint_cursor(p: QPainter, tip: QPointF, scale: float = 1.0):
    pts = [(0, 0), (0, 17), (4.2, 13), (7.4, 19.6), (10.2, 18.4), (7.1, 12), (12.6, 12)]
    path = QPainterPath(QPointF(tip.x(), tip.y()))
    for x, y in pts[1:]:
        path.lineTo(QPointF(tip.x() + x * scale, tip.y() + y * scale))
    path.closeSubpath()
    p.setPen(QPen(QColor(15, 17, 21), 1.4))
    p.setBrush(QColor(255, 255, 255))
    p.drawPath(path)


# ---------------------------------------------------------------- entrance effects


def fade_in(widget: QWidget, delay_ms: int = 0, duration: int = 420, rise: int = 14):
    """Fade a widget in while it rises into place."""
    eff = QGraphicsOpacityEffect(widget)
    eff.setOpacity(0.0)
    widget.setGraphicsEffect(eff)

    def alive() -> bool:
        # A newer fade_in on the same widget replaces (and deletes) this effect.
        try:
            import shiboken6

            return shiboken6.isValid(eff) and shiboken6.isValid(widget) and widget.graphicsEffect() is eff
        except Exception:
            return False

    def done():
        if alive():
            widget.setGraphicsEffect(None)

    def go():
        if not alive():
            return
        if not widget.isVisible():
            eff.setOpacity(1.0)
            return
        a = QPropertyAnimation(eff, b"opacity", widget)
        a.setDuration(duration)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.finished.connect(done)
        a.start()
        if rise:
            m = QPropertyAnimation(widget, b"pos", widget)
            end = widget.pos()
            m.setDuration(duration)
            m.setStartValue(end + QPointF(0, rise).toPoint())
            m.setEndValue(end)
            m.setEasingCurve(QEasingCurve.Type.OutCubic)
            m.start()

    QTimer.singleShot(delay_ms, go)
