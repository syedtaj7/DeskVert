"""Settings > Customize: what sits on the picker's inner ring.

Favourites and your own presets (for example "WhatsApp photo" or "College PDF under
300 KB") are pinned closest to the centre; recently used actions can join them.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont, QIntValidator
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from .. import menu
from ..settings import Settings
from . import theme
from .chrome import label
from .fx import PillButton, Segmented, Toggle, with_alpha
from .guide import h1, para, section_page


def _box() -> tuple[QFrame, QVBoxLayout]:
    box = QFrame()
    box.setObjectName("row")
    box.setStyleSheet(f"QFrame#row {{ background: {theme.rgba(with_alpha(theme.SURFACE, 0.7))};"
                      f" border: 1px solid {theme.rgba(theme.LINE)}; border-radius: 14px; }}")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(16, 12, 16, 14)
    lay.setSpacing(8)
    return box, lay


def _clear(lay) -> None:
    while lay.count():
        item = lay.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


def _num(placeholder: str, width: int = 84) -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setValidator(QIntValidator(1, 99_999))
    e.setFixedWidth(width)
    return e


class Customize(QObject):
    """Builds the page; ``changed(key, value)`` goes to the same handler as other settings."""

    changed = Signal(str, object)

    def __init__(self, s: Settings, parent=None):
        super().__init__(parent)
        self.s = s
        self.page, lay = section_page()
        a = h1("Customize")
        b = para("Your favourites and presets sit closest to the centre of the picker, so they're one short move "
                 "away. They only show up for files they work on.")

        # ---- recents
        from .settings_ui import setting_row

        rec = Toggle(bool(getattr(s, "quick_recents", True)))
        rec.toggled.connect(lambda v: self.changed.emit("quick_recents", bool(v)))
        r1 = setting_row("Recently used near the centre",
                         "What you used last moves to the inner ring by itself (after favourites and presets).", rec)

        # ---- favourites
        fav_box, fl = _box()
        fl.addWidget(label("Favourites", 14, QFont.Weight.DemiBold))
        fl.addWidget(label("Always on the inner ring when they apply.", 12, dim=True))
        self.fav_rows = QVBoxLayout()
        self.fav_rows.setSpacing(6)
        fl.addLayout(self.fav_rows)
        add = QHBoxLayout()
        self.fav_pick = QComboBox()
        self.fav_pick.setMinimumWidth(260)
        fav_add = PillButton("Add", "ghost", min_width=80)
        fav_add.clicked.connect(self._add_favourite)
        add.addWidget(self.fav_pick)
        add.addWidget(fav_add)
        add.addStretch(1)
        fl.addLayout(add)

        # ---- presets
        pre_box, pl = _box()
        pl.addWidget(label("Your presets", 14, QFont.Weight.DemiBold))
        pl.addWidget(label("One tap does it all: the size, the format and the name are already chosen.", 12,
                           dim=True))
        self.preset_rows = QVBoxLayout()
        self.preset_rows.setSpacing(6)
        pl.addLayout(self.preset_rows)
        self.starters = QHBoxLayout()
        self.starters.setSpacing(8)
        pl.addLayout(self.starters)

        new_box, nl = _box()
        nl.addWidget(label("New preset", 14, QFont.Weight.DemiBold))
        self.kind = Segmented(menu.PRESET_KINDS, "image_size")
        self.kind.changed.connect(self._kind_changed)
        nl.addWidget(self.kind)
        form = QHBoxLayout()
        form.setSpacing(8)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name, e.g. WhatsApp photo")
        self.name.setMaxLength(28)
        self.kb = _num("KB")
        self.w, self.h = _num("width px"), _num("height px")
        self.fmt = Segmented([("JPG", "JPG"), ("WEBP", "WEBP")], "JPG")
        self.under = label("under", 12, dim=True, wrap=False)
        self.kb_unit = label("KB", 12, dim=True, wrap=False)
        form.addWidget(self.name, 1)
        for w in (self.w, self.h, self.fmt, self.under, self.kb, self.kb_unit):
            form.addWidget(w)
        nl.addLayout(form)
        foot = QHBoxLayout()
        self.err = label("", 12, wrap=False)
        self.err.setStyleSheet(f"color: {theme.rgba(theme.ERROR)};")
        save = PillButton("Save preset", "primary", min_width=130)
        save.clicked.connect(self._save_new)
        self.name.returnPressed.connect(self._save_new)
        self.kb.returnPressed.connect(self._save_new)
        foot.addWidget(self.err, 1)
        foot.addWidget(save)
        nl.addLayout(foot)

        for w in (a, b, r1, fav_box, pre_box, new_box):
            lay.addWidget(w)
        lay.addStretch(1)
        self.animate = [a, b, r1, fav_box, pre_box, new_box]
        self._kind_changed("image_size")
        self._refresh()

    # ------------------------------------------------------------- state
    def _favs(self) -> list[str]:
        return list(getattr(self.s, "favourites", []) or [])

    def _presets(self) -> list[dict]:
        return [dict(p) for p in (getattr(self.s, "presets", []) or [])]

    def _set(self, key: str, value) -> None:
        setattr(self.s, key, value)  # keep the page in step even before the app applies it
        self.changed.emit(key, value)
        self._refresh()

    # ------------------------------------------------------------- views
    def _refresh(self) -> None:
        _clear(self.fav_rows)
        favs = self._favs()
        if not favs:
            self.fav_rows.addWidget(label("None yet. Pick an action below and press Add.", 12, dim=True))
        for k in favs:
            self.fav_rows.addLayout(self._row(menu.FAVOURITE_NAMES.get(k, k), "",
                                              lambda _=False, k=k: self._set("favourites",
                                                                             [f for f in self._favs() if f != k])))
        self.fav_pick.clear()
        for k, name in menu.FAVOURITE_CHOICES:
            if k not in favs:
                self.fav_pick.addItem(name, k)

        _clear(self.preset_rows)
        presets = self._presets()
        if not presets:
            self.preset_rows.addWidget(label("None yet. Start from one of these, or make your own below.", 12,
                                             dim=True))
        for p in presets:
            pid = p.get("id")
            self.preset_rows.addLayout(self._row(p.get("name", "Preset"), p.get("summary", ""),
                                                 lambda _=False, pid=pid: self._set(
                                                     "presets", [q for q in self._presets() if q.get("id") != pid])))
        _clear(self.starters)
        have = {p.get("name", "").lower() for p in presets}
        shown = 0
        for name, kind, v in menu.STARTER_PRESETS:
            if name.lower() in have:
                continue
            btn = PillButton(f"+ {name}", "ghost", min_width=120)
            btn.clicked.connect(lambda _=False, n=name, k=kind, v=v: self._add_preset(
                menu.make_preset(n, k, v["kb"], v.get("w", 0), v.get("h", 0), v.get("fmt", "JPG"))))
            self.starters.addWidget(btn)
            shown += 1
        if shown:
            self.starters.addStretch(1)

    def _row(self, title: str, sub: str, on_remove) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        dot = label("●", 10, wrap=False)
        dot.setStyleSheet(f"color: {theme.rgba(theme.ACCENT)};")
        row.addWidget(dot)
        row.addWidget(label(title, 13, QFont.Weight.DemiBold, wrap=False))
        if sub:
            row.addWidget(label(sub, 12, dim=True, wrap=False))
        row.addStretch(1)
        rm = PillButton("Remove", "ghost", min_width=84)
        rm.clicked.connect(on_remove)
        row.addWidget(rm)
        return row

    def _kind_changed(self, kind: str) -> None:
        exact = kind == "image_exact"
        self.w.setVisible(exact)
        self.h.setVisible(exact)
        self.fmt.setVisible(kind == "image_size")
        self.err.setText("")

    # ------------------------------------------------------------- actions
    def _add_favourite(self) -> None:
        k = self.fav_pick.currentData()
        if k and k not in self._favs():
            self._set("favourites", self._favs() + [k])

    def _add_preset(self, preset: dict) -> None:
        self._set("presets", self._presets() + [preset])

    def _save_new(self) -> None:
        def n(e: QLineEdit) -> int:
            return int(e.text()) if e.text().strip().isdigit() else 0

        try:
            p = menu.make_preset(self.name.text(), self.kind.value, n(self.kb), n(self.w), n(self.h), self.fmt.value)
        except ValueError as e:
            self.err.setText(str(e))
            return
        if any(q.get("name", "").lower() == p["name"].lower() for q in self._presets()):
            self.err.setText("There's already a preset with that name.")
            return
        self.err.setText("")
        for e in (self.name, self.kb, self.w, self.h):
            e.clear()
        self._add_preset(p)
