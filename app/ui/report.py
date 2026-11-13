"""The Report a problem window: describe it, see exactly what would be shared, then open GitHub.

Tapshift sends nothing itself. "Open on GitHub" fills in a new issue in your browser, where you read
it, change it, and post it (or don't). The log is shown first, with names and folders hidden.
"""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout

from .. import report
from . import theme
from .chrome import ChromeWindow, label
from .fx import PillButton


def _box_qss() -> str:
    return (f"QPlainTextEdit {{ background: {theme.rgba(theme.SURFACE)}; color: {theme.rgba(theme.TEXT)};"
            f" border: 1px solid {theme.rgba(theme.LINE)}; border-radius: {theme.RADIUS_CONTROL}px; padding: 6px;"
            f" font: 13px '{theme.FONT}'; selection-background-color: {theme.rgba(theme.ACCENT)}; }}"
            f"QPlainTextEdit:focus {{ border: 1px solid {theme.rgba(theme.ACCENT)}; }}"
            f"QCheckBox {{ color: {theme.rgba(theme.TEXT)}; font: 13px '{theme.FONT}'; background: transparent; }}")


class ReportWindow(ChromeWindow):
    def __init__(self, about: str = ""):
        super().__init__("Report a problem", QSize(620, 600))
        self.setStyleSheet(self.styleSheet() + _box_qss())
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(label("Report a problem", 22, QFont.Weight.Bold, display=True))
        lay.addWidget(label("Tapshift sends nothing by itself. <b>Open on GitHub</b> fills in a new issue in your "
                            "browser: you read it, change anything, and post it yourself (a free GitHub account is "
                            "needed). Your name and folders are hidden in the log below.", 13, dim=True))
        self.title = QLineEdit(f"Problem: {about}" if about else "")
        self.title.setPlaceholderText("A short title, e.g. “Word files fail to convert to PDF”")
        lay.addWidget(self.title)
        self.what = QPlainTextEdit()
        self.what.setPlaceholderText("What did you do, what happened, and what did you expect?")
        self.what.setFixedHeight(110)
        if about:
            self.what.setPlainText(f"{about}\n\n")
        lay.addWidget(self.what)
        self.with_log = QCheckBox("Include the recent log (names and folders hidden)")
        self.with_log.setChecked(True)
        self.with_log.toggled.connect(self._refresh)
        lay.addWidget(self.with_log)
        lay.addWidget(label("What will be shared", 13, QFont.Weight.DemiBold))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont("Consolas", 9))
        lay.addWidget(self.preview, 1)
        self.what.textChanged.connect(self._refresh)
        row = QHBoxLayout()
        logs = PillButton("Log folder", "ghost", min_width=110)
        logs.clicked.connect(report.open_log_folder)
        copy = PillButton("Copy", "ghost", min_width=90)
        copy.clicked.connect(self._copy)
        go = PillButton("Open on GitHub", "primary", min_width=170)
        go.clicked.connect(self._open)
        row.addWidget(logs)
        row.addStretch(1)
        row.addWidget(copy)
        row.addWidget(go)
        lay.addLayout(row)
        self._refresh()

    def body_text(self) -> str:
        return report.issue_body(self.what.toPlainText(), self.with_log.isChecked())

    def _refresh(self) -> None:
        self.preview.setPlainText(self.body_text())

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(f"{self.title.text().strip()}\n\n{self.body_text()}")

    def _open(self) -> None:
        webbrowser.open(report.issue_url(self.title.text().strip(), self.body_text()))
