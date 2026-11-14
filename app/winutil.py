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
RUN_NAME = "Deskvert"


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


def single_instance(name: str = "Local\\Deskvert.SingleInstance", wait_seconds: float = 0.0):
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


SHOW_EVENT = "Local\\Deskvert.Show"


def _signal(name: str) -> bool:
    kernel32.OpenEventW.restype = ctypes.c_void_p
    h = kernel32.OpenEventW(0x0002, False, name)  # EVENT_MODIFY_STATE
    if not h:
        return False
    kernel32.SetEvent(ctypes.c_void_p(h))
    kernel32.CloseHandle(ctypes.c_void_p(h))
    return True


def _watch(name: str, callback) -> None:
    """Call ``callback`` (from a background thread) each time the named event is set.
    Waiting on a Windows event uses no CPU."""
    import threading

    kernel32.CreateEventW.restype = ctypes.c_void_p
    h = kernel32.CreateEventW(None, False, False, name)  # auto-reset
    if not h:
        return

    def run():
        while kernel32.WaitForSingleObject(ctypes.c_void_p(h), 0xFFFFFFFF) == 0:
            try:
                callback()
            except Exception:
                pass

    threading.Thread(target=run, name=f"watch {name}", daemon=True).start()


def signal_running_instance() -> bool:
    """Ask the Deskvert that's already running to show its window (used when it's started twice)."""
    return _signal(SHOW_EVENT)


def watch_show_requests(callback) -> None:
    _watch(SHOW_EVENT, callback)


# ---------------------------------------------------------------- right-click "Convert with Deskvert"

PICK_EVENT = "Local\\Deskvert.Pick"
MENU_KEY = r"Software\Classes\*\shell\Deskvert"
FOLDER_MENU_KEY = r"Software\Classes\Directory\shell\Deskvert"


def ctrl_shift_switches_layout() -> bool:
    """True when tapping Ctrl+Shift already means "next keyboard layout" on this PC (so it's a poor
    shortcut for Deskvert here). That needs two or more layouts and Windows set to switch with it."""
    try:
        import winreg

        user32 = ctypes.windll.user32
        n = user32.GetKeyboardLayoutList(0, None)
        if n < 2:
            return False
        buf = (ctypes.c_void_p * n)()
        user32.GetKeyboardLayoutList(n, buf)
        languages = {(h or 0) & 0xFFFF for h in buf}
        keys = {}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Keyboard Layout\Toggle") as k:
                for name in ("Hotkey", "Language Hotkey", "Layout Hotkey"):
                    try:
                        keys[name] = str(winreg.QueryValueEx(k, name)[0])
                    except OSError:
                        pass
        except OSError:
            pass
        # Windows' defaults: Alt+Shift ("1") between languages, Ctrl+Shift ("2") between layouts of one language.
        language_key = keys.get("Language Hotkey", keys.get("Hotkey", "1"))
        layout_key = keys.get("Layout Hotkey", "2")
        if language_key == "2" and len(languages) > 1:
            return True
        return layout_key == "2" and len(languages) < n
    except Exception:  # noqa: BLE001 - a guess that fails is just "no"
        return False


def sendto_link() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "Microsoft" / "Windows" / "SendTo" / "Deskvert.lnk"


def set_sendto(enabled: bool, link: Path | None = None) -> None:
    """Add (or remove) Deskvert in the right-click "Send to" menu. Unlike our own menu entry, Send to
    is on Windows 11's short menu, and it hands over every selected file or folder at once."""
    link = link or sendto_link()
    if not enabled:
        try:
            link.unlink()
        except OSError:
            pass
        return
    import win32com.client

    link.parent.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):
        target, args = sys.executable, "--pick"
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        script = Path(__file__).resolve().parent.parent / "run.pyw"
        target, args = str(pythonw if pythonw.exists() else sys.executable), f'"{script}" --pick'
    sc = win32com.client.Dispatch("WScript.Shell").CreateShortCut(str(link))
    sc.Targetpath = target
    sc.Arguments = args
    sc.Description = "Convert with Deskvert"
    if getattr(sys, "frozen", False):
        sc.IconLocation = f"{sys.executable},0"
    sc.save()


def pick_spool() -> Path:
    from .paths import _dir

    return _dir("LOCALAPPDATA", "pick")


def send_pick(paths: list[str]) -> bool:
    """Hand files from a right-click to the running Deskvert. Explorer starts one copy per
    selected file; each drops its file here and the running app gathers them into one picker."""
    import uuid

    spool = pick_spool()
    (spool / f"{uuid.uuid4().hex}.txt").write_text("\n".join(paths), encoding="utf-8")
    return _signal(PICK_EVENT)


def take_picks() -> list[str]:
    paths: list[str] = []
    for f in sorted(pick_spool().glob("*.txt"), key=lambda q: q.stat().st_mtime):
        try:
            paths += [line for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
            f.unlink()
        except OSError:
            pass
    seen, out = set(), []
    for p in paths:
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def watch_picks(callback) -> None:
    _watch(PICK_EVENT, callback)


def context_menu_enabled() -> bool:
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEY))
        return True
    except OSError:
        return False


def set_context_menu(enabled: bool) -> None:
    """Add (or remove) "Convert with Deskvert" to the right-click menu of every file.
    Per user, no admin rights. On Windows 11 it's under "Show more options"."""
    import winreg

    try:
        set_sendto(enabled)
    except Exception:  # noqa: BLE001 - the menu entry still works without it
        pass
    if not enabled:
        for key in (MENU_KEY, FOLDER_MENU_KEY):
            for sub in (key + r"\command", key):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                except OSError:
                    pass
        return
    exe = sys.executable if getattr(sys, "frozen", False) else str(Path(sys.executable).with_name("pythonw.exe"))
    for key in (MENU_KEY, FOLDER_MENU_KEY):  # files, and folders (everything inside them)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "Convert with Deskvert")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, f'"{exe}",0')
            winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Player")  # many at once
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, launch_command('--pick "%1"'))


# ---------------------------------------------------------------- recycle bin

def recycle(paths: list[str]) -> int:
    """Move files or folders to the Recycle Bin (they can be restored). Returns how many were moved."""
    from win32com.shell import shell, shellcon

    existing = [str(Path(p)) for p in paths if os.path.exists(p)]
    if not existing:
        return 0
    flags = shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION | shellcon.FOF_SILENT | shellcon.FOF_NOERRORUI
    res, aborted = shell.SHFileOperation((0, shellcon.FO_DELETE, "\0".join(existing), None, flags, None, None))
    if res != 0 or aborted:
        raise OSError(f"the Recycle Bin refused the files (code {res})")
    return sum(1 for p in existing if not os.path.exists(p))


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


# ---------------------------------------------------------------- moving over from the old name
OLD_NAME = "Tapshift"  # Deskvert's name until 1.14


def _delete_tree(root, path: str) -> bool:
    """Delete a registry key and everything under it (False if it wasn't there)."""
    import winreg

    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, path + "\\" + sub)
        winreg.DeleteKey(root, path)
        return True
    except OSError:
        return False


def move_from_old_name() -> dict:
    """Tapshift became Deskvert: take over its start-up entry, and remove its right-click and Send to
    entries (Deskvert adds its own). Returns what was found, e.g. {"autostart": True}."""
    import winreg

    found = {"autostart": False, "menu": False, "sendto": False}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            try:
                winreg.QueryValueEx(k, OLD_NAME)
                found["autostart"] = True
                winreg.DeleteValue(k, OLD_NAME)
            except OSError:
                pass
    except OSError:
        pass
    if found["autostart"]:
        try:
            set_autostart(True)  # it started with Windows before the rename: it still does
        except OSError:
            pass
    for key in (r"Software\Classes\*\shell" + "\\" + OLD_NAME, r"Software\Classes\Directory\shell" + "\\" + OLD_NAME):
        found["menu"] |= _delete_tree(winreg.HKEY_CURRENT_USER, key)
    old_link = sendto_link().with_name(OLD_NAME + ".lnk")
    if old_link.exists():
        try:
            old_link.unlink()
            found["sendto"] = True
        except OSError:
            pass
    return found


def is_fullscreen(hwnd: int) -> bool:
    """A window covering its whole screen (a game, a video player, a slideshow): Deskvert stays out of its way."""
    try:
        import win32api
        import win32con
        import win32gui

        if not hwnd or not win32gui.IsWindowVisible(hwnd):
            return False
        if win32gui.GetClassName(hwnd) in ("Progman", "WorkerW", "Shell_TrayWnd"):  # the desktop and taskbar
            return False
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        mon = win32api.GetMonitorInfo(win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST))
        m_left, m_top, m_right, m_bottom = mon["Monitor"]
        return left <= m_left and top <= m_top and right >= m_right and bottom >= m_bottom
    except Exception:  # noqa: BLE001 - can't tell: behave as usual
        return False


INSTALLER_ID = "{6D3B7E2A-4C1F-4B8E-9A57-2F1C0D9E7A31}_is1"  # installer/deskvert.iss AppId, as Windows records it


def _registered_uninstaller(app_dir: Path) -> Path | None:
    """The uninstaller Windows has on record for Deskvert, when it was installed into ``app_dir``."""
    import winreg

    key = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{INSTALLER_ID}"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, key) as k:
                where = str(winreg.QueryValueEx(k, "InstallLocation")[0])
                command = str(winreg.QueryValueEx(k, "UninstallString")[0])
        except OSError:
            continue
        if where and os.path.normcase(os.path.normpath(where)) == os.path.normcase(os.path.normpath(str(app_dir))):
            exe = Path(command.strip().strip('"'))
            if exe.exists():
                return exe
    return None


def uninstaller() -> Path | None:
    """The installer's uninstaller, when Deskvert was installed with Setup
    (the portable zip and the source version have none): the file next to Deskvert.exe, or the one Windows has
    on record for this folder."""
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).with_name("unins000.exe")
    if exe.exists():
        return exe
    try:
        return _registered_uninstaller(Path(sys.executable).parent)
    except Exception:  # noqa: BLE001 - no record to read: not an installed copy
        return None


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
