"""The popup shown when the hotkey is pressed.

Views sharing one card:
- Orbit: tools and formats circling the selection, with a side card that
  explains the one you point at (mouse or arrow keys). See orbit.py.
- List: every format, with search. Start typing anywhere to open it.
- Options: quality and other settings (right-click an option, or Tab in the list).
"""

from __future__ import annotations


from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QKeyEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton, QCheckBox, QComboBox, QFrame, QHBoxLayout, QSizePolicy, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSlider, QStackedWidget, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ..catalog import Offer
from ..winutil import force_foreground
from . import theme
from .orbit import OrbitView, real_warning


def _font(px: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(theme.FONT)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


def with_a(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlphaF(a)
    return out


# ====================================================================== list helpers


# ====================================================================== list


class OfferDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        o: Offer = index.data(Qt.ItemDataRole.UserRole)
        return QSize(0, 52 if o.warnings else 36)  # rows take the list's width

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
            caution = real_warning(o)  # amber only for real cautions; other notes stay quiet
            fm = QFontMetrics(f2)
            text = fm.elidedText(caution or o.warnings[0], Qt.TextElideMode.ElideRight, r.width() - 24)
            p.setPen(with_a(theme.ON_ACCENT, 0.85) if selected else (theme.WARN if caution else theme.DIM))
            p.drawText(QPointF(x, top + 18), text)
        p.restore()


class ListPage(QWidget):
    activated = Signal(object)
    options_requested = Signal(object)
    back = Signal()

    def __init__(self, offers: list[Offer], parent=None):
        super().__init__(parent)
        self.setMinimumWidth(420)
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
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        self.setMinimumWidth(320)
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
        self.setMinimumWidth(340)
        self.estimator = estimator
        self.offer: Offer | None = None
        self._req = 0
        self._curve: list = []
        self._size = 0
        self.mode = "size"  # "size": a size limit or quality; "forms": upload-form presets
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
        tabs = Segmented([("size", "Size limit"), ("forms", "For forms")], self.mode)
        tabs.changed.connect(lambda v: (setattr(self, "mode", v), self.load(self.offer, self.fmt)))
        self.lay.addWidget(tabs)
        if self.mode == "forms":
            self._build_forms(offer)
            return
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

    def _build_forms(self, offer: Offer):
        """Exact sizes asked for by upload forms: photo, passport photo, signature, or your own."""
        from PySide6.QtGui import QIntValidator

        from ..toolbox import FORM_PRESET_ROWS

        many = len(offer.sources) > 1
        sub = QLabel(("Each image gets" if many else "Makes") + " an exact-size JPG next to the original. "
                     "Check your form's rules: sizes vary.")
        sub.setObjectName("sub")
        sub.setWordWrap(True)
        self.lay.addWidget(sub)
        self.form_rows: list[CompressRow] = []
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)
        for key, title, detail, label in FORM_PRESET_ROWS:
            r = CompressRow(title, detail, "JPG")
            r.preset, r.label = key, label
            r.toggled.connect(lambda on: self.go.setEnabled(True))
            self.form_rows.append(r)
            bl.addWidget(r)
        self.custom_size = CompressRow("Custom size", "your width, height and size limit", "JPG")
        self.custom_size.preset, self.custom_size.label = "custom", ""
        self.custom_size.toggled.connect(lambda on: self.go.setEnabled(True))
        self.form_rows.append(self.custom_size)
        bl.addWidget(self.custom_size)
        self.lay.addWidget(box)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.cw, self.ch, self.ckb = QLineEdit(), QLineEdit(), QLineEdit()
        for edit, ph, top in ((self.cw, "width", 8000), (self.ch, "height", 8000), (self.ckb, "KB", 20000)):
            edit.setPlaceholderText(ph)
            edit.setValidator(QIntValidator(1, top, edit))
            edit.setFixedWidth(64)
            edit.textEdited.connect(lambda _t: self.custom_size.setChecked(True))
        for w in (self.cw, QLabel("×"), self.ch, QLabel("px, under"), self.ckb, QLabel("KB")):
            row.addWidget(w)
        row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        self.lay.addWidget(holder)
        self.form_err = QLabel()
        self.form_err.setObjectName("error")
        self.form_err.setWordWrap(True)
        self.form_err.hide()
        self.lay.addWidget(self.form_err)
        self.lay.addStretch(1)
        btns = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(self.back.emit)
        self.go = QPushButton("Make it")
        self.go.setObjectName("primary")
        self.go.setEnabled(False)
        self.go.clicked.connect(self._go)
        btns.addWidget(back)
        btns.addStretch(1)
        btns.addWidget(self.go)
        bh = QWidget()
        bh.setLayout(btns)
        self.lay.addWidget(bh)
        w = self.window()
        if hasattr(w, "_fit"):
            w._fit()

    def _go_forms(self):
        chosen = next((r for r in self.form_rows if r.isChecked()), None)
        if chosen is None:
            return
        opts = {"format": "JPG", "mode": "preset", "preset": chosen.preset}
        if chosen.preset == "custom":
            try:
                w, h, kb = int(self.cw.text()), int(self.ch.text()), int(self.ckb.text())
            except ValueError:
                self.form_err.setText("Type a width, a height and a size limit.")
                self.form_err.show()
                return
            if not (16 <= w <= 8000 and 16 <= h <= 8000) or not (5 <= kb <= 20000):
                self.form_err.setText("Width and height: 16 to 8000 px. Size limit: 5 to 20000 KB.")
                self.form_err.show()
                return
            opts.update(w=w, h=h, max_kb=kb, name_suffix=f" ({w}x{h})")
        else:
            opts["name_suffix"] = f" ({chosen.label})"
        self.convert.emit(self.offer, opts)

    def _go(self):
        if self.mode == "forms":
            self._go_forms()
            return
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

    def __init__(self, title: str, center_title: str, subtitle: str, offers: list[Offer], estimator=None,
                 nodes=None, quick=None, scale: float = 1.0):
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
        # The shadow is a pre-drawn image (see paintEvent), not a QGraphicsDropShadowEffect:
        # an effect re-blurs the whole card on every frame of the orbit's animation.
        self._card = card
        self._shadow: QPixmap | None = None
        self._shadow_key = None
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)
        head = self._head = QLabel(title)
        head.setObjectName("title")
        head.setText(QFontMetrics(_font(13, QFont.Weight.DemiBold)).elidedText(title, Qt.TextElideMode.ElideMiddle, 300))
        head.setToolTip(title)
        lay.addWidget(head)
        self._sub = None
        if subtitle:
            sub = self._sub = QLabel(subtitle)
            sub.setObjectName("sub")
            sub.setWordWrap(True)
            lay.addWidget(sub)

        self.stack = QStackedWidget()
        # The side card goes where there's room: left of the orbit near the screen's right edge.
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        side = "left" if QCursor.pos().x() > area.left() + area.width() * 0.6 else "right"
        items = nodes if nodes is not None else offers
        # Picker size (Settings > Shortcut and look) sets the scale it opens at.
        self.wheel = self.orbit = OrbitView(items, title, card_side=side, scale=scale, note=subtitle, quick=quick)
        # Small screens (or big Windows zoom): shrink the whole web so it fits, never cut off.
        room_h, room_w = area.height() - 90, area.width() - 60  # the window adds its own margins
        if self.orbit.height() > room_h or self.orbit.width() > room_w:
            k = max(0.62, min((room_h - 34) / (self.orbit.height() - 34), room_w / self.orbit.width()))
            self.orbit.deleteLater()
            self.wheel = self.orbit = OrbitView(items, title, card_side=side, scale=max(0.55, scale * k),
                                                note=subtitle, quick=quick)
        self.last_key = ""  # what was chosen (for recents and "tap twice to repeat")
        self._chosen_node = None
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
        self.hint.setMinimumHeight(22)
        self.hint.setMaximumWidth(460)
        lay.addWidget(self.hint)
        self._card_lay = lay
        self._chrome_on = True
        self._set_chrome(False)  # the orbit floats on its own; the card frame is for the list and options
        self._default_hint()

        self.wheel.activated.connect(self._wheel_activate)
        self.wheel.options_requested.connect(self._wheel_options)
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
        self.hint.setText("Right-click an option for its settings.")

    def _wheel_activate(self, node):
        if node.key.startswith("more:") or node.offer is None:
            self._show_list("")
            return
        self._chosen_node = node
        self.last_key = node.key
        self._choose(node.offer, dict(node.preset) if node.preset is not None else None)

    def _wheel_options(self, node):
        if node.offer is None:
            self._show_list("")
        else:
            self.last_key = node.key
            self._show_options(node.offer)

    def _show_list(self, text: str):
        self.last_key = ""  # whatever is picked in the list is what gets remembered
        self._chosen_node = None
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

    def _set_chrome(self, on: bool) -> None:
        """The card frame, title and hint line: shown for the list and options pages,
        hidden for the orbit, which floats on its own disc."""
        if on == self._chrome_on:
            return
        self._chrome_on = on
        self._card.setStyleSheet(theme.CARD_QSS if on else
                                 theme.CARD_QSS + "QFrame#card { background: transparent; border: none; }")
        for w in (self._head, self._sub, self.hint):
            if w is not None:
                w.setVisible(on)
        if on:
            self._card_lay.setContentsMargins(16, 14, 16, 12)
        else:
            self._card_lay.setContentsMargins(0, 0, 0, 0)
        self.update()

    def _fit(self):
        """Size the window to the page that's showing (the orbit is much wider than
        the list or the options), keeping it centered where it was."""
        center = self.geometry().center()
        current = self.stack.currentIndex()
        self._set_chrome(current != 0)
        for k in range(self.stack.count()):
            w = self.stack.widget(k)
            pol = QSizePolicy.Policy.Preferred if k == current else QSizePolicy.Policy.Ignored
            w.setSizePolicy(pol, pol)
            w.updateGeometry()
        # Layouts cache size hints; drop them so the window can shrink as well as grow.
        self.stack.updateGeometry()
        self._card.updateGeometry()
        self.setMinimumSize(0, 0)  # the layout had pinned the window's minimum to the orbit's size
        self._card.layout().invalidate()
        self.layout().invalidate()
        self.layout().activate()
        self.adjustSize()
        self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
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
        if not self.last_key:
            self.last_key = offer.target.key
        self.chosen.emit(offer, opts)  # the conversion starts now; the exit motion runs alongside
        node = self._chosen_node
        if self.stack.currentIndex() == 0 and node is not None and node in self.orbit.items and self.orbit.motion:
            fade = QPropertyAnimation(self, b"windowOpacity", self)
            fade.setDuration(200)
            fade.setStartValue(self.windowOpacity())
            fade.setEndValue(0.0)
            fade.setEasingCurve(QEasingCurve.Type.InCubic)
            fade.start()
            self.orbit.play_exit(node, self.close)
        else:
            self.close()

    def paintEvent(self, _):
        """The card's soft shadow, drawn once per size and then reused."""
        if not self._chrome_on:
            return  # the orbit draws its own disc and shadow
        r = self._card.geometry()
        key = (r.width(), r.height(), self.devicePixelRatioF())
        if key != self._shadow_key:
            self._shadow_key = key
            self._shadow = _shadow_pixmap(r.width(), r.height(), self.devicePixelRatioF())
        p = QPainter(self)
        p.drawPixmap(QPoint(r.x() - SHADOW_PAD, r.y() - SHADOW_PAD + 6), self._shadow)
        p.end()

    # ------------------------------------------------------------- window
    def show_at_cursor(self):
        self.adjustSize()
        pos = QCursor.pos()
        self.setWindowOpacity(0.0)
        self.move(pos - QPoint(self.width() // 2, self.height() // 2))
        self.show()  # invisible (opacity 0) until positioned
        # Child positions are only final once shown; center the orbit on the cursor.
        wheel_center = self.orbit.mapTo(self, self.orbit.orbit_center().toPoint())
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
        # No search box: everything is in the web itself, one point away.
        super().keyPressEvent(e)


SHADOW_PAD = 20


def _shadow_pixmap(w: int, h: int, dpr: float) -> QPixmap:
    """A soft shadow for a rounded card: stacked translucent rounded rects (cheap, no blur pass)."""
    pm = QPixmap(int((w + 2 * SHADOW_PAD) * dpr), int((h + 2 * SHADOW_PAD) * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    steps = SHADOW_PAD
    base = theme.SHADOW.alphaF()
    for k in range(steps):
        grow = steps - k
        c = QColor(theme.SHADOW)
        c.setAlphaF(base * 0.11 * (k + 1) / steps)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(SHADOW_PAD - grow, SHADOW_PAD - grow, w + 2 * grow, h + 2 * grow),
                          theme.RADIUS_CARD + grow, theme.RADIUS_CARD + grow)
    p.end()
    return pm


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
