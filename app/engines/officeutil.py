"""Helpers for driving Microsoft Office safely and lightly.

- Each conversion starts its own hidden Office instance (except PowerPoint,
  which only allows one: if you already have it open, your instance is used,
  never closed and never slowed down).
- Instances we start are launched by us, so they live inside the same hard CPU
  cap as every other engine from their very first moment, at idle priority,
  and are closed as soon as the job is done.
- Macros are disabled for files we open, files are opened read-only, and
  Office's alerts are switched off for our instance only (none of your Office
  settings are changed).
- A watchdog closes our instance if it stops responding (e.g. a hidden
  dialog), so a conversion can never hang forever.
"""

from __future__ import annotations

import ctypes
import os
import re
import threading
import unicodedata
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

from ..errors import ConversionError

NO_PASSWORD = "\u00a7deskvert-no-password\u00a7"  # wrong on purpose: protected files fail fast instead of prompting
MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3

PROCESS_TERMINATE = 0x0001
PROCESS_SET_QUOTA = 0x0100
PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_k32 = ctypes.windll.kernel32
_psapi = ctypes.windll.psapi
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]


def pids_named(exe: str) -> set[int]:
    arr = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    _psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(needed))
    out = set()
    buf = ctypes.create_unicode_buffer(1024)
    for pid in arr[: needed.value // ctypes.sizeof(wintypes.DWORD)]:
        h = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            continue
        size = wintypes.DWORD(1024)
        if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            if os.path.basename(buf.value).lower() == exe.lower():
                out.add(int(pid))
        _k32.CloseHandle(h)
    return out


def adopt(pid: int) -> None:
    """Put an Office process we started under this worker's CPU cap."""
    from .. import lowimpact

    h = _k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_SET_INFORMATION, False, pid)
    if not h:
        return
    try:
        if lowimpact._job:
            _k32.AssignProcessToJobObject(wintypes.HANDLE(lowimpact._job), wintypes.HANDLE(h))
        lowimpact.throttle(h)
    finally:
        _k32.CloseHandle(h)


def kill(pid: int) -> None:
    h = _k32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if h:
        _k32.TerminateProcess(h, 1)
        _k32.CloseHandle(h)


class OfficeApp:
    def __init__(self, app, owned_pids: set[int], name: str):
        self.app = app
        self.pids = owned_pids  # empty when we're borrowing the user's running instance
        self.name = name

    @property
    def owned(self) -> bool:
        return bool(self.pids)


def _server_path(progid: str) -> str | None:
    """The Office program registered for automation (e.g. ...\\Office16\\WINWORD.EXE)."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID") as k:
            clsid = winreg.QueryValueEx(k, "")[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\LocalServer32") as k:
            cmd = winreg.QueryValueEx(k, "")[0]
    except OSError:
        return None
    # Often unquoted despite spaces: C:\Program Files\...\WINWORD.EXE /Automation
    cmd = cmd.strip().strip('"')
    end = cmd.lower().find(".exe")
    if end < 0:
        return None
    exe = cmd[: end + 4].strip('"')
    return exe if os.path.isfile(exe) else None


def _window_of_pid(cls: str, pid: int) -> bool:
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        if buf.value == cls:
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    return bool(found)


def _launch_capped(progid: str):
    """Start the Office program ourselves, so it begins life inside this
    worker's CPU cap (startup included). Windows then hands our automation
    request to this already-running instance instead of starting a new one."""
    import subprocess

    path = _server_path(progid)
    if not path:
        return None
    try:
        p = subprocess.Popen([path, "/Automation", "-Embedding"])
    except OSError:
        return None
    ctypes.windll.user32.WaitForInputIdle(wintypes.HANDLE(int(p._handle)), 30000)
    # Wait until it has told Windows it's ready to take automation requests;
    # its main window class appears at that point.
    cls = {"WINWORD.EXE": "OpusApp", "EXCEL.EXE": "XLMAIN", "POWERPNT.EXE": "PPTFrameClass"}.get(
        os.path.basename(path).upper())
    deadline = 15.0
    while cls and deadline > 0 and p.poll() is None:
        if _window_of_pid(cls, p.pid):
            break
        threading.Event().wait(0.1)
        deadline -= 0.1
    threading.Event().wait(0.3)
    return p


@contextmanager
def office(progid: str, exe: str, name: str):
    """Start a private, hidden, CPU-capped Office instance; always cleaned up."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    before = pids_named(exe)
    if not (before and exe.upper() == "POWERPNT.EXE"):  # PowerPoint allows only one instance
        _launch_capped(progid)
    try:
        app = win32com.client.DispatchEx(progid)
    except Exception as e:
        raise ConversionError(f"Microsoft {name} couldn't be started ({e}).") from e
    new = pids_named(exe) - before
    for pid in new:
        adopt(pid)
    oa = OfficeApp(app, new, name)
    try:
        try:
            app.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE  # never run macros from files
        except Exception:
            pass
        yield oa
    finally:
        if oa.owned:
            try:
                app.Quit()
            except Exception:
                pass
            # Make sure it's really gone (a hidden Office left running would
            # grab files you open later).
            for _ in range(20):
                if not (oa.pids & pids_named(exe)):
                    break
                threading.Event().wait(0.1)
            for pid in oa.pids & pids_named(exe):
                kill(pid)
        oa.app = None
        del app
        # COM stays initialized for this thread on purpose: uninitializing while
        # Python still holds Office objects breaks the next Office call.


class Watchdog:
    """Closes our Office instance if one step takes far too long."""

    def __init__(self, oa: OfficeApp, seconds: float, what: str):
        self.oa, self.seconds, self.what = oa, seconds, what
        self.fired = False
        self._t: threading.Timer | None = None

    def _fire(self):
        self.fired = True
        for pid in self.oa.pids:
            kill(pid)

    def __enter__(self):
        if self.oa.owned:
            self._t = threading.Timer(self.seconds, self._fire)
            self._t.daemon = True
            self._t.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._t:
            self._t.cancel()
        if self.fired:
            raise ConversionError(
                f"{self.oa.name} stopped responding while {self.what}, so it was closed. "
                "The file may be damaged, password-protected, or need a dialog answered.")
        return False


def timeout_for(path: Path, base: float = 120) -> float:
    try:
        mb = path.stat().st_size / 1e6
    except OSError:
        mb = 1
    return min(1800.0, base + mb * 15)


def is_encrypted_ooxml(path: Path) -> bool:
    """Password-protected .docx/.xlsx/.pptx are stored as OLE files, not ZIP."""
    if path.suffix.lower() not in (".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm", ".ppsx"):
        return False
    try:
        with open(path, "rb") as f:
            return f.read(8) == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except OSError:
        return False


def friendly_com_error(e: Exception, name: str) -> ConversionError:
    text = str(e)
    low = text.lower()
    if "password" in low:
        return ConversionError("This file is password-protected. Remove the password in Office first.")
    if "corrupt" in low or "damaged" in low or "cannot be opened" in low or "can't open" in low:
        return ConversionError(f"{name} couldn't open this file; it may be damaged.")
    m = re.search(r"'([^']{8,300})'", text)
    detail = m.group(1) if m else text[:200]
    return ConversionError(f"{name} reported a problem: {detail}")


# ------------------------------------------------------------------ text checks

_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return _WORD.findall(text)


def text_coverage(source_text: str, output_text: str, sample: int = 400) -> float | None:
    """Share of the source's distinct words that appear in the output.
    None when the source has too little text to judge."""
    src = list(dict.fromkeys(words(source_text)))
    if len(src) < 5:
        return None
    if len(src) > sample:
        step = len(src) / sample
        src = [src[int(i * step)] for i in range(sample)]
    out = set(words(output_text))
    return sum(1 for w in src if w in out) / len(src)
