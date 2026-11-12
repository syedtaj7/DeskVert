"""Two small windows:

- Notice: a message card near the cursor ("Can't convert this file", "Nothing
  selected"...). Closes with OK, Esc, a click elsewhere, or after a few seconds.
- ProgressPanel: a card at the bottom-right of the screen showing what's being
  converted, a progress bar, Cancel, and the result: what was saved, the size
  before and after, and Open / Copy / Show in folder / Undo (or what went wrong).

Neither takes keyboard focus away from what you're doing unless needed.
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QMimeData, QParallelAnimationGroup, QPoint, QPointF, QPropertyAnimation,
                            QRectF, QSize, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QImage, QLinearGradient, QPainter,
                           QPen)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from . import theme
from .fx import with_alpha

_FLAGS = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint


def _font(px: float, weight=QFont.Weight.Normal) -> QFont:
    f = QFont(theme.FONT)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


class StatusIcon(QWidget):
    """A colored circle with a symbol: info / warning / error / success / busy."""

    def __init__(self, kind: str = "info", parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(QSize(30, 30))

    def set_kind(self, kind: str):
        self.kind = kind
        self.update()

    def paintEvent(self, _):
        color = {"warning": theme.WARN, "error": theme.ERROR, "success": theme.SUCCESS}.get(self.kind, theme.ACCENT_B)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(color)
        bg.setAlpha(40)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawEllipse(QRectF(1, 1, 28, 28))
        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if self.kind == "success":
            p.drawPolyline([QPointF(9.5, 15.5), QPointF(13.5, 19.5), QPointF(20.5, 11)])
        elif self.kind == "error":
            p.drawLine(QPointF(11, 11), QPointF(19, 19))
            p.drawLine(QPointF(19, 11), QPointF(11, 19))
        elif self.kind == "warning":
            p.drawLine(QPointF(15, 9), QPointF(15, 16.5))
            p.drawPoint(QPointF(15, 20.5))
        elif self.kind == "busy":
            p.drawArc(QRectF(8, 8, 14, 14), 90 * 16, 270 * 16)
        else:  # info
            p.drawPoint(QPointF(15, 9.5))
            p.drawLine(QPointF(15, 13.5), QPointF(15, 20.5))
        p.end()


class Bar(QWidget):
    """Rounded progress bar with the accent gradient."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.color_override: QColor | None = None
        self.setFixedHeight(6)

    def set_value(self, v: float):
        self.value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.TRACK)
        p.drawRoundedRect(r, 3, 3)
        if self.value > 0:
            w = max(self.height(), r.width() * self.value)
            if self.color_override is not None:
                p.setBrush(self.color_override)
            else:
                g = QLinearGradient(0, 0, r.width(), 0)
                g.setColorAt(0, theme.ACCENT_A)
                g.setColorAt(1, theme.ACCENT_B)
                p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 0, w, r.height()), 3, 3)
        p.end()


class _Card(QWidget):
    """Frameless translucent window with a rounded, shadowed card inside."""

    def __init__(self, width: int):
        super().__init__(None, _FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setStyleSheet(theme.CARD_QSS)
        self.card.setFixedWidth(width)
        sh = QGraphicsDropShadowEffect(self.card)
        sh.setBlurRadius(36)
        sh.setOffset(0, 6)
        sh.setColor(theme.SHADOW)
        self.card.setGraphicsEffect(sh)
        outer.addWidget(self.card)

    def _fade_in(self):
        self.setWindowOpacity(0.0)
        self.show()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(140)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start()


def _clamp(w: QWidget, pos: QPoint) -> None:
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    area = screen.availableGeometry()
    x = min(max(pos.x(), area.left()), area.right() - w.width())
    y = min(max(pos.y(), area.top()), area.bottom() - w.height())
    w.move(x, y)


# ====================================================================== notice


class Notice(_Card):
    def __init__(self, title: str, message: str, kind: str = "warning", ms: int = 9000):
        super().__init__(340)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        row = QHBoxLayout(self.card)
        row.setContentsMargins(16, 14, 14, 14)
        row.setSpacing(12)
        icon = StatusIcon(kind)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("big")
        t.setWordWrap(True)
        m = QLabel(message)
        m.setWordWrap(True)
        m.setStyleSheet(f"color: {theme.rgba(theme.DIM)}; font-size: 12px;")
        ok = QPushButton("OK")
        ok.setObjectName("primary")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self.close)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(ok)
        col.addWidget(t)
        col.addWidget(m)
        col.addSpacing(4)
        col.addLayout(btns)
        row.addLayout(col, 1)
        self.adjustSize()
        self._remaining = ms
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close)
        self._outside = QTimer(self)
        self._outside.setInterval(80)
        self._outside.timeout.connect(self._check_outside)

    def show_near_cursor(self):
        _clamp(self, QCursor.pos() + QPoint(-30, 12))
        self._fade_in()
        self._timer.start(self._remaining)
        QTimer.singleShot(250, self._outside.start)  # ignore the click/keys that opened it

    def _check_outside(self):
        from ..winutil import mouse_button_down

        if mouse_button_down() and not self.frameGeometry().contains(QCursor.pos()):
            self.close()

    def enterEvent(self, e):
        self._timer.stop()  # keep it open while you read it
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._timer.start(3000)
        super().leaveEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.close()
        else:
            super().keyPressEvent(e)


# ====================================================================== progress panel


def _size_text(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    return f"{max(1, round(n / 1000))} KB"


def _total_size(paths) -> int:
    total = 0
    for p in paths or []:
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    return total


class _Anim(QWidget):
    """A small painted piece with its own clock, ticking only while it has something to animate."""

    FPS = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t0 = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / self.FPS))
        self._timer.timeout.connect(self._tick)

    @property
    def t(self) -> float:
        return time.perf_counter() - self._t0

    def restart(self):
        self._t0 = time.perf_counter()
        self._timer.start()

    def _tick(self):
        if not self.isVisible() or not self.animating():
            self._timer.stop()
        self.update()

    def animating(self) -> bool:
        return True

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


class LiveIcon(_Anim):
    """Busy: a turning arc. Done: the circle fills and the mark draws itself in, with a small pop."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "busy"
        self.setFixedSize(QSize(34, 34))

    def set_kind(self, kind: str):
        self.kind = kind
        self.restart()

    def animating(self) -> bool:
        return self.kind == "busy" or self.t < 0.8

    def paintEvent(self, _):
        color = {"warning": theme.WARN, "error": theme.ERROR, "success": theme.SUCCESS}.get(self.kind, theme.ACCENT)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(17, 17)
        t = self.t
        if self.kind == "busy":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(color, 0.14))
            p.drawEllipse(c, 15, 15)
            pen = QPen(color, 2.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(QRectF(8, 8, 18, 18), int(-(t * 400) % 360 * 16), 250 * 16)
            p.end()
            return
        pop = _ease(t / 0.35)
        s = 0.7 + 0.3 * pop + 0.08 * math.sin(min(1.0, t / 0.5) * math.pi)
        p.translate(c)
        p.scale(s, s)
        p.translate(-c)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(color, 0.18))
        p.drawEllipse(c, 15, 15)
        pen = QPen(color, 2.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        draw = _ease((t - 0.12) / 0.4)
        if self.kind == "success":
            pts = [QPointF(11, 17.5), QPointF(15.5, 22), QPointF(23.5, 12.5)]
            a = math.dist((pts[0].x(), pts[0].y()), (pts[1].x(), pts[1].y()))
            b = math.dist((pts[1].x(), pts[1].y()), (pts[2].x(), pts[2].y()))
            k = draw * (a + b)
            if k > 0:
                f = min(1.0, k / a)
                p.drawLine(pts[0], pts[0] + (pts[1] - pts[0]) * f)
            if k > a:
                f = (k - a) / b
                p.drawLine(pts[1], pts[1] + (pts[2] - pts[1]) * f)
        elif self.kind == "error":
            d = 5.5 * draw
            p.drawLine(QPointF(17 - d, 17 - d), QPointF(17 + d, 17 + d))
            p.drawLine(QPointF(17 + d, 17 - d), QPointF(17 - d, 17 + d))
        elif self.kind == "warning":
            p.drawLine(QPointF(17, 10), QPointF(17, 10 + 8 * draw))
            if draw > 0.9:
                p.drawPoint(QPointF(17, 23))
        else:  # info
            p.drawPoint(QPointF(17, 11))
            p.drawLine(QPointF(17, 15), QPointF(17, 15 + 8 * draw))
        p.end()


class LiveBar(_Anim):
    """A progress bar that glides to each new value, shimmers while working, and turns green when done."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target = 0.0
        self.shown = 0.0
        self.done = False
        self.color_override: QColor | None = None  # kept for callers of the older bar
        self.setFixedHeight(6)

    def reset(self):
        self.target = self.shown = 0.0
        self.done = False
        self.restart()

    def set_value(self, v: float):
        self.target = max(0.0, min(1.0, v))
        if not self._timer.isActive():
            self.restart()

    def finish(self):
        self.done = True
        self.target = 1.0
        self.restart()

    def animating(self) -> bool:
        return not self.done or abs(self.shown - self.target) > 0.002

    def paintEvent(self, _):
        self.shown += (self.target - self.shown) * 0.18
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.TRACK)
        p.drawRoundedRect(r, 3, 3)
        w = max(self.height(), r.width() * self.shown) if self.shown > 0.002 else 0
        if w:
            p.setBrush(theme.SUCCESS if self.done else theme.ACCENT)
            p.drawRoundedRect(QRectF(0, 0, w, r.height()), 3, 3)
        if not self.done:  # a soft light sweeping along: it's working, even before the first percent
            x = (self.t * 0.8 % 1.4 - 0.2) * r.width()
            g = QLinearGradient(x - 40, 0, x + 40, 0)
            g.setColorAt(0, with_alpha(theme.ACCENT, 0))
            g.setColorAt(0.5, with_alpha(theme.ACCENT if w == 0 else QColor(255, 255, 255), 0.45))
            g.setColorAt(1, with_alpha(theme.ACCENT, 0))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 0, r.width() if w == 0 else w, r.height()), 3, 3)
        p.end()


class SizeStrip(_Anim):
    """Before and after: "HEIC 2.4 MB → WEBP 380 KB   −84 %"."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.before = self.after = ("", 0)
        self.setFixedHeight(30)

    def set_sizes(self, before: tuple[str, int], after: tuple[str, int]):
        self.before, self.after = before, after
        self.restart()

    def animating(self) -> bool:
        return self.t < 0.9

    def _pill(self, p, x, fmt, size, a, accent):
        f1 = _font(10.5, QFont.Weight.Bold)
        f2 = _font(11.5)
        fm1, fm2 = QFontMetrics(f1), QFontMetrics(f2)
        w = fm1.horizontalAdvance(fmt) + fm2.horizontalAdvance(_size_text(size)) + 30
        r = QRectF(x, 3, w, 24)
        p.save()
        p.setOpacity(a)
        p.setPen(QPen(with_alpha(theme.ACCENT, 0.5) if accent else theme.LINE, 1))
        p.setBrush(with_alpha(theme.ACCENT, 0.1) if accent else theme.SURFACE2)
        p.drawRoundedRect(r, 12, 12)
        p.setFont(f1)
        p.setPen(theme.ACCENT if accent and theme.contrast(theme.ACCENT, theme.SURFACE) >= 4.5 else theme.TEXT)
        p.drawText(QRectF(x + 11, 3, w, 24), Qt.AlignmentFlag.AlignVCenter, fmt)
        p.setFont(f2)
        p.setPen(theme.DIM)
        p.drawText(QRectF(x + 11 + fm1.horizontalAdvance(fmt) + 7, 3, w, 24), Qt.AlignmentFlag.AlignVCenter,
                   _size_text(size))
        p.restore()
        return w

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        t = self.t
        w1 = self._pill(p, 0, self.before[0], self.before[1], _ease(t / 0.3), False)
        k = _ease((t - 0.15) / 0.45)
        ax = w1 + 8
        pen = QPen(with_alpha(theme.DIM, k), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(ax, 15), QPointF(ax + 18 * k, 15))
        if k > 0.9:
            p.drawLine(QPointF(ax + 13, 11), QPointF(ax + 18, 15))
            p.drawLine(QPointF(ax + 13, 19), QPointF(ax + 18, 15))
        w2 = self._pill(p, ax + 26, self.after[0], self.after[1], _ease((t - 0.35) / 0.3), True)
        if self.before[1] and self.after[1]:
            change = (self.after[1] - self.before[1]) / self.before[1] * 100
            if abs(change) >= 1:
                p.setFont(_font(12, QFont.Weight.Bold))
                p.setPen(with_alpha(theme.SUCCESS if change < 0 else theme.DIM, _ease((t - 0.55) / 0.3)))
                txt = f"−{abs(change):.0f} %" if change < 0 else f"+{change:.0f} %"
                p.drawText(QRectF(ax + 26 + w2 + 10, 3, 80, 24), Qt.AlignmentFlag.AlignVCenter, txt)
        p.end()


class CloseRing(QAbstractButton):
    """✕ with a thin ring that empties as the card's time runs out (pauses while you point at the card)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(26, 26))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.left = 0.0  # 1 full .. 0 about to close; < 0: no countdown
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(13, 13)
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.HOVER)
            p.drawEllipse(c, 12, 12)
        if self.left > 0:
            pen = QPen(with_alpha(theme.DIM, 0.6), 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(QRectF(2, 2, 22, 22), 90 * 16, int(360 * 16 * self.left))
        pen = QPen(theme.TEXT if self._hover else theme.DIM, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(9.5, 9.5), QPointF(16.5, 16.5))
        p.drawLine(QPointF(16.5, 9.5), QPointF(9.5, 16.5))
        p.end()


class ProgressPanel(_Card):
    """The card at the bottom-right: what's converting, then what was saved, with what you'd do next.

    Slides in, shows progress, then the result: before and after sizes, Open, Copy (paste the new file
    straight into a chat, an e-mail or a folder), Show in folder and Undo. A ring around the close
    button shows when it will go away; pointing at the card holds it."""

    W = 380
    cancel_requested = Signal()
    show_folder = Signal(str)
    undo_requested = Signal(list)  # the files this conversion made
    details_requested = Signal()  # the list of every file in the batch

    def __init__(self):
        super().__init__(self.W)
        self.text_w = self.W - 16 - 14 - 34 - 12 - 26 - 6  # what's left for the words next to the icon
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(16, 14, 14, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.icon = LiveIcon()
        top.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("title")
        self.title.setStyleSheet("font-size: 14px;")
        self.title.setFixedWidth(self.text_w)
        self.name = QLabel()
        self.name.setStyleSheet(f"color: {theme.rgba(theme.TEXT)}; font-size: 12px;")
        self.name.setFixedWidth(self.text_w)
        self.sub = QLabel()
        self.sub.setObjectName("sub")
        self.sub.setStyleSheet(f"color: {theme.rgba(theme.DIM)}; font-size: 12px;")
        self.sub.setWordWrap(True)
        self.sub.setFixedWidth(self.text_w)
        for w in (self.title, self.name, self.sub):
            texts.addWidget(w)
        top.addLayout(texts, 1)
        self.close_btn = CloseRing()
        self.close_btn.setToolTip("Hide (conversions keep running)")
        self.close_btn.clicked.connect(self._dismiss)
        top.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)

        self.sizes = SizeStrip()
        self.sizes_row = QWidget()
        sl = QHBoxLayout(self.sizes_row)
        sl.setContentsMargins(46, 0, 0, 0)
        sl.addWidget(self.sizes, 1)
        lay.addWidget(self.sizes_row)

        barrow = QHBoxLayout()
        barrow.setSpacing(10)
        barrow.setContentsMargins(46, 0, 4, 0)
        self.bar = LiveBar()
        self.pct = QLabel("")
        self.pct.setObjectName("sub")
        self.pct.setFixedWidth(64)
        self.pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        barrow.addWidget(self.bar, 1)
        barrow.addWidget(self.pct)
        self.bar_row = QWidget()
        self.bar_row.setLayout(barrow)
        lay.addWidget(self.bar_row)

        btns = QHBoxLayout()
        btns.setContentsMargins(46, 2, 0, 0)
        btns.setSpacing(6)

        def button(text, tip, slot, primary=False):
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            if primary:
                b.setObjectName("primary")
            b.clicked.connect(slot)
            return b

        self.undo_btn = button("Undo", "Move the new file to the Recycle Bin", self._undo)
        self.undo_btn.setObjectName("flat")
        self.cancel_btn = button("Cancel", "Stop converting; nothing is saved", self.cancel_requested.emit)
        self.copy_btn = button("Copy", "Copy the new file, to paste into a chat, an e-mail or a folder", self._copy)
        self.open_btn = button("Open", "Open the new file", self._open)
        self.details_btn = button("Details", "Every file, and why any failed", self._details)
        self.action_btn = button("", "", self._action, primary=True)  # a one-off action, e.g. "Update" (offer())
        self.folder_btn = button("Show in folder", "Show the new file in File Explorer", self._open_folder, True)
        btns.addWidget(self.undo_btn)
        btns.addStretch(1)
        for b in (self.cancel_btn, self.details_btn, self.copy_btn, self.open_btn, self.folder_btn, self.action_btn):
            btns.addWidget(b)
        self.btn_row = QWidget()
        self.btn_row.setLayout(btns)
        lay.addWidget(self.btn_row)

        self._action_cb = None
        self._output = ""
        self._outputs: list[str] = []
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._dismiss)
        self._hide_after = 0
        self._ring = QTimer(self)  # keeps the close ring's countdown moving
        self._ring.setInterval(80)
        self._ring.timeout.connect(self._ring_tick)
        self._busy = False
        self._leaving = False
        self._slide: QPropertyAnimation | None = None

    # ---------------------------------------------------------------- texts
    def _set_texts(self, title: str, name: str = "", body: str = ""):
        fm = QFontMetrics(self.title.font())
        self.title.setText(fm.elidedText(title, Qt.TextElideMode.ElideRight, self.text_w))
        self.title.setToolTip(title if fm.horizontalAdvance(title) > self.text_w else "")
        fn = QFontMetrics(self.name.font())
        self.name.setText(fn.elidedText(name, Qt.TextElideMode.ElideMiddle, self.text_w))
        self.name.setToolTip(name if fn.horizontalAdvance(name) > self.text_w else "")
        self.name.setVisible(bool(name))
        self.sub.setText(body)
        self.sub.setVisible(bool(body))
        # the wrapped height has to be known before the card is measured, or the last line gets cut off
        self.sub.setFixedHeight(self.sub.heightForWidth(self.text_w) if body else 0)

    def _buttons(self, *shown):
        for b in (self.undo_btn, self.cancel_btn, self.details_btn, self.copy_btn, self.open_btn, self.folder_btn,
                  self.action_btn):
            b.setVisible(b in shown)
        self.btn_row.setVisible(bool(shown))

    # ---------------------------------------------------------------- states
    def start(self, label: str, total: int):
        self._busy = True
        self._hide_timer.stop()
        self._ring.stop()
        self.close_btn.left = 0
        self.icon.set_kind("busy")
        self._set_texts(f"Converting to {label}", "", f"{total} files" if total > 1 else "Starting…")
        self.sizes_row.hide()
        self.bar.reset()
        self.pct.setText("")
        self.bar_row.show()
        self._buttons(self.cancel_btn)
        self._action_cb = None
        self._place_and_show()

    def set_file(self, name: str, index: int, total: int):
        self.name.setVisible(True)
        fn = QFontMetrics(self.name.font())
        self.name.setText(fn.elidedText(name, Qt.TextElideMode.ElideMiddle, self.text_w))
        self.sub.setText(f"File {index} of {total}" if total > 1 else "")
        self.sub.setVisible(total > 1)
        self.sub.setFixedHeight(self.sub.heightForWidth(self.text_w) if total > 1 else 0)
        self._place_and_show()

    def set_progress(self, frac: float):
        if not self._busy:
            return
        self.bar.set_value(frac)
        self.pct.setText(f"{frac * 100:.0f} %" if frac > 0 else "working…")

    def finish(self, kind: str, title: str, body: str, output: str = "", outputs: list[str] | None = None,
               sources: list[str] | None = None, name: str = "", details: bool = False):
        self._busy = False
        self._action_cb = None
        self.icon.set_kind(kind)
        self._output = output
        self._outputs = list(outputs or [])
        self._set_texts(title, name, body)
        before, after = _total_size(sources), _total_size(self._outputs)
        if kind in ("success", "warning") and self._outputs and before and after:
            fmt_in = Path(sources[0]).suffix.lstrip(".").upper() if len(sources) == 1 else f"{len(sources)} files"
            fmt_out = (Path(self._outputs[0]).suffix.lstrip(".").upper() if len(self._outputs) == 1
                       else f"{len(self._outputs)} new files")
            self.sizes.set_sizes((fmt_in, before), (fmt_out, after))
            self.sizes_row.show()
        else:
            self.sizes_row.hide()
        if kind == "success":
            self.bar.finish()
            self.pct.setText("100 %")
            self.bar_row.show()
        else:
            self.bar_row.hide()
        if self._outputs:
            one = len(self._outputs) == 1
            self.undo_btn.setText("Undo" if one else f"Undo all {len(self._outputs)}")
            self.copy_btn.setToolTip("Copy the new file, to paste into a chat, an e-mail or a folder" if one
                                     else f"Copy the {len(self._outputs)} new files, to paste anywhere")
            shown = ([self.undo_btn] + ([self.details_btn] if details else [self.copy_btn])
                     + ([self.open_btn] if one else []) + [self.folder_btn])
            self._buttons(*shown)
        else:
            self._buttons(*(([self.details_btn] if details else []) + ([self.folder_btn] if output else [])))
        self._hide_after = 9000 if kind == "success" else 14000
        self._place_and_show()
        self._countdown(self._hide_after)

    def message(self, kind: str, title: str, body: str, ms: int = 5000):
        if self._busy:
            return
        self.finish(kind, title, body)
        self._countdown(ms)

    def offer(self, kind: str, title: str, body: str, button: str, callback, ms: int = 20000) -> bool:
        """A message with one button (e.g. an update). Not while converting; returns whether it showed."""
        if self._busy:
            return False
        self.finish(kind, title, body)
        self.action_btn.setText(button)
        self._buttons(self.action_btn)
        self._action_cb = callback
        self._place_and_show()
        self._hide_after = ms
        self._countdown(ms)
        return True

    # ---------------------------------------------------------------- the close ring
    def _countdown(self, ms: int):
        self._hide_after = ms
        self._deadline = time.monotonic() + ms / 1000
        self._hide_timer.start(ms)
        self._ring.start()
        self._ring_tick()

    def _ring_tick(self):
        if not self._hide_timer.isActive():
            self.close_btn.left = 1.0 if self._hide_after and not self._busy else 0.0
            self.close_btn.update()
            return
        self.close_btn.left = max(0.0, (self._deadline - time.monotonic()) / (self._hide_after / 1000))
        self.close_btn.update()

    # ---------------------------------------------------------------- window
    def _place_and_show(self):
        for w in (self.title, self.name, self.sub):
            w.updateGeometry()
        self.card.layout().activate()
        self.card.adjustSize()
        self.layout().activate()
        self.adjustSize()
        area = QGuiApplication.primaryScreen().availableGeometry()
        margin = self.layout().contentsMargins()
        # the card's edge sits 12 px from the screen's edge (the window around it holds the shadow)
        home = QPoint(area.right() - self.width() + margin.right() - 12, area.bottom() - self.height() + margin.bottom() - 12)
        sliding = self._slide is not None and self._slide.state() == QParallelAnimationGroup.State.Running
        if self.isVisible() and not self._leaving:
            # Already showing (or still sliding in): never stop the slide-in half way, or the card stays
            # see-through (this happened when "converting this file" arrived right after "started").
            if sliding:
                self._slide_to.setEndValue(home)
            else:
                self.move(home)
                self.setWindowOpacity(1.0)
            return
        if self._slide is not None:
            self._slide.stop()
        self._leaving = False
        self.move(home + QPoint(60, 0))
        self.setWindowOpacity(0.0)
        self.show()
        self._animate(home, 1.0, 320)

    def _animate(self, pos: QPoint, opacity: float, ms: int, then=None):
        group = QParallelAnimationGroup(self)
        a = QPropertyAnimation(self, b"pos", group)
        a.setDuration(ms)
        a.setEndValue(pos)
        a.setEasingCurve(QEasingCurve.Type.OutCubic if opacity > 0 else QEasingCurve.Type.InCubic)
        b = QPropertyAnimation(self, b"windowOpacity", group)
        b.setDuration(ms)
        b.setEndValue(opacity)
        group.addAnimation(a)
        group.addAnimation(b)
        if then is not None:
            group.finished.connect(then)
        else:  # arriving: whatever happened meanwhile, end fully shown
            group.finished.connect(lambda: self.setWindowOpacity(1.0) if not self._leaving else None)
        self._slide = group
        self._slide_to = a
        group.start()

    def _dismiss(self):
        self._hide_timer.stop()
        self._ring.stop()
        if not self.isVisible() or self._leaving:
            return
        self._leaving = True

        def gone():
            if self._leaving:
                self.hide()
                self._leaving = False

        self._animate(self.pos() + QPoint(60, 0), 0.0, 220, gone)

    def _undo(self):
        if self._outputs:
            self.undo_requested.emit(self._outputs)
            self._outputs = []
            self.undo_btn.hide()

    def _open_folder(self):
        if self._output:
            self.show_folder.emit(self._output)
        self._dismiss()

    def _open(self):
        if self._outputs and os.path.exists(self._outputs[0]):
            os.startfile(self._outputs[0])  # noqa: S606 - the file Tapshift just made, opened like a double-click
        self._dismiss()

    def _copy(self):
        """Put the new files on the clipboard like Explorer's Copy (and a picture as a picture, too),
        so Ctrl + V works in a chat, an e-mail or a folder."""
        files = [f for f in self._outputs if os.path.exists(f)]
        if not files:
            return
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(f) for f in files])
        if len(files) == 1 and Path(files[0]).suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"):
            img = QImage(files[0])
            if not img.isNull() and img.width() * img.height() <= 40_000_000:
                data.setImageData(img)
        QGuiApplication.clipboard().setMimeData(data)
        self.copy_btn.setText("Copied")
        QTimer.singleShot(1600, lambda: self.copy_btn.setText("Copy"))

    def _details(self):
        self.details_requested.emit()
        self._dismiss()

    def _action(self):
        cb = self._action_cb
        self._dismiss()
        if cb is not None:
            cb()

    def enterEvent(self, e):
        self._hide_timer.stop()  # hold it while you read it
        self._ring_tick()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._busy and self.isVisible() and self._hide_after and not self._leaving:
            self._countdown(5000)
        super().leaveEvent(e)
