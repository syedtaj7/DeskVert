"""What happened to every file in a batch: the ones that failed first, each with its reason."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from . import theme
from .chrome import ChromeWindow, label
from .fx import PillButton, with_alpha
from .panels import StatusIcon


def summarize(results: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    ok = [r for r in results if r.get("ok")]
    cancelled = [r for r in results if r.get("cancelled")]
    failed = [r for r in results if not r.get("ok") and not r.get("cancelled")]
    return ok, failed, cancelled


def as_text(label_: str, results: list[dict]) -> str:
    """The same list as plain text, to paste into a message or a bug report."""
    ok, failed, cancelled = summarize(results)
    lines = [f"Deskvert: {label_}. {len(ok)} converted, {len(failed)} failed, {len(cancelled)} cancelled."]
    for r in failed:
        lines.append(f"FAILED  {Path(r['sources'][0]).name}: {r.get('error', 'Unknown error')}")
    for r in cancelled:
        lines.append(f"CANCELLED  {Path(r['sources'][0]).name}")
    for r in ok:
        lines.append(f"OK  {Path(r['sources'][0]).name} -> {Path(r['output']).name}")
    return "\n".join(lines)


class ResultsWindow(ChromeWindow):
    show_file = Signal(str)

    def __init__(self, label_: str, results: list[dict]):
        super().__init__("Deskvert results", QSize(640, 540))
        ok, failed, cancelled = summarize(results)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.setSpacing(6)
        parts = [f"{len(ok)} converted"]
        if failed:
            parts.append(f"{len(failed)} failed")
        if cancelled:
            parts.append(f"{len(cancelled)} cancelled")
        lay.addWidget(label(label_, 22, QFont.Weight.Bold, display=True))
        lay.addWidget(label("  ·  ".join(parts) + ". Your original files are unchanged.", 13, dim=True))
        lay.addSpacing(6)

        rows = QVBoxLayout()
        rows.setSpacing(6)
        rows.setContentsMargins(0, 0, 8, 0)
        for kind, group in (("error", failed), ("info", cancelled), ("success", ok)):
            for r in group:
                rows.addWidget(self._row(kind, r))
        rows.addStretch(1)
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder.setLayout(rows)
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        from .showcase import scroll_qss

        scroll.setStyleSheet(scroll_qss())
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)

        foot = QHBoxLayout()
        self.copy_btn = PillButton("Copy the list", "ghost", min_width=130)
        self.copy_btn.clicked.connect(lambda: self._copy(as_text(label_, results)))
        close = PillButton("Close", "primary", min_width=110)
        close.clicked.connect(self.close)
        foot.addWidget(self.copy_btn)
        foot.addStretch(1)
        foot.addWidget(close)
        lay.addLayout(foot)

    def _row(self, kind: str, r: dict) -> QFrame:
        box = QFrame()
        box.setObjectName("res")
        tint = theme.ERROR if kind == "error" else theme.SURFACE
        box.setStyleSheet(f"QFrame#res {{ background: {theme.rgba(with_alpha(tint, 0.08) if kind == 'error' else tint)};"
                          f" border: 1px solid {theme.rgba(theme.LINE)}; border-radius: 12px; }}")
        row = QHBoxLayout(box)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)
        row.addWidget(StatusIcon(kind), 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = Path(r["sources"][0]).name if len(r["sources"]) == 1 else f"{len(r['sources'])} files"
        title = label("", 13, QFont.Weight.DemiBold, wrap=False)
        title.setText(QFontMetrics(title.font()).elidedText(name, Qt.TextElideMode.ElideMiddle, 430))
        title.setToolTip(name)
        col.addWidget(title)
        if kind == "success":
            detail = "Saved as " + Path(r["output"]).name
        elif kind == "info":
            detail = "Cancelled before it was converted."
        else:
            detail = r.get("error", "Unknown error")
        col.addWidget(label(detail, 12, dim=True))
        row.addLayout(col, 1)
        if kind == "success":
            show = PillButton("Show", "ghost", min_width=70)
            show.clicked.connect(lambda _=False, p=r["output"]: self.show_file.emit(p))
            row.addWidget(show, 0, Qt.AlignmentFlag.AlignVCenter)
        return box

    def _copy(self, text: str):
        QGuiApplication.clipboard().setText(text)
        self.copy_btn.setText("Copied")
