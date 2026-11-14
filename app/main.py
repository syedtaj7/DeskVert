"""Tray app: wires the shortcut, the selection reader, the popup, the progress
panel, the job runner, and the welcome tour / guide / settings windows."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, selection, updater, winutil
from .catalog import describe_selection, explain_unsupported, office_installed
from .hotkey import is_modifier_tap, make_listener
from .jobs import Batch, JobManager, clean_stale_workdirs
from .paths import APP_NAME, documents_dir, log_dir
from .settings import Settings
from .ui import theme
from .ui.panels import Notice, ProgressPanel
from .ui.popup import Popup

log = logging.getLogger("deskvert")

UPDATE_FIRST_MS = 90_000  # first look for a new version a minute and a half after start (not during start-up)
UPDATE_POLL_MS = 30 * 60_000  # then wake every half hour to see whether it's time to look again
UPDATE_EVERY_S = 6 * 3600  # ...which is every six hours
NOTICE_AGAIN_S = 24 * 3600  # remind about the same version at most once a day


def setup_logging() -> None:
    handler = RotatingFileHandler(log_dir() / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # The installed app has no console: an error inside a window or a card would otherwise vanish without
    # a trace. Write it to the log instead (and keep running).
    def log_uncaught(kind, value, tb):
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, tb)
            return
        logging.getLogger("deskvert").error("unexpected error", exc_info=(kind, value, tb))

    sys.excepthook = log_uncaught


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
    show_requested = Signal()  # Deskvert was started again while running
    pick_requested = Signal()  # files arrived from the right-click menu
    update_checked = Signal(object)  # a Release from GitHub (or None), from the background check
    drag_started = Signal()  # Ctrl+Shift held during a drag (from the listener thread)
    drop_ready = Signal(object, str)  # files saved from a drop (or an error message), from a worker thread
    page_found = Signal(str, str)  # (address, title) of the page in the browser where Ctrl+Shift was tapped
    selection_found = Signal(object)  # the browser's selected text, saved as a web clip (a Path)
    fetching = Signal(str)  # a link's file is being fetched (its address), from a worker thread

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
        self.drag_listener = None
        self.dropzone = None
        self.drag_started.connect(self.show_dropzone)
        self.drop_ready.connect(self._drop_ready)
        self.page_found.connect(self._page_found)
        self.selection_found.connect(self._selection_found)
        self.fetching.connect(self._fetching)
        self._own_clip_until = 0.0  # Deskvert's own copy of a selection (and putting the clipboard back)
        self._drop_notes: list[str] = []
        self._drop_site = ""
        self._clip_changed = 0.0  # when the clipboard last got a picture (a screenshot, "Copy image"...)
        self._clip_saved: tuple[str, Path] | None = None  # (fingerprint, file): the same copy isn't saved twice
        self._text_copied = 0.0  # when text or a table was last copied (from a web page, it becomes a clip)
        self._text_used = ""  # fingerprint of the copied clip already opened: the next tap gives the page again
        app.clipboard().dataChanged.connect(self._clipboard_changed)
        self._roots: list[Path] = []  # folders in the current selection (their files are what's converted)
        self._last_batch = None
        self.layout_clash = False
        if not self.settings.onboarded:
            self.layout_clash = winutil.ctrl_shift_switches_layout()
            if self.layout_clash and self.settings.hotkey == "Ctrl+Shift":
                self.settings.hotkey = "Ctrl+Shift+Space"
                log.info("Ctrl+Shift switches the keyboard layout here: starting with Ctrl+Shift+Space")
                try:
                    self.settings.save()
                except OSError:
                    pass

        self.jobs = JobManager(self.settings)
        self.jobs.started.connect(self._on_started)
        self.jobs.file_started.connect(self._on_file_started)
        self.jobs.progress.connect(lambda *_: self._poll_progress())
        self.jobs.finished.connect(self._on_finished)

        self._new_panel()

        self.tray = QSystemTrayIcon(theme.app_icon(), self)
        self.tray.activated.connect(self._tray_activated)
        self._build_menu()
        self.tray.show()

        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(300)
        self.progress_timer.timeout.connect(self._poll_progress)

        self.hotkey_pressed.connect(self.on_hotkey)
        try:  # Tapshift is now Deskvert: take over its start-up, right-click and Send to entries
            moved = winutil.move_from_old_name()
            if any(moved.values()):
                log.info("moved over from the old name: %s", moved)
        except Exception:  # noqa: BLE001
            log.exception("moving over from the old name failed")
        if winutil.autostart_enabled():
            try:
                winutil.set_autostart(True)  # keep the start-up entry pointing at this copy (e.g. after installing)
            except OSError:
                pass
        self.show_requested.connect(lambda: self.show_settings(0))
        winutil.watch_show_requests(self.show_requested.emit)
        # Right-click "Convert with Deskvert": Explorer starts one copy per file; gather them briefly.
        self._pick_timer = QTimer(self)
        self._pick_timer.setSingleShot(True)
        self._pick_timer.setInterval(350)
        self._pick_timer.timeout.connect(self._open_picked)
        self.pick_requested.connect(self._pick_timer.start)
        winutil.watch_picks(self.pick_requested.emit)
        if self.settings.context_menu:
            try:
                winutil.set_context_menu(True)  # keep it pointing at this copy (e.g. after an update)
            except OSError:
                log.exception("couldn't add the right-click menu entry")
        self._last_action: dict | None = None  # for "tap twice to repeat"
        self._popup_opened = 0.0
        self._popup_files: list[Path] = []
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
        # New versions: a quiet look at GitHub soon after start, then every few hours (Settings > General).
        self.available_update = None
        self.update_checked.connect(self._on_update_checked)
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(UPDATE_POLL_MS)
        self.update_timer.timeout.connect(self._auto_check_updates)
        self.update_timer.start()
        QTimer.singleShot(UPDATE_FIRST_MS, self._auto_check_updates)
        # WEBP and AVIF downloads -> JPG (Settings > General), watched only while turned on.
        self._watcher = None
        self._watch_seen: dict[str, int] = {}
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.setInterval(1500)
        self._watch_timer.timeout.connect(self._scan_downloads)
        self._set_download_watch(self.settings.auto_jpg_downloads)
        from .ui import fx

        fx.REDUCE_MOTION = self.settings.reduce_motion
        from .watch import FolderWatcher

        self.folder_watch = FolderWatcher(self.settings, self)
        self.folder_watch.convert.connect(lambda offer, opts, dest: self.jobs.submit(offer, opts, dest))
        self.folder_watch.set_rules(self.settings.watch_folders)

    # ------------------------------------------------------------ updates
    def _auto_check_updates(self, force: bool = False) -> None:
        """Ask GitHub (in the background) whether a newer Deskvert exists. At most every few hours."""
        s = self.settings
        if not s.auto_update_check and not force:
            return
        if not force and time.time() - s.last_update_check < UPDATE_EVERY_S:
            return
        s.last_update_check = time.time()
        s.save()

        def work():
            try:
                self.update_checked.emit(updater.fetch_latest())
            except Exception as e:  # noqa: BLE001 - offline, rate-limited...: just try again later
                log.info("update check: %s", e)
                self.update_checked.emit(None)

        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, rel) -> None:
        if rel is None or not updater.is_newer(rel.version):
            return
        log.info("update available: %s", rel.version)
        self.available_update = rel
        self.update_action.setText(f"Update to Deskvert {rel.version}\u2026")
        self.tray.setToolTip(f"{APP_NAME} {__version__} \u00b7 {rel.version} is available")
        # Tell you once a day at most for the same version, not every few hours.
        seen, _, when = self.settings.update_noticed.partition("@")
        if seen == rel.version and time.time() - float(when or 0) < NOTICE_AGAIN_S:
            return
        what = rel.notes[0] if rel.notes else "Improvements and fixes."
        shown = self.panel.offer("info", f"Deskvert {rel.version} is available",
                                 f"You have {__version__}. New: {what}", "Update",
                                 lambda: self.show_settings(5, check_updates=True))
        if shown:
            self.settings.update_noticed = f"{rel.version}@{time.time():.0f}"
            self.settings.save()

    @property
    def key_label(self) -> str:
        return pretty_hotkey(self.settings.hotkey)

    # ------------------------------------------------------------ shortcut
    def _start_hotkey(self) -> tuple[bool, str | None]:
        if self.hotkey is not None:
            self.hotkey.stop()
        if self.drag_listener is not None:
            self.drag_listener.stop()
            self.drag_listener = None
        on_drag = self.drag_started.emit if self.settings.drag_convert else None
        try:
            self.hotkey = make_listener(self.settings.hotkey, self.hotkey_pressed.emit, on_drag)
            ok = self.hotkey.start()
            err = self.hotkey.error
        except ValueError as e:
            ok, err = False, str(e)
        if on_drag is not None and not is_modifier_tap(self.settings.hotkey):
            # A three-key shortcut doesn't read the keyboard itself: a small listener just for the drag gesture.
            from .hotkey import make_drag_listener

            self.drag_listener = make_drag_listener(on_drag)
            if not self.drag_listener.start():
                log.warning("drag listener: %s", self.drag_listener.error)
        self.tray.setToolTip(f"{APP_NAME} - {'tap' if is_modifier_tap(self.settings.hotkey) else 'press'} "
                             f"{self.key_label}")
        if hasattr(self, "head_action"):
            self.head_action.setText(f"{APP_NAME} {__version__}  ·  {self.key_label}")
        return ok, err

    def _new_panel(self) -> None:
        old = getattr(self, "panel", None)
        self.panel = ProgressPanel()
        self.panel.cancel_requested.connect(self.jobs.cancel)
        self.panel.show_folder.connect(winutil.show_in_explorer)
        self.panel.undo_requested.connect(self.undo)
        self.panel.details_requested.connect(self.show_results)
        self.panel.report_requested.connect(self.show_report)
        if old is not None:
            old.hide()
            old.deleteLater()

    def _restyle(self) -> None:
        """Apply a new look (Settings > Shortcut and look) right away, without restarting."""
        theme.refresh(self.settings.theme, self.settings.palette)
        icon = theme.app_icon()
        self.app.setWindowIcon(icon)
        self.tray.setIcon(icon)
        if self.tray.contextMenu() is not None:
            self.tray.contextMenu().setStyleSheet(theme.MENU_QSS)
        self.recent_menu.setStyleSheet(theme.MENU_QSS)
        if not self.jobs.busy:
            self._new_panel()  # the progress card is rebuilt; while converting it keeps the old look
        if _alive(self.notice):
            self.notice.close()
        reopen = {}
        for key in ("settings", "guide"):
            w = self.windows.get(key)
            if _alive(w):
                section = w.sections.currentIndex() if key == "settings" else 0
                geo = w.geometry()
                reopen[key] = (section, geo)
                w.close()
        for key, (section, geo) in reopen.items():
            (self.show_settings(section) if key == "settings" else self.show_guide())
            w = self.windows.get(key)
            if _alive(w):
                w.setGeometry(geo)

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
        m.addAction("How to use Deskvert", self.show_guide)
        m.addAction("Settings", lambda: self.show_settings(0))
        m.addAction("Customize the picker", lambda: self.show_settings(4))
        m.addAction("Welcome tour", self.show_tour)
        m.addSeparator()
        self.pause_action = m.addAction("Pause shortcut")
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(lambda v: setattr(self, "paused", v))
        m.addAction("About Deskvert", lambda: self.show_settings(5))
        m.addAction("Report a problem…", self.show_report)
        self.update_action = m.addAction("Check for updates\u2026", lambda: self.show_settings(5, check_updates=True))
        rel = getattr(self, "available_update", None)
        if rel is not None:
            self.update_action.setText(f"Update to Deskvert {rel.version}\u2026")
        if winutil.uninstaller() is not None:
            m.addAction("Uninstall Deskvert\u2026", self.uninstall)
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
        # Clicking the icon opens Deskvert itself; the latest files are under "Recent conversions".
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_settings(0)

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

        s = self.settings
        choices = {"autostart": True if not s.onboarded else winutil.autostart_enabled(),
                   "theme": s.theme, "cpu": s.max_cpu_percent, "hotkey": s.hotkey, "palette": s.palette,
                   "picker_size": s.picker_size, "quality": s.quality_level, "quick_recents": s.quick_recents,
                   "context_menu": s.context_menu, "keep_modified_date": s.keep_modified_date,
                   "use_clipboard_fallback": s.use_clipboard_fallback, "two_at_once": s.max_workers >= 2,
                   "auto_update_check": s.auto_update_check, "layout_clash": self.layout_clash,
                   "auto_jpg_downloads": s.auto_jpg_downloads, "browser_actions": s.browser_actions,
                   "reduce_motion": s.reduce_motion}
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
        s = self.settings
        theme_changed = (choices["theme"], choices.get("palette", s.palette)) != (s.theme, s.palette)
        s.theme = choices["theme"]
        s.palette = choices.get("palette", s.palette)
        s.picker_size = choices.get("picker_size", s.picker_size)
        if choices.get("quality", s.quality_level) != s.quality_level:
            s.set_quality_level(choices["quality"])
        for key in ("quick_recents", "keep_modified_date", "use_clipboard_fallback", "auto_update_check",
                    "browser_actions"):
            setattr(s, key, bool(choices.get(key, getattr(s, key))))
        if bool(choices.get("reduce_motion", s.reduce_motion)) != s.reduce_motion:
            self._apply("reduce_motion", bool(choices["reduce_motion"]), save=False)
        if bool(choices.get("auto_jpg_downloads", s.auto_jpg_downloads)) != s.auto_jpg_downloads:
            self._apply("auto_jpg_downloads", bool(choices["auto_jpg_downloads"]))
        workers = max(2, s.max_workers) if choices.get("two_at_once", s.max_workers >= 2) else 1
        if workers != s.max_workers:
            self._apply("max_workers", workers, save=False)
        if bool(choices.get("context_menu", s.context_menu)) != s.context_menu:
            self._apply("context_menu", bool(choices["context_menu"]))  # saves too
        s.save()
        if theme_changed:
            QTimer.singleShot(0, self._restyle)
        if first:
            how = "Tap" if is_modifier_tap(self.settings.hotkey) else "Press"
            self.panel.message("success", "Deskvert is ready",
                               f"{how} {self.key_label} with a file selected in File Explorer.", 5000)

    def show_report(self, about: str = "") -> None:
        """Report a problem: you see everything first; GitHub opens in your browser to post it."""
        from .ui.report import ReportWindow

        old = self.windows.get("report")
        if _alive(old) and about:
            old.close()
        w = self._window("report", lambda: ReportWindow(about if isinstance(about, str) else ""))
        if w is not None:
            w.present()

    def show_guide(self) -> None:
        from .ui.guide import GuideWindow

        w = self._window("guide", GuideWindow)
        if w is not None:
            w.present()

    def show_settings(self, section: int = 0, check_updates: bool = False) -> None:
        from .ui.settings_ui import SettingsWindow

        existing = self.windows.get("settings")
        if _alive(existing):
            existing.nav.select(section)
            existing.raise_()
            existing.activateWindow()
            if check_updates:
                existing.check_updates()
            return
        w = self._window("settings", lambda: SettingsWindow(self.settings, winutil.autostart_enabled()))
        if w is None:
            return
        w.changed.connect(self._apply)
        w.show_tour.connect(self.show_tour)
        w.open_logs.connect(lambda: os.startfile(str(log_dir())))
        w.report_problem.connect(self.show_report)
        w.uninstall.connect(self.uninstall)
        w.install_update.connect(self.install_update)
        w.present(section)
        if check_updates:
            w.check_updates()

    def undo(self, outputs: list[str]) -> None:
        """Undo on the Saved card: the new files go to the Recycle Bin (originals are never touched)."""
        try:
            n = winutil.recycle(outputs)
        except Exception as e:  # noqa: BLE001
            log.exception("undo failed")
            self.panel.message("error", "Couldn't undo", f"{e}. The new file is still there.", 8000)
            return
        self.recent = [p for p in self.recent if p not in outputs]
        self._refresh_recent()
        self.panel.message("info", "Undone", f"Moved {n} new file{'s' if n != 1 else ''} to the Recycle Bin. "
                           "Your originals are unchanged.", 5000)

    def _apply(self, key: str, value, save: bool = True) -> None:
        """Apply one setting change right away."""
        if key == "watch_folders":
            self.settings.watch_folders = [dict(r) for r in value or []]
            if save:
                self.settings.save()
            self.folder_watch.set_rules(self.settings.watch_folders)
            return
        if key == "reduce_motion":
            from .ui import fx

            self.settings.reduce_motion = fx.REDUCE_MOTION = bool(value)
            if save:
                self.settings.save()
            return
        if key == "auto_jpg_downloads":
            setattr(self.settings, key, bool(value))
            self.settings.save()
            self._set_download_watch(bool(value))
            return
        if key == "drag_convert":
            setattr(self.settings, key, bool(value))
            self.settings.save()
            self._start_hotkey()  # the listener watches for the gesture only when it's on
            return
        if key == "auto_update_check":
            setattr(self.settings, key, bool(value))
            self.settings.save()
            if value:
                self._auto_check_updates()
            return
        if key == "context_menu":
            setattr(self.settings, key, bool(value))
            self.settings.save()
            try:
                winutil.set_context_menu(bool(value))
            except OSError:
                log.exception("couldn't change the right-click menu entry")
            return
        if key == "autostart":
            try:
                winutil.set_autostart(bool(value))
            except OSError:
                log.exception("couldn't change start-with-Windows")
            return
        if key in ("theme", "palette"):
            setattr(self.settings, key, value)
            self.settings.save()
            QTimer.singleShot(0, self._restyle)  # after the click that changed it has finished
            return
        unchanged = key == "hotkey" and value == self.settings.hotkey and self.hotkey is not None
        setattr(self.settings, key, value)
        if save:
            self.settings.save()
        if key == "hotkey" and unchanged:
            return  # same shortcut: keep the running listener (restarting it gains nothing)
        if key == "hotkey":
            ok, err = self._start_hotkey()
            if not ok:
                self.panel.message("error", "That shortcut couldn't be used", str(err), 8000)
            else:
                how = "Tap" if is_modifier_tap(self.settings.hotkey) else "Press"
                self.panel.message("success", "Shortcut changed", f"{how} {self.key_label} with files selected.",
                                   4500)
            log.info("shortcut set to %s (%s)", self.settings.hotkey, "ok" if ok else err)
        if key in ("max_cpu_percent", "max_workers") and not self.jobs.busy:
            self.jobs.reset_pool()  # the next conversion starts with the new limit

    def try_samples(self) -> None:
        folder = make_samples(documents_dir() / "Deskvert Samples")
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
        import time

        if _alive(self.popup):
            quick = time.monotonic() - self._popup_opened < 0.55
            files = list(self._popup_files)
            self.popup.close()  # pressing the shortcut again closes the popup
            self.popup = None
            if quick and self._last_action:  # a double tap: repeat the last action on these files
                self.repeat_last(files)
            return
        self.popup = None
        try:
            files, where = selection.selected_files(hwnd, self.settings.use_clipboard_fallback)
        except Exception:
            log.exception("reading selection failed")
            files, where = [], ""
        cls = selection._class_name(hwnd)
        picked = len(files)
        files, roots, cut = selection.expand_selection(files)
        log.info("hotkey: window=%s files=%d source=%s folders=%d", cls, len(files), where or "-", len(roots))
        if picked and not files:
            self._show_notice("Nothing to convert in there",
                              "The selected folder has no files in it." if len(roots) == 1 else
                              "The selected folders have no files in them.", "info")
            return
        if not files:
            in_files = cls in selection.EXPLORER_CLASSES | selection.DESKTOP_CLASSES
            if self.settings.use_clipboard_fallback and self._copied_picture(fresh_only=not in_files):
                return
            if self.settings.browser_actions and not in_files:
                from . import browserurl

                if browserurl.is_browser(hwnd):
                    self._read_page(hwnd)  # the selected text if there is some, otherwise the page
                    return
                if self._copied_clip():  # text copied from a page, then a tap in another app
                    return
            if not in_files:
                return  # tapped in another app (e.g. switching keyboard layout): stay quiet
            how = "tap" if is_modifier_tap(self.settings.hotkey) else "press"
            self._show_notice("No file selected",
                              f"Select one or more files in File Explorer or on the Desktop, then {how} "
                              f"{self.key_label}.", "info")
            return
        self.open_picker(files, where, roots, cut)

    def _open_picked(self) -> None:
        paths = [Path(p) for p in winutil.take_picks() if os.path.exists(p)]
        files, roots, cut = selection.expand_selection(paths)
        if files:
            if _alive(self.popup):
                self.popup.close()
            self.open_picker(files, "menu", roots, cut)
        elif paths:
            self._show_notice("Nothing to convert in there", "The selected folder has no files in it.", "info")

    def repeat_last(self, files: list[Path]) -> None:
        """Run the last chosen action again, with the same options, on these files."""
        from .menu import build_menu

        last = self._last_action
        nodes, quick, _ = build_menu(files, self.settings)
        leaves = [leaf for n in quick + nodes for leaf in n.leaves()]
        node = next((n for n in leaves if n.key == last["key"]), None) or next(
            (n for n in leaves if n.offer is not None and n.offer.target.key == last["target"]), None)
        offer = node.offer if node is not None else None
        if offer is None:
            self._show_notice(f"Can't repeat {last['label']} here",
                              f"{last['label']} doesn't apply to the selected files.", "info")
            return
        log.info("repeat: %s on %d file(s)", last["key"], len(offer.sources))
        self._submit(offer, dict(last["options"]), last["key"])

    def _submit(self, offer, options: dict, key: str = "") -> None:
        from .menu import remember

        key = key or (self.popup.last_key if _alive(self.popup) and self.popup.last_key else offer.target.key)
        self._last_action = {"key": key, "target": offer.target.key, "label": offer.target.label,
                             "options": dict(options)}
        remember(self.settings, key)  # recently used actions move to the picker's inner ring
        try:
            self.settings.save()
        except OSError:
            pass
        options = dict(options)
        if self._roots and offer.target.engine in ("archive", "hash") and offer.target.combine:
            options["_roots"] = [str(r) for r in self._roots]  # keep the folders' structure inside the archive
        dest = ""
        if self.settings.save_to == "ask":
            from PySide6.QtWidgets import QFileDialog

            start = str((self._roots[0] if self._roots else offer.sources[0]).parent)
            dest = QFileDialog.getExistingDirectory(None, "Save the new files in", start)
            if not dest:
                return  # cancelled: nothing is converted
        self.jobs.submit(offer, options, dest)

    # ------------------------------------------------------------ drag and convert
    def show_dropzone(self) -> None:
        """Ctrl+Shift held while dragging: a "Drop to convert" circle under the pointer."""
        if self.paused or not self.settings.drag_convert:
            return
        if _alive(self.popup):
            self.popup.close()
        if self.dropzone is None:
            from .ui.dropzone import DropZone

            self.dropzone = DropZone()
            self.dropzone.dropped.connect(self._dropped)
            self.dropzone.failed.connect(lambda msg: self._show_notice("Couldn't use that", msg, "info"))
            self.dropzone.missed.connect(self._drop_missed)
        if not self.dropzone.show_at():
            log.warning("the drop target couldn't be shown")

    def _drop_missed(self) -> None:
        """The circle showed but nothing was dragged in: most often selected text, where Shift + press changes
        the selection instead of picking it up. Say what works (at most every few minutes)."""
        if time.monotonic() - getattr(self, "_missed_said", -1e9) < 300:
            return
        self._missed_said = time.monotonic()
        log.info("drop circle: nothing was dragged in")
        self._show_notice("Nothing was dragged in",
                          f"For text, no drag is needed: select it and tap {self.key_label}.", "info")

    def _dropped(self, dropped) -> None:
        """Something was let go on the circle. Real files open the picker at once; anything else is saved
        (or fetched) into Downloads\\Deskvert first, off the UI thread."""
        from . import dropread

        self._drop_site = dropped.from_video_site  # a video site's thumbnail: say so in the picker

        if dropped.files:
            files, roots, cut = selection.expand_selection(dropped.files)
            log.info("drop: %d file(s) from %d item(s)", len(files), len(dropped.files))
            if files:
                self.open_picker(files, "drop", roots, cut)
            else:
                self._show_notice("Nothing to convert in there", "The dropped folder has no files in it.", "info")
            return
        if dropped.url and not dropped.blobs:
            host = dropped.url.split("/")[2] if dropped.url.lower().startswith(("http://", "https://")) else ""
            self.panel.message("info", "Fetching what you dropped",
                               f"From {host}. It's saved in Downloads\\Deskvert, then the picker opens."
                               if host else "Saving it in Downloads\\Deskvert.", 30000)

        def work():
            try:
                files, how = dropread.to_files(dropped)
                self._drop_notes = list(dropped.notes)
                self.drop_ready.emit(files, how)
            except dropread.DropError as e:
                self.drop_ready.emit([], str(e))
            except Exception as e:  # noqa: BLE001
                log.exception("saving a drop failed")
                self.drop_ready.emit([], f"Couldn't save what was dropped ({e}).")

        threading.Thread(target=work, daemon=True).start()

    def _drop_ready(self, files: list, how: str) -> None:
        if not files:
            self.panel.hide()
            self._show_notice("Couldn't use that", how, "info")
            return
        log.info("drop: %s %d file(s) into %s", how, len(files), files[0].parent)
        self.panel.hide()
        self.open_picker(list(files), how)

    # ------------------------------------------------------------ copied pictures, browser pages
    def _clipboard_changed(self) -> None:
        if time.monotonic() < self._own_clip_until:
            return  # reading a browser's selection, then putting the clipboard back: not a copy of yours
        try:
            data = self.app.clipboard().mimeData()
            if data.hasImage():
                self._clip_changed = time.monotonic()
            elif data.hasHtml():
                self._text_copied = time.monotonic()
        except Exception:  # noqa: BLE001
            pass

    def _copied_picture(self, fresh_only: bool) -> bool:
        """A picture on the clipboard (a screenshot, a browser's "Copy image"): saved in Downloads\\Deskvert,
        then the picker. Outside File Explorer only if it was copied in the last few minutes."""
        if fresh_only and time.monotonic() - self._clip_changed > 300:
            return False
        from . import dropread

        data = dropread.clipboard_picture()
        if not data:
            return False
        import hashlib

        mark = hashlib.sha256(data).hexdigest()
        if self._clip_saved and self._clip_saved[0] == mark and self._clip_saved[1].exists():
            path = self._clip_saved[1]
        else:
            try:
                path = dropread.save(f"Copied picture {time.strftime('%Y-%m-%d %H.%M.%S')}.png", data)
            except Exception:  # noqa: BLE001
                log.exception("couldn't save the copied picture")
                return False
            self._clip_saved = (mark, path)
        log.info("copied picture -> %s", path.name)
        self._drop_notes, self._drop_site = [], ""
        self.open_picker([path], "copied")
        return True

    def _copied_clip(self) -> bool:
        """Text or a table just copied from a web page (Ctrl + C): saved as a web clip, then the picker.
        Dragging selected text is awkward (Shift + click changes the selection), so copy, then tap."""
        if time.monotonic() - self._text_copied > 120:
            return False
        from . import dropread

        clip = dropread.clipboard_clip()
        if clip is None:
            return False
        import hashlib

        mark = hashlib.sha256((clip.source + "|" + clip.html).encode("utf-8", "ignore")).hexdigest()
        if mark == self._text_used:
            return False  # already opened once: this tap is for the page itself
        try:
            path = dropread.save_clip(clip)
        except Exception:  # noqa: BLE001
            log.exception("couldn't save the copied text")
            return False
        self._text_used = mark
        log.info("copied text -> %s", path.name)
        self._drop_notes, self._drop_site = [], ""
        self.open_picker([path], "clip")
        return True

    def _read_page(self, hwnd: int) -> None:
        """Tapped on a browser: its selected text or table if there is one, otherwise the page itself
        (off the UI thread; it takes a moment)."""
        from . import browserurl

        title = browserurl.page_title(hwnd)
        self._own_clip_until = time.monotonic() + 3.0
        try:
            import win32api

            px, py = win32api.GetCursorPos()  # where the pointer was at the tap (a link under it counts)
        except Exception:  # noqa: BLE001
            px = py = None

        def work():
            import pythoncom

            from . import browsercopy, dropread

            try:
                clip = browsercopy.copy_selection(hwnd)
                if clip is not None:
                    link = dropread.only_link(clip.html, clip.source)
                    if link:  # only a link was selected: what it points to, not its words
                        self._use_link(link, dropread.link_text(clip.html))
                        return
                    self.selection_found.emit(dropread.save_clip(clip))
                    return
            except Exception:  # noqa: BLE001
                log.exception("reading the browser's selection failed")
            finally:
                self._own_clip_until = time.monotonic() + 0.5  # the last clipboard changes are ours too
            pythoncom.CoInitialize()
            try:
                if px is not None:
                    link, text = browserurl.link_at(px, py)
                    if link:
                        log.info("browser: tapped on a link")
                        self._use_link(link, text)
                        return
                url = browserurl.page_url(hwnd)
            except Exception:  # noqa: BLE001
                log.exception("reading the browser's address failed")
                url = ""
            finally:
                pythoncom.CoUninitialize()
            self.page_found.emit(url, title)

        threading.Thread(target=work, daemon=True).start()

    def _use_link(self, url: str, text: str) -> None:
        """A link in the browser (pointed at, or selected on its own): a file is fetched, a cloud share
        link fetches its file, a page becomes a shortcut. Runs on the worker thread; the picker opens after."""
        from . import dropread

        dropped = dropread.Dropped(url=url, link=url, title=text)
        if dropread.cloud_link(url) or dropread.is_file_link(url):
            self.fetching.emit(url)
        try:
            files, how = dropread._link(url, text, dropped, None, None)
            self._drop_notes, self._drop_site = list(dropped.notes), dropped.from_video_site
            self.drop_ready.emit(files, how)
        except dropread.DropError as e:
            self.drop_ready.emit([], str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("using a browser link failed")
            self.drop_ready.emit([], f"Couldn't use that link ({e}).")

    def _fetching(self, url: str) -> None:
        host = url.split("/")[2] if url.lower().startswith(("http://", "https://")) else ""
        self.panel.message("info", "Fetching the linked file",
                           f"From {host}. It's saved in Downloads\\Deskvert, then the picker opens.", 30000)

    def _selection_found(self, path) -> None:
        log.info("browser selection -> %s", path.name)
        self._drop_notes, self._drop_site = [], ""
        self.open_picker([path], "clip")

    def _page_found(self, url: str, title: str) -> None:
        from . import dropread

        if not url.lower().startswith(("http://", "https://")):
            self._show_notice("Couldn't read this page's address",
                              "Deskvert reads it from the browser's address bar. Try again once the page has loaded, "
                              "or drag the padlock icon next to the address onto the circle instead.", "info")
            return
        try:
            shortcut = dropread._page_shortcut(url, title, None)
        except Exception as e:  # noqa: BLE001
            self._show_notice("Couldn't save the link", str(e), "info")
            return
        log.info("browser page -> %s", shortcut.name)
        dropped = dropread.Dropped(url=url, link=url)
        self._drop_notes, self._drop_site = [], dropped.from_video_site
        self.open_picker([shortcut], "page")

    # ------------------------------------------------------------ WEBP / AVIF downloads -> JPG
    def _set_download_watch(self, on: bool) -> None:
        from PySide6.QtCore import QFileSystemWatcher

        from .dropread import downloads_dir

        if self._watcher is not None:
            self._watcher.deleteLater()
            self._watcher = None
        if not on:
            return
        folder = downloads_dir().parent  # the Downloads folder itself
        self._watch_since = time.time()
        self._watch_seen = {}
        self._watcher = QFileSystemWatcher([str(folder)], self)
        self._watcher.directoryChanged.connect(lambda _p: self._watch_timer.start())
        log.info("watching Downloads for WEBP / AVIF pictures")

    def _scan_downloads(self) -> None:
        """New WEBP / AVIF files that have finished downloading (same size twice in a row) get a JPG copy."""
        from .catalog import offers_for
        from .dropread import downloads_dir

        folder = downloads_dir().parent
        waiting = False
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        for e in entries:
            name = e.name.lower()
            if not e.is_file() or not name.endswith((".webp", ".avif")):
                continue
            try:
                st = e.stat()
            except OSError:
                continue
            if st.st_mtime < self._watch_since or self._watch_seen.get(e.path) == -1:
                continue
            if self._watch_seen.get(e.path) != st.st_size:  # still arriving: look again in a moment
                self._watch_seen[e.path] = st.st_size
                waiting = True
                continue
            self._watch_seen[e.path] = -1  # done (converted once, even if it's renamed or deleted later)
            jpg = Path(e.path).with_suffix(".jpg")
            if jpg.exists():
                continue
            offers, _ = offers_for([Path(e.path)], self.settings)
            offer = next((o for o in offers if o.target.key == "image.jpg"), None)
            if offer is not None:
                log.info("download watch: %s -> JPG", e.name)
                self.jobs.submit(offer, {o.key: o.default for o in offer.options})
        if waiting:
            self._watch_timer.start()

    def show_results(self) -> None:
        """Every file of the last batch, with what happened to it (the card's Details button)."""
        from .ui.results import ResultsWindow

        batch = self._last_batch
        if batch is None:
            return
        old = self.windows.get("results")
        if _alive(old):
            old.close()
        w = self._window("results", lambda: ResultsWindow(f"To {batch.label}", batch.results))
        if w is not None:
            w.show_file.connect(winutil.show_in_explorer)
            w.present()

    def open_picker(self, files: list[Path], where: str, roots: list[Path] | None = None, cut: bool = False) -> None:
        import time

        from .menu import build_menu

        self._roots = list(roots or [])

        nodes, quick, left_out = build_menu(files, self.settings)
        offers = []  # every action, for the searchable list
        for n in quick + nodes:
            for leaf in n.leaves():
                if leaf.offer is not None and leaf.preset is None and all(leaf.offer is not o for o in offers):
                    offers.append(leaf.offer)
        if not offers:
            title, msg = explain_unsupported(left_out or files)
            self._show_notice(title, msg)
            return
        notes = []
        if where == "clipboard":
            notes.append("From files copied to the clipboard.")
        site = getattr(self, "_drop_site", "")
        if where in ("saved", "downloaded"):
            if site:
                notes.append(f"This is the {site} video's thumbnail picture: videos on streaming sites can't be "
                             "downloaded.")
            notes += getattr(self, "_drop_notes", [])
            notes.append("Saved in Downloads\\Deskvert" + (" from the web" if where == "downloaded" else "")
                         + "; the new file goes next to it.")
        elif where == "page":
            if site:
                notes.append(f"A {site} page: save it or make a QR code. The video itself can't be downloaded.")
            notes.append("The link is kept in Downloads\\Deskvert; what you make goes next to it.")
        elif where == "clip":
            notes.append("Your selection is saved as a web clip in Downloads\\Deskvert, with where it came from.")
        elif where == "copied":
            notes.append("The copied picture is saved in Downloads\\Deskvert; the new file goes next to it.")
        if self._roots:
            n = len(self._roots)
            notes.append(f"{'This folder' if n == 1 else f'These {n} folders'}: {len(files)} "
                         f"file{'s' if len(files) != 1 else ''} inside.")
        if cut:
            notes.append(f"Only the first {selection.MAX_FILES} files are used.")
        group = [p for p in files if p not in left_out] or files
        if left_out and len(left_out) == len(files):
            # Nothing to convert, but the files can still be zipped: say why ZIP is the only choice.
            notes.append(explain_unsupported(files)[1].split(". Deskvert")[0] + ". You can still zip it.")
        elif left_out:
            notes.append(f"{len(left_out)} file(s) of an unsupported type: only ZIP includes them.")
        center = f"1 {group[0].suffix.upper().lstrip('.') or 'file'}" if len(group) == 1 else f"{len(group)} files"
        self.popup = Popup(describe_selection(group), center, " ".join(notes), offers,
                           estimator=self.jobs.estimate, nodes=nodes, quick=quick, scale=self.settings.picker_scale)
        self.popup.chosen.connect(self._submit)
        self.popup.destroyed.connect(self._popup_closed)
        self.popup.show_at_cursor()
        self._popup_opened = time.monotonic()
        self._popup_files = list(files)

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
        self._last_batch = batch

        if cancelled and not ok and not failed:
            self.panel.finish("info", "Conversion cancelled", "Nothing was saved, and your files are unchanged.")
        elif len(batch.results) == 1 and ok:
            r = ok[0]
            body = "  ".join(r.get("notes", [])[:2]) or "Checked against the original: everything matches."
            kind = Path(r["output"]).suffix.lstrip(".").upper() or batch.label
            self.panel.finish("success", f"Saved as {kind}", body, first_out, [r["output"]],
                              sources=list(r.get("sources") or []), name=Path(r["output"]).name)
        elif len(batch.results) == 1 and failed:
            r = failed[0]
            self.panel.finish("error", "Couldn't convert this file",
                              r.get("error", "Unknown error") + " Your original file is unchanged.",
                              name=Path(r["sources"][0]).name)
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
                              title, "\n".join(lines), first_out, [r["output"] for r in ok],
                              sources=[s for r in ok for s in (r.get("sources") or [])], details=True)
        QTimer.singleShot(3000, winutil.trim_memory)

    # ------------------------------------------------------------ exit
    def install_update(self, path: str) -> None:
        """Start the downloaded installer and quit; it installs over this copy and opens the new one."""
        from pathlib import Path

        from . import updater

        try:
            updater.launch_installer(Path(path))
        except OSError as e:
            log.error("couldn't start the installer: %s", e)
            return
        self.quit()

    def uninstall(self) -> None:
        """Hand over to the uninstaller (it asks "remove Deskvert?" first) and quit,
        so Deskvert's files aren't in use."""
        if winutil.start_uninstall():
            self.quit()

    def quit(self, restart_cmd: str | None = None) -> None:
        if self.hotkey is not None:
            self.hotkey.stop()
        self.jobs.shutdown()
        self.tray.hide()
        if restart_cmd:
            os.environ.pop("DESKVERT_THEME", None)
            subprocess.Popen(restart_cmd, close_fds=True, creationflags=0x00000008)  # DETACHED_PROCESS
        self.app.quit()


def make_samples(folder: Path) -> Path:
    """A few small files to try Deskvert on, drawn with Qt (no extra files to ship)."""
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
        notes.write_text("Meeting notes\n\nTry Deskvert on this file too: select it, tap Ctrl + Shift and pick PDF.\n"
                         "Word does the conversion, and Deskvert checks every word made it across.\n",
                         encoding="utf-8")
    return folder


def main() -> int:
    setup_logging()
    if "--check-update" in sys.argv:  # used to verify a built copy can reach GitHub over HTTPS
        import json

        from . import updater

        i = sys.argv.index("--check-update")
        target = Path(sys.argv[i + 1]) if len(sys.argv) > i + 1 else Path.cwd()
        target.mkdir(parents=True, exist_ok=True)
        try:
            rel = updater.fetch_latest()
            res = {"ok": True, "latest": rel.version, "current": __version__, "newer": updater.is_newer(rel.version),
                   "setup": rel.setup.name if rel.setup else None,
                   "checksum": bool(rel.setup and rel.setup.sha256)}
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "error": str(e)}
        log.info("update check: %s", res)
        (target / "update-check.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
        return 0 if res["ok"] else 1
    if "--selftest" in sys.argv:
        from .selftest import run as selftest

        i = sys.argv.index("--selftest")
        target = Path(sys.argv[i + 1]) if len(sys.argv) > i + 1 else Path.cwd() / "deskvert-selftest"
        return selftest(target)
    picks = []
    if "--pick" in sys.argv:  # right-click "Convert with Deskvert"
        picks = [a for a in sys.argv[sys.argv.index("--pick") + 1:] if not a.startswith("--")]
    mutex = winutil.single_instance(wait_seconds=8.0 if "--restarted" in sys.argv else 0.0)
    if mutex is None:
        if picks:
            winutil.send_pick(picks)  # the running Deskvert opens the picker for these files
        else:
            winutil.signal_running_instance()  # already running: bring its window to the front instead
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
    if picks:
        winutil.send_pick(picks)  # started from the right-click menu: open the picker right away
    from .ui.orbit import warm_fonts

    QTimer.singleShot(1500, warm_fonts)  # so the picker's first hover doesn't pay for loading fonts
    log.info("started %s %s, shortcut %s", APP_NAME, __version__, ctl.settings.hotkey)
    code = app.exec()
    log.info("stopped")
    return code
