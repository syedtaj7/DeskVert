"""Watch folders: files you put in a chosen folder are converted by themselves.

Each watched folder has one action ("PDF", "JPG", "Compress"...). A new file is converted once it has
finished arriving (the same size twice in a row), and the result goes into a "Converted" folder inside
the watched one, so results are never picked up again. Only files added after Tapshift started
watching count; files already there are left alone. Nothing is ever deleted or moved.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

log = logging.getLogger(__name__)

ACTIONS = ("PDF", "JPG", "PNG", "WEBP", "Compress", "MP3", "TXT")
SKIP_SUFFIXES = (".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload", ".!ut", ".ini", ".lnk")
OUT_FOLDER = "Converted"


def pick_offer(path: Path, action: str, settings):
    """The picker's choice that does `action` for this file (None if it doesn't apply to it)."""
    from .catalog import offers_for

    offers, _ = offers_for([path], settings)
    for o in offers:
        if o.target.combine:
            continue
        if action == "Compress" and o.target.engine in ("compress", "pdf") and o.target.label == "Compress":
            return o
        if o.target.label == action:
            return o
    return None


def is_candidate(path: Path) -> bool:
    n = path.name.lower()
    return not (n.startswith(("~$", ".")) or n.endswith(SKIP_SUFFIXES) or n in ("desktop.ini", "thumbs.db"))


class FolderWatcher(QObject):
    """Watches folders; emits convert(offer, options, dest) for each new, finished file."""

    convert = Signal(object, dict, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._fs: QFileSystemWatcher | None = None
        self._rules: dict[str, str] = {}  # folder (lower) -> action
        self._paths: dict[str, Path] = {}
        self._since = time.time()
        self._seen: dict[str, int] = {}  # file -> last size seen; -1 = handled
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self.scan)

    def set_rules(self, rules: list[dict]) -> None:
        """[{"path": folder, "action": "PDF"}, ...]: start watching these (and stop watching others)."""
        if self._fs is not None:
            self._fs.deleteLater()
            self._fs = None
        self._rules, self._paths = {}, {}
        for r in rules or []:
            p = Path(str(r.get("path", "")))
            if p.is_dir() and r.get("action") in ACTIONS:
                self._rules[str(p).lower()] = r["action"]
                self._paths[str(p).lower()] = p
        self._since = time.time()
        self._seen = {}
        if self._rules:
            self._fs = QFileSystemWatcher([str(p) for p in self._paths.values()], self)
            self._fs.directoryChanged.connect(lambda _p: self._timer.start())
            log.info("watching %d folder(s)", len(self._rules))

    def scan(self) -> None:
        waiting = False
        for key, folder in self._paths.items():
            action = self._rules[key]
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for e in entries:
                if not e.is_file() or not is_candidate(Path(e.path)):
                    continue
                try:
                    st = e.stat()
                except OSError:
                    continue
                if st.st_mtime < self._since or self._seen.get(e.path) == -1:
                    continue
                if self._seen.get(e.path) != st.st_size:  # still arriving: look again in a moment
                    self._seen[e.path] = st.st_size
                    waiting = True
                    continue
                self._seen[e.path] = -1  # handled once, even if it fails or is renamed later
                offer = pick_offer(Path(e.path), action, self.settings)
                if offer is None:
                    log.info("watch: %s has no %s choice; left alone", e.name, action)
                    continue
                log.info("watch: %s -> %s", e.name, action)
                self.convert.emit(offer, {o.key: o.default for o in offer.options}, str(folder / OUT_FOLDER))
        if waiting:
            self._timer.start()
