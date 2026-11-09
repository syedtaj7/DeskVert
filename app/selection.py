"""Find out which files the user has selected: in the active File Explorer
window (including the active tab on Windows 11), on the Desktop, or, as a
fallback, files copied to the clipboard with Ctrl+C."""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

EXPLORER_CLASSES = {"CabinetWClass", "ExploreWClass"}
DESKTOP_CLASSES = {"Progman", "WorkerW"}


def _class_name(hwnd: int) -> str:
    import win32gui

    try:
        return win32gui.GetClassName(hwnd)
    except Exception:
        return ""


def _items_to_paths(items) -> list[Path]:
    paths = []
    for i in range(items.Count):
        try:
            p = items.Item(i).Path
        except Exception:
            continue
        if p and os.path.isfile(p):
            paths.append(Path(p))
    return paths


def _tab_hwnd(window) -> int | None:
    import pythoncom
    from win32com.shell import shell

    try:
        sp = window._oleobj_.QueryInterface(pythoncom.IID_IServiceProvider)
        browser = sp.QueryService(shell.SID_STopLevelBrowser, shell.IID_IShellBrowser)
        return browser.GetWindow()
    except Exception:
        return None


def _from_explorer(hwnd: int) -> list[Path]:
    import pythoncom
    import win32com.client
    import win32gui

    import time

    pythoncom.CoInitialize()
    for attempt in range(2):
        paths, diag = _read_explorer_once(hwnd, win32com, win32gui)
        log.info("explorer read %d: %s -> %d file(s)", attempt + 1, diag, len(paths))
        if paths:
            return paths
        time.sleep(0.08)  # Explorer can be briefly busy (e.g. right after a folder changes)
    return []


def _read_explorer_once(hwnd: int, win32com, win32gui) -> tuple[list[Path], str]:
    shell_app = win32com.client.Dispatch("Shell.Application")
    matches = []
    for w in shell_app.Windows():
        try:
            if int(w.HWND) == hwnd:
                matches.append(w)
        except Exception:
            continue
    if not matches:
        return [], "no matching Explorer window"
    counts = [_safe_count(w) for w in matches]
    chosen = matches[0]
    how = "single tab"
    if len(matches) > 1:
        # Windows 11 tabs: every tab shares the window handle. The active tab is
        # the one whose view is visible; fall back to the first tab child.
        tabs = [(w, _tab_hwnd(w)) for w in matches]
        visible = [w for w, t in tabs if t and win32gui.IsWindowVisible(t)]
        if len(visible) == 1:
            chosen, how = visible[0], "visible tab"
        else:
            first = win32gui.FindWindowEx(hwnd, 0, "ShellTabWindowClass", None)
            hit = next((w for w, t in tabs if t == first), None)
            chosen, how = (hit, "first tab") if hit is not None else (matches[0], "fallback")
    try:
        paths = _items_to_paths(chosen.Document.SelectedItems())
    except Exception as e:
        paths = []
        how += f", read failed: {e}"
    if not paths:
        # The chosen tab shows nothing selected: if exactly one tab of this
        # window has a selection, that's the one the user means.
        with_sel = [w for w, n in zip(matches, counts) if n]
        if len(with_sel) == 1 and with_sel[0] is not chosen:
            try:
                paths = _items_to_paths(with_sel[0].Document.SelectedItems())
                how += ", used the only tab with a selection"
            except Exception:
                pass
    return paths, f"{len(matches)} tab(s), selected per tab {counts}, chose {how}"

def _safe_count(w) -> int:
    try:
        return int(w.Document.SelectedItems().Count)
    except Exception:
        return 0


def _from_desktop() -> list[Path]:
    import pythoncom
    import win32com.client
    from win32com.client import VARIANT

    pythoncom.CoInitialize()
    SWC_DESKTOP, SWFO_NEEDDISPATCH = 8, 1
    windows = win32com.client.Dispatch("{9BA05972-F6A8-11CF-A442-00A0C90A8F39}")  # ShellWindows
    hwnd_out = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    try:
        desk = windows.FindWindowSW(
            VARIANT(pythoncom.VT_I4, 0), VARIANT(pythoncom.VT_EMPTY, None), SWC_DESKTOP, hwnd_out, SWFO_NEEDDISPATCH
        )
        if isinstance(desk, tuple):
            desk = desk[0]
        desk = win32com.client.Dispatch(desk)
        return _items_to_paths(desk.Document.SelectedItems())
    except Exception:
        log.exception("couldn't read Desktop selection")
        return []


def from_clipboard() -> list[Path]:
    import win32clipboard
    import win32con

    try:
        win32clipboard.OpenClipboard()
    except Exception:
        return []
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP):
            files = win32clipboard.GetClipboardData(win32con.CF_HDROP)
            return [Path(f) for f in files if os.path.isfile(f)]
    except Exception:
        log.exception("couldn't read clipboard")
    finally:
        win32clipboard.CloseClipboard()
    return []


def selected_files(hwnd: int, clipboard_fallback: bool = True) -> tuple[list[Path], str]:
    """Return (files, where) with where in {"explorer", "desktop", "clipboard", ""}."""
    cls = _class_name(hwnd)
    files: list[Path] = []
    where = ""
    if cls in EXPLORER_CLASSES:
        files, where = _from_explorer(hwnd), "explorer"
    elif cls in DESKTOP_CLASSES:
        files, where = _from_desktop(), "desktop"
    if not files and clipboard_fallback:
        clip = from_clipboard()
        if clip:
            return clip, "clipboard"
    return files, where if files else ""
