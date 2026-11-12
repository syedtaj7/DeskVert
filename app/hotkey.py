"""System-wide shortcut.

Two kinds:
- "Ctrl+Shift" (the default): a *tap* of Ctrl and Shift together, detected with
  Windows Raw Input. Raw Input only reads keyboard events (it never blocks or
  delays them, unlike a keyboard hook) and costs nothing while you type.
- Any other combination, e.g. "Ctrl+Shift+Space": registered with Windows'
  RegisterHotKey, so Windows itself watches for it.

And one gesture: Ctrl+Shift held while dragging something (a picture in a browser,
a file...) calls ``on_drag``, so a drop target can appear under the pointer.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT, "alt": MOD_ALT, "win": MOD_WIN}
_KEYS = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "insert": 0x2D, "delete": 0x2E, "home": 0x24,
    "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "pause": 0x13, "`": 0xC0, "-": 0xBD,
    "=": 0xBB, "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC,
}


def parse(combo: str) -> tuple[int, int]:
    """'Ctrl+Shift+Space' -> (modifiers, virtual key)."""
    mods, vk = 0, None
    for part in [p.strip().lower() for p in combo.split("+") if p.strip()]:
        if part in _MODS:
            mods |= _MODS[part]
        elif part in _KEYS:
            vk = _KEYS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            vk = 0x70 + int(part[1:]) - 1
        else:
            raise ValueError(f"Unknown key '{part}' in hotkey '{combo}'")
    if vk is None or not mods:
        raise ValueError(f"Hotkey '{combo}' needs at least one modifier and one key")
    return mods, vk


VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x11, 0x12, 0x5B, 0x5C
VK_LBUTTON, VK_RBUTTON, VK_MBUTTON, VK_XBUTTON1, VK_XBUTTON2 = 0x01, 0x02, 0x04, 0x05, 0x06


def is_modifier_tap(combo: str) -> bool:
    parts = {p.strip().lower() for p in combo.split("+") if p.strip()}
    return parts == {"ctrl", "shift"} or parts == {"control", "shift"}


class TapDetector:
    """Decides when a Ctrl+Shift *tap* happened.

    Fires on release, only if both keys were down together, nothing else was
    pressed in between (no other key, no mouse click) and the hold was short.
    Pure logic, no Windows calls, so it can be unit-tested.
    """

    MAX_HOLD = 1.2  # seconds

    def __init__(self):
        self.ctrl = self.shift = False
        self.active = False  # both were down together
        self.dirty: bool | str = False  # falsy = clean; a string says why the tap was spoiled
        self.t_both = 0.0
        self.last_reject: str | bool | None = None

    def key(self, vk: int, down: bool, now: float) -> bool:
        """Feed one key event. Returns True when the tap is complete."""
        if vk in (VK_CONTROL, VK_SHIFT):
            if vk == VK_CONTROL:
                self.ctrl = down
            else:
                self.shift = down
            if down and self.ctrl and self.shift and not self.active:
                self.active, self.dirty, self.t_both = True, False, now
            if not down and self.active and not self.ctrl and not self.shift:
                held = now - self.t_both
                fire = not self.dirty and held <= self.MAX_HOLD
                if not fire:
                    self.last_reject = self.dirty or f"held {held:.1f}s (limit {self.MAX_HOLD}s)"
                self.active = False
                return fire
            return False
        if down and (self.ctrl or self.shift):
            if self.active and not self.dirty:
                self.dirty = f"another key (code {vk:#x}) was pressed"
            elif not self.active:
                self.dirty = self.dirty or True
        return False

    def mouse_pressed(self) -> None:
        if self.active and not self.dirty:
            self.dirty = "a mouse button was pressed"  # Ctrl+Shift+click (e.g. range-select in Explorer)


class DragGesture:
    """Decides when "Ctrl+Shift held during a drag" happened. Pure logic, unit-tested.

    - Already dragging, then Ctrl+Shift: fires as soon as both keys are down.
    - Ctrl+Shift held first, then the mouse goes down: fires once the pointer has moved a little,
      so a plain Ctrl+Shift+click (range-select in Explorer) never counts.
    Fires once per hold."""

    MOVE_PX = 10

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.armed_with_button = None  # was the button already down when both keys went down?
        self.press_at: tuple[int, int] | None = None
        self.fired = False

    def update(self, keys_held: bool, button: bool, pos: tuple[int, int]) -> bool:
        if not keys_held:
            self.reset()
            return False
        if self.armed_with_button is None:
            self.armed_with_button = button
            if button:  # a drag was already going when Ctrl+Shift went down
                self.fired = True
                return True
        if self.fired:
            return False
        if not button:
            self.press_at = None
            return False
        if self.press_at is None:
            self.press_at = pos
            return False
        if abs(pos[0] - self.press_at[0]) + abs(pos[1] - self.press_at[1]) >= self.MOVE_PX:
            self.fired = True
            return True
        return False


class ModifierTapListener:
    """Watches the keyboard with Windows Raw Input (read-only: keystrokes are
    never blocked or delayed, unlike a keyboard hook) and calls
    ``on_press(foreground_hwnd)`` when Ctrl+Shift is tapped (if given), and
    ``on_drag()`` when Ctrl+Shift is held during a drag (if given)."""

    def __init__(self, on_press: Callable[[int], None] | None, on_drag: Callable[[], None] | None = None):
        self.on_press = on_press
        self.on_drag = on_drag
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._ready = threading.Event()
        self.error: str | None = None
        self._wndproc = None  # keep the callback alive
        self.hwnd = 0
        self.handled = 0  # messages this listener's own window procedure has seen (for tests)

    def start(self) -> bool:
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="hotkey-tap", daemon=True)
        self._thread.start()
        self._ready.wait(2)
        return self.error is None

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = None

    def _run(self) -> None:
        import time

        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        WM_INPUT, WM_TIMER, RID_INPUT, RI_KEY_BREAK = 0x00FF, 0x0113, 0x10000003, 0x1
        RIDEV_INPUTSINK, HWND_MESSAGE = 0x100, wintypes.HWND(-3)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                        ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]

        class RAWINPUTDEVICE(ctypes.Structure):
            _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                        ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]

        class RAWINPUTHEADER(ctypes.Structure):
            _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                        ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]

        class RAWKEYBOARD(ctypes.Structure):
            _fields_ = [("MakeCode", wintypes.USHORT), ("Flags", wintypes.USHORT), ("Reserved", wintypes.USHORT),
                        ("VKey", wintypes.USHORT), ("Message", wintypes.UINT), ("ExtraInformation", wintypes.ULONG)]

        class RAWINPUT(ctypes.Structure):
            _fields_ = [("header", RAWINPUTHEADER), ("keyboard", RAWKEYBOARD)]

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                           ctypes.POINTER(wintypes.UINT), wintypes.UINT]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                           wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
        user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        user32.GetAsyncKeyState.restype = ctypes.c_short

        det = TapDetector()
        gesture = DragGesture()
        pt = wintypes.POINT()
        buf = RAWINPUT()
        size = wintypes.UINT(ctypes.sizeof(RAWINPUT))
        hdr = ctypes.sizeof(RAWINPUTHEADER)
        state = {"timer": False}

        def tick():
            """While Ctrl+Shift are held: mouse buttons spoil a tap; a drag shows the drop target."""
            left = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            for b in (VK_LBUTTON, VK_RBUTTON, VK_MBUTTON, VK_XBUTTON1, VK_XBUTTON2):
                if user32.GetAsyncKeyState(b) & 0x8000:
                    det.mouse_pressed()
            if self.on_drag is not None:
                user32.GetCursorPos(ctypes.byref(pt))
                if gesture.update(det.ctrl and det.shift, left, (pt.x, pt.y)):
                    self.on_drag()

        def wndproc(hwnd, msg, wparam, lparam):
            self.handled += 1
            try:
                if msg == WM_INPUT:
                    size.value = ctypes.sizeof(RAWINPUT)
                    if user32.GetRawInputData(wintypes.HANDLE(lparam), RID_INPUT, ctypes.byref(buf),
                                              ctypes.byref(size), hdr) > 0 and buf.header.dwType == 1:
                        vk = buf.keyboard.VKey
                        if vk and vk != 0xFF:
                            down = not (buf.keyboard.Flags & RI_KEY_BREAK)
                            det.last_reject = None
                            fired = det.key(vk, down, time.monotonic())
                            if det.last_reject:
                                log.info("Ctrl+Shift tap ignored: %s", det.last_reject)
                            # While Ctrl+Shift are held, watch the mouse buttons (stops when released).
                            if det.active and not state["timer"]:
                                user32.SetTimer(hwnd, 1, 15, None)
                                state["timer"] = True
                            elif not det.active and state["timer"]:
                                user32.KillTimer(hwnd, 1)
                                state["timer"] = False
                            if fired and self.on_press is not None:
                                self.on_press(user32.GetForegroundWindow())
                            if det.active and self.on_drag is not None:
                                tick()  # at once: a drag may already be going
                elif msg == WM_TIMER:
                    tick()
                    if not det.active:
                        user32.KillTimer(hwnd, 1)
                        state["timer"] = False
                    return 0
            except Exception:
                log.exception("tap listener error")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(wndproc)
        self._tid = kernel32.GetCurrentThreadId()
        hinst = kernel32.GetModuleHandleW(None)
        cls = WNDCLASSEXW()
        cls.cbSize = ctypes.sizeof(WNDCLASSEXW)
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = hinst
        # A class name of its own: when the listener restarts (new shortcut, end of the welcome tour),
        # reusing one name made Windows keep the old, freed window procedure, so taps stopped after one.
        cls.lpszClassName = f"TapshiftTapListener-{id(self):x}-{self._tid:x}"
        if not user32.RegisterClassExW(ctypes.byref(cls)):
            self.error = "Couldn't start the Ctrl+Shift listener."
            self._ready.set()
            return
        hwnd = user32.CreateWindowExW(0, cls.lpszClassName, "", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinst, None)
        self.hwnd = hwnd or 0
        dev = RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd)  # generic desktop / keyboard
        if not hwnd or not user32.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev)):
            self.error = "Couldn't start the Ctrl+Shift listener."
            if hwnd:
                user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(cls.lpszClassName, hinst)
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW(cls.lpszClassName, hinst)


class HotkeyListener:
    """A regular combination (e.g. Ctrl+Shift+Space) through RegisterHotKey.
    ``on_press(foreground_hwnd)`` is called from the listener thread, so it
    should only hand off to the UI thread (e.g. emit a Qt signal)."""

    def __init__(self, combo: str, on_press: Callable[[int], None]):
        self.combo = combo
        self.on_press = on_press
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._ready = threading.Event()
        self.error: str | None = None

    def start(self) -> bool:
        mods, vk = parse(self.combo)
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, args=(mods, vk), name="hotkey", daemon=True)
        self._thread.start()
        self._ready.wait(2)
        return self.error is None

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = None

    def _run(self, mods: int, vk: int) -> None:
        self._tid = kernel32.GetCurrentThreadId()
        self.error = None
        if not user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk):
            self.error = f"{self.combo} is already used by another app."
            log.warning("RegisterHotKey failed for %s", self.combo)
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.on_press(user32.GetForegroundWindow())
                    except Exception:
                        log.exception("hotkey handler failed")
        finally:
            user32.UnregisterHotKey(None, 1)


def make_listener(combo: str, on_press: Callable[[int], None], on_drag: Callable[[], None] | None = None):
    """Ctrl+Shift alone -> tap listener (which also watches for the drag gesture); anything else ->
    RegisterHotKey. Windows gives raw keyboard input to one window per app, so there must never be
    two raw-input listeners: with a combo, make_drag_listener is the only one."""
    if is_modifier_tap(combo):
        return ModifierTapListener(on_press, on_drag)
    return HotkeyListener(combo, on_press)


def make_drag_listener(on_drag: Callable[[], None]) -> ModifierTapListener:
    """Ctrl+Shift held during a drag, for any shortcut setting (it never fires a tap)."""
    return ModifierTapListener(None, on_drag)
