"""The History window: recent conversions, newest first, each with Open, Show in folder and Convert again."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from .. import history
from ..winutil import show_in_explorer
from . import theme
from .chrome import ChromeWindow, label
from .fx import PillButton

SHOWN = 120  # rows drawn at once (the file keeps more)


class HistoryWindow(ChromeWindow):
    convert_again = Signal(list)  # the original files: open the picker for them

    def __init__(self):
        super().__init__("History", QSize(720, 620))
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label("History", 22, QFont.Weight.Bold, display=True))
        head.addStretch(1)
        self.clear_btn = PillButton("Clear history", "ghost", min_width=130)
        self.clear_btn.clicked.connect(self._clear)
        head.addWidget(self.clear_btn)
        lay.addLayout(head)
        lay.addWidget(label("What you converted, newest first. It's kept on this PC only; clearing it doesn't touch "
                            "any files.", 13, dim=True))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        lay.addWidget(self.scroll, 1)
        self.refresh()

    def refresh(self) -> None:
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        rows = QVBoxLayout(holder)
        rows.setContentsMargins(0, 0, 6, 0)
        rows.setSpacing(8)
        entries = history.load()
        self.clear_btn.setEnabled(bool(entries))
        if not entries:
            rows.addWidget(label("Nothing yet. Conversions show up here once they're done.", 13, dim=True))
        for e in entries[:SHOWN]:
            rows.addWidget(self._row(e))
        rows.addStretch(1)
        self.scroll.setWidget(holder)

    def _row(self, e: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("hrow")
        card.setStyleSheet(f"QFrame#hrow {{ background: {theme.rgba(theme.SURFACE)}; border: 1px solid "
                           f"{theme.rgba(theme.LINE)}; border-radius: {theme.RADIUS_CONTROL + 4}px; }}")
        h = QHBoxLayout(card)
        h.setContentsMargins(14, 10, 10, 10)
        h.setSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        outputs = [o for o in e.get("outputs", []) if os.path.exists(o)]
        sources = [s for s in e.get("sources", []) if os.path.exists(s)]
        title = label(history.describe(e), 13, QFont.Weight.DemiBold, wrap=False)
        title.setToolTip("\n".join(e.get("outputs", [])[:20]))
        texts.addWidget(title)
        sub = history.when(e.get("time", 0))
        if e.get("failed"):
            sub += f" · {e['failed']} failed"
        if not outputs:
            sub += " · moved or deleted since"
        texts.addWidget(label(sub, 12, dim=True, wrap=False))
        h.addLayout(texts, 1)
        if len(outputs) == 1:
            op = PillButton("Open", "ghost", min_width=70)
            op.clicked.connect(lambda _=False, f=outputs[0]: os.startfile(f))  # noqa: S606 - a file Deskvert made
            h.addWidget(op)
        if outputs:
            fold = PillButton("Show in folder", "ghost", min_width=120)
            fold.clicked.connect(lambda _=False, f=outputs[0]: show_in_explorer(f))
            h.addWidget(fold)
        again = PillButton("Convert again", "primary", min_width=120)
        again.setEnabled(bool(sources))
        again.setToolTip("" if sources else "The original files aren't there any more")
        again.clicked.connect(lambda _=False, s=sources: self.convert_again.emit(s))
        h.addWidget(again)
        return card

    def _clear(self) -> None:
        history.clear()
        self.refresh()

    def sizeHint(self):
        return QSize(720, 620)

