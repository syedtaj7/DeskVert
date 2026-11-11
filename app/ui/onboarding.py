"""The welcome tour: Tapshift's real picker, live, plus everything it converts.

Pages: a live web picker driven by a ghost cursor (take over with your mouse),
how it works, a map of every format (counted live from the catalog, so new
conversions appear here by themselves), every conversion acted out in a scrolling
gallery, power moves and safety on one page, setup and the finish.

Pages are built when first needed, and the formats are counted on a background thread,
so the first page is up and moving at once.

Every animation runs only while its page is showing, and stops when it's done.
"""

from __future__ import annotations

import math
import random
import threading
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QParallelAnimationGroup, QPoint, QPointF,
                            QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QCursor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout,
                               QWidget)

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
QUALITY_CHOICES = [("smaller", "Smaller"), ("high", "High"), ("best", "Best")]
QUALITY_TEXT = {
    "smaller": "Noticeably smaller photos; fine for sharing and forms.",
    "high": "Looks just like the original. Recommended.",
    "best": "Closest to the original, larger files.",
}
PICKER_CHOICES = [("compact", "Compact"), ("normal", "Normal"), ("large", "Large")]
ACCENT_CHOICES = [("verdant", "Green"), ("signal", "Orange"), ("native", "Windows")]


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

    def _inside(self, pos: QPointF) -> bool:
        """Is this point on the picker's disc (not just somewhere in its window)?"""
        o = self.orbit
        c = o.orbit_center()
        return math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= o.DR * o.disc_s.v + 4

    def eventFilter(self, obj, e):
        if obj is not self.orbit or not e.spontaneous():
            return False
        kind = e.type()
        if kind in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            if self._inside(e.position()):
                self.paused_for = 1.5  # you're driving now
                self.ghost.pos_ = None
                self.ghost.update()
                return False
            # outside the circle: the ghost keeps driving, so the picker ignores this pointer
            return self.paused_for <= 0
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
            if self.paused_for <= 0:
                if self._inside(QPointF(self.orbit.mapFromGlobal(QCursor.pos()))):
                    self.paused_for = 0.5  # still pointing at it: wait
                else:
                    self.step = 0
                    self.dwell = 0.3
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


class SafeArt(Clock):
    """A small looping picture for each promise on the safety page."""

    FPS = 24
    LOOP = 5.0
    ZOOM = 1.2  # drawn in a 170 x 92 box, shown a little larger

    def __init__(self, kind: str, zoom: float | None = None, parent=None):
        super().__init__(parent)
        self.kind = kind
        if zoom is not None:
            self.ZOOM = zoom
        self.setFixedSize(QSize(int(170 * self.ZOOM), int(92 * self.ZOOM)))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, 12, 12)
        t = self.t % self.LOOP
        p.setOpacity(ease_out(phase(t, 0, 0.3)) * (1 - ease_in_out(phase(t, self.LOOP - 0.35, self.LOOP))))
        p.scale(self.ZOOM, self.ZOOM)
        getattr(self, f"_{self.kind}")(p, t)
        p.end()

    def _small(self, p, r: QRectF, s: str, color=None, weight=QFont.Weight.DemiBold):
        p.setPen(color or theme.DIM)
        p.setFont(font(9.5, weight))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, s)

    def _lock(self, p, c: QPointF, k: float):
        p.save()
        p.setOpacity(p.opacity() * k)
        pen = QPen(theme.SUCCESS, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - 5, c.y() - 10, 10, 12), 0, 180 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.SUCCESS)
        p.drawRoundedRect(QRectF(c.x() - 7, c.y() - 4, 14, 11), 2.5, 2.5)
        p.restore()

    def _original(self, p, t):
        """The original stays put (and locked); the new file is a copy that slides out beside it."""
        paint_file_icon(p, QRectF(22, 16, 38, 48), "image")
        self._lock(p, QPointF(58, 18), ease_out(phase(t, 0.3, 0.7)))
        self._small(p, QRectF(6, 66, 70, 16), "original")
        k = ease_in_out(phase(t, 0.9, 1.9))
        if k > 0:
            x = 22 + (106 - 22) * k
            p.save()
            p.setOpacity(p.opacity() * min(1.0, k * 2))
            paint_file_icon(p, QRectF(x, 16, 38, 48), "image")
            p.restore()
            self._small(p, QRectF(90, 66, 70, 16), "new copy", theme.ACCENT if k > 0.98 else None)

    def _checked(self, p, t):
        """Both files side by side, compared; a match turns into a check."""
        paint_file_icon(p, QRectF(20, 18, 34, 44), "image")
        paint_file_icon(p, QRectF(116, 18, 34, 44), "image")
        sweep = 0.5 - 0.5 * math.cos(math.pi * 2 * phase(t, 0.3, 2.3))
        c = QPointF(37 + (133 - 37) * sweep, 40)
        if t < 2.4:
            p.setPen(QPen(theme.TEXT, 2.2))
            p.setBrush(with_alpha(theme.SURFACE, 0.4))
            p.drawEllipse(c, 12, 12)
            p.drawLine(QPointF(c.x() + 8.5, c.y() + 8.5), QPointF(c.x() + 15, c.y() + 15))
        ok = phase(t, 2.4, 3.0)
        if ok > 0:
            paint_check(p, QPointF(85, 40), 30, ease_out(ok))
        else:
            p.setPen(theme.DIM)
            p.setFont(font(18, QFont.Weight.Bold))
            p.drawText(QRectF(70, 26, 30, 28), Qt.AlignmentFlag.AlignCenter, "=")
        self._small(p, QRectF(0, 68, 170, 16), "same pixels · pages · words", theme.SUCCESS if ok > 0.5 else None)

    def _offline(self, p, t):
        """Your PC, and the internet it never talks to."""
        scr = QRectF(18, 20, 58, 38)
        p.setPen(QPen(theme.TEXT, 1.6))
        p.setBrush(theme.SURFACE2)
        p.drawRoundedRect(scr, 4, 4)
        p.drawLine(QPointF(10, 64), QPointF(84, 64))
        paint_file_icon(p, QRectF(37, 25, 20, 26), "image")
        cloud = QPainterPath()
        cx, cy = 132, 34
        cloud.addEllipse(QPointF(cx - 12, cy + 4), 11, 9)
        cloud.addEllipse(QPointF(cx + 2, cy - 3), 13, 12)
        cloud.addEllipse(QPointF(cx + 14, cy + 4), 10, 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(theme.DIM, 0.35))
        p.drawPath(cloud.simplified())
        # a dot sets off for the cloud and is stopped halfway
        go = phase(t, 0.4, 1.4)
        x = 84 + (104 - 84) * ease_out(go)
        if 0 < go < 1 or t < 2.8:
            p.setBrush(with_alpha(theme.ACCENT, 1 - phase(t, 1.4, 2.0)))
            p.drawEllipse(QPointF(x, 42), 3, 3)
        p.setPen(QPen(with_alpha(theme.DIM, 0.6), 1.4, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(86, 42), QPointF(116, 38))
        stop = ease_back(phase(t, 1.3, 1.7))
        if stop > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ERROR)
            p.drawEllipse(QPointF(104, 40), 9 * stop, 9 * stop)
            pen = QPen(QColor(255, 255, 255), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            d = 3.6 * stop
            p.drawLine(QPointF(104 - d, 40 - d), QPointF(104 + d, 40 + d))
            p.drawLine(QPointF(104 + d, 40 - d), QPointF(104 - d, 40 + d))
        self._small(p, QRectF(0, 68, 170, 16), "nothing leaves your PC")

    def _light(self, p, t):
        """A gauge that never goes past its cap, and drops to zero when there's nothing to do."""
        c = QPointF(85, 62)
        rad = 40
        rect = QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad)
        pen = QPen(theme.TRACK, 7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, 0, 180 * 16)
        busy = 1 - ease_in_out(phase(t, 2.6, 3.2))
        v = (0.13 + 0.08 * math.sin(t * 2.6)) * busy  # share of the processor, always under 25 %
        pen.setColor(theme.ACCENT)
        p.setPen(pen)
        if v > 0.003:
            p.drawArc(rect, 180 * 16, -int(180 * 16 * v))
        cap = math.pi * (1 - 0.25)
        p.setPen(QPen(theme.ERROR, 2))
        p.drawLine(QPointF(c.x() + math.cos(cap) * (rad - 8), c.y() - math.sin(cap) * (rad - 8)),
                   QPointF(c.x() + math.cos(cap) * (rad + 8), c.y() - math.sin(cap) * (rad + 8)))
        a = math.pi * (1 - v)
        p.setPen(QPen(theme.TEXT, 2.2))
        p.drawLine(c, QPointF(c.x() + math.cos(a) * (rad - 12), c.y() - math.sin(a) * (rad - 12)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.TEXT)
        p.drawEllipse(c, 3.5, 3.5)
        p.setPen(theme.TEXT)
        p.setFont(font(12, QFont.Weight.Bold))
        p.drawText(QRectF(c.x() - 40, c.y() + 4, 80, 18), Qt.AlignmentFlag.AlignCenter,
                   f"{v * 100:.0f} %" if busy > 0.02 else "idle: 0 %")
        self._small(p, QRectF(108, 22, 62, 14), "limit", theme.ERROR)


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

    FPS = 30
    LOOP = 4.0

    def __init__(self, kind: str, zoom: float = 1.0, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.zoom = zoom
        self.loop = 5.0 if kind == "undo" else self.LOOP
        self.setFixedSize(QSize(round(260 * zoom), round(120 * zoom)))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        t = self.t % self.loop
        if self.kind == "undo":  # a story with an end: fade between rounds instead of jumping
            p.setOpacity(ease_out(phase(t, 0, 0.3)) * (1 - ease_in_out(phase(t, self.loop - 0.4, self.loop))))
        p.scale(self.zoom, self.zoom)
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

    def _bin(self, p, c: QPointF, lid: float, shake: float):
        """A recycle bin; ``lid`` 0 shut .. 1 open."""
        p.save()
        p.translate(c.x() + math.sin(shake * math.pi * 6) * 2.2 * (1 - shake), c.y())
        body = QPainterPath()
        body.moveTo(-17, -20)
        body.lineTo(17, -20)
        body.lineTo(13, 22)
        body.quadTo(12.5, 25, 9, 25)
        body.lineTo(-9, 25)
        body.quadTo(-12.5, 25, -13, 22)
        body.closeSubpath()
        p.setPen(QPen(theme.DIM, 1.6))
        p.setBrush(theme.SURFACE2)
        p.drawPath(body)
        for x in (-7, 0, 7):
            p.drawLine(QPointF(x, -12), QPointF(x * 0.85, 18))
        p.save()
        p.translate(-20, -24)
        p.rotate(-38 * lid)
        p.setBrush(theme.SURFACE2)
        p.drawRoundedRect(QRectF(0, -2, 40, 6), 2, 2)
        p.drawRoundedRect(QRectF(14, -7, 12, 5), 2, 2)
        p.restore()
        p.restore()

    def _undo(self, p, t):
        """Saved card -> click Undo -> the new file drops into the Recycle Bin; the original stays."""
        undone = t >= 1.25
        card = QRectF(6, 10, 168, 100)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(card, 10, 10)
        # status line
        if undone:
            p.setPen(theme.DIM)
            p.setFont(font(11.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(18, 16, 150, 20), Qt.AlignmentFlag.AlignVCenter, "Undone")
        else:
            paint_check(p, QPointF(26, 26), 18, 1.0, ring=False)
            p.setPen(theme.SUCCESS)
            p.setFont(font(11.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(38, 16, 130, 20), Qt.AlignmentFlag.AlignVCenter, "Saved")
        # the file row: the new file, then (after Undo) the original that was never touched
        if not undone:
            paint_file_icon(p, QRectF(18, 44, 26, 32), "image")
            p.setPen(theme.TEXT)
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.drawText(QRectF(52, 44, 118, 18), Qt.AlignmentFlag.AlignVCenter, "beach.webp")
            p.setPen(theme.DIM)
            p.setFont(font(10))
            p.drawText(QRectF(52, 60, 118, 16), Qt.AlignmentFlag.AlignVCenter, "next to beach.heic")
        else:
            a = ease_out(phase(t, 2.3, 2.7))
            p.save()
            p.setOpacity(p.opacity() * a)
            paint_file_icon(p, QRectF(18, 44, 26, 32), "image")
            p.setPen(theme.TEXT)
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.drawText(QRectF(52, 44, 118, 18), Qt.AlignmentFlag.AlignVCenter, "beach.heic")
            p.setPen(theme.SUCCESS)
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(QRectF(52, 60, 118, 16), Qt.AlignmentFlag.AlignVCenter, "original, untouched")
            p.restore()
        # the Undo button
        pressed = 0.95 <= t < 1.25
        btn = QRectF(102, 80, 62, 24) if not undone else None
        if btn is not None:
            self._chip(p, btn.adjusted(0, 1, 0, 1) if pressed else btn, "Undo", pressed)
        # the new file flies into the bin
        fly = ease_in_out(phase(t, 1.25, 2.15))
        if 0 < fly < 1:
            sx, sy, ex, ey = 31, 60, 222, 50
            x = sx + (ex - sx) * fly
            y = sy + (ey - sy) * fly - math.sin(math.pi * fly) * 38
            s = 1 - 0.45 * fly
            paint_file_icon(p, QRectF(x - 13 * s, y - 16 * s, 26 * s, 32 * s), "image")
        lid = ease_out(phase(t, 1.1, 1.4)) * (1 - ease_in_out(phase(t, 2.15, 2.4)))
        self._bin(p, QPointF(222, 72), lid, phase(t, 2.35, 2.9))
        p.setPen(theme.DIM)
        p.setFont(font(9.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(186, 100, 72, 16), Qt.AlignmentFlag.AlignCenter, "Recycle Bin")
        # the pointer
        path = [(0.0, (160, 116)), (0.3, (160, 116)), (0.9, (140, 94)), (1.6, (140, 94)), (2.3, (250, 24)),
                (self.loop, (250, 24))]
        for (t0, a), (t1, b) in zip(path, path[1:]):
            if t <= t1:
                k = ease_in_out(phase(t, t0, t1))
                pt = QPointF(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
                break
        ring = phase(t, 0.95, 1.4)
        if 0 < ring < 1:
            p.setPen(QPen(with_alpha(theme.ACCENT, 1 - ring), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(pt, 5 + 14 * ring, 5 + 14 * ring)
        paint_cursor(p, pt, 0.9)

    def _presets(self, p, t):
        c = QPointF(130, 60)
        p.setPen(QPen(with_alpha(theme.TEXT, 0.18), 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, 74, 42)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE2)
        p.drawEllipse(c, 22, 22)
        names = ["WhatsApp photo", "College PDF", "Exam photo"]
        for k, n in enumerate(names):
            a = t * 0.6 + k * 2 * math.pi / 3
            pos = QPointF(c.x() + math.cos(a) * 74, c.y() + math.sin(a) * 42)
            w = 100
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

    def __init__(self, parent=None):
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
        stats = self.stats = label("Hundreds of file types &nbsp;·&nbsp; nothing leaves your PC", 13, dim=True)
        stats.setTextFormat(Qt.TextFormat.RichText)  # the counts arrive later, in bold
        stats.setFixedWidth(300)
        stats.setFixedHeight(stats.heightForWidth(300) + 24)
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
            fade_in(self.orbit, 0, 320, 0)
        QTimer.singleShot(350, self.pilot.start)

    def set_counts(self, n_types: int, n_actions: int):
        self.stats.setText(f"<b>{n_types}</b> file types &nbsp;·&nbsp; <b>{n_actions}</b> ways to convert &nbsp;·&nbsp; "
                           "nothing leaves your PC")

    def leave(self):
        if self.pilot is not None:
            self.pilot.stop()


class HowPage(Page):
    """Select, tap, point, saved: acted out in a File Explorer window, with the steps alongside."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 36, 0)
        lay.setSpacing(4)
        t, s = _heading("How it works", "No app to open, nothing to upload. It all happens right where your files are.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addStretch(1)
        self.demo = DemoScene(width=960, height=420, steps=True)
        lay.addWidget(self.demo, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(2)
        self.anim_items = [t, s, self.demo]

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = max(560, min(1000, self.width() - 72))
        self.demo.setFixedSize(QSize(w, max(300, min(int(w * 0.44), self.height() - 110))))


class UniversePage(Page):
    """Every kind of file, and what it becomes: a steady map, counted live."""

    def __init__(self, worlds, n_types, n_actions, parent=None):
        super().__init__(parent)
        from .universe import FormatMap

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 36, 0)
        lay.setSpacing(4)
        t, s = _heading("Every format, one shortcut",
                        "Counted live from the picker. Point at a kind of file to see what goes in and what comes out.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(16)
        self.map = FormatMap(worlds, n_types, n_actions, QSize(980, 450))
        lay.addWidget(self.map, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        self.anim_items = [t, s]

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.map.setFixedSize(QSize(max(720, min(1000, self.width() - 72)), max(360, min(470, self.height() - 110))))


class ShowcasePage(Page):
    """Every conversion acted out: scroll through, and they all play at once."""

    def __init__(self, worlds, parent=None):
        super().__init__(parent)
        from .showcase import Showcase

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 24, 0)
        lay.setSpacing(4)
        t, s = _heading("Watch them work", "Every kind of conversion, acted out. Scroll down: they all play at once.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(10)
        self.show_ = Showcase(worlds)
        lay.addWidget(self.show_, 1)
        self.anim_items = [t, s]

    def enter(self):
        super().enter()
        self.show_.verticalScrollBar().setValue(0)
        self.show_.start()

    def leave(self):
        self.show_.stop()


class MovesPage(Page):
    """Power moves and the safety promises, side by side on one page."""

    POWER = [
        ("repeat", "Tap twice to repeat", "Select new files and tap Ctrl + Shift twice: the last action runs again, "
                                          "with the same settings."),
        ("menu", "Right-click works too", "Convert with Tapshift is in files' right-click menu (on Windows 11, under "
                                          "Show more options)."),
        ("undo", "Undo, any time", "Undo on the Saved card sends the new file to the Recycle Bin. The original "
                                   "stays."),
        ("presets", "Favourites in the centre", "Presets like WhatsApp photo, and what you use most, sit closest to "
                                                "the middle."),
    ]
    SAFE = [
        ("original", "Your original is never touched", "Only read. The new file gets its own name next to it; "
                                                       "nothing is overwritten."),
        ("checked", "Every result is double-checked", "Reopened and compared: pixels, pages, words, cells, timings. "
                                                      "If anything is off, it's thrown away."),
        ("offline", "Private and offline", "Nothing is uploaded. The only thing it asks the internet is "
                                           "whether a newer Tapshift exists."),
        ("light", "Light on your laptop", "A capped slice of the processor at low priority, and none at all when "
                                          "idle."),
    ]
    ART = QSize(196, 92)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 24, 0)
        lay.setSpacing(4)
        t, s = _heading("Fast, and safe", "Small things that make it quick after day one, and the promises behind "
                                          "every conversion.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(8)
        self.anim_items = [t, s]
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for col, (heading, rows) in enumerate((("POWER MOVES", self.POWER), ("SAFE BY DESIGN", self.SAFE))):
            head = label(heading, 11.5, QFont.Weight.Bold, dim=True)
            grid.addWidget(head, 0, col)
            self.anim_items.append(head)
            for r, (kind, title, text) in enumerate(rows):
                card = QFrame()
                card.setObjectName("mcard")
                card.setStyleSheet(f"QFrame#mcard {{ background: {theme.rgba(theme.SURFACE)};"
                                   f" border: 1px solid {theme.rgba(theme.LINE)}; border-radius: {theme.RADIUS_CARD}px; }}")
                row = QHBoxLayout(card)
                row.setContentsMargins(10, 8, 14, 8)
                row.setSpacing(14)
                art = PowerArt(kind, zoom=0.74) if col == 0 else SafeArt(kind, zoom=0.98)
                holder = QWidget()
                holder.setFixedSize(self.ART)
                hl = QHBoxLayout(holder)
                hl.setContentsMargins(0, 0, 0, 0)
                hl.addWidget(art, 0, Qt.AlignmentFlag.AlignCenter)
                row.addWidget(holder, 0, Qt.AlignmentFlag.AlignVCenter)
                txt = QVBoxLayout()
                txt.setSpacing(3)
                txt.addStretch(1)
                txt.addWidget(label(title, 14, QFont.Weight.DemiBold))
                txt.addWidget(label(text, 12, dim=True))
                txt.addStretch(1)
                row.addLayout(txt, 1)
                grid.addWidget(card, r + 1, col)
                self.anim_items.append(card)
        for c in range(2):
            grid.setColumnStretch(c, 1)
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        box.setLayout(grid)
        from .showcase import scroll_qss

        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(scroll_qss())
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(box)
        lay.addWidget(scroll, 1)

    def enter(self):
        for clock in self.findChildren(Clock):
            clock.restart()
            clock._timer.start()
        for i, w in enumerate(self.anim_items):
            fade_in(w, delay_ms=40 + i * 40, duration=340, rise=10)


class SetupPage(Page):
    """Everything worth choosing on day one, each with a line on what it does."""

    def __init__(self, choices: dict, parent=None):
        super().__init__(parent)
        self.choices = choices
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 24, 0)
        lay.setSpacing(4)
        t, s = _heading("Make it yours", "Applied when you finish. You can change any of this later in Settings.")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(10)
        self.anim_items = [t, s]

        def seg(key, options, fallback):
            value = str(choices.get(key, fallback))
            ctl = Segmented(options, value if value in {v for v, _ in options} else fallback)
            ctl.changed.connect(lambda v: choices.__setitem__(key, v))
            return ctl

        def toggle(key):
            ctl = Toggle(bool(choices.get(key, False)))
            ctl.toggled.connect(lambda v: choices.__setitem__(key, v))
            return ctl

        cpu = Segmented(CPU_CHOICES, str(choices["cpu"]) if str(choices["cpu"]) in CPU_TEXT else "25")
        self.cpu_text = label(CPU_TEXT.get(str(choices["cpu"]), CPU_TEXT["25"]), 12, dim=True)
        cpu.changed.connect(self._cpu)
        quality = seg("quality", QUALITY_CHOICES, "high")
        self.quality_text = label(QUALITY_TEXT.get(choices.get("quality", "high"), QUALITY_TEXT["high"]), 12, dim=True)
        quality.changed.connect(lambda v: self.quality_text.setText(QUALITY_TEXT[v]))

        cards = [
            ("Shortcut", "A quick tap of both keys, or a three-key combo if Ctrl + Shift switches your keyboard "
             "layout.", seg("hotkey", [("Ctrl+Shift", "Tap Ctrl + Shift"), ("Ctrl+Shift+Space", "Ctrl+Shift+Space")],
                            "Ctrl+Shift")),
            ("Start with Windows", "Waits quietly in the tray, ready whenever you tap the shortcut.",
             toggle("autostart")),
            ("Appearance", "Auto follows your Windows light or dark setting.",
             seg("theme", [("auto", "Auto"), ("dark", "Dark"), ("light", "Light")], "auto")),
            ("Accent color", "Windows uses the accent you chose in Windows Settings.",
             seg("palette", ACCENT_CHOICES, "verdant")),
            ("Picker size", "How big the web of choices opens. Compact suits small screens.",
             seg("picker_size", PICKER_CHOICES, "normal")),
            ("Performance", self.cpu_text, cpu),
            ("Photo quality", self.quality_text, quality),
            ("Recent actions in the centre", "What you used last sits closest to the middle of the picker.",
             toggle("quick_recents")),
            ("Right-click menu", "Adds Convert with Tapshift to files' right-click menu.", toggle("context_menu")),
            ("Tell me about updates", "Lets you know when a new version is out. It only asks GitHub for the "
             "latest version number.", toggle("auto_update_check")),
            ("Use copied files", "Nothing selected? Convert the files you copied with Ctrl + C.",
             toggle("use_clipboard_fallback")),
            ("Two files at a time", "Converts two at once when you pick many; the processor limit is shared.",
             toggle("two_at_once")),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        for i, (title, text, ctl) in enumerate(cards):
            box = QFrame()
            box.setObjectName("row")
            box.setStyleSheet(f"QFrame#row {{ background: {theme.rgba(with_alpha(theme.SURFACE, 0.7))};"
                              f" border: 1px solid {theme.rgba(theme.LINE)}; border-radius: 14px; }}")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(16, 12, 16, 14)
            bl.setSpacing(4)
            head = QHBoxLayout()
            head.addWidget(label(title, 14, QFont.Weight.DemiBold), 1)
            if isinstance(ctl, Toggle):
                head.addWidget(ctl, 0, Qt.AlignmentFlag.AlignVCenter)
            bl.addLayout(head)
            bl.addWidget(text if isinstance(text, QWidget) else label(text, 12, dim=True))
            if not isinstance(ctl, Toggle):
                bl.addSpacing(6)
                bl.addWidget(ctl, 0, Qt.AlignmentFlag.AlignLeft)
            bl.addStretch(1)
            grid.addWidget(box, i // 3, i % 3)
            self.anim_items.append(box)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder.setLayout(grid)
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        from .showcase import scroll_qss

        scroll.setStyleSheet(scroll_qss())
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)

    def enter(self):
        for clock in self.findChildren(Clock):
            clock.restart()
        for i, w in enumerate(self.anim_items):  # quicker, so twelve cards don't take long to arrive
            fade_in(w, delay_ms=40 + i * 35, duration=320, rise=10)

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
    _counted = Signal(object)  # (worlds, n_types, n_actions), from the background thread

    def __init__(self, choices: dict, office: dict[str, bool]):
        from PySide6.QtGui import QGuiApplication

        avail = QGuiApplication.primaryScreen().availableGeometry()
        super().__init__("Tapshift", QSize(min(1120, avail.width() - 60), min(780, avail.height() - 60)))
        self.choices = dict(choices)
        # Counted from the catalog (new conversions show up by themselves), on a thread: it takes a moment,
        # and the first page shouldn't wait for it.
        self._world_data = None
        self._world_ready = threading.Event()
        self._counted.connect(self._on_counted)

        def count():
            from .universe import gather

            try:
                data = gather()
            except Exception:  # noqa: BLE001 - the tour must still open
                data = ([], 0, 0)
            self._world_data = data
            self._world_ready.set()
            self._counted.emit(data)

        threading.Thread(target=count, daemon=True).start()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(12)
        self.stage = _Stage()
        lay.addWidget(self.stage, 1)
        self._factories = [HeroPage, HowPage, lambda: UniversePage(*self._worlds()),
                           lambda: ShowcasePage(self._worlds()[0]), MovesPage, lambda: SetupPage(self.choices),
                           self._ready_page]
        self.pages: list[Page | None] = [None] * len(self._factories)
        self._page(0)

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

    def _worlds(self):
        self._world_ready.wait()
        return self._world_data

    def _on_counted(self, data):
        hero = self.pages[0]
        if hero is not None and data[1]:
            hero.set_counts(data[1], data[2])

    def _ready_page(self):
        ready = ReadyPage()
        ready.try_samples.connect(self.try_samples.emit)
        return ready

    def _page(self, i: int) -> Page:
        """Build a page the first time it's needed."""
        if self.pages[i] is None:
            pg = self._factories[i]()
            pg.setParent(self.stage)
            pg.hide()
            self.pages[i] = pg
        return self.pages[i]

    def _prebuild(self, i: int):
        """Get the next page ready while you look at this one (so Next is instant)."""
        if 0 <= i < len(self.pages) and self.pages[i] is None and (i < 2 or self._world_ready.is_set()):
            self._page(i)

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
        new = self._page(i)
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
        QTimer.singleShot(1500, lambda n=i + 1: self._prebuild(n))
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
            if pg is not None:
                pg.leave()
        super().closeEvent(e)

