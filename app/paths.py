"""Where the app keeps its settings, logs and temporary work files."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_NAME = "Deskvert"
APP_ID = "Deskvert"
# Earlier names: settings are carried over once from the newest one found (Deskvert was called Tapshift
# until 1.14; early development builds were FileFormatter).
_OLD_IDS = ("Tapshift", "FileFormatter")


def _dir(base_env: str, *parts: str) -> Path:
    base = os.environ.get(base_env) or str(Path.home())
    p = Path(base, APP_ID, *parts)
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
        if base_env == "APPDATA" and not parts:
            for old_id in _OLD_IDS:
                old = Path(base, old_id, "settings.json")
                if old.exists():
                    shutil.copy2(old, p / "settings.json")  # carry settings over once
                    break
    return p


def config_dir() -> Path:
    return _dir("APPDATA")


def log_dir() -> Path:
    return _dir("LOCALAPPDATA", "logs")


def work_root() -> Path:
    """Scratch space for conversions. Outputs are built here, checked, then moved."""
    return _dir("LOCALAPPDATA", "work")


def documents_dir() -> Path:
    try:
        from win32com.shell import shell, shellcon

        return Path(shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0))
    except Exception:
        return Path.home() / "Documents"


def fallback_output_dir() -> Path:
    """Used only when the source folder can't be written to (read-only, protected)."""
    p = documents_dir() / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def long_path(p: Path | str) -> str:
    """Return a path string that also works beyond Windows' 260-character limit."""
    s = str(Path(p).absolute())
    if os.name == "nt" and len(s) >= 240 and not s.startswith("\\\\?\\"):
        if s.startswith("\\\\"):
            return "\\\\?\\UNC\\" + s[2:]
        return "\\\\?\\" + s
    return s
