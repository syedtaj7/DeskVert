"""Tapping Ctrl+Shift on a browser while text is selected: the selection itself.

Browsers don't let other apps read a page's selection, so Tapshift does what you would: it sends the
browser Ctrl+C, reads what the browser copied (with the page's address, which browsers include), and
then puts the clipboard back exactly as it was. Nothing selected means the browser copies nothing, so
the clipboard is untouched and the tap is about the page itself.
"""

from __future__ import annotations

import ctypes
import html
import logging
import re
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
user32.EnumClipboardFormats.restype = wintypes.UINT
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# Formats that hold a drawing handle rather than memory: Windows makes them again from the memory ones.
GDI_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E} | set(range(0x300, 0x400))
MAX_SNAPSHOT = 64 * 1024 * 1024  # a clipboard bigger than this isn't copied aside (and isn't touched)
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, VK_C = 0x10, 0x11, 0x12, 0x5B, 0x5C, 0x43
KEYUP = 0x0002


def _open() -> bool:
    for _ in range(15):  # another app may have it open for a moment
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def _read(fmt: int) -> bytes | None:
    h = user32.GetClipboardData(fmt)
    if not h:
        return None
    size = kernel32.GlobalSize(h)
    ptr = kernel32.GlobalLock(h)
    if not ptr:
        return None
    try:
        return ctypes.string_at(ptr, size)
    finally:
        kernel32.GlobalUnlock(h)


def snapshot() -> list[tuple[int, bytes]] | None:
    """Everything on the clipboard, as (format, bytes). None if it can't be copied aside safely."""
    if not _open():
        return None
    try:
        items, total, fmt = [], 0, 0
        while True:
            fmt = user32.EnumClipboardFormats(fmt)
            if not fmt:
                break
            if fmt in GDI_FORMATS:
                continue
            data = _read(fmt)
            if data is None:
                continue
            total += len(data)
            if total > MAX_SNAPSHOT:
                return None
            items.append((fmt, data))
        return items
    finally:
        user32.CloseClipboard()


def restore(items: list[tuple[int, bytes]]) -> bool:
    """Put a snapshot back (an empty one empties the clipboard, as it was)."""
    if not _open():
        return False
    try:
        user32.EmptyClipboard()
        for fmt, data in items:
            h = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(1, len(data)))
            if not h:
                continue
            ptr = kernel32.GlobalLock(h)
            if ptr:
                ctypes.memmove(ptr, data, len(data))
                kernel32.GlobalUnlock(h)
            if not user32.SetClipboardData(fmt, h):
                kernel32.GlobalFree(h)
        return True
    finally:
        user32.CloseClipboard()


def _keys_free(timeout: float = 0.5) -> bool:
    """Wait until Ctrl, Shift, Alt and Windows are up (they'd change what Ctrl+C means)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN)):
            return True
        time.sleep(0.02)
    return False


def _send_copy() -> None:
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    user32.keybd_event(VK_C, 0, KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYUP, 0)


def _wait_for_copy(before: int, timeout: float = 0.8) -> bool:
    """True once the browser has put something on the clipboard (and finished: several formats in a row)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        now = user32.GetClipboardSequenceNumber()
        if now != before:
            while True:  # settled: no change for a short moment
                time.sleep(0.06)
                later = user32.GetClipboardSequenceNumber()
                if later == now or time.monotonic() > end + 0.5:
                    return True
                now = later
        time.sleep(0.02)
    return False


def clip_from_copy(items: list[tuple[int, bytes]]):
    """What the browser copied, as a web clip (or None: nothing usable, e.g. just the page's address)."""
    from . import dropread

    html_fmt = user32.RegisterClipboardFormatW("HTML Format")
    data = dict(items)
    if html_fmt in data:
        clip = dropread.clip_from_html(data[html_fmt].rstrip(b"\0"))
        if clip is not None:
            return clip
    raw = data.get(CF_UNICODETEXT)
    text = raw.decode("utf-16-le", errors="ignore").split("\0", 1)[0].strip() if raw else ""
    if not text or (re.match(r"\S+://\S+$", text)):  # nothing, or only an address (the address bar)
        return None
    paras = [p.strip() for p in re.split(r"\r?\n\s*\r?\n", text) if p.strip()]
    body = "\n".join("<p>" + html.escape(p).replace("\n", "<br>") + "</p>" for p in paras)
    return dropread.Dropped(html=body, clip=True)


def copy_selection(hwnd: int):
    """The browser window's selected text or table as a web clip, or None when nothing is selected.
    The clipboard is left exactly as it was. Runs off the UI thread (it waits for the browser)."""
    if user32.GetForegroundWindow() != hwnd or not _keys_free():
        return None
    before = user32.GetClipboardSequenceNumber()
    saved = snapshot()
    if saved is None:
        log.info("selection: the clipboard is too big or busy to set aside; not copying")
        return None
    _send_copy()
    if not _wait_for_copy(before):
        return None  # nothing selected: the browser copied nothing, the clipboard is untouched
    try:
        copied = snapshot() or []
        return clip_from_copy(copied)
    finally:
        if not restore(saved):
            log.warning("selection: couldn't put the clipboard back")
