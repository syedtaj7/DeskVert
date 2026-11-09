"""Shared window frame for the tour, guide and settings: frameless, rounded,
animated aurora backdrop, logo + title header, close button, draggable,
fades in and out."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme
from .fx import Aurora, font


class _MiniLogo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(26, 26))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme.paint_logo(p, QPointF(13, 13), 26)
        p.end()


class _CloseButton(QAbstractButton):
    """Window control: kind 'close' (an x) or 'min' (a dash)."""

    def __init__(self, parent=None, kind: str = "close"):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(QSize(32, 32))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self.setToolTip("Minimize" if kind == "min" else "Close")

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.HOVER)
            p.drawEllipse(QRectF(2, 2, 28, 28))
        pen = QPen(theme.TEXT if self._hover else theme.DIM, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        if self.kind == "min":
            p.drawLine(QPointF(11, 16), QPointF(21, 16))
        else:
            p.drawLine(QPointF(11.5, 11.5), QPointF(20.5, 20.5))
            p.drawLine(QPointF(20.5, 11.5), QPointF(11.5, 20.5))
        p.end()


class ChromeWindow(QWidget):
    closed = Signal()

    def __init__(self, title: str, size: QSize):
        # Frameless, but still a normal window to Windows: the minimize/system-menu
        # hints let the taskbar button minimize and restore it.
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowSystemMenuHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(title)
        self.setWindowIcon(theme.app_icon())
        self.resize(size.width() + 40, size.height() + 40)
        self._drag: QPoint | None = None
        self._closing = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        self.frame = Aurora()
        shadow = QGraphicsDropShadowEffect(self.frame)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 10)
        shadow.setColor(theme.SHADOW)
        self.frame.setGraphicsEffect(shadow)
        outer.addWidget(self.frame)

        lay = QVBoxLayout(self.frame)
        lay.setContentsMargins(22, 14, 14, 18)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(_MiniLogo())
        name = QLabel(title)
        name.setFont(font(13, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {theme.rgba(theme.TEXT)}; background: transparent;")
        head.addWidget(name)
        head.addStretch(1)
        minimize = _CloseButton(kind="min")
        minimize.clicked.connect(self.showMinimized)
        head.addWidget(minimize)
        close = _CloseButton()
        close.clicked.connect(self.close)
        head.addWidget(close)
        lay.addLayout(head)
        self.body = QWidget()
        self.body.setStyleSheet("background: transparent;")
        lay.addWidget(self.body, 1)

    # ------------------------------------------------------------- show / close
    def present(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - QPoint(self.width() // 2, self.height() // 2))
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            from ..winutil import force_foreground

            force_foreground(int(self.winId()))
        except Exception:
            pass
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(260)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start()

    def closeEvent(self, e):
        if not self._closing:
            self._closing = True
            e.ignore()
            a = QPropertyAnimation(self, b"windowOpacity", self)
            a.setDuration(180)
            a.setStartValue(self.windowOpacity())
            a.setEndValue(0.0)
            a.finished.connect(self.close)
            a.start()
            return
        self.closed.emit()
        super().closeEvent(e)

    # ------------------------------------------------------------- dragging
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < 70:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)


def label(text: str, px: float = 13, weight=QFont.Weight.Normal, dim: bool = False, wrap: bool = True,
          display: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setFont(font(px, weight, display=display))
    lab.setWordWrap(wrap)
    lab.setStyleSheet(f"color: {theme.rgba(theme.DIM if dim else theme.TEXT)}; background: transparent;")
    lab.setTextFormat(Qt.TextFormat.RichText if "<" in text else Qt.TextFormat.PlainText)
    lab.setOpenExternalLinks(True)
    return lab
