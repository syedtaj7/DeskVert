"""The welcome tour: Tapshift's real picker, live, plus everything it converts.

Pages: a live web picker driven by a ghost cursor (take over with your mouse),
how it works, the universe of formats (counted live from the catalog, so new
conversions appear here by themselves), a playground with sample files, power
moves, safety, setup and the finish.

Every animation runs only while its page is showing, and stops when it's done.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QParallelAnimationGroup, QPoint, QPointF,
                            QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from . import theme
from .chrome import ChromeWindow, label
from .demo import DemoScene
from .fx import (Clock, GradientTitle, PillButton, Segmented, StepDots, Toggle, ease_back, ease_in_out,
                 ease_out, fade_in, font, paint_check, paint_cursor, paint_file_icon, paint_keycap, phase, with_alpha)

CPU_CHOICES = [("15", "Gentle"), ("25", "Balanced"), ("50", "Faster")]
CPU_TEXT = {
    "15": "Uses at most 15% of your processor. Coolest and quietest; big documents take longer.",
    "25": "Uses at most 25% of your processor. Recommended: fast, and you won't notice it running.",
    "50": "Uses at most 50% of your processor. Quickest conversions; the fan may spin up on big files.",
}
SAMPLE_DIR = Path("C:/Tapshift tour")  # never read: the picker only needs the names


def _menu_for(name: str):
    from ..menu import build_menu
    from ..settings import Settings

    return build_menu([SAMPLE_DIR / name], Settings())


# ====================================================================== the live picker, with a ghost cursor


class _Ghost(QWidget):
    """Draws the ghost cursor over the picker (never takes the mouse)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.pos_: QPointF | None = None
        self.press = 0.0

    def paintEvent(self, _):
        if self.pos_ is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.press > 0:
            p.setPen(QPen(with_alpha(theme.ACCENT, 0.8 * self.press), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self.pos_, 14 * (1.6 - self.press), 14 * (1.6 - self.press))
        paint_cursor(p, self.pos_, 1.1)
        p.end()


class Pilot(QObject):
    """Moves a ghost cursor through the real picker: a choice, a branch, its farthest choice, a
    branch inside a branch... The moment your own mouse arrives, it steps aside; it comes back
    a few seconds after you leave."""

    SCRIPT = [("hub",), ("top", 0), ("branch", "Split"), ("far",), ("hub",), ("branch", "Convert"),
              ("kid", "As images"), ("far",), ("branch", "Protect"), ("far",), ("hub",)]

    def __init__(self, orbit):
        super().__init__(orbit)
        self.orbit = orbit
        self.ghost = _Ghost(orbit)
        self.ghost.resize(orbit.size())
        self.step = 0
        self.pos = QPointF(orbit.orbit_center())
        self.src = QPointF(self.pos)
        self.dst = QPointF(self.pos)
        self.t = 0.0
        self.dur = 0.5
        self.dwell = 0.0
        self.paused_for = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(33)  # 30 steps a second is plenty for a cursor
        self.timer.timeout.connect(self._tick)
        orbit.installEventFilter(self)

    def start(self):
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def eventFilter(self, obj, e):
        if obj is self.orbit and e.type() in (QEvent.Type.MouseMove, QEvent.Type.Enter) and e.spontaneous():
            self.paused_for = 4.0  # you're driving now
            self.ghost.pos_ = None
            self.ghost.update()
        return False

    def _target(self) -> QPointF | None:
        o = self.orbit
        kind = self.SCRIPT[self.step % len(self.SCRIPT)]
        if kind[0] == "hub":
            return QPointF(o.orbit_center())
        if kind[0] == "top":
            leaves = [i for i in range(o.n_top) if not o.items[i].children]
            i = leaves[kind[1] % len(leaves)] if leaves else 0
        elif kind[0] == "branch":
            i = next((k for k in range(o.n_top) if o.items[k].label == kind[1]), -1)
        elif kind[0] == "kid":
            i = next((k for k in range(o.n_top, o.l2) if o.items[k].label == kind[1]), -1)
        else:  # the farthest choice of the deepest open fan
            lo, hi, b = (o.l2, len(o.ps), o.sub) if o.sub >= 0 else (o.n_top, o.l2, o.open)
            if b < 0 or hi <= lo:
                return None
            bp = o.ps[b]
            i = max(range(lo, hi), key=lambda j: math.hypot(o.ps[j].hx - bp.hx, o.ps[j].hy - bp.hy))
        if i < 0 or i >= len(o.ps):
            return None
        return QPointF(o.ps[i].hx, o.ps[i].hy)

    def _tick(self):
        dt = 0.033
        if self.paused_for > 0:
            self.paused_for -= dt
            if self.paused_for <= 0 and not self.orbit.underMouse():
                self.step = 0
            return
        if self.dwell > 0:
            self.dwell -= dt
            if self.dwell <= 0:
                self.step += 1
                tgt = self._target()
                if tgt is None:  # e.g. this sample has no such branch: skip that step
                    self.step += 1
                    tgt = self._target() or QPointF(self.orbit.orbit_center())
                self.src, self.dst, self.t = QPointF(self.pos), tgt, 0.0
                self.dur = max(0.35, min(1.1, math.hypot(tgt.x() - self.pos.x(), tgt.y() - self.pos.y()) / 520))
            return
        self.t = min(1.0, self.t + dt / self.dur)
        k = ease_in_out(self.t)
        self.pos = QPointF(self.src.x() + (self.dst.x() - self.src.x()) * k,
                           self.src.y() + (self.dst.y() - self.src.y()) * k)
        ev = QMouseEvent(QEvent.Type.MouseMove, self.pos, self.pos, Qt.MouseButton.NoButton,
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        self.orbit.mouseMoveEvent(ev)  # the real picker reacts exactly as it would to you
        self.ghost.pos_ = self.pos
        self.ghost.press = max(0.0, 1 - abs(self.t - 1) * 6) if self.t >= 0.999 else 0.0
        self.ghost.update()
        if self.t >= 1.0:
            # rest at each stop; after a full round, a longer pause so the picker can go fully still
            self.dwell = 3.0 if self.SCRIPT[self.step % len(self.SCRIPT)][0] == "hub" and self.step else 1.4


def live_orbit(name: str, note: str, avail_w: int, avail_h: int):
    """The real picker for a sample file, as large as the space allows (readable, never cut off)."""
    from .orbit import OrbitView

    nodes, quick, _ = _menu_for(name)
    probe = OrbitView(nodes, name, card_side="right", scale=1.0, note=note, quick=quick)
    w, h = probe.width(), probe.height()
    probe.deleteLater()
    scale = max(0.42, min(0.85, (avail_h - 4) / h, (avail_w - 4) / w))
    nodes, quick, _ = _menu_for(name)  # fresh nodes for the real one
    o = OrbitView(nodes, name, card_side="right", scale=scale, note=note, quick=quick)
    o.frame_ms = 33  # 30 fps is smooth enough here, at half the work
    return o


# ====================================================================== small painted pieces


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
        p.setPen(QPen(theme.SUCCESS, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - 46, c.y() - 46, 92, 92), 90 * 16, int(-360 * 16 * ease_out(phase(t, 0.1, 0.8))))
        paint_check(p, c, 70, ease_out(phase(t, 0.5, 1.2)), ring=False)
        p.end()
        if t > 2:
            self._timer.stop()


class PowerArt(Clock):
    """Small looping animations for the power moves."""

    FPS = 20
    LOOP = 4.0

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(QSize(260, 120))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        t = self.t % self.LOOP
        getattr(self, f"_{self.kind}")(p, t)
        p.end()

    def _chip(self, p, r: QRectF, text: str, on: bool = False, px: float = 11):
        p.setPen(QPen(theme.ACCENT if on else theme.LINE, 1.2))
        p.setBrush(theme.ACCENT if on else theme.SURFACE2)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(theme.ON_ACCENT if on else theme.TEXT)
        p.setFont(font(px, QFont.Weight.DemiBold))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def _repeat(self, p, t):
        taps = [(0.3, 0.55), (0.85, 1.1)]
        pressed = max((1 - abs((t - (a + b) / 2) / ((b - a) / 2))) if a <= t <= b else 0 for a, b in taps)
        paint_keycap(p, QRectF(20, 26, 86, 54), "Ctrl", pressed, pressed)
        paint_keycap(p, QRectF(118, 26, 86, 54), "Shift", pressed, pressed)
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.setPen(theme.DIM)
        p.drawText(QRectF(20, 88, 190, 20), Qt.AlignmentFlag.AlignCenter, "tap  ·  tap")
        k = ease_back(phase(t, 1.2, 1.6))
        if k > 0:
            r = QRectF(214, 40, 40 * k, 26 * k)
            r.moveCenter(QPointF(232, 53))
            self._chip(p, r, "×2", True, 11 * max(k, 0.1))

    def _menu(self, p, t):
        paint_file_icon(p, QRectF(16, 30, 44, 54), "image", "")
        menu = QRectF(80, 8, 168, 104)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(menu, 8, 8)
        items = ["Open", "Copy", "Convert with Tapshift", "Properties"]
        sel = min(2, int(phase(t, 0.3, 1.6) * 3))
        for k, it in enumerate(items):
            r = QRectF(menu.left() + 6, menu.top() + 6 + k * 24, menu.width() - 12, 22)
            on = k == sel
            if on:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.ACCENT if k == 2 and t > 1.6 else with_alpha(theme.TEXT, 0.12))
                p.drawRoundedRect(r, 5, 5)
            p.setPen(theme.ON_ACCENT if on and k == 2 and t > 1.6 else theme.TEXT)
            p.setFont(font(10.5, QFont.Weight.DemiBold if k == 2 else QFont.Weight.Normal))
            p.drawText(r.adjusted(10, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, it)
        paint_cursor(p, QPointF(menu.right() - 30, menu.top() + 16 + sel * 24), 0.9)

    def _undo(self, p, t):
        card = QRectF(10, 18, 190, 84)
        gone = ease_in_out(phase(t, 1.5, 2.2))
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(card, 10, 10)
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.setPen(theme.SUCCESS if t < 1.5 else theme.DIM)
        p.drawText(QRectF(24, 26, 160, 20), Qt.AlignmentFlag.AlignVCenter, "Saved" if t < 1.5 else "Undone")
        icon = QRectF(24 + 190 * gone, 50 - 12 * math.sin(gone * math.pi), 30 * (1 - 0.5 * gone), 38 * (1 - 0.5 * gone))
        paint_file_icon(p, icon, "image", "")
        btn = QRectF(120, 58, 66, 28)
        self._chip(p, btn, "Undo", 0.9 < t < 1.6)
        # the recycle bin
        bin_ = QRectF(214, 46, 32, 40)
        p.setPen(QPen(theme.DIM, 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(bin_, 4, 4)
        p.drawLine(QPointF(bin_.left() - 4, bin_.top()), QPointF(bin_.right() + 4, bin_.top()))
        if 0.9 < t < 1.6:
            paint_cursor(p, QPointF(150, 70), 0.9)

    def _presets(self, p, t):
        c = QPointF(130, 60)
        p.setPen(QPen(with_alpha(theme.TEXT, 0.18), 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, 92, 46)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE2)
        p.drawEllipse(c, 22, 22)
        names = ["WhatsApp photo", "College PDF", "Exam photo"]
        for k, n in enumerate(names):
            a = t * 0.6 + k * 2 * math.pi / 3
            pos = QPointF(c.x() + math.cos(a) * 92, c.y() + math.sin(a) * 46)
            w = 96
            self._chip(p, QRectF(pos.x() - w / 2, pos.y() - 12, w, 24), n, k == int(t / (self.LOOP / 3)) % 3, 10)
        p.setPen(theme.ACCENT)
        p.setBrush(theme.ACCENT)
        p.drawEllipse(c, 5, 5)


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

    def leave(self):
        pass


def _heading(title: str, sub: str) -> tuple[QWidget, QWidget]:
    return label(title, 28, QFont.Weight.Bold, display=True), label(sub, 14, dim=True)


class HeroPage(Page):
    """The real picker, alive, with a ghost cursor showing the web. Move your mouse in to take over."""

    def __init__(self, n_types: int, n_actions: int, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(40, 0, 8, 0)
        row.setSpacing(18)
        col = QVBoxLayout()
        col.setSpacing(14)
        col.addStretch(1)
        title = GradientTitle("Tapshift", 56, align=Qt.AlignmentFlag.AlignLeft)
        tag = label("Tap. Shift. Done.", 22, QFont.Weight.Bold, display=True)
        sub = label("Select files, tap <b>Ctrl + Shift</b>, and a web of choices opens right where you are. "
                    "Point, click, and the new file appears next to the original.", 15)
        for w in (sub,):
            w.setFixedWidth(300)
            w.setFixedHeight(w.heightForWidth(300) + 4)
        stats = label(f"<b>{n_types}</b> file types &nbsp;·&nbsp; <b>{n_actions}</b> ways to convert &nbsp;·&nbsp; "
                      "nothing leaves your PC", 13, dim=True)
        stats.setFixedWidth(300)
        stats.setFixedHeight(stats.heightForWidth(300) + 4)
        try_it = label("← The web on the right is the real picker. Move your mouse onto it.", 12, dim=True)
        try_it.setFixedWidth(300)
        try_it.setFixedHeight(try_it.heightForWidth(300) + 4)
        for w in (title, tag, sub, stats, try_it):
            col.addWidget(w)
        col.addStretch(1)
        row.addLayout(col)
        self.row = row
        self.orbit = None
        self.pilot = None
        self.anim_items = [title, tag, sub, stats, try_it]

    def enter(self):
        super().enter()
        if self.orbit is None:  # built on first show, sized to the room the page really has
            self.orbit = live_orbit("Report.pdf", "Watch, or take over with your mouse",
                                    self.width() - 40 - 300 - 26, self.height() - 8)
            self.pilot = Pilot(self.orbit)
            self.row.addWidget(self.orbit, 0, Qt.AlignmentFlag.AlignVCenter)
            self.row.addStretch(1)
            fade_in(self.orbit, 120, 420, 0)
        QTimer.singleShot(900, self.pilot.start)

    def leave(self):
        if self.pilot is not None:
            self.pilot.stop()


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
        demo = DemoScene(width=700, height=385)
        lay.addWidget(demo, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        self.anim_items = [t, s, demo]


class UniversePage(Page):
    def __init__(self, worlds, n_types, n_actions, parent=None):
        super().__init__(parent)
        from .universe import Universe

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 36, 0)
        lay.setSpacing(4)
        t, s = _heading("A whole universe, one shortcut",
                        "Everything Tapshift converts, counted live. Point at a world to see what goes in and what "
                        "comes out; click to keep it.")
        lay.addWidget(t)
        lay.addWidget(s)
        uni = Universe(worlds, n_types, n_actions, QSize(900, 440))
        lay.addWidget(uni, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        self.anim_items = [t, s]


class PlaygroundPage(Page):
    """Pick a sample file and play with the real picker for it. Nothing is converted here."""

    SAMPLES = ["Holiday.heic", "Notes.pdf", "Song.wav", "Trip.gpx", "Rocket.stl", "Contacts.vcf", "Film.srt",
               "Novel.epub", "Brand.ttf", "Plan.dxf"]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 36, 0)
        lay.setSpacing(4)
        t, s = _heading("Try it here", "Pick a file. This is the real picker, so point around: groups open into "
                                       "webs, and clicking shows what you'd get. Nothing is converted here.")
        lay.addWidget(t)
        lay.addWidget(s)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.buttons = []
        for name in self.SAMPLES:
            b = PillButton(name, "ghost", min_width=60)
            b.setFixedHeight(32)
            b.clicked.connect(lambda _=False, n=name: self.show_sample(n))
            chips.addWidget(b)
            self.buttons.append(b)
        chips.addStretch(1)
        holder = QWidget()
        holder.setLayout(chips)
        lay.addWidget(holder)
        self.area = QHBoxLayout()
        self.area.setContentsMargins(0, 0, 0, 0)
        self.area.addStretch(1)
        self.area.addStretch(1)  # the picker goes between these, centred
        area_w = QWidget()
        area_w.setLayout(self.area)
        lay.addWidget(area_w, 1)
        self.toast = label("", 13, QFont.Weight.DemiBold)
        self.toast.setStyleSheet(f"color: {theme.rgba(theme.ACCENT)}; background: transparent;")
        lay.addWidget(self.toast)
        self.orbit = None
        self.anim_items = [t, s, holder]

    def show_sample(self, name: str):
        from .orbit import out_name

        if self.orbit is not None:
            self.area.removeWidget(self.orbit)
            self.orbit.deleteLater()
        self.orbit = live_orbit(name, "Point to explore  ·  this is the real picker", self.width() - 72,
                                self.height() - 118)
        self.area.insertWidget(1, self.orbit, 0, Qt.AlignmentFlag.AlignVCenter)

        def chosen(node):
            o = node.offer
            if o is not None:
                self.toast.setText(f"In real use: “{out_name(o, (node.preset or {}).get('name_suffix'))}” would be "
                                   "saved next to the original, then checked.")

        self.orbit.activated.connect(chosen)
        self.orbit.options_requested.connect(
            lambda n: self.toast.setText(f"Right-click opens the options for {n.label} (quality, pages, size...)."))
        self.toast.setText(f"{name}: point at anything. Groups open their own webs.")
        fade_in(self.orbit, 0, 360, 10)

    def enter(self):
        super().enter()
        if self.orbit is None:
            QTimer.singleShot(250, lambda: self.show_sample(self.SAMPLES[0]))


class PowerPage(Page):
    MOVES = [
        ("repeat", "Tap twice to repeat", "Did the same thing yesterday? Select new files and tap Ctrl + Shift twice: "
                                          "the last action runs again, with the same settings."),
        ("menu", "Right-click works too", "Right-click files → Convert with Tapshift (on Windows 11 under Show more "
                                          "options). Same web, no shortcut needed."),
        ("undo", "Undo, any time", "Changed your mind? Undo on the Saved card sends the new file to the Recycle Bin. "
                                   "Your original was never touched."),
        ("presets", "Your favourites in the centre", "Presets like WhatsApp photo or College PDF under 300 KB, and "
                                                     "what you use most, sit closest to the middle."),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 36, 0)
        lay.setSpacing(4)
        t, s = _heading("Power moves", "Small things that make it fast after day one.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(10)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.anim_items = [t, s]
        for k, (kind, title, text) in enumerate(self.MOVES):
            card = QFrame()
            card.setObjectName("pcard")
            card.setStyleSheet(f"QFrame#pcard {{ background: {theme.rgba(theme.SURFACE)};"
                               f" border: 1px solid {theme.rgba(theme.LINE)}; border-radius: {theme.RADIUS_CARD}px; }}")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.addWidget(PowerArt(kind), 0, Qt.AlignmentFlag.AlignVCenter)
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(label(title, 15, QFont.Weight.DemiBold))
            txt = label(text, 12, dim=True)
            col.addWidget(txt)
            col.addStretch(1)
            cl.addLayout(col, 1)
            grid.addWidget(card, k // 2, k % 2)
            self.anim_items.append(card)
        holder = QWidget()
        holder.setLayout(grid)
        lay.addWidget(holder)
        lay.addStretch(1)


class SafePage(Page):
    ROWS = [
        ("Your original is never touched", "Tapshift only reads it. The new file is saved next to it with its own "
                                           "name, and nothing is ever overwritten."),
        ("Every result is double-checked", "The new file is opened again and compared with the original: pixels, "
                                           "pages, words, cell values, subtitle timings, sound length. If anything "
                                           "is off, it's thrown away and you're told why."),
        ("Private and offline", "Nothing is uploaded. Tapshift only goes online when you click Check for updates."),
        ("Light on your laptop", "A capped slice of the processor at low priority; no CPU at all when idle. Heavy "
                                 "jobs like re-encoding video are left out on purpose."),
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
                  "icon any time for <b>How to use</b>, <b>Settings</b>, <b>Customize</b> and recent conversions.",
                  14, dim=True)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setFixedWidth(620)
        s.setFixedHeight(s.heightForWidth(620) + 4)
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
        from PySide6.QtGui import QGuiApplication

        avail = QGuiApplication.primaryScreen().availableGeometry()
        super().__init__("Tapshift", QSize(min(1120, avail.width() - 60), min(780, avail.height() - 60)))
        from .universe import gather

        self.choices = dict(choices)
        worlds, n_types, n_actions = gather()  # counted from the catalog: new conversions show up by themselves
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(12)
        self.stage = _Stage()
        lay.addWidget(self.stage, 1)
        ready = ReadyPage()
        ready.try_samples.connect(self.try_samples.emit)
        self.pages: list[Page] = [HeroPage(n_types, n_actions), HowPage(), UniversePage(worlds, n_types, n_actions),
                                  PlaygroundPage(), PowerPage(), SafePage(), SetupPage(self.choices), ready]
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
            old.leave()
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
        for pg in self.pages:
            pg.leave()
        super().closeEvent(e)

