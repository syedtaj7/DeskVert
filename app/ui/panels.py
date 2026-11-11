"""Two small windows:

- Notice: a message card near the cursor ("Can't convert this file", "Nothing
  selected"...). Closes with OK, Esc, a click elsewhere, or after a few seconds.
- ProgressPanel: a card at the bottom-right of the screen showing what's being
  converted, a progress bar, Cancel, and the result ("Saved photo.webp" with a
  Show-in-folder button, or what went wrong).

Neither takes keyboard focus away from what you're doing unless needed.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from . import theme

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


class ProgressPanel(_Card):
    cancel_requested = Signal()
    show_folder = Signal(str)
    undo_requested = Signal(list)  # the files this conversion made

    def __init__(self):
        super().__init__(340)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(16, 14, 12, 14)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.icon = StatusIcon("busy")
        top.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("title")
        self.title.setStyleSheet("font-size: 13px;")
        self.sub = QLabel()
        self.sub.setObjectName("sub")
        self.sub.setWordWrap(True)
        texts.addWidget(self.title)
        texts.addWidget(self.sub)
        top.addLayout(texts, 1)
        close = QPushButton("✕")
        close.setObjectName("flat")
        close.setFixedSize(26, 26)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("Hide (conversions keep running)")
        close.clicked.connect(self._dismiss)
        top.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)

        barrow = QHBoxLayout()
        barrow.setSpacing(10)
        self.bar = Bar()
        self.pct = QLabel("")
        self.pct.setObjectName("sub")
        self.pct.setFixedWidth(64)
        self.pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        barrow.addWidget(self.bar, 1)
        barrow.addWidget(self.pct)
        self.bar_row = QWidget()
        self.bar_row.setLayout(barrow)
        barrow.setContentsMargins(42, 0, 4, 0)
        lay.addWidget(self.bar_row)

        btns = QHBoxLayout()
        btns.setContentsMargins(42, 0, 4, 0)
        btns.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_btn.setToolTip("Move the new file to the Recycle Bin")
        self.undo_btn.clicked.connect(self._undo)
        self.action_btn = QPushButton("")  # a one-off action, e.g. "Update" (see offer())
        self.action_btn.setObjectName("primary")
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.clicked.connect(self._action)
        self.action_btn.hide()
        self._action_cb = None
        self.folder_btn = QPushButton("Show in folder")
        self.folder_btn.setObjectName("primary")
        self.folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_btn.clicked.connect(self._open_folder)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.undo_btn)
        btns.addWidget(self.folder_btn)
        btns.addWidget(self.action_btn)
        lay.addLayout(btns)

        self._output = ""
        self._outputs: list[str] = []
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._dismiss)
        self._hide_after = 0
        self._busy = False

    # ---------------------------------------------------------------- states
    def start(self, label: str, total: int):
        self._busy = True
        self.action_btn.hide()
        self._action_cb = None
        self._hide_timer.stop()
        self.icon.set_kind("busy")
        self.title.setText(f"Converting to {label}")
        self.sub.setText(f"{total} files" if total > 1 else "Starting...")
        self.bar.color_override = None
        self.bar.set_value(0)
        self.pct.setText("")
        self.bar_row.show()
        self.cancel_btn.show()
        self.folder_btn.hide()
        self.undo_btn.hide()
        self._place_and_show()

    def set_file(self, name: str, index: int, total: int):
        suffix = f"  ({index} of {total})" if total > 1 else ""
        fm = self.sub.fontMetrics()
        self.sub.setText(fm.elidedText(name, Qt.TextElideMode.ElideMiddle, 230) + suffix)

    def set_progress(self, frac: float):
        if not self._busy:
            return
        self.bar.set_value(frac)
        self.pct.setText(f"{frac * 100:.0f}%" if frac > 0 else "working...")

    def finish(self, kind: str, title: str, body: str, output: str = "", outputs: list[str] | None = None):
        self._busy = False
        self.action_btn.hide()
        self._action_cb = None
        self.icon.set_kind(kind)
        self.title.setText(title)
        self.sub.setText(body)
        self.cancel_btn.hide()
        self._output = output
        self._outputs = list(outputs or [])
        self.folder_btn.setVisible(bool(output))
        self.undo_btn.setVisible(bool(self._outputs))
        self.undo_btn.setText("Undo" if len(self._outputs) <= 1 else f"Undo all {len(self._outputs)}")
        if kind == "success":
            self.bar.color_override = theme.SUCCESS
            self.bar.set_value(1)
            self.pct.setText("100%")
            self.bar_row.show()
        else:
            self.bar_row.hide()
        self._hide_after = 7000 if kind == "success" else 12000
        self._place_and_show()
        self._hide_timer.start(self._hide_after)

    def message(self, kind: str, title: str, body: str, ms: int = 5000):
        if self._busy:
            return
        self.finish(kind, title, body)
        self._hide_timer.start(ms)

    def offer(self, kind: str, title: str, body: str, button: str, callback, ms: int = 20000) -> bool:
        """A message with one button (e.g. an update). Not while converting; returns whether it showed."""
        if self._busy:
            return False
        self.finish(kind, title, body)
        self.action_btn.setText(button)
        self.action_btn.show()
        self._action_cb = callback
        self._place_and_show()
        self._hide_after = ms
        self._hide_timer.start(ms)
        return True

    def _action(self):
        cb = self._action_cb
        self._dismiss()
        if cb is not None:
            cb()

    # ---------------------------------------------------------------- window
    def _place_and_show(self):
        self.card.adjustSize()
        self.adjustSize()
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.right() - self.width() + 4, area.bottom() - self.height() + 4)
        if not self.isVisible():
            self._fade_in()

    def _dismiss(self):
        self._hide_timer.stop()
        self.hide()

    def _undo(self):
        if self._outputs:
            self.undo_requested.emit(self._outputs)
            self._outputs = []
            self.undo_btn.hide()

    def _open_folder(self):
        if self._output:
            self.show_folder.emit(self._output)
        self._dismiss()

    def enterEvent(self, e):
        self._hide_timer.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._busy and self.isVisible() and self._hide_after:
            self._hide_timer.start(4000)
        super().leaveEvent(e)
