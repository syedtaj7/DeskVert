"""Tray app: wires the shortcut, the selection reader, the popup, the progress
panel, the job runner, and the welcome tour / guide / settings windows."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, selection, winutil
from .catalog import describe_selection, explain_unsupported, office_installed, offers_for, pick_group
from .hotkey import is_modifier_tap, make_listener
from .jobs import Batch, JobManager, clean_stale_workdirs
from .paths import APP_NAME, documents_dir, log_dir
from .settings import Settings
from .ui import theme
from .ui.panels import Notice, ProgressPanel
from .ui.popup import Popup

log = logging.getLogger("tapshift")


def setup_logging() -> None:
    handler = RotatingFileHandler(log_dir() / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def pretty_hotkey(combo: str) -> str:
    return " + ".join(p.strip().capitalize() if len(p.strip()) > 1 else p.strip().upper()
                      for p in combo.split("+") if p.strip())


def _alive(w) -> bool:
    try:
        import shiboken6

        return w is not None and shiboken6.isValid(w) and w.isVisible()
    except Exception:
        return False


class Controller(QObject):
    hotkey_pressed = Signal(int)

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = Settings.load()
        self.popup: Popup | None = None
        self.notice: Notice | None = None
        self.windows: dict[str, object] = {}
        self.paused = False
        self.recent: list[str] = []
        self._last_output: str | None = None
        self._label = ""
        self.hotkey = None

        self.jobs = JobManager(self.settings)
        self.jobs.started.connect(self._on_started)
        self.jobs.file_started.connect(self._on_file_started)
        self.jobs.progress.connect(lambda *_: self._poll_progress())
        self.jobs.finished.connect(self._on_finished)

        self.panel = ProgressPanel()
        self.panel.cancel_requested.connect(self.jobs.cancel)
        self.panel.show_folder.connect(winutil.show_in_explorer)

        self.tray = QSystemTrayIcon(theme.app_icon(), self)
        self.tray.activated.connect(self._tray_activated)
        self._build_menu()
        self.tray.show()

        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(300)
        self.progress_timer.timeout.connect(self._poll_progress)

        self.hotkey_pressed.connect(self.on_hotkey)
        if winutil.autostart_enabled():
            try:
                winutil.set_autostart(True)  # keep the start-up entry pointing at this copy (e.g. after installing)
            except OSError:
                pass
        ok, err = self._start_hotkey()
        if not self.settings.onboarded:
            QTimer.singleShot(700, self.show_tour)
        elif ok:
            how = "tap" if is_modifier_tap(self.settings.hotkey) else "press"
            self.panel.message("info", f"{APP_NAME} is running",
                               f"Select files in File Explorer and {how} {self.key_label}.", 4000)
        if not ok:
            self.panel.message("error", "The shortcut couldn't be started",
                               f"{err} Choose another shortcut in Settings.", 12000)
        QTimer.singleShot(6000, winutil.trim_memory)

    @property
    def key_label(self) -> str:
        return pretty_hotkey(self.settings.hotkey)

    # ------------------------------------------------------------ shortcut
    def _start_hotkey(self) -> tuple[bool, str | None]:
        if self.hotkey is not None:
            self.hotkey.stop()
        try:
            self.hotkey = make_listener(self.settings.hotkey, self.hotkey_pressed.emit)
            ok = self.hotkey.start()
            err = self.hotkey.error
        except ValueError as e:
            ok, err = False, str(e)
        self.tray.setToolTip(f"{APP_NAME} - {'tap' if is_modifier_tap(self.settings.hotkey) else 'press'} "
                             f"{self.key_label}")
        if hasattr(self, "head_action"):
            self.head_action.setText(f"{APP_NAME} {__version__}  ·  {self.key_label}")
        return ok, err

    # ------------------------------------------------------------ tray menu
    def _build_menu(self) -> None:
        m = QMenu()
        m.setStyleSheet(theme.MENU_QSS)
        self.head_action = QAction(f"{APP_NAME} {__version__}  ·  {self.key_label}", m)
        self.head_action.setEnabled(False)
        m.addAction(self.head_action)
        self.status_action = QAction("Idle", m)
        self.status_action.setEnabled(False)
        m.addAction(self.status_action)
        m.addSeparator()
        self.recent_menu = m.addMenu("Recent conversions")
        self.recent_menu.setStyleSheet(theme.MENU_QSS)
        self._refresh_recent()
        self.cancel_action = m.addAction("Cancel conversions", self.jobs.cancel)
        self.cancel_action.setEnabled(False)
        m.addSeparator()
        m.addAction("How to use Tapshift", self.show_guide)
        m.addAction("Settings", lambda: self.show_settings(0))
        m.addAction("Welcome tour", self.show_tour)
        m.addSeparator()
        self.pause_action = m.addAction("Pause shortcut")
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(lambda v: setattr(self, "paused", v))
        m.addAction("About Tapshift", lambda: self.show_settings(4))
        if winutil.uninstaller() is not None:
            m.addAction("Uninstall Tapshift\u2026", self.uninstall)
        m.addAction("Quit", self.quit)
        self.menu = m
        self.tray.setContextMenu(m)

    def _refresh_recent(self) -> None:
        self.recent_menu.clear()
        if not self.recent:
            a = self.recent_menu.addAction("Nothing yet")
            a.setEnabled(False)
        for path in self.recent[:10]:
            self.recent_menu.addAction(Path(path).name, lambda p=path: winutil.show_in_explorer(p))

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._last_output:
                winutil.show_in_explorer(self._last_output)
            else:
                self.show_guide()

    # ------------------------------------------------------------ windows
    def _window(self, key: str, factory):
        w = self.windows.get(key)
        if _alive(w):
            w.raise_()
            w.activateWindow()
            return None
        w = factory()
        self.windows[key] = w
        w.closed.connect(lambda: (self.windows.pop(key, None), QTimer.singleShot(1500, winutil.trim_memory)))
        return w

    def show_tour(self) -> None:
        from .ui.onboarding import TourWindow

        choices = {"autostart": True if not self.settings.onboarded else winutil.autostart_enabled(),
                   "theme": self.settings.theme, "cpu": self.settings.max_cpu_percent, "hotkey": self.settings.hotkey}
        office = {k: office_installed(k) for k in ("word", "excel", "powerpoint")}
        w = self._window("tour", lambda: TourWindow(choices, office))
        if w is None:
            return
        w.finished.connect(self._tour_finished)
        w.try_samples.connect(self.try_samples)
        w.present()

    def _tour_finished(self, choices: dict) -> None:
        first = not self.settings.onboarded
        self.settings.onboarded = True
        self._apply("autostart", choices["autostart"], save=False)
        self._apply("max_cpu_percent", int(choices["cpu"]), save=False)
        self._apply("hotkey", choices["hotkey"], save=False)
        theme_changed = choices["theme"] != self.settings.theme
        self.settings.theme = choices["theme"]
        self.settings.save()
        if theme_changed:
            QTimer.singleShot(400, self.restart)
        elif first:
            how = "Tap" if is_modifier_tap(self.settings.hotkey) else "Press"
            self.panel.message("success", "Tapshift is ready",
                               f"{how} {self.key_label} with a file selected in File Explorer.", 5000)

    def show_guide(self) -> None:
        from .ui.guide import GuideWindow

        w = self._window("guide", GuideWindow)
        if w is not None:
            w.present()

    def show_settings(self, section: int = 0) -> None:
        from .ui.settings_ui import SettingsWindow

        existing = self.windows.get("settings")
        if _alive(existing):
            existing.nav.select(section)
            existing.raise_()
            existing.activateWindow()
            return
        w = self._window("settings", lambda: SettingsWindow(self.settings, winutil.autostart_enabled()))
        if w is None:
            return
        w.changed.connect(self._apply)
        w.show_tour.connect(self.show_tour)
        w.open_logs.connect(lambda: os.startfile(str(log_dir())))
        w.uninstall.connect(self.uninstall)
        w.present(section)

    def _apply(self, key: str, value, save: bool = True) -> None:
        """Apply one setting change right away."""
        if key == "autostart":
            try:
                winutil.set_autostart(bool(value))
            except OSError:
                log.exception("couldn't change start-with-Windows")
            return
        if key in ("theme", "palette"):
            setattr(self.settings, key, value)
            self.settings.save()
            self.panel.message("info", "Appearance saved", "The new look applies the next time Tapshift starts.", 4500)
            return
        setattr(self.settings, key, value)
        if save:
            self.settings.save()
        if key == "hotkey":
            ok, err = self._start_hotkey()
            if not ok:
                self.panel.message("error", "That shortcut couldn't be used", str(err), 8000)
        if key == "max_cpu_percent" and not self.jobs.busy:
            self.jobs.reset_pool()  # the next conversion starts with the new limit

    def try_samples(self) -> None:
        folder = make_samples(documents_dir() / "Tapshift Samples")
        winutil.show_in_explorer(folder / "Sunset.png")
        how = "tap" if is_modifier_tap(self.settings.hotkey) else "press"
        self.panel.message("info", "Try it now",
                           f"Sunset.png is selected in the folder that just opened: {how} {self.key_label}.", 9000)

    def restart(self) -> None:
        self.quit(restart_cmd=winutil.launch_command("--restarted"))

    # ------------------------------------------------------------ hotkey
    def _show_notice(self, title: str, message: str, kind: str = "warning") -> None:
        if _alive(self.notice):
            self.notice.close()
        self.notice = Notice(title, message, kind)
        self.notice.show_near_cursor()

    def on_hotkey(self, hwnd: int) -> None:
        if self.paused:
            return
        if _alive(self.popup):
            self.popup.close()  # pressing the shortcut again closes the popup
            self.popup = None
            return
        self.popup = None
        try:
            files, where = selection.selected_files(hwnd, self.settings.use_clipboard_fallback)
        except Exception:
            log.exception("reading selection failed")
            files, where = [], ""
        cls = selection._class_name(hwnd)
        log.info("hotkey: window=%s files=%d source=%s", cls, len(files), where or "-")
        if not files:
            if cls not in selection.EXPLORER_CLASSES | selection.DESKTOP_CLASSES:
                return  # tapped in another app (e.g. switching keyboard layout): stay quiet
            how = "tap" if is_modifier_tap(self.settings.hotkey) else "press"
            self._show_notice("No file selected",
                              f"Select one or more files in File Explorer or on the Desktop, then {how} "
                              f"{self.key_label}.", "info")
            return
        offers, left_out = offers_for(files, self.settings)
        kind, group, _ = pick_group(files)
        if not offers:
            title, msg = explain_unsupported(left_out or files)
            self._show_notice(title, msg)
            return
        notes = []
        if where == "clipboard":
            notes.append("From files copied to the clipboard.")
        if kind is None:
            # Nothing to convert, but the files can still be zipped: say why ZIP is the only choice.
            group = files
            notes.append(explain_unsupported(files)[1].split(". Tapshift")[0] + ". You can still zip it.")
        elif left_out:
            notes.append(f"{len(left_out)} other file(s) aren't included (different type); ZIP includes everything.")
        center = f"1 {group[0].suffix.upper().lstrip('.') or 'file'}" if len(group) == 1 else f"{len(group)} files"
        self.popup = Popup(describe_selection(group), center, " ".join(notes), offers,
                           estimator=self.jobs.estimate)
        self.popup.chosen.connect(self.jobs.submit)
        self.popup.destroyed.connect(self._popup_closed)
        self.popup.show_at_cursor()

    def _popup_closed(self, *_):
        self.popup = None
        QTimer.singleShot(1500, winutil.trim_memory)

    # ------------------------------------------------------------ job events
    def _on_started(self, label: str, total: int) -> None:
        self._label = label
        self.tray.setIcon(theme.app_icon(busy=True))
        self.status_action.setText(f"Converting to {label}...")
        self.cancel_action.setEnabled(True)
        self.panel.start(label, total)
        self.progress_timer.start()

    def _on_file_started(self, name: str, index: int, total: int) -> None:
        self.panel.set_file(name, index, total)

    def _poll_progress(self) -> None:
        frac = self.jobs.fraction_done()
        if frac is None:
            return
        self.panel.set_progress(frac)
        self.status_action.setText(f"Converting to {self._label}: {frac * 100:.0f}%")

    def _on_finished(self, batch: Batch) -> None:
        busy = self.jobs.busy
        self.tray.setIcon(theme.app_icon(busy=busy))
        self.cancel_action.setEnabled(busy)
        if not busy:
            self.progress_timer.stop()
            self.status_action.setText("Idle")
        ok = [r for r in batch.results if r.get("ok")]
        failed = [r for r in batch.results if not r.get("ok") and not r.get("cancelled")]
        cancelled = [r for r in batch.results if r.get("cancelled")]
        for r in ok:
            self.recent.insert(0, r["output"])
        self.recent = self.recent[:10]
        self._refresh_recent()
        if ok:
            self._last_output = ok[0]["output"]
        first_out = ok[0]["output"] if ok else ""

        if cancelled and not ok and not failed:
            self.panel.finish("info", "Conversion cancelled", "Nothing was saved, and your files are unchanged.")
        elif len(batch.results) == 1 and ok:
            r = ok[0]
            body = "  ".join(r.get("notes", [])[:2]) or "Checked against the original: everything matches."
            self.panel.finish("success", f"Saved {Path(r['output']).name}", body, first_out)
        elif len(batch.results) == 1 and failed:
            r = failed[0]
            self.panel.finish("error", f"Couldn't convert {Path(r['sources'][0]).name}",
                              r.get("error", "Unknown error") + " Your original file is unchanged.")
        else:
            title = f"Converted {len(ok)} file{'s' if len(ok) != 1 else ''} to {batch.label}"
            lines = []
            if failed:
                title += f", {len(failed)} failed"
                lines.append(f"{Path(failed[0]['sources'][0]).name}: {failed[0].get('error')}")
            if cancelled:
                lines.append(f"{len(cancelled)} cancelled.")
            if batch.skipped_same:
                lines.append(f"{batch.skipped_same} already in that format, skipped.")
            if not lines:
                lines.append("All checked against the originals.")
            self.panel.finish("error" if failed and not ok else ("warning" if failed else "success"),
                              title, "\n".join(lines), first_out)
        QTimer.singleShot(3000, winutil.trim_memory)

    # ------------------------------------------------------------ exit
    def uninstall(self) -> None:
        """Hand over to the uninstaller (it asks "remove Tapshift?" first) and quit,
        so Tapshift's files aren't in use."""
        if winutil.start_uninstall():
            self.quit()

    def quit(self, restart_cmd: str | None = None) -> None:
        if self.hotkey is not None:
            self.hotkey.stop()
        self.jobs.shutdown()
        self.tray.hide()
        if restart_cmd:
            os.environ.pop("TAPSHIFT_THEME", None)
            subprocess.Popen(restart_cmd, close_fds=True, creationflags=0x00000008)  # DETACHED_PROCESS
        self.app.quit()


def make_samples(folder: Path) -> Path:
    """A few small files to try Tapshift on, drawn with Qt (no extra files to ship)."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient

    folder.mkdir(parents=True, exist_ok=True)

    def scene(path: Path, sky: tuple, sun: QColor, hills: tuple, fmt: str):
        if path.exists():
            return
        img = QImage(1600, 1000, QImage.Format.Format_RGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 0, 1000)
        g.setColorAt(0, QColor(*sky[0]))
        g.setColorAt(1, QColor(*sky[1]))
        p.fillRect(img.rect(), g)
        rg = QRadialGradient(QPointF(1100, 560), 260)
        rg.setColorAt(0, sun)
        rg.setColorAt(1, QColor(sun.red(), sun.green(), sun.blue(), 0))
        p.fillRect(img.rect(), rg)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sun)
        p.drawEllipse(QPointF(1100, 560), 120, 120)
        for i, col in enumerate(hills):
            shape = QPainterPath(QPointF(0, 1000))
            base = 640 + i * 110
            for x in range(0, 1700, 100):
                shape.lineTo(QPointF(x, base - 90 * ((x / 230 + i * 1.7) % 2 - 1) ** 2 * (1 + i * 0.3)))
            shape.lineTo(QPointF(1600, 1000))
            shape.closeSubpath()
            p.fillPath(shape, QColor(*col))
        p.end()
        if not img.save(str(path), fmt, 92):
            log.warning("couldn't write sample %s", path)

    scene(folder / "Sunset.png", ((32, 24, 72), (250, 128, 114)), QColor(255, 214, 140),
          ((88, 52, 110), (52, 32, 80), (24, 16, 44)), "PNG")
    scene(folder / "Mountains.jpg", ((14, 70, 140), (150, 210, 245)), QColor(255, 250, 225),
          ((70, 120, 150), (40, 84, 110), (20, 50, 70)), "JPG")
    notes = folder / "Meeting notes.txt"
    if not notes.exists():
        notes.write_text("Meeting notes\n\nTry Tapshift on this file too: select it, tap Ctrl + Shift and pick PDF.\n"
                         "Word does the conversion, and Tapshift checks every word made it across.\n",
                         encoding="utf-8")
    return folder


def main() -> int:
    setup_logging()
    if "--selftest" in sys.argv:
        from .selftest import run as selftest

        i = sys.argv.index("--selftest")
        target = Path(sys.argv[i + 1]) if len(sys.argv) > i + 1 else Path.cwd() / "tapshift-selftest"
        return selftest(target)
    mutex = winutil.single_instance(wait_seconds=8.0 if "--restarted" in sys.argv else 0.0)
    if mutex is None:
        return 0
    try:
        clean_stale_workdirs()
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(theme.app_icon())
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.error("no system tray available")
    ctl = Controller(app)  # noqa: F841 - keep alive
    from .ui.orbit import warm_fonts

    QTimer.singleShot(1500, warm_fonts)  # so the picker's first hover doesn't pay for loading fonts
    log.info("started %s %s, shortcut %s", APP_NAME, __version__, ctl.settings.hotkey)
    code = app.exec()
    log.info("stopped")
    return code
