"""Small Windows helpers: focus, memory trimming, start-with-Windows, Explorer."""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Tapshift"


def force_foreground(hwnd: int) -> None:
    """Bring our popup to the front and give it keyboard focus. Windows only
    lets the foreground thread do this, so we briefly share its input queue."""
    fg = user32.GetForegroundWindow()
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != me and user32.AttachThreadInput(other, me, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(other, me, False)
    if user32.GetForegroundWindow() != hwnd:
        # Windows refused. Sending one input event (an unassigned key that no
        # app reacts to) makes us the "last input" process, which is allowed
        # to take focus. Then try again.
        VK_UNASSIGNED, KEYUP = 0xE8, 0x2
        user32.keybd_event(VK_UNASSIGNED, 0, 0, 0)
        user32.keybd_event(VK_UNASSIGNED, 0, KEYUP, 0)
        user32.SetForegroundWindow(hwnd)


def mouse_button_down() -> bool:
    for b in (0x01, 0x02, 0x04):
        if user32.GetAsyncKeyState(b) & 0x8000:
            return True
    return False


def trim_memory() -> None:
    """Return unused memory pages to Windows while the app sits idle."""
    try:
        ctypes.windll.psapi.EmptyWorkingSet(kernel32.GetCurrentProcess())
    except Exception:
        pass


def single_instance(name: str = "Local\\Tapshift.SingleInstance", wait_seconds: float = 0.0):
    """Returns a handle if we're the only instance, else None. With
    ``wait_seconds`` (used when restarting), waits for the old copy to exit."""
    import time

    deadline = time.monotonic() + wait_seconds
    while True:
        handle = kernel32.CreateMutexW(None, False, name)
        if kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
            return handle
        kernel32.CloseHandle(handle)
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.2)


def launch_command(extra: str = "") -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {extra}'.strip()
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    script = Path(__file__).resolve().parent.parent / "run.pyw"
    return f'"{pythonw if pythonw.exists() else exe}" "{script}" {extra}'.strip()


def autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass


def uninstaller() -> Path | None:
    """The installer's uninstaller, when Tapshift was installed with Setup
    (the portable zip and the source version have none)."""
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).with_name("unins000.exe")
    return exe if exe.exists() else None


def start_uninstall() -> bool:
    """Start the uninstaller (it asks for confirmation first). The caller
    should quit right after, so the files can be removed."""
    exe = uninstaller()
    if exe is None:
        return False
    subprocess.Popen([str(exe)], close_fds=True, creationflags=0x00000008)  # DETACHED_PROCESS
    return True


def show_in_explorer(path: str | Path) -> None:
    p = Path(path)
    if p.exists():
        subprocess.Popen(["explorer.exe", "/select,", str(p)])
    elif p.parent.exists():
        os.startfile(str(p.parent))
