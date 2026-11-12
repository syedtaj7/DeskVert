"""The address of the page open in a browser window (Edge, Chrome, Brave, Firefox...).

Read from the browser's address bar through Windows accessibility (oleacc, the same
channel screen readers use), called directly: nothing is typed into the browser and
the clipboard isn't touched. Only the address is read, only when you tap Ctrl+Shift
on that window.
"""

from __future__ import annotations

import ctypes
import logging
import re
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

BROWSER_CLASSES = {"Chrome_WidgetWin_1", "MozillaWindowClass"}  # Chromium browsers (Edge, Chrome, Brave...), Firefox
BROWSER_EXES = {"msedge.exe", "chrome.exe", "brave.exe", "firefox.exe", "opera.exe", "vivaldi.exe", "arc.exe",
                "librewolf.exe", "waterfox.exe", "chromium.exe", "yandex.exe"}
BROWSER_TITLES = (" - Google Chrome", " - Microsoft​ Edge", " - Microsoft Edge", " — Mozilla Firefox",
                  " - Mozilla Firefox", " - Brave", " - Opera", " - Vivaldi")
_ADDRESS_WORDS = ("address", "url", "location", "adresse", "dirección", "indirizzo", "adres", "पता")

OBJID_CLIENT = -4
ROLE_TEXT, ROLE_COMBOBOX = 42, 46
VT_I4, VT_DISPATCH = 3, 9


class GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


def _guid(text: str) -> GUID:
    h = text.strip("{}").replace("-", "")
    g = GUID(int(h[:8], 16), int(h[8:12], 16), int(h[12:16], 16))
    for i in range(8):
        g.d[i] = int(h[16 + 2 * i:18 + 2 * i], 16)
    return g


IID_IACCESSIBLE = _guid("{618736E0-3C3D-11CF-810C-00AA00389B71}")


class VARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("val", ctypes.c_void_p), ("val2", ctypes.c_void_p)]


def _self_variant() -> VARIANT:
    v = VARIANT()
    v.vt = VT_I4  # CHILDID_SELF (0)
    return v


# IAccessible's vtable (after IUnknown's 3 and IDispatch's 4 methods)
_CHILD_COUNT, _NAME, _VALUE, _ROLE = 8, 10, 11, 13


def _method(ptr: int, index: int, *argtypes):
    vtable = ctypes.cast(ctypes.c_void_p(ptr), ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return proto(vtable[index])


def _release(ptr: int) -> None:
    if ptr:
        _method(ptr, 2)(ptr)


class Acc:
    """One accessible part of a window (an IAccessible pointer), released when done."""

    def __init__(self, ptr: int):
        self.ptr = ptr

    def __del__(self):
        try:
            _release(self.ptr)
        except Exception:  # noqa: BLE001
            pass

    def _text(self, index: int) -> str:
        out = ctypes.c_void_p()
        if _method(self.ptr, index, VARIANT, ctypes.POINTER(ctypes.c_void_p))(self.ptr, _self_variant(),
                                                                             ctypes.byref(out)) != 0 or not out:
            return ""
        try:
            return ctypes.wstring_at(out.value)
        finally:
            ctypes.windll.oleaut32.SysFreeString(out)

    def name(self) -> str:
        return self._text(_NAME)

    def value(self) -> str:
        return self._text(_VALUE)

    def role(self) -> int:
        out = VARIANT()
        if _method(self.ptr, _ROLE, VARIANT, ctypes.POINTER(VARIANT))(self.ptr, _self_variant(), ctypes.byref(out)):
            return 0
        return (out.val or 0) & 0xFFFFFFFF if out.vt == VT_I4 else 0

    def children(self, limit: int = 80) -> list["Acc"]:
        count = ctypes.c_long()
        if _method(self.ptr, _CHILD_COUNT, ctypes.POINTER(ctypes.c_long))(self.ptr, ctypes.byref(count)) != 0:
            return []
        n = max(0, min(count.value, limit))
        if not n:
            return []
        arr = (VARIANT * n)()
        got = ctypes.c_long()
        if ctypes.windll.oleacc.AccessibleChildren(ctypes.c_void_p(self.ptr), 0, n, arr, ctypes.byref(got)) < 0:
            return []
        kids = []
        for v in arr[:got.value]:
            if v.vt == VT_DISPATCH and v.val:
                acc = ctypes.c_void_p()
                qi = _method(v.val, 0, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
                if qi(v.val, ctypes.byref(IID_IACCESSIBLE), ctypes.byref(acc)) == 0 and acc.value:
                    kids.append(Acc(acc.value))
                _release(v.val)
        return kids


def is_browser(hwnd: int) -> bool:
    """A browser window (not another app built on Chromium, like this one's own neighbours)."""
    import win32gui
    import win32process

    try:
        if win32gui.GetClassName(hwnd) not in BROWSER_CLASSES:
            return False
        import psutil

        return psutil.Process(win32process.GetWindowThreadProcessId(hwnd)[1]).name().lower() in BROWSER_EXES
    except Exception:  # noqa: BLE001
        return False


def page_title(hwnd: int) -> str:
    import win32gui

    title = win32gui.GetWindowText(hwnd) or ""
    for tail in BROWSER_TITLES:
        if title.endswith(tail):
            title = title[: -len(tail)]
    title = re.sub(r"\s+and \d+ more pages?$", "", title)  # Edge: "Page and 2 more pages"
    return title.strip()


def _looks_like_address(value: str) -> bool:
    v = (value or "").strip()
    return bool(v) and " " not in v and ("." in v or v.startswith(("http:", "https:", "localhost")))


def page_url(hwnd: int, budget: float = 3.0) -> str:
    """The open page's address ('' when it can't be found). Call from a thread with COM initialised."""
    ptr = ctypes.c_void_p()
    hr = ctypes.windll.oleacc.AccessibleObjectFromWindow(wintypes.HWND(hwnd), wintypes.DWORD(OBJID_CLIENT & 0xFFFFFFFF),
                                                         ctypes.byref(IID_IACCESSIBLE), ctypes.byref(ptr))
    if hr != 0 or not ptr.value:
        log.info("browser: no accessibility on this window (%#x)", hr & 0xFFFFFFFF)
        return ""
    deadline = time.monotonic() + budget
    queue = [(Acc(ptr.value), 0)]
    seen = 0
    fallback = ""
    while queue and seen < 3000 and time.monotonic() < deadline:
        node, depth = queue.pop(0)
        seen += 1
        try:
            role = node.role()
            if role in (ROLE_TEXT, ROLE_COMBOBOX):
                value = node.value()
                if _looks_like_address(value):
                    if any(w in node.name().lower() for w in _ADDRESS_WORDS):
                        return _normal(value)
                    fallback = fallback or value
            if depth < 16:
                queue += [(k, depth + 1) for k in node.children()]
        except Exception:  # noqa: BLE001 - one odd part of the window: skip it
            continue
    if fallback:
        return _normal(fallback)
    log.info("browser: no address bar found (%d parts looked at)", seen)
    return ""


def _normal(value: str) -> str:
    v = value.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*:", v, re.I):
        v = "https://" + v  # browsers hide the "https://" in the address bar
    return v
