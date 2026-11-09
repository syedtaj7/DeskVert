"""The popup shown when the hotkey is pressed.

Three views share one card:
- Wheel: up to 8 formats in a ring around the selection (mouse or arrow keys).
- List: every format, with search. Start typing anywhere to open it.
- Options: quality and other settings (right-click a format, or Tab in the list).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QKeyEvent, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSlider, QStackedWidget, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ..catalog import Offer
from ..winutil import force_foreground
from . import theme

WHEEL_MAX = 8


def _font(px: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(theme.FONT)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


# ====================================================================== wheel


class Wheel(QWidget):
    activated = Signal(int)
    options_requested = Signal(int)
    hovered = Signal(int)  # -1 = none

    def __init__(self, items: list[Offer | None], center_title: str, parent=None):
        super().__init__(parent)
        self.items = items  # None = "More..."
        self.center_title = center_title
        self.hover = -1
        self.setMouseTracking(True)
        self.setFixedSize(QSize(300, 300))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.R, self.r = 146.0, 60.0

    # geometry ----------------------------------------------------------
    @property
    def span(self) -> float:
        return 360.0 / max(1, len(self.items))

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _mid_angle(self, i: int) -> float:
        return 90.0 - i * self.span

    def _index_at(self, pos: QPointF) -> int:
        c = self._center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        dist = math.hypot(dx, dy)
        if dist < self.r or dist > self.R + 6:
            return -1
        ang = math.degrees(math.atan2(-dy, dx))
        offset = (90.0 - ang) % 360.0
        return int((offset + self.span / 2) // self.span) % len(self.items)

    def _slice_path(self, i: int) -> QPainterPath:
        c = self._center()
        outer = QRectF(c.x() - self.R, c.y() - self.R, 2 * self.R, 2 * self.R)
        inner = QRectF(c.x() - self.r, c.y() - self.r, 2 * self.r, 2 * self.r)
        start = self._mid_angle(i) + self.span / 2
        path = QPainterPath()
        path.arcMoveTo(outer, start)
        path.arcTo(outer, start, -self.span)
        path.arcTo(inner, start - self.span, self.span)
        path.closeSubpath()
        return path

    # painting ----------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        c = self._center()
        edge = QPen(theme.SLICE_EDGE, 3)

        for i, item in enumerate(self.items):
            path = self._slice_path(i)
            if i == self.hover:
                g = QLinearGradient(c.x() - self.R, c.y() - self.R, c.x() + self.R, c.y() + self.R)
                g.setColorAt(0, theme.ACCENT_A)
                g.setColorAt(1, theme.ACCENT_B)
                p.fillPath(path, QBrush(g))
            else:
                p.fillPath(path, theme.SLICE)
            p.setPen(edge)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

            mid = self._mid_angle(i)
            pos = theme.polar(c, (self.r + self.R) / 2 + 3, mid)
            label = "More" if item is None else item.target.label
            caption = "all formats" if item is None else item.caption
            f1 = _font(15 if len(label) <= 4 else 13, QFont.Weight.Bold)
            f2 = _font(9.5)
            p.setFont(f1)
            p.setPen(theme.ON_ACCENT if i == self.hover else theme.TEXT)
            fm1 = QFontMetrics(f1)
            w1 = fm1.horizontalAdvance(label)
            p.drawText(QPointF(pos.x() - w1 / 2, pos.y() + 2), label)
            if caption:
                p.setFont(f2)
                fm2 = QFontMetrics(f2)
                cap = fm2.elidedText(caption, Qt.TextElideMode.ElideRight, 70)
                p.setPen(QColor(255, 255, 255, 210) if i == self.hover else theme.DIM)
                p.drawText(QPointF(pos.x() - fm2.horizontalAdvance(cap) / 2, pos.y() + 16), cap)
            if item is not None and _has_real_warning(item):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.WARN)
                p.drawEllipse(QPointF(pos.x() + w1 / 2 + 6, pos.y() - 9), 3, 3)

        # center
        p.setPen(QPen(theme.LINE, 1.5))
        p.setBrush(theme.CENTER)
        p.drawEllipse(c, self.r - 7, self.r - 7)
        p.setPen(theme.TEXT)
        f = _font(14, QFont.Weight.Bold)
        p.setFont(f)
        fm = QFontMetrics(f)
        title = fm.elidedText(self.center_title, Qt.TextElideMode.ElideMiddle, int(2 * self.r - 22))
        p.drawText(QPointF(c.x() - fm.horizontalAdvance(title) / 2, c.y() - 2), title)
        f = _font(10.5, QFont.Weight.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        if 0 <= self.hover < len(self.items):
            item = self.items[self.hover]
            sub = "all formats" if item is None else f"→ {item.target.label}"
            p.setPen(theme.ACCENT_A)
        else:
            sub = "convert to"
            p.setPen(theme.DIM)
        p.drawText(QPointF(c.x() - fm.horizontalAdvance(sub) / 2, c.y() + 15), sub)
        p.end()

    # interaction -------------------------------------------------------
    def set_hover(self, i: int) -> None:
        if i != self.hover:
            self.hover = i
            self.hovered.emit(i)
            self.update()

    def mouseMoveEvent(self, e):
        self.set_hover(self._index_at(e.position()))

    def leaveEvent(self, _):
        self.set_hover(-1)

    def mouseReleaseEvent(self, e):
        i = self._index_at(e.position())
        if i < 0:
            return
        if e.button() == Qt.MouseButton.RightButton:
            self.options_requested.emit(i)
        elif e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(i)

    def keyPressEvent(self, e: QKeyEvent):
        n = len(self.items)
        k = e.key()
        if k in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.set_hover((self.hover + 1) % n if self.hover >= 0 else 0)
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.set_hover((self.hover - 1) % n if self.hover >= 0 else n - 1)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.hover >= 0:
            self.activated.emit(self.hover)
        elif k == Qt.Key.Key_Menu and self.hover >= 0:
            self.options_requested.emit(self.hover)
        else:
            e.ignore()


def _has_real_warning(o: Offer) -> bool:
    """Lossy-quality notes are shown in the caption; the dot marks anything else."""
    return any("lossy" not in w.lower() for w in o.warnings)


# ====================================================================== list


class OfferDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        o: Offer = index.data(Qt.ItemDataRole.UserRole)
        return QSize(300, 52 if o.warnings else 36)

    def paint(self, p: QPainter, option, index):
        o: Offer = index.data(Qt.ItemDataRole.UserRole)
        r = option.rect.adjusted(2, 1, -2, -1)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ACCENT_B)
            p.drawRoundedRect(r, 9, 9)
        elif hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.HOVER)
            p.drawRoundedRect(r, 9, 9)
        f1 = _font(13, QFont.Weight.Bold)
        p.setFont(f1)
        p.setPen(theme.ON_ACCENT if selected else theme.TEXT)
        x = r.left() + 12
        top = r.top() + 22
        p.drawText(QPointF(x, top), o.target.label)
        w1 = QFontMetrics(f1).horizontalAdvance(o.target.label)
        f2 = _font(11)
        p.setFont(f2)
        p.setPen(QColor(255, 255, 255, 200) if selected else theme.DIM)
        p.drawText(QPointF(x + w1 + 10, top), o.caption)
        if o.warnings:
            fm = QFontMetrics(f2)
            text = fm.elidedText(" · ".join(o.warnings), Qt.TextElideMode.ElideRight, r.width() - 24)
            p.setPen(QColor(255, 244, 214) if selected else theme.WARN)
            p.drawText(QPointF(x, top + 18), text)
        p.restore()


class ListPage(QWidget):
    activated = Signal(object)
    options_requested = Signal(object)
    back = Signal()

    def __init__(self, offers: list[Offer], parent=None):
        super().__init__(parent)
        self.offers = offers
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search formats...  (Enter to convert, Tab for options)")
        self.list = QListWidget()
        self.list.setItemDelegate(OfferDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFixedHeight(300)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        lay.addWidget(self.search)
        lay.addWidget(self.list)
        for o in offers:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, o)
            it.setText(f"{o.target.label} {o.caption} {o.target.ext}")
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        self.search.textChanged.connect(self._filter)
        self.search.installEventFilter(self)
        self.list.itemClicked.connect(lambda it: self.activated.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.list.customContextMenuRequested.connect(self._context)

    def _context(self, pos):
        it = self.list.itemAt(pos)
        if it:
            self.options_requested.emit(it.data(Qt.ItemDataRole.UserRole))

    def _filter(self, text: str):
        t = text.strip().lower().lstrip(".")
        first = None
        for i in range(self.list.count()):
            it = self.list.item(i)
            o: Offer = it.data(Qt.ItemDataRole.UserRole)
            hay = f"{o.target.label} {o.target.ext} {o.caption}".lower()
            show = not t or t in hay
            it.setHidden(not show)
            if show and first is None:
                first = it
        # Prefer an exact format-name match ("jpg" -> JPG, not "1 PDF").
        for i in range(self.list.count()):
            it = self.list.item(i)
            o = it.data(Qt.ItemDataRole.UserRole)
            if not it.isHidden() and t and o.target.label.lower().startswith(t):
                first = it
                break
        if first:
            self.list.setCurrentItem(first)

    def _current(self) -> Offer | None:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it and not it.isHidden() else None

    def _step(self, d: int):
        rows = [i for i in range(self.list.count()) if not self.list.item(i).isHidden()]
        if not rows:
            return
        cur = self.list.currentRow()
        idx = rows.index(cur) if cur in rows else -1
        self.list.setCurrentRow(rows[(idx + d) % len(rows)])

    def eventFilter(self, obj, e):
        if obj is self.search and e.type() == QEvent.Type.KeyPress:
            k = e.key()
            if k == Qt.Key.Key_Down:
                self._step(1)
                return True
            if k == Qt.Key.Key_Up:
                self._step(-1)
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                o = self._current()
                if o:
                    (self.options_requested if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else self.activated).emit(o)
                return True
            if k == Qt.Key.Key_Tab:
                o = self._current()
                if o:
                    self.options_requested.emit(o)
                return True
        return super().eventFilter(obj, e)

    def focus(self, text: str = ""):
        self.search.setFocus()
        if text:
            self.search.setText(text)
            self.search.setCursorPosition(len(text))


# ====================================================================== options


class OptionsPage(QWidget):
    convert = Signal(object, dict)
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 4, 4, 4)
        self.lay.setSpacing(10)
        self.offer: Offer | None = None
        self.getters: dict = {}

    def load(self, offer: Offer):
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.offer = offer
        self.getters = {}
        title = QLabel(f"{offer.target.label} options")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 16px;")
        self.lay.addWidget(title)
        if offer.caption:
            sub = QLabel(offer.caption)
            sub.setObjectName("sub")
            self.lay.addWidget(sub)
        if not offer.options:
            none = QLabel("This format has no settings; the best quality is used automatically.")
            none.setObjectName("sub")
            none.setWordWrap(True)
            self.lay.addWidget(none)
        for opt in offer.options:
            if opt.kind == "slider":
                row = QWidget()
                rl = QVBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(4)
                lab = QLabel()
                s = QSlider(Qt.Orientation.Horizontal)
                s.setRange(opt.min, opt.max)
                s.setValue(int(opt.default))
                upd = lambda v, lab=lab, opt=opt: lab.setText(f"{opt.label}: {v}")  # noqa: E731
                s.valueChanged.connect(upd)
                upd(s.value())
                rl.addWidget(lab)
                rl.addWidget(s)
                self.lay.addWidget(row)
                self.getters[opt.key] = s.value
            elif opt.kind == "toggle":
                cb = QCheckBox(opt.label)
                cb.setChecked(bool(opt.default))
                self.lay.addWidget(cb)
                self.getters[opt.key] = cb.isChecked
            elif opt.kind == "choice":
                lab = QLabel(opt.label)
                combo = QComboBox()
                combo.addItems(list(opt.choices))
                combo.setCurrentText(str(opt.default))
                self.lay.addWidget(lab)
                self.lay.addWidget(combo)
                self.getters[opt.key] = combo.currentText
        for w in offer.warnings:
            lab = QLabel("⚠ " + w)
            lab.setObjectName("warn")
            lab.setWordWrap(True)
            self.lay.addWidget(lab)
        self.lay.addStretch(1)
        btns = QWidget()
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(0, 0, 0, 0)
        back = QPushButton("Back")
        go = QPushButton("Convert")
        go.setObjectName("primary")
        go.setDefault(True)
        back.clicked.connect(self.back.emit)
        go.clicked.connect(self._go)
        bl.addWidget(back)
        bl.addStretch(1)
        bl.addWidget(go)
        self.lay.addWidget(btns)
        go.setFocus()

    def _go(self):
        self.convert.emit(self.offer, {k: g() for k, g in self.getters.items()})

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._go()
        else:
            super().keyPressEvent(e)


# ====================================================================== popup


class Popup(QWidget):
    chosen = Signal(object, dict)  # Offer, options

    def __init__(self, title: str, center_title: str, subtitle: str, offers: list[Offer]):
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.offers = offers
        self._armed = False
        self._done = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 22)
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(theme.CARD_QSS)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 150))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)
        head = QLabel(title)
        head.setObjectName("title")
        head.setText(QFontMetrics(_font(13, QFont.Weight.DemiBold)).elidedText(title, Qt.TextElideMode.ElideMiddle, 300))
        head.setToolTip(title)
        lay.addWidget(head)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("sub")
            sub.setWordWrap(True)
            lay.addWidget(sub)

        self.stack = QStackedWidget()
        wheel_items: list[Offer | None] = list(offers) if len(offers) <= WHEEL_MAX else list(offers[: WHEEL_MAX - 1]) + [None]
        self.wheel = Wheel(wheel_items, center_title)
        wheel_holder = QWidget()
        wl = QHBoxLayout(wheel_holder)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addStretch(1)
        wl.addWidget(self.wheel)
        wl.addStretch(1)
        self.list_page = ListPage(offers)
        self.options = OptionsPage()
        self.stack.addWidget(wheel_holder)
        self.stack.addWidget(self.list_page)
        self.stack.addWidget(self.options)
        lay.addWidget(self.stack)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setMinimumHeight(30)
        self.hint.setFixedWidth(300)
        lay.addWidget(self.hint)
        self._default_hint()

        self.wheel.activated.connect(self._wheel_activate)
        self.wheel.options_requested.connect(self._wheel_options)
        self.wheel.hovered.connect(self._wheel_hover)
        self.list_page.activated.connect(lambda o: self._choose(o, None))
        self.list_page.options_requested.connect(self._show_options)
        self.options.convert.connect(self._choose)
        self.options.back.connect(self._back_from_options)
        self._options_return = 0

    # ------------------------------------------------------------- views
    def _default_hint(self):
        self.hint.setObjectName("hint")
        self.hint.setStyleSheet("")
        self.hint.setText("Click a format · right-click for options · type to search · Esc closes")

    def _wheel_hover(self, i: int):
        item = self.wheel.items[i] if 0 <= i < len(self.wheel.items) else None
        if i < 0 or item is None:
            self._default_hint()
            if item is None and i >= 0:
                self.hint.setText(f"Show all {len(self.offers)} formats")
            return
        if item.warnings:
            self.hint.setObjectName("warn")
            self.hint.setStyleSheet(f"color: {theme.rgba(theme.WARN)};")
            self.hint.setText("⚠ " + "  ".join(item.warnings))
        else:
            self.hint.setStyleSheet("")
            self.hint.setText(f"{item.target.label}: {item.caption}. No quality loss.")

    def _wheel_activate(self, i: int):
        item = self.wheel.items[i]
        if item is None:
            self._show_list("")
        else:
            self._choose(item, None)

    def _wheel_options(self, i: int):
        item = self.wheel.items[i]
        if item is None:
            self._show_list("")
        else:
            self._show_options(item)

    def _show_list(self, text: str):
        self.stack.setCurrentIndex(1)
        self._default_hint()
        self.hint.setText("↑↓ to move · Enter to convert · Tab for options · Esc to go back")
        self.list_page.focus(text)
        self._fit()

    def _show_options(self, offer: Offer):
        self._options_return = self.stack.currentIndex()
        self.options.load(offer)
        self.stack.setCurrentIndex(2)
        self.hint.setText("")
        self._fit()

    def _back_from_options(self):
        self.stack.setCurrentIndex(self._options_return)
        self._default_hint()
        (self.list_page.search if self._options_return == 1 else self.wheel).setFocus()
        self._fit()

    def _fit(self):
        self.adjustSize()
        _clamp_to_screen(self)

    def _choose(self, offer: Offer, opts: dict | None):
        if self._done:
            return
        self._done = True
        if opts is None:
            opts = {o.key: o.default for o in offer.options}
        self.chosen.emit(offer, opts)
        self.close()

    # ------------------------------------------------------------- window
    def show_at_cursor(self):
        self.adjustSize()
        pos = QCursor.pos()
        self.setWindowOpacity(0.0)
        self.move(pos - QPoint(self.width() // 2, self.height() // 2))
        self.show()  # invisible (opacity 0) until positioned
        # Child positions are only final once shown; center the wheel on the cursor.
        wheel_center = self.wheel.mapTo(self, QPoint(self.wheel.width() // 2, self.wheel.height() // 2))
        self.move(pos - wheel_center)
        _clamp_to_screen(self)
        self.raise_()
        self.activateWindow()
        force_foreground(int(self.winId()))
        self.wheel.setFocus()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(120)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        QTimer.singleShot(150, self._arm)

    def _arm(self):
        self._armed = True
        if not self.isActiveWindow():
            force_foreground(int(self.winId()))
        # Safety net: if Windows didn't give us focus, "click elsewhere to close"
        # can't rely on focus events, so watch for an outside click instead.
        self._outside = QTimer(self)
        self._outside.setInterval(80)
        self._outside.timeout.connect(self._check_outside_click)
        self._outside.start()

    def _check_outside_click(self):
        from ..winutil import mouse_button_down

        if mouse_button_down() and not self.frameGeometry().contains(QCursor.pos()):
            self.close()

    def event(self, e):
        if e.type() == QEvent.Type.WindowDeactivate and self._armed:
            QTimer.singleShot(0, self.close)
        return super().event(e)

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        page = self.stack.currentIndex()
        if k == Qt.Key.Key_Escape:
            if page == 2:
                self._back_from_options()
            elif page == 1 and len(self.offers) > 0:
                self.stack.setCurrentIndex(0)
                self._default_hint()
                self.wheel.setFocus()
                self._fit()
            else:
                self.close()
            return
        if page == 0:
            if k == Qt.Key.Key_Tab:
                self._show_list("")
                return
            text = e.text()
            if text and text.isprintable() and not text.isspace():
                self._show_list(text)
                return
        super().keyPressEvent(e)


def _clamp_to_screen(w: QWidget) -> None:
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    area = screen.availableGeometry()
    g = w.frameGeometry()
    x = min(max(g.x(), area.left()), area.right() - g.width())
    y = min(max(g.y(), area.top()), area.bottom() - g.height())
    w.move(x, y)


# ====================================================================== bubble


class Bubble(QWidget):
    """A small message near the cursor that fades away by itself."""

    def __init__(self, text: str, ms: int = 2600):
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(theme.CARD_QSS)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setMaximumWidth(320)
        lab.setStyleSheet("font-size: 12px;")
        cl.addWidget(lab)
        lay.addWidget(card)
        self.adjustSize()
        self.move(QCursor.pos() + QPoint(14, 14))
        _clamp_to_screen(self)
        QTimer.singleShot(ms, self.close)
