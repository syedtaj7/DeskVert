"""The first-run welcome tour: six animated pages that explain Tapshift and
let people pick their setup."""

from __future__ import annotations

import math
import random

from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint, QPointF, QPropertyAnimation, QRectF, QSize,
                            Qt, Signal)
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QVBoxLayout, QWidget

from . import theme
from .chrome import ChromeWindow, label
from .demo import DemoScene
from .fx import (Clock, GradientTitle, PillButton, Segmented, StepDots, Toggle, accent_gradient, clamp, ease_back,
                 ease_out, fade_in, font, paint_check, paint_file_icon, phase, with_alpha)

CPU_CHOICES = [("15", "Gentle"), ("25", "Balanced"), ("50", "Faster")]
CPU_TEXT = {
    "15": "Uses at most 15% of your processor. Coolest and quietest; big documents take longer.",
    "25": "Uses at most 25% of your processor. Recommended: fast, and you won't notice it running.",
    "50": "Uses at most 50% of your processor. Quickest conversions; the fan may spin up on big files.",
}


# ====================================================================== painted pieces


class OrbitHero(Clock):
    """The logo drawing itself in, with format chips orbiting around it."""

    CHIPS = ["JPG", "PDF", "PNG", "DOCX", "WEBP", "XLSX", "HEIC", "PPTX"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(460, 220))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.t
        c = QPointF(self.width() / 2, self.height() / 2)
        appear = ease_out(phase(t, 0.4, 1.6))
        chips = []
        for i, name in enumerate(self.CHIPS):
            a = t * 0.35 + i * (2 * math.pi / len(self.CHIPS))
            depth = (math.sin(a) + 1) / 2  # 0 = back, 1 = front
            pos = QPointF(c.x() + math.cos(a) * 190, c.y() + math.sin(a) * 62)
            chips.append((depth, pos, name, i))
        chips.sort()
        for depth, pos, name, i in chips:
            if depth < 0.5:
                self._chip(p, pos, name, depth, appear * ease_out(phase(t, 0.5 + i * 0.08, 1.0 + i * 0.08)))
        glow = ease_out(t / 1.2)
        g = QBrush(with_alpha(theme.ACCENT_A, 0.0))
        from PySide6.QtGui import QRadialGradient

        rg = QRadialGradient(c, 110)
        rg.setColorAt(0, with_alpha(theme.ACCENT_A, (0.28 + 0.06 * math.sin(t * 2)) * glow))
        rg.setColorAt(1, with_alpha(theme.ACCENT_A, 0))
        p.fillRect(self.rect(), rg)
        theme.paint_logo(p, c, 128, progress=ease_out(t / 1.2), spin=0 if t < 1.2 else (t - 1.2) * 14)
        for depth, pos, name, i in chips:
            if depth >= 0.5:
                self._chip(p, pos, name, depth, appear * ease_out(phase(t, 0.5 + i * 0.08, 1.0 + i * 0.08)))
        p.end()

    def _chip(self, p: QPainter, pos: QPointF, name: str, depth: float, k: float):
        if k <= 0:
            return
        s = 0.72 + 0.38 * depth
        f = font(12 * s, QFont.Weight.Bold)
        w = QFontMetricsF(f).horizontalAdvance(name) + 22 * s
        h = 26 * s
        r = QRectF(pos.x() - w / 2, pos.y() - h / 2, w, h)
        p.save()
        p.setOpacity((0.35 + 0.65 * depth) * k)
        p.setPen(QPen(with_alpha(theme.ACCENT_A, 0.5 + 0.5 * depth), 1.2))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, h / 2, h / 2)
        p.setPen(theme.TEXT)
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, name)
        p.restore()


class CheckDot(Clock):
    def __init__(self, delay: float, parent=None):
        super().__init__(parent)
        self.delay = delay
        self.setFixedSize(QSize(40, 40))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_check(p, QPointF(20, 20), 34, ease_out(phase(self.t, self.delay, self.delay + 0.7)))
        p.end()
        if self.t > self.delay + 1:
            self._timer.stop()


class ChipCloud(Clock):
    """Format chips that pop in one after another, wrapped onto lines."""

    def __init__(self, chips: list[str], delay: float = 0.0, width: int = 220, parent=None):
        super().__init__(parent)
        self.chips, self.delay = chips, delay
        self.f = font(11.5, QFont.Weight.DemiBold)
        fm = QFontMetricsF(self.f)
        self.rects: list[QRectF] = []
        x = y = 0.0
        for c in chips:
            w = fm.horizontalAdvance(c) + 18
            if x + w > width and x > 0:
                x, y = 0.0, y + 30
            self.rects.append(QRectF(x, y, w, 24))
            x += w + 6
        self.setFixedSize(QSize(width, int(y + 26)))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(self.f)
        for i, (name, r) in enumerate(zip(self.chips, self.rects)):
            k = ease_back(phase(self.t, self.delay + i * 0.05, self.delay + i * 0.05 + 0.35))
            if k <= 0:
                continue
            p.save()
            c = r.center()
            p.translate(c)
            p.scale(k, k)
            p.translate(-c)
            p.setPen(QPen(theme.LINE, 1))
            p.setBrush(theme.SURFACE)
            p.drawRoundedRect(r, 12, 12)
            p.setPen(theme.TEXT)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, name)
            p.restore()
        p.end()
        if self.t > self.delay + len(self.chips) * 0.05 + 0.6:
            self._timer.stop()


class FileBadge(QWidget):
    def __init__(self, kind: str, lbl: str = "", parent=None):
        super().__init__(parent)
        self.kind, self.lbl = kind, lbl
        self.setFixedSize(QSize(40, 48))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_file_icon(p, QRectF(2, 2, 36, 44), self.kind, self.lbl)
        p.end()


class Celebration(Clock):
    """Big check mark with a burst of confetti."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(260, 170))
        rnd = random.Random(7)
        self.bits = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(70, 125), rnd.uniform(3, 6), rnd.random())
                     for _ in range(34)]

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.t
        c = QPointF(self.width() / 2, self.height() / 2)
        burst = phase(t, 0.35, 1.6)
        if 0 < burst < 1:
            for a, dist, size, hue in self.bits:
                d = dist * ease_out(burst)
                pos = QPointF(c.x() + math.cos(a) * d, c.y() + math.sin(a) * d * 0.7 + 40 * burst * burst)
                col = theme.ACCENT if hue < 0.6 else theme.DIM
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(col, 1 - burst))
                p.save()
                p.translate(pos)
                p.rotate(burst * 360 * (hue - 0.5))
                p.drawRoundedRect(QRectF(-size / 2, -size / 4, size, size / 2), 1, 1)
                p.restore()
        ring = ease_out(phase(t, 0.0, 0.6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(theme.SUCCESS, 0.14 * ring))
        p.drawEllipse(c, 70 * ring, 70 * ring)
        pen = QPen(theme.SUCCESS, 3)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - 46, c.y() - 46, 92, 92), 90 * 16, int(-360 * 16 * ease_out(phase(t, 0.1, 0.8))))
        paint_check(p, c, 70, ease_out(phase(t, 0.5, 1.2)), ring=False)
        p.end()
        if t > 2:
            self._timer.stop()


# ====================================================================== pages


class Page(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.anim_items: list[QWidget] = []

    def enter(self):
        for i, w in enumerate(self.anim_items):
            fade_in(w, delay_ms=60 + i * 90)
        for clock in self.findChildren(Clock):
            clock.restart()
            clock._timer.start()


def _heading(title: str, sub: str) -> tuple[QWidget, QWidget]:
    t = label(title, 28, QFont.Weight.Bold, display=True)
    s = label(sub, 14, dim=True)
    return t, s


class WheelHero(Clock):
    """The real format wheel, stepping through formats: shows the product, not decoration."""

    SEQUENCE = ["WEBP", "PDF", "PNG", "JPG", "AVIF", "HEIC"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(330, 330))

    def paintEvent(self, _):
        from .demo import paint_wheel

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.t
        appear = ease_back(phase(t, 0.15, 0.75), 1.2)
        step = int(max(0.0, t - 0.9) / 1.4)
        selected = None if t < 0.9 else self.SEQUENCE[step % len(self.SEQUENCE)]
        paint_wheel(p, QPointF(self.width() / 2, self.height() / 2), 138 * appear, clamp(appear), selected)
        p.end()


class WelcomePage(Page):
    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(44, 0, 24, 0)
        row.setSpacing(28)
        col = QVBoxLayout()
        col.setSpacing(14)
        col.addStretch(1)
        title = GradientTitle("Tapshift", 60, align=Qt.AlignmentFlag.AlignLeft)
        sub = label("Select a file, tap <b>Ctrl + Shift</b>, pick a format. "
                    "The converted file lands right next to the original.", 17)
        sub.setFixedWidth(360)
        sub.setFixedHeight(sub.heightForWidth(360) + 4)
        note = label("Images, Office documents and PDFs. Private: nothing leaves your computer.", 13, dim=True)
        note.setFixedWidth(360)
        note.setFixedHeight(note.heightForWidth(360) + 4)
        col.addWidget(title)
        col.addWidget(sub)
        col.addWidget(note)
        col.addStretch(1)
        row.addLayout(col)
        row.addStretch(1)
        hero = WheelHero()
        row.addWidget(hero, 0, Qt.AlignmentFlag.AlignVCenter)
        self.anim_items = [title, sub, note]


class HowPage(Page):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 36, 0)
        lay.setSpacing(4)
        t, s = _heading("How it works", "No app to open, nothing to upload. It all happens right where your files are.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(10)
        demo = DemoScene(width=640, height=352)
        lay.addWidget(demo, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        self.anim_items = [t, s, demo]


class SafePage(Page):
    ROWS = [
        ("Your original is never touched", "Tapshift only reads it. The new file is saved next to it with its own "
                                           "name, and nothing is ever overwritten."),
        ("Every result is double-checked", "After converting, the new file is opened again and compared with the "
                                           "original: pixels, pages, words, cell values. If anything is off, it's "
                                           "thrown away and you're told why."),
        ("Private and offline", "Nothing is uploaded anywhere. Conversion happens on your own computer."),
        ("Light on your laptop", "Conversions use a capped slice of the processor at low priority, so your "
                                 "laptop stays cool and responsive. When idle, Tapshift uses no CPU at all."),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 36, 0)
        lay.setSpacing(4)
        t, s = _heading("Safe by design", "Built so a conversion can never cost you a file.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(16)
        self.anim_items = [t, s]
        for i, (title, text) in enumerate(self.ROWS):
            row = QHBoxLayout()
            row.setSpacing(14)
            row.addWidget(CheckDot(0.35 + i * 0.25), 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(label(title, 15, QFont.Weight.DemiBold))
            col.addWidget(label(text, 13, dim=True))
            row.addLayout(col, 1)
            holder = QWidget()
            holder.setLayout(row)
            lay.addWidget(holder)
            lay.addSpacing(8)
            self.anim_items.append(holder)
        lay.addStretch(1)


class FormatsPage(Page):
    """One large Images tile next to Office and PDF stacked: an asymmetric grid, not three equal cards."""

    def __init__(self, office: dict[str, bool], parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QGridLayout

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 36, 0)
        lay.setSpacing(4)
        t, s = _heading("What it converts", "The wheel only offers formats that make sense for the files you picked.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(16)
        self.anim_items = [t, s]
        has_office = any(office.values())

        def tile(kind, lbl, name, chips, note, ok, width, delay, accent=False):
            card = QFrame()
            card.setObjectName("fcard")
            bg = theme.ACCENT_SOFT if accent else theme.SURFACE
            card.setStyleSheet(f"QFrame#fcard {{ background: {theme.rgba(bg)};"
                               f" border: 1px solid {theme.rgba(theme.LINE)}; border-radius: {theme.RADIUS_CARD}px; }}")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(18, 16, 18, 14)
            cl.setSpacing(10)
            top = QHBoxLayout()
            top.addWidget(FileBadge(kind, lbl))
            top.addSpacing(6)
            top.addWidget(label(name, 16, QFont.Weight.DemiBold), 1)
            cl.addLayout(top)
            cl.addWidget(ChipCloud(chips, delay=delay, width=width))
            cl.addStretch(1)
            n = label(note, 12, dim=ok)
            if not ok:
                n.setStyleSheet(f"color: {theme.rgba(theme.WARN)}; background: transparent;")
            cl.addWidget(n)
            return card

        images = tile("image", "", "Images",
                      ["JPG", "PNG", "WEBP", "HEIC", "AVIF", "GIF", "TIFF", "BMP", "ICO", "TGA", "PDF",
                       "Several images in 1 PDF"],
                      "Also reads camera RAW, PSD and SVG. Lossless formats are checked pixel for pixel.",
                      True, 740, 0.35, accent=True)
        office_card = tile("doc", "DOC", "Office documents",
                           ["PDF", "DOCX", "ODT", "RTF", "TXT", "XLSX", "CSV", "ODS", "PPTX", "Slides as images"],
                           "Converted by your own Microsoft Office." if has_office
                           else "Needs Microsoft Office installed.", has_office, 340, 0.5)
        pdf = tile("pdf", "PDF", "PDF tools", ["Merge", "Split", "Pages as PNG", "Pages as JPG", "Text"],
                   "Select several PDFs to merge them into one.", True, 300, 0.65)
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(images, 0, 0, 1, 2)
        grid.addWidget(office_card, 1, 0)
        grid.addWidget(pdf, 1, 1)
        grid.setColumnStretch(0, 6)
        grid.setColumnStretch(1, 5)
        holder = QWidget()
        holder.setLayout(grid)
        holder.setFixedHeight(360)
        lay.addWidget(holder)
        lay.addStretch(1)
        self.anim_items += [images, office_card, pdf]


class SetupPage(Page):
    def __init__(self, choices: dict, parent=None):
        super().__init__(parent)
        self.choices = choices
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 36, 0)
        lay.setSpacing(4)
        t, s = _heading("Make it yours", "You can change any of this later in Settings.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(14)
        self.anim_items = [t, s]

        auto = Toggle(choices["autostart"])
        auto.toggled.connect(lambda v: choices.__setitem__("autostart", v))
        theme_ctl = Segmented([("auto", "Auto"), ("dark", "Dark"), ("light", "Light")], choices["theme"])
        theme_ctl.changed.connect(lambda v: choices.__setitem__("theme", v))
        cpu = Segmented(CPU_CHOICES, str(choices["cpu"]))
        self.cpu_text = label(CPU_TEXT.get(str(choices["cpu"]), CPU_TEXT["25"]), 12, dim=True)
        cpu.changed.connect(self._cpu)
        keys = Segmented([("Ctrl+Shift", "Tap Ctrl + Shift"), ("Ctrl+Shift+Space", "Ctrl + Shift + Space")],
                         choices["hotkey"] if choices["hotkey"] in ("Ctrl+Shift", "Ctrl+Shift+Space") else "Ctrl+Shift")
        keys.changed.connect(lambda v: choices.__setitem__("hotkey", v))

        rows = [
            ("Start with Windows", "Tapshift waits quietly in the tray, ready whenever you tap the shortcut.", auto),
            ("Shortcut", "A quick tap of both keys, or a three-key combo if Ctrl + Shift switches your keyboard layout.",
             keys),
            ("Appearance", "Auto follows your Windows light or dark setting.", theme_ctl),
            ("Performance", None, cpu),
        ]
        for title, text, ctl in rows:
            box = QFrame()
            box.setObjectName("row")
            box.setStyleSheet(f"QFrame#row {{ background: {theme.rgba(with_alpha(theme.SURFACE, 0.7))};"
                              f" border: 1px solid {theme.rgba(theme.LINE)}; border-radius: 14px; }}")
            bl = QHBoxLayout(box)
            bl.setContentsMargins(16, 12, 16, 12)
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(label(title, 14, QFont.Weight.DemiBold))
            col.addWidget(self.cpu_text if text is None else label(text, 12, dim=True))
            bl.addLayout(col, 1)
            bl.addSpacing(16)
            bl.addWidget(ctl, 0, Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(box)
            lay.addSpacing(6)
            self.anim_items.append(box)
        lay.addStretch(1)

    def _cpu(self, v: str):
        self.choices["cpu"] = int(v)
        self.cpu_text.setText(CPU_TEXT[v])


class ReadyPage(Page):
    try_samples = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 0, 36, 0)
        lay.addStretch(1)
        cel = Celebration()
        lay.addWidget(cel, 0, Qt.AlignmentFlag.AlignHCenter)
        t = label("You're all set!", 30, QFont.Weight.Bold, display=True)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s = label("Tapshift now lives in your system tray, by the clock at the bottom-right. Right-click its "
                  "icon any time for <b>How to use</b>, <b>Settings</b> and recent conversions.", 14, dim=True)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setFixedWidth(600)
        s.setFixedHeight(s.heightForWidth(600) + 4)
        btn = PillButton("Try it with sample files", "primary", min_width=230)
        btn.clicked.connect(self.try_samples.emit)
        hint = label("Opens a folder with a few sample files. Select one and tap Ctrl + Shift.", 12, dim=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(s, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(14)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(hint)
        lay.addStretch(1)
        self.anim_items = [t, s, btn, hint]


# ====================================================================== window


class _Stage(QWidget):
    """Holds the pages; keeps the visible page filling it when resized."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self.current: QWidget | None = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.current is not None:
            self.current.setGeometry(self.rect())


class TourWindow(ChromeWindow):
    finished = Signal(dict)
    try_samples = Signal()

    def __init__(self, choices: dict, office: dict[str, bool]):
        super().__init__("Tapshift", QSize(880, 600))
        self.choices = dict(choices)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(12)
        self.stage = _Stage()
        lay.addWidget(self.stage, 1)
        ready = ReadyPage()
        ready.try_samples.connect(self.try_samples.emit)
        self.pages: list[Page] = [WelcomePage(), HowPage(), SafePage(), FormatsPage(office),
                                  SetupPage(self.choices), ready]
        for pg in self.pages:
            pg.setParent(self.stage)
            pg.hide()

        foot = QHBoxLayout()
        foot.setContentsMargins(16, 0, 8, 0)
        self.dots = StepDots(len(self.pages))
        foot.addWidget(self.dots, 0, Qt.AlignmentFlag.AlignVCenter)
        foot.addStretch(1)
        self.back = PillButton("Back", "ghost", min_width=96)
        self.next = PillButton("Get started", "primary", min_width=150)
        self.back.clicked.connect(lambda: self.go(self.idx - 1))
        self.next.clicked.connect(self._next)
        foot.addWidget(self.back)
        foot.addSpacing(8)
        foot.addWidget(self.next)
        lay.addLayout(foot)
        self.idx = -1
        self._group: QParallelAnimationGroup | None = None
        self._done = False

    def present(self):
        super().present()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(30, lambda: self.go(0))  # after the layout has given the stage its size

    def _next(self):
        if self.idx == len(self.pages) - 1:
            self._finish()
        else:
            self.go(self.idx + 1)

    def go(self, i: int):
        if i < 0 or i >= len(self.pages) or i == self.idx:
            return
        if self._group and self._group.state() == QParallelAnimationGroup.State.Running:
            self._group.stop()
        old = self.pages[self.idx] if self.idx >= 0 else None
        new = self.pages[i]
        direction = 1 if i > self.idx else -1
        rect = self.stage.rect()
        new.setGeometry(rect)
        new.move(QPoint(rect.x() + 70 * direction, rect.y()))
        new.show()
        new.raise_()
        group = QParallelAnimationGroup(self)
        a = QPropertyAnimation(new, b"pos")
        a.setDuration(420)
        a.setStartValue(new.pos())
        a.setEndValue(rect.topLeft())
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(a)
        if old is not None:
            eff = QGraphicsOpacityEffect(old)
            old.setGraphicsEffect(eff)
            b = QPropertyAnimation(old, b"pos")
            b.setDuration(300)
            b.setStartValue(old.pos())
            b.setEndValue(QPoint(rect.x() - 70 * direction, rect.y()))
            b.setEasingCurve(QEasingCurve.Type.InCubic)
            c = QPropertyAnimation(eff, b"opacity")
            c.setDuration(260)
            c.setStartValue(1.0)
            c.setEndValue(0.0)
            group.addAnimation(b)
            group.addAnimation(c)

            def done(o=old):
                o.hide()
                o.setGraphicsEffect(None)

            group.finished.connect(done)
        self._group = group
        group.start()
        self.idx = i
        self.stage.current = new
        new.enter()
        self.dots.set_index(i)
        self.back.setVisible(i > 0)
        self.next.setText("Get started" if i == 0 else ("Finish" if i == len(self.pages) - 1 else "Next"))

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._next()
        elif e.key() == Qt.Key.Key_Left:
            self.go(self.idx - 1)
        else:
            super().keyPressEvent(e)

    def _finish(self):
        if not self._done:
            self._done = True
            self.finished.emit(self.choices)
        self.close()

    def closeEvent(self, e):
        if not self._done:  # closed early: keep what was chosen so far, don't show the tour again
            self._done = True
            self.finished.emit(self.choices)
        super().closeEvent(e)
