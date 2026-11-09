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
    QAbstractButton, QCheckBox, QComboBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QListWidget,
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


def with_a(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlphaF(a)
    return out


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
                p.setPen(with_a(theme.ON_ACCENT, 0.75) if i == self.hover else theme.DIM)
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
        p.setPen(with_a(theme.ON_ACCENT, 0.75) if selected else theme.DIM)
        p.drawText(QPointF(x + w1 + 10, top), o.caption)
        if o.warnings:
            fm = QFontMetrics(f2)
            text = fm.elidedText(o.warnings[0], Qt.TextElideMode.ElideRight, r.width() - 24)
            p.setPen(with_a(theme.ON_ACCENT, 0.85) if selected else theme.WARN)
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
    """A small form: quality sliders, choices, and text/password fields for tools.
    Text fields are checked before anything runs; problems show under the field."""

    convert = Signal(object, dict)
    back = Signal()

    VERBS = {"pdf.lock": "Lock PDF", "pdf.unlock": "Unlock", "pdf.pages": "Apply", "pdf.numbers": "Add numbers",
             "pdf.watermark": "Add watermark", "pdf.rotate": "Rotate", "pdf.compress": "Compress"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 4, 4, 4)
        self.lay.setSpacing(8)
        self.offer: Offer | None = None
        self.fields: list = []

    def load(self, offer: Offer):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.offer = offer
        self.fields = []
        tool = offer.target.ask or bool(offer.target.suffix)
        title = QLabel(offer.target.label if tool else f"{offer.target.label} options")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 16px;")
        self.lay.addWidget(title)
        if offer.caption:
            sub = QLabel(offer.caption)
            sub.setObjectName("sub")
            self.lay.addWidget(sub)
        if not offer.options:
            none = QLabel("No settings needed; the best quality is used automatically.")
            none.setObjectName("sub")
            none.setWordWrap(True)
            self.lay.addWidget(none)
        first_input = None
        for opt in offer.options:
            err = QLabel()
            err.setObjectName("error")
            err.setWordWrap(True)
            err.hide()
            if opt.kind == "slider":
                lab = QLabel()
                s = QSlider(Qt.Orientation.Horizontal)
                s.setRange(opt.min, opt.max)
                s.setValue(int(opt.default))
                upd = lambda v, lab=lab, opt=opt: lab.setText(  # noqa: E731
                    f"{opt.label[:-2]}: {v}%" if opt.label.endswith(" %") else f"{opt.label}: {v}")
                s.valueChanged.connect(upd)
                upd(s.value())
                self.lay.addWidget(lab)
                self.lay.addWidget(s)
                getter = s.value
            elif opt.kind == "toggle":
                cb = QCheckBox(opt.label)
                cb.setChecked(bool(opt.default))
                self.lay.addWidget(cb)
                getter = cb.isChecked
            elif opt.kind == "choice":
                self.lay.addWidget(QLabel(opt.label))
                combo = QComboBox()
                combo.addItems(list(opt.choices))
                combo.setCurrentText(str(opt.default))
                self.lay.addWidget(combo)
                getter = combo.currentText
            else:  # text / password
                self.lay.addWidget(QLabel(opt.label))
                edit = QLineEdit(str(opt.default or ""))
                edit.setPlaceholderText(opt.placeholder)
                if opt.kind == "password":
                    edit.setEchoMode(QLineEdit.EchoMode.Password)
                edit.returnPressed.connect(self._go)
                edit.textChanged.connect(lambda _=None, e=err: e.hide())
                self.lay.addWidget(edit)
                if opt.kind == "password":
                    show = QCheckBox("Show password")
                    show.toggled.connect(lambda on, e=edit: e.setEchoMode(
                        QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
                    self.lay.addWidget(show)
                getter = edit.text
                first_input = first_input or edit
            self.lay.addWidget(err)
            self.fields.append((opt, getter, err))
        for w in offer.warnings:
            lab = QLabel(w)
            lab.setObjectName("warn" if not tool else "sub")
            lab.setWordWrap(True)
            self.lay.addWidget(lab)
        self.lay.addStretch(1)
        btns = QWidget()
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(0, 0, 0, 0)
        back = QPushButton("Back")
        go = QPushButton(self.VERBS.get(offer.target.key, "Convert"))
        go.setObjectName("primary")
        go.setDefault(True)
        back.clicked.connect(self.back.emit)
        go.clicked.connect(self._go)
        bl.addWidget(back)
        bl.addStretch(1)
        bl.addWidget(go)
        self.lay.addWidget(btns)
        (first_input or go).setFocus()

    def _go(self):
        from ..toolbox import validate

        values, ok = {}, True
        for opt, getter, err in self.fields:
            value = getter()
            problem = validate(opt, value)
            if problem:
                err.setText(problem)
                err.show()
                ok = False
            values[opt.key] = value
        if ok:
            self.convert.emit(self.offer, values)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._go()
        else:
            super().keyPressEvent(e)


class CompressRow(QAbstractButton):
    """One size choice: 'Under 100 KB', the quality it needs, and how much smaller it gets."""

    def __init__(self, title: str, detail: str, right: str, low: bool = False, parent=None):
        super().__init__(parent)
        self.title, self.detail, self.right, self.low = title, detail, right, low
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
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
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on = self.isChecked()
        if not self.isEnabled():
            p.setOpacity(0.45)
        p.setPen(QPen(theme.ACCENT if on else theme.LINE, 1.5 if on else 1))
        p.setBrush(theme.ACCENT_SOFT if on else (theme.SURFACE2 if self._hover else theme.SURFACE))
        p.drawRoundedRect(r, theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)
        p.setPen(theme.TEXT)
        p.setFont(_font(13, QFont.Weight.DemiBold))
        p.drawText(QRectF(12, 4, r.width() - 100, 20), Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setPen(theme.WARN if self.low else theme.DIM)
        p.setFont(_font(11))
        p.drawText(QRectF(12, 22, r.width() - 100, 18), Qt.AlignmentFlag.AlignVCenter, self.detail)
        p.setPen(theme.ACCENT if on else theme.DIM)
        p.setFont(_font(12, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.width() - 92, 0, 82, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self.right)
        p.end()


def _quality_word(q: int) -> str:
    return "excellent" if q >= 85 else "good" if q >= 70 else "fair" if q >= 55 else "low, visible loss"


def _saved_text(percent: float) -> str:
    """'−81%'; never '−100%' (something is always left)."""
    p = max(0.0, percent)
    return "−>99%" if p > 99 else f"−{p:.0f}%"


class CompressPage(QWidget):
    """Pick a size limit (with the quality each one needs) or a quality (with its size)."""

    convert = Signal(object, dict)
    back = Signal()

    def __init__(self, estimator=None, parent=None):
        super().__init__(parent)
        self.estimator = estimator
        self.offer: Offer | None = None
        self._req = 0
        self._curve: list = []
        self._size = 0
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 4, 4, 4)
        self.lay.setSpacing(8)

    def load(self, offer: Offer, fmt: str | None = None):
        from .fx import Segmented

        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.offer = offer
        self.fmt = fmt or "JPG"
        self.rows: list[CompressRow] = []
        src = offer.sources[0]
        title = QLabel("Compress")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 16px;")
        self.lay.addWidget(title)
        many = len(offer.sources) > 1
        self.sub = QLabel(f"{len(offer.sources)} images; each one gets the size you pick." if many
                          else "Measuring sizes...")
        self.sub.setObjectName("sub")
        self.sub.setWordWrap(True)
        self.lay.addWidget(self.sub)
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Save as"))
        fmt_row.addStretch(1)
        self.fmt_ctl = Segmented([("JPG", "JPG"), ("WEBP", "WEBP"), ("Same as original", "Same")], self.fmt)
        self.fmt_ctl.changed.connect(lambda v: self.load(self.offer, v))
        fmt_row.addWidget(self.fmt_ctl)
        holder = QWidget()
        holder.setLayout(fmt_row)
        self.lay.addWidget(holder)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(6)
        rows_holder = QWidget()
        rows_holder.setLayout(self.rows_box)
        self.lay.addWidget(rows_holder)
        self.wait = QLabel("Working out the quality for each size...")
        self.wait.setObjectName("sub")
        self.rows_box.addWidget(self.wait)
        self.custom = CompressRow("Pick a quality", "drag the slider", "", parent=self)
        self.custom.toggled.connect(lambda on: self.slider.setEnabled(True))
        self.rows.append(self.custom)
        self.lay.addWidget(self.custom)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(10, 100)
        self.slider.setValue(75)
        self.slider.valueChanged.connect(self._slider_changed)
        self.lay.addWidget(self.slider)
        self.lay.addStretch(1)
        btns = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(self.back.emit)
        self.go = QPushButton("Compress")
        self.go.setObjectName("primary")
        self.go.setEnabled(False)
        self.go.clicked.connect(self._go)
        btns.addWidget(back)
        btns.addStretch(1)
        btns.addWidget(self.go)
        bh = QWidget()
        bh.setLayout(btns)
        self.lay.addWidget(bh)
        self._slider_changed(self.slider.value())
        self._req += 1
        req = self._req
        if self.estimator is not None:
            from ..toolbox import COMPRESS_IMAGE, output_ext

            ext = output_ext(COMPRESS_IMAGE, src, {"format": self.fmt})
            self.estimator(str(src), ext, lambda res, r=req: self._estimated(r, res))

    def _slider_changed(self, v: int):
        size = ""
        if self._curve:
            pts = sorted(self._curve)
            near = min(pts, key=lambda qb: abs(qb[0] - v))
            size = f"about {_human(near[1])}"
        self.custom.title = f"Quality {v}%"
        self.custom.detail = _quality_word(v) + (f", {size}" if size else "")
        if self._size and self._curve:
            pts = sorted(self._curve)
            near = min(pts, key=lambda qb: abs(qb[0] - v))
            self.custom.right = _saved_text(100 - 100 * near[1] / self._size)
        self.custom.setChecked(True)
        self.custom.update()
        self.go.setEnabled(True)

    def _estimated(self, req: int, res: dict):
        if req != self._req:
            return  # an older measurement (the format was changed meanwhile)
        try:
            import shiboken6

            if not shiboken6.isValid(self.wait):
                return
        except Exception:
            pass
        self.wait.hide()
        if not res.get("ok"):
            self.sub.setText("Couldn't measure this image. You can still pick a quality.")
            return
        self._size = res["bytes"]
        self._curve = res.get("quality_curve", [])
        if len(self.offer.sources) == 1:
            self.sub.setText(f"Now {_human(res['bytes'])}, {res['width']}x{res['height']} px. "
                             "Sizes are estimates; the limit is always respected.")
        for t in res["targets"]:
            if t.get("impossible"):
                row = CompressRow(f"Under {_kb(t['kb'])}", "too small for this picture", "", low=True)
                row.setEnabled(False)
            else:
                detail = f"quality {t['quality']}% ({_quality_word(t['quality'])})"
                if t["resized"]:
                    detail += f", {t['width']}x{t['height']}"
                saved = max(0, 100 - 100 * t["bytes"] / max(1, res["bytes"]))
                row = CompressRow(f"Under {_kb(t['kb'])}", detail, _saved_text(saved), low=t["quality"] < 55)
                row.kb = t["kb"]
                row.toggled.connect(lambda on: self.go.setEnabled(True))
            self.rows.append(row)
            self.rows_box.addWidget(row)
        if not res["targets"]:
            note = QLabel("This image is already small. Pick a quality below to make it smaller still.")
            note.setObjectName("sub")
            note.setWordWrap(True)
            self.rows_box.addWidget(note)
        self._slider_changed(self.slider.value())
        self.custom.setChecked(False)
        self.go.setEnabled(False)
        w = self.window()
        if hasattr(w, "_fit"):
            w._fit()

    def _go(self):
        chosen = next((r for r in self.rows if r.isChecked()), None)
        if chosen is None:
            return
        opts = {"format": self.fmt_ctl.value}
        if chosen is self.custom:
            opts.update(mode="quality", quality=self.slider.value())
        else:
            opts.update(mode="size", target_kb=chosen.kb)
        self.convert.emit(self.offer, opts)


def _human(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1000:
        return f"{n / 1000:.0f} KB"
    return f"{int(n)} bytes"


def _kb(kb: int) -> str:
    return f"{kb // 1000} MB" if kb >= 1000 else f"{kb} KB"


# ====================================================================== popup


class Popup(QWidget):
    chosen = Signal(object, dict)  # Offer, options

    def __init__(self, title: str, center_title: str, subtitle: str, offers: list[Offer], estimator=None):
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
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(theme.SHADOW)
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
        self.compress = CompressPage(estimator)
        self.stack.addWidget(wheel_holder)
        self.stack.addWidget(self.list_page)
        self.stack.addWidget(self.options)
        self.stack.addWidget(self.compress)
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
        self.compress.convert.connect(self._choose)
        self.compress.back.connect(self._back_from_options)
        self._options_return = 0

    # ------------------------------------------------------------- views
    def _default_hint(self):
        self.hint.setObjectName("hint")
        self.hint.setStyleSheet("")
        self.hint.setText("Right-click a format for its options, or start typing to search.")

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
            self.hint.setText("  ".join(item.warnings))
        else:
            self.hint.setStyleSheet("")
            tool = item.target.ask or bool(item.target.suffix) or item.target.engine in ("archive", "ocr", "data")
            self.hint.setText(f"{item.target.label}: {item.caption}." + ("" if tool else " No quality loss."))

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
        self.hint.setText("Enter converts. Tab opens options. Esc goes back.")
        self.list_page.focus(text)
        self._fit()

    def _show_options(self, offer: Offer):
        self._options_return = self.stack.currentIndex()
        if offer.target.key == "compress.image":
            self.compress.load(offer)
            self.stack.setCurrentIndex(3)
        else:
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
        if opts is None and offer.target.ask:
            self._show_options(offer)  # tools that need input (a password, page numbers...) ask first
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
