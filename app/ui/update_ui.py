"""The "Check for updates" panel on the About page: check, download (with progress),
then install and restart. Network work runs on a background thread."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from .. import __version__, updater
from ..winutil import uninstaller
from . import theme
from .fx import PillButton


class _Bridge(QObject):
    """Carries results from the worker thread back to the window (queued signals)."""

    checked = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)
    downloaded = Signal(str)


def _mb(n: int) -> str:
    return f"{n / 1_000_000:.1f} MB" if n >= 100_000 else f"{max(1, n // 1000)} KB"


class UpdatePanel(QFrame):
    install_requested = Signal(str)  # path of the downloaded installer

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("upd")
        self.setStyleSheet(
            f"QFrame#upd {{ background: {theme.rgba(theme.SURFACE)}; border: 1px solid {theme.rgba(theme.LINE)};"
            f" border-radius: 14px; }}"
            f"QLabel {{ color: {theme.rgba(theme.TEXT)}; background: transparent; border: none; }}"
            f"QLabel#dim {{ color: {theme.rgba(theme.DIM)}; }}"
            f"QProgressBar {{ background: {theme.rgba(theme.TRACK)}; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {theme.rgba(theme.ACCENT)}; border-radius: 3px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.text = QLabel()
        self.text.setObjectName("dim")
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setTextFormat(Qt.TextFormat.PlainText)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 0)
        self.primary = PillButton("", "primary", min_width=170)
        self.secondary = PillButton("", "ghost", min_width=120)
        row.addWidget(self.primary)
        row.addWidget(self.secondary)
        row.addStretch(1)
        btns = QWidget()
        btns.setLayout(row)
        for w in (self.title, self.text, self.notes, self.bar, btns):
            lay.addWidget(w)
        self.primary.clicked.connect(lambda: self._primary and self._primary())
        self.secondary.clicked.connect(lambda: self._secondary and self._secondary())
        self._primary = self._secondary = None
        self._bridge = _Bridge()
        self._bridge.checked.connect(self._on_checked)
        self._bridge.failed.connect(self._on_failed)
        self._bridge.progress.connect(self._on_progress)
        self._bridge.downloaded.connect(self._on_downloaded)
        self._busy = False
        self._cancel = False
        self.release: updater.Release | None = None
        self.hide()

    # ------------------------------------------------------------ states
    def _show(self, title: str, text: str = "", notes: list[str] | None = None, bar: bool = False,
              primary: tuple[str, object] | None = None, secondary: tuple[str, object] | None = None):
        self.title.setText(title)
        self.text.setText(text)
        self.text.setVisible(bool(text))
        self.notes.setText("\n".join(f"•  {n}" for n in (notes or [])))
        self.notes.setVisible(bool(notes))
        self.bar.setVisible(bar)
        for btn, spec, attr in ((self.primary, primary, "_primary"), (self.secondary, secondary, "_secondary")):
            btn.setVisible(spec is not None)
            if spec is not None:
                btn.setText(spec[0])
                btn.updateGeometry()
                btn.update()
            setattr(self, attr, spec[1] if spec else None)
        self.show()

    def start_check(self):
        if self._busy:
            return
        self._busy = True
        self._show("Checking for updates…", "Asking GitHub for the latest version of Deskvert.")

        def work():
            try:
                self._bridge.checked.emit(updater.fetch_latest())
            except updater.UpdateError as e:
                self._bridge.failed.emit(str(e))
            except Exception:  # noqa: BLE001
                self._bridge.failed.emit("Couldn't check for updates. Try again later.")

        threading.Thread(target=work, daemon=True).start()

    def _on_checked(self, rel: updater.Release):
        self._busy = False
        self.release = rel
        if not updater.is_newer(rel.version):
            self._show("You're up to date", f"Deskvert {__version__} is the latest version.",
                       secondary=("Check again", self.start_check))
            return
        what = rel.notes or ["Improvements and fixes."]
        if uninstaller() is not None and rel.setup is not None:
            self._show(f"Deskvert {rel.version} is available", f"You have {__version__}. What's new:", what,
                       primary=(f"Download ({_mb(rel.setup.size)})", self._download),
                       secondary=("Release page", lambda: self._open(rel.page)))
        else:  # the portable zip (or no installer in this release): get it from the release page
            self._show(f"Deskvert {rel.version} is available",
                       f"You have {__version__}. This copy wasn't installed with Setup, so download the new "
                       "version from the release page. What's new:", what,
                       primary=("Open download page", lambda: self._open(rel.page)))

    def _download(self):
        rel = self.release
        if self._busy or rel is None or rel.setup is None:
            return
        self._busy, self._cancel = True, False
        self.bar.setRange(0, max(1, rel.setup.size))
        self.bar.setValue(0)
        self._show(f"Downloading Deskvert {rel.version}…", f"0 of {_mb(rel.setup.size)}", bar=True,
                   secondary=("Cancel", self._cancel_download))

        def work():
            try:
                path = updater.download(rel.setup, lambda d, t: self._bridge.progress.emit(d, t),
                                        lambda: self._cancel)
                self._bridge.downloaded.emit(str(path))
            except updater.UpdateError as e:
                self._bridge.failed.emit(str(e))
            except Exception:  # noqa: BLE001
                self._bridge.failed.emit("The download failed. Try again.")

        threading.Thread(target=work, daemon=True).start()

    def _cancel_download(self):
        self._cancel = True

    def _on_progress(self, done: int, total: int):
        if total > 0 and self.bar.maximum() != total:
            self.bar.setRange(0, total)
        self.bar.setValue(done)
        self.text.setText(f"{_mb(done)} of {_mb(total or (self.release.setup.size if self.release else 0))}")

    def _on_downloaded(self, path: str):
        self._busy = False
        ver = self.release.version if self.release else ""
        self._show(f"Deskvert {ver} is ready to install",
                   "Checked: the file matches the one published on GitHub. Deskvert will close, install the "
                   "update and open again; conversions still running will stop.",
                   primary=("Install and restart", lambda: self.install_requested.emit(path)),
                   secondary=("Later", self.hide))

    def _on_failed(self, msg: str):
        self._busy = False
        retry = self._download if (self.release and self.title.text().startswith("Downloading")) else self.start_check
        cancelled = msg.startswith("Download cancelled")
        self._show("Download cancelled" if cancelled else "Something went wrong",
                   "" if cancelled else msg, primary=("Try again", retry))

    @staticmethod
    def _open(url: str):
        import webbrowser

        webbrowser.open(url)


def installer_ready(path: str) -> bool:
    p = Path(path)
    return p.exists() and p.stat().st_size > 0
