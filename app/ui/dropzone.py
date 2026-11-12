"""The "Drop to convert" circle: appears under the pointer when you hold Ctrl+Shift while
dragging something (a picture in a browser, a file, an attachment...). Let go on it and the
picker opens for what you dropped.

It receives the drop straight from Windows (OLE IDropTarget through pywin32) rather than
through Qt, because browsers and Outlook hand dragged pictures and attachments over as
"virtual files" that only the raw data object gives access to.
"""

from __future__ import annotations

import logging
import math
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme
from .fx import ease_back, ease_out, font, mix, with_alpha

log = logging.getLogger(__name__)

DROPEFFECT_NONE, DROPEFFECT_COPY = 0, 1
VK_LBUTTON = 0x01


class _Target:
    """The COM drop target (its methods are called by Windows on the UI thread)."""

    _public_methods_ = ["DragEnter", "DragOver", "DragLeave", "Drop"]

    def __init__(self, zone: "DropZone"):
        import pythoncom

        self._com_interfaces_ = [pythoncom.IID_IDropTarget]
        self.zone = zone

    def DragEnter(self, data_object, key_state, point, effect):  # noqa: N802 - COM names
        self.zone.entered = True
        self.zone._hover(True)
        return DROPEFFECT_COPY

    def DragOver(self, key_state, point, effect):  # noqa: N802
        return DROPEFFECT_COPY

    def DragLeave(self):  # noqa: N802
        self.zone._hover(False)

    def Drop(self, data_object, key_state, point, effect):  # noqa: N802
        from ..dropread import DropError, read

        self.zone._hover(False)
        try:
            dropped = read(data_object)  # now: the data only exists during the drop
        except DropError as e:
            self.zone.failed.emit(str(e))
            return DROPEFFECT_NONE
        except Exception:  # noqa: BLE001
            log.exception("reading a drop failed")
            self.zone.failed.emit("Tapshift couldn't read what was dropped.")
            return DROPEFFECT_NONE
        self.zone._got_drop(dropped)
        return DROPEFFECT_COPY if not dropped.empty else DROPEFFECT_NONE


class DropZone(QWidget):
    dropped = Signal(object)  # dropread.Dropped
    failed = Signal(str)
    missed = Signal()  # the circle went away without anything ever being dragged over it

    SIZE = 236  # the window: the disc (R) plus room for its halo and the rings that call you in
    R = 81
    FPS = 40

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(QSize(self.SIZE, self.SIZE))
        self._registered = False
        self._target = None
        self.hot = 0.0  # 0..1: something is being dragged over it
        self._hot_to = 0.0
        self.t0 = time.perf_counter()
        self.done = False
        self.entered = False  # a real drag reached the circle
        self._hot_at = -9.0
        self._released_at = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / self.FPS))
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------ Windows drop target
    def _register(self) -> bool:
        if self._registered:
            return True
        try:
            import pythoncom
            from win32com.server.util import wrap

            pythoncom.OleInitialize()
            hwnd = int(self.winId())
            try:
                pythoncom.RevokeDragDrop(hwnd)  # in case Qt registered its own
            except Exception:  # noqa: BLE001
                pass
            self._target = wrap(_Target(self), pythoncom.IID_IDropTarget)
            pythoncom.RegisterDragDrop(hwnd, self._target)
            self._registered = True
        except Exception:  # noqa: BLE001
            log.exception("couldn't register the drop target")
        return self._registered

    def unregister(self) -> None:
        if self._registered:
            try:
                import pythoncom

                pythoncom.RevokeDragDrop(int(self.winId()))
            except Exception:  # noqa: BLE001
                pass
            self._registered = False

    # ------------------------------------------------------------ showing
    def show_at(self, pos: QPoint | None = None) -> bool:
        """Centred under the pointer, kept on screen. False if Windows wouldn't take the drop target."""
        pos = pos or QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(pos.x() - self.SIZE // 2, area.left()), area.right() - self.SIZE)
        y = min(max(pos.y() - self.SIZE // 2, area.top()), area.bottom() - self.SIZE)
        self.move(x, y)
        self.done = False
        self.entered = False
        self.hot = self._hot_to = 0.0
        self._hot_at = -9.0
        self._released_at = 0.0
        self.t0 = time.perf_counter()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        if not self._register():
            self.hide()
            return False
        self._timer.start()
        return True

    def _hover(self, on: bool) -> None:
        if on and self._hot_to < 1.0:
            self._hot_at = time.perf_counter()  # a ripple when something arrives over the circle
        self._hot_to = 1.0 if on else 0.0

    def _got_drop(self, dropped) -> None:
        self.done = True
        QTimer.singleShot(0, lambda: (self.hide(), self.dropped.emit(dropped)))

    def _tick(self) -> None:
        import ctypes

        self.hot += (self._hot_to - self.hot) * 0.25
        now = time.perf_counter()
        button = bool(ctypes.windll.user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        if not button and not self._released_at:
            self._released_at = now  # let go somewhere else: a moment for the drop to arrive, then go
        if button:
            self._released_at = 0.0
        if self.done or (self._released_at and now - self._released_at > 0.6) or now - self.t0 > 30:
            self._timer.stop()
            self.hide()
            if not self.done and not self.entered:
                self.missed.emit()  # e.g. Shift + press on selected text changed the selection: no drag began
            return
        self.update()

    # ------------------------------------------------------------ painting
    def paintEvent(self, _):
        from PySide6.QtGui import QBrush, QLinearGradient

        from .showcase import glow

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        now = time.perf_counter()
        t = now - self.t0
        hot = max(0.0, min(1.0, self.hot))
        pop = ease_back(min(1.0, t / 0.32), 1.5)
        c = QPointF(self.SIZE / 2, self.SIZE / 2)
        breathe = 1 + 0.018 * math.sin(t * 2 * math.pi * 0.9) * (1 - hot)
        r = self.R * (0.55 + 0.45 * pop) * (1 + 0.07 * hot) * breathe
        p.setOpacity(ease_out(min(1.0, t / 0.2)))
        # a soft halo, brighter while something is over it
        glow(p, c, r + 34, theme.ACCENT, 0.55 + 0.45 * hot)
        # rings that spread out and fade: "drop here"
        for i in range(2):
            k = (t * 0.7 + i * 0.5) % 1.0
            p.setPen(QPen(with_alpha(theme.ACCENT, 0.4 * (1 - k) * (1 - hot) * min(1.0, t / 0.4)), 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r + 2 + 26 * ease_out(k), r + 2 + 26 * ease_out(k))
        # the arrival ripple
        k = (now - self._hot_at) / 0.6
        if 0 <= k < 1:
            p.setPen(QPen(with_alpha(theme.ACCENT, 0.7 * (1 - k)), 3 * (1 - k) + 0.6))
            p.drawEllipse(c, r + 30 * ease_out(k), r + 30 * ease_out(k))
        # shadow, then the disc: a gentle gradient that blends into the accent as you hover
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            p.setBrush(with_alpha(theme.SHADOW, 0.18))
            p.drawEllipse(QPointF(c.x(), c.y() + 3 + 2 * i), r + 1 + i * 1.5, r + 1 + i * 1.5)
        g = QLinearGradient(0, c.y() - r, 0, c.y() + r)
        g.setColorAt(0, mix(mix(theme.SURFACE, theme.ACCENT, 0.05), theme.ACCENT, hot))
        g.setColorAt(1, mix(theme.SURFACE, mix(theme.ACCENT, QColor(0, 0, 0), 0.18), hot))
        p.setBrush(QBrush(g))
        p.setPen(QPen(theme.ACCENT, 2))
        p.drawEllipse(c, r, r)
        ink = mix(theme.ACCENT, theme.ON_ACCENT, hot)
        # a dashed ring that turns, with a light running around it
        pen = QPen(with_alpha(ink, 0.85), 2.4)
        pen.setDashPattern([3, 4])
        pen.setDashOffset(-t * 12)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r - 10, r - 10)
        a = t * 2.2
        dot = QPointF(c.x() + math.cos(a) * (r - 10), c.y() + math.sin(a) * (r - 10))
        glow(p, dot, 12, ink, 0.9)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawEllipse(dot, 3, 3)
        # an arrow dropping into a tray, bobbing (it settles while something is over it)
        bob = 4 * math.sin(t * 5) * (1 - hot) + 3 * hot
        ax, ay = c.x(), c.y() - r * 0.36 + bob
        arrow = QPen(ink, 3.2)
        arrow.setCapStyle(Qt.PenCapStyle.RoundCap)
        arrow.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(arrow)
        p.drawLine(QPointF(ax, ay - 16), QPointF(ax, ay + 10))
        p.drawPolyline([QPointF(ax - 9, ay + 2), QPointF(ax, ay + 11), QPointF(ax + 9, ay + 2)])
        tray = QPainterPath()
        ty = c.y() - r * 0.36 + 22
        tray.moveTo(ax - 20, ty)
        tray.lineTo(ax - 20, ty + 9)
        tray.lineTo(ax + 20, ty + 9)
        tray.lineTo(ax + 20, ty)
        p.drawPath(tray)
        p.setPen(mix(theme.TEXT, theme.ON_ACCENT, hot))
        p.setFont(font(15, QFont.Weight.Bold, display=True))
        p.drawText(QRectF(c.x() - r, c.y() + 8, 2 * r, 24), Qt.AlignmentFlag.AlignCenter,
                   "Let go to convert" if hot > 0.5 else "Drop to convert")
        p.setPen(mix(theme.DIM, with_alpha(theme.ON_ACCENT, 0.85), hot))
        p.setFont(font(11))
        p.drawText(QRectF(c.x() - r, c.y() + 32, 2 * r, 18), Qt.AlignmentFlag.AlignCenter, "Tapshift")
        p.end()

    def closeEvent(self, e):
        self._timer.stop()
        self.unregister()
        super().closeEvent(e)

