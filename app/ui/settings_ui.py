"""The Settings window (with the About page)."""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSlider, QVBoxLayout, QWidget

from .. import GITHUB_REPO, __version__, github_url
from ..settings import Settings
from . import theme
from .chrome import ChromeWindow, label
from .fx import AnimatedLogo, GradientTitle, PillButton, Segmented, Toggle, with_alpha
from .guide import NavRail, Sections, h1, para, section_page
from .onboarding import CPU_CHOICES, CPU_TEXT


def licenses_dir():
    """The license texts and third-party notices bundled with the app."""
    import sys
    from pathlib import Path

    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "licenses"
    return Path(__file__).resolve().parent.parent.parent / "licenses"


def open_licenses():
    import os

    d = licenses_dir()
    if d.exists():
        os.startfile(str(d))
    else:
        webbrowser.open(github_url("/blob/main/THIRD-PARTY-NOTICES.md"))


def setting_row(title: str, text: str | QWidget, control: QWidget | None) -> QFrame:
    box = QFrame()
    box.setObjectName("row")
    box.setStyleSheet(f"QFrame#row {{ background: {theme.rgba(with_alpha(theme.SURFACE, 0.7))};"
                      f" border: 1px solid {theme.rgba(theme.LINE)}; border-radius: 14px; }}")
    bl = QHBoxLayout(box)
    bl.setContentsMargins(16, 12, 16, 12)
    col = QVBoxLayout()
    col.setSpacing(2)
    col.addWidget(label(title, 14, QFont.Weight.DemiBold))
    col.addWidget(text if isinstance(text, QWidget) else label(text, 12, dim=True))
    bl.addLayout(col, 1)
    if control is not None:
        bl.addSpacing(16)
        bl.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return box


def quality_slider(value: int, on_change) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(50, 100)
    s.setValue(value)
    s.setFixedWidth(180)
    s.setStyleSheet(theme.CARD_QSS)
    num = label(str(value), 13, QFont.Weight.DemiBold, wrap=False)
    num.setFixedWidth(30)
    s.valueChanged.connect(lambda v: (num.setText(str(v)), on_change(v)))
    row.addWidget(s)
    row.addWidget(num)
    return holder


class SettingsWindow(ChromeWindow):
    """``changed(key, value)`` is emitted for every setting the user changes."""

    changed = Signal(str, object)
    show_tour = Signal()
    open_logs = Signal()
    uninstall = Signal()

    def __init__(self, s: Settings, autostart: bool):
        super().__init__("Tapshift Settings", QSize(860, 600))
        self.s = s
        row = QHBoxLayout(self.body)
        row.setContentsMargins(0, 6, 0, 0)
        row.setSpacing(18)
        self.sections = Sections()
        names = []

        # ---- General
        page, lay = section_page()
        a = h1("General")
        auto = Toggle(autostart)
        auto.toggled.connect(lambda v: self.changed.emit("autostart", v))
        clip = Toggle(s.use_clipboard_fallback)
        clip.toggled.connect(lambda v: self.changed.emit("use_clipboard_fallback", v))
        dates = Toggle(s.keep_modified_date)
        dates.toggled.connect(lambda v: self.changed.emit("keep_modified_date", v))
        tour = PillButton("Show the welcome tour", "ghost", min_width=200)
        tour.clicked.connect(self.show_tour.emit)
        rows = [setting_row("Start with Windows", "Wait in the tray, ready for the shortcut.", auto),
                setting_row("Use copied files", "If nothing is selected, convert files you copied with Ctrl + C.",
                            clip),
                setting_row("Keep the original's date", "Give new files the same 'modified' date as the original.",
                            dates),
                setting_row("Welcome tour", "Walk through how Tapshift works again.", tour)]
        lay.addWidget(a)
        for r in rows:
            lay.addWidget(r)
        lay.addStretch(1)
        self.sections.add(page, [a, *rows])
        names.append("General")

        # ---- Shortcut & appearance
        page, lay = section_page()
        a = h1("Shortcut and look")
        keys = Segmented([("Ctrl+Shift", "Tap Ctrl + Shift"), ("Ctrl+Shift+Space", "Ctrl + Shift + Space")],
                         s.hotkey if s.hotkey in ("Ctrl+Shift", "Ctrl+Shift+Space") else "Ctrl+Shift")
        keys.changed.connect(lambda v: self.changed.emit("hotkey", v))
        look = Segmented([("auto", "Auto"), ("dark", "Dark"), ("light", "Light")], s.theme)
        look.changed.connect(lambda v: self.changed.emit("theme", v))
        accent = Segmented([("verdant", "Green"), ("signal", "Orange"), ("native", "Windows color")],
                           s.palette if s.palette in ("verdant", "signal", "native") else "verdant")
        accent.changed.connect(lambda v: self.changed.emit("palette", v))
        rows = [setting_row("Shortcut", "Choose the three-key combo if Ctrl + Shift switches your keyboard layout. "
                                        "Applies immediately.", keys),
                setting_row("Appearance", "Auto follows Windows' light or dark mode. Applies after Tapshift "
                                          "restarts.", look),
                setting_row("Accent color", "Windows color uses the accent you picked in Windows Settings. "
                                            "Applies after Tapshift restarts.", accent)]
        lay.addWidget(a)
        for r in rows:
            lay.addWidget(r)
        lay.addStretch(1)
        self.sections.add(page, [a, *rows])
        names.append("Shortcut & look")

        # ---- Performance
        page, lay = section_page()
        a = h1("Performance")
        cpu_text = label(CPU_TEXT.get(str(s.max_cpu_percent), CPU_TEXT["25"]), 12, dim=True)
        cpu_value = str(s.max_cpu_percent) if str(s.max_cpu_percent) in CPU_TEXT else "25"
        cpu = Segmented(CPU_CHOICES, cpu_value)

        def cpu_changed(v: str):
            cpu_text.setText(CPU_TEXT[v])
            self.changed.emit("max_cpu_percent", int(v))

        cpu.changed.connect(cpu_changed)
        b = para("Windows itself enforces this limit for Tapshift and the hidden Office copies it uses. When "
                 "nothing is converting, Tapshift uses no processor time at all.")
        r1 = setting_row("Processor limit", cpu_text, cpu)
        lay.addWidget(a)
        lay.addWidget(r1)
        lay.addWidget(b)
        lay.addStretch(1)
        self.sections.add(page, [a, r1, b])
        names.append("Performance")

        # ---- Quality
        page, lay = section_page()
        a = h1("Quality")
        b = para("Default quality for lossy image formats (higher is better and bigger). You can also change it "
                 "for one conversion by right-clicking the format in the picker. Lossless formats (PNG, TIFF, "
                 "lossless WEBP) are always exact.")
        rows = [setting_row(name, desc, quality_slider(getattr(s, key), lambda v, k=key: self.changed.emit(k, v)))
                for name, desc, key in (("JPG", "92 is visually lossless for photos.", "jpeg_quality"),
                                        ("WEBP", "Used when the source is already lossy.", "webp_quality"),
                                        ("AVIF", "Very efficient; 88 looks like the original.", "avif_quality"),
                                        ("HEIC", "The iPhone photo format.", "heic_quality"))]
        lay.addWidget(a)
        lay.addWidget(b)
        for r in rows:
            lay.addWidget(r)
        lay.addStretch(1)
        self.sections.add(page, [a, b, *rows])
        names.append("Quality")

        # ---- About
        page, lay = section_page()
        top = QHBoxLayout()
        logo = AnimatedLogo(96)
        top.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(GradientTitle("Tapshift", 40, align=Qt.AlignmentFlag.AlignLeft))
        col.addWidget(label(f"Version {__version__}", 13, dim=True))
        top.addSpacing(8)
        top.addLayout(col, 1)
        head = QWidget()
        head.setLayout(top)
        b = para("Select files, tap Ctrl + Shift, pick a format. Free and open source.")
        btns = QHBoxLayout()
        gh = PillButton("GitHub page", "primary", min_width=150)
        gh.clicked.connect(lambda: webbrowser.open(github_url()))
        upd = PillButton("Check for updates", "ghost", min_width=170)
        upd.clicked.connect(lambda: webbrowser.open(github_url("/releases/latest")))
        lic = PillButton("Licenses", "ghost", min_width=110)
        lic.clicked.connect(open_licenses)
        logs = PillButton("Log folder", "ghost", min_width=120)
        logs.clicked.connect(self.open_logs.emit)
        for w in (gh, upd, lic, logs):
            btns.addWidget(w)
        from ..winutil import uninstaller

        if uninstaller() is not None:  # installed with Setup (not the portable zip)
            rem = PillButton("Uninstall", "ghost", min_width=110)
            rem.clicked.connect(self.uninstall.emit)
            btns.addWidget(rem)
        btns.addStretch(1)
        bh = QWidget()
        bh.setLayout(btns)
        # Appropriate legal notice (AGPL-3.0 section 0): license, no warranty, where the source is.
        credits = para(
            "Tapshift is free software: you can redistribute and modify it under the terms of the GNU Affero "
            "General Public License, version 3. It comes with no warranty. "
            f"Source code: <a style='color:{theme.rgba(theme.ACCENT)}' href='{github_url()}'>"
            f"github.com/{GITHUB_REPO}</a><br><br>"
            "Built with Python, Qt (PySide6), Pillow, pillow-heif, rawpy, PyMuPDF and img2pdf; Licenses lists "
            "each one. Office documents are converted by your own Microsoft Office.")
        for w in (head, b, bh, credits):
            lay.addWidget(w)
        lay.addStretch(1)
        self.sections.add(page, [head, b, bh, credits])
        names.append("About")

        self.nav = NavRail(names)
        col = QVBoxLayout()
        col.addWidget(self.nav)
        col.addStretch(1)
        row.addLayout(col)
        row.addWidget(self.sections, 1)
        self.nav.selected.connect(self.sections.show_section)

    def present(self, section: int = 0):
        super().present()
        self.nav.select(section, emit=False)
        self.sections.show_section(section)
