"""Conversion history: what was converted, when, and into what. Kept on this PC only
(%LOCALAPPDATA%\\Deskvert\\history.json), newest first, the last 300 conversions."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .paths import _dir

LIMIT = 300


def path() -> Path:
    return _dir("LOCALAPPDATA") / "history.json"


def load() -> list[dict]:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
        return [e for e in data if isinstance(e, dict) and e.get("outputs")] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def add(label: str, sources: list[str], outputs: list[str], failed: int = 0) -> None:
    """One finished conversion (only the files it made; nothing about failures beyond how many)."""
    if not outputs:
        return
    entry = {"time": time.time(), "label": label, "sources": list(dict.fromkeys(sources)), "outputs": list(outputs),
             "failed": failed}
    items = [entry] + load()
    p = path()
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(items[:LIMIT], indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def clear() -> None:
    try:
        path().unlink()
    except OSError:
        pass


def when(t: float, now: float | None = None) -> str:
    """"Today 14:05", "Yesterday 09:12" or "12 Nov 18:30"."""
    now = now or time.time()
    day, today = time.localtime(t), time.localtime(now)
    clock = time.strftime("%H:%M", day)
    if day.tm_yday == today.tm_yday and day.tm_year == today.tm_year:
        return f"Today {clock}"
    yesterday = time.localtime(now - 86400)
    if day.tm_yday == yesterday.tm_yday and day.tm_year == yesterday.tm_year:
        return f"Yesterday {clock}"
    return time.strftime("%d %b %H:%M", day).lstrip("0")


def describe(entry: dict) -> str:
    """"beach.heic → beach.jpg" or "12 files → PDF"."""
    src, out = entry.get("sources") or [], entry.get("outputs") or []
    if len(src) == 1 and len(out) == 1:
        return f"{Path(src[0]).name} → {Path(out[0]).name}"
    what = f"{len(src)} files" if len(src) != 1 else Path(src[0]).name
    made = Path(out[0]).name if len(out) == 1 else f"{len(out)} {entry.get('label', 'files')} files"
    return f"{what} → {made}"
