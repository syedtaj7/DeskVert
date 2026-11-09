"""Where the app keeps its settings, logs and temporary work files."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_NAME = "Tapshift"
APP_ID = "Tapshift"
_OLD_ID = "FileFormatter"  # name used by early development builds


def _dir(base_env: str, *parts: str) -> Path:
    base = os.environ.get(base_env) or str(Path.home())
    p = Path(base, APP_ID, *parts)
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
        old = Path(base, _OLD_ID, *parts)
        if base_env == "APPDATA" and not parts and (old / "settings.json").exists():
            shutil.copy2(old / "settings.json", p / "settings.json")  # carry settings over once
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
