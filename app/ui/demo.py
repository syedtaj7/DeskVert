"""An animated, looping demo of how Deskvert works (used in the welcome tour
and the guide). Everything is painted, so it's crisp at any size and costs
nothing when not on screen."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap

from . import theme
from .fx import (Clock, clamp, ease_back, ease_in_out, ease_out, font, mix, paint_check, paint_cursor,
                 paint_file_icon, paint_keycap, phase, with_alpha)

LOOP = 11.0

STEPS = [
    (0.0, "Select files", "In File Explorer or on the desktop. One file or many."),
    (1.6, "Tap Ctrl + Shift", "Both keys together, then let go. Nothing to open."),
    (2.9, "Point and click", "The web opens right where you are. Pick what you want."),
    (4.7, "Saved next to it", "Checked first. Your original is never touched."),
]
CAPTIONS = [(start, str(i + 1), title) for i, (start, title, _) in enumerate(STEPS)]

STAGE_W, STAGE_H = 700.0, 420.0
PANEL_W = 270.0
PICK_C, PICK_R = QPointF(486, 250), 100.0
TILES = [("image", "beach.heic", ""), ("doc", "report.docx", "DOC"), ("slides", "pitch.pptx", "PPT"),
         ("sheet", "budget.xlsx", "XLS"), ("pdf", "notes.pdf", "PDF")]


def _tile_rect(i: int) -> QRectF:
    row, col = divmod(i, 5)
    return QRectF(170 + col * 104, 86 + row * 124, 92, 108)


class DemoScene(Clock):
    """How Deskvert works, acted out in a File Explorer window: select, tap, point, saved.

    Steady by design: the window and the picker are drawn once into pictures and only placed
    each frame, so nothing shimmers; just the pointer, a highlight and the progress move.
    With ``steps`` the four steps are listed on the left and follow along."""

    FPS = 40

    def __init__(self, parent=None, width: int = 600, height: int = 330, steps: bool = False):
        super().__init__(parent)
        self.steps = steps
        self.setFixedSize(QSize(width, height))
        self.base_w = (PANEL_W + STAGE_W) if steps else STAGE_W
        self.base_h = STAGE_H if steps else STAGE_H + 52
        self._cache: dict = {}

    # ------------------------------------------------------------ layout
    def _scale(self) -> float:
        return min(self.width() / self.base_w, self.height() / self.base_h)

    def resizeEvent(self, e):
        self._cache.clear()
        super().resizeEvent(e)

    @staticmethod
    def _blit(p: QPainter, pm: QPixmap, x: float, y: float) -> None:
        """Copy a prepared picture pixel for pixel (no scaling, so it's cheap and sharp)."""
        at = p.transform().map(QPointF(x, y))
        p.save()
        p.resetTransform()
        p.drawPixmap(round(at.x()), round(at.y()), pm)
        p.restore()

    def _pixmap(self, key, w: float, h: float, draw):
        """A picture of something that doesn't change, at the screen's real resolution."""
        if key not in self._cache:
            dpr = self.devicePixelRatioF()
            s = self._scale() * dpr
            pm = QPixmap(max(1, math.ceil(w * s)), max(1, math.ceil(h * s)))
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            q.scale(s, s)
            draw(q)
            q.end()
            pm.setDevicePixelRatio(dpr)  # one picture pixel per screen pixel when copied
            self._cache[key] = pm
        return self._cache[key]

    # ------------------------------------------------------------ painting
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        s = self._scale()
        p.translate((self.width() - self.base_w * s) / 2, (self.height() - self.base_h * s) / 2)
        p.scale(s, s)
        t = self.t % LOOP
        if self.steps:
            cur = max(i for i, (start, _, _) in enumerate(STEPS) if t >= start)
            final = cur == len(STEPS) - 1 and t > 6.7
            self._blit(p, self._pixmap(("panel", cur, final), PANEL_W, STAGE_H,
                                       lambda q: self._panel(q, cur, final)), 0, 0)
            self._panel_lines(p, t, cur)
            p.translate(PANEL_W, 0)
        fade = ease_out(phase(t, 0, 0.4)) * (1 - ease_in_out(phase(t, LOOP - 0.6, LOOP)))
        p.setOpacity(fade)
        self._blit(p, self._pixmap("window", STAGE_W, STAGE_H, self._window), 0, 0)
        self._live(p, t)
        p.setOpacity(1.0)
        if not self.steps:
            self._caption(p, t)
        p.end()

    def _window(self, p: QPainter):
        """File Explorer, as a still picture (files, folders, the address bar)."""
        win = QRectF(0.5, 0.5, STAGE_W - 1, STAGE_H - 1)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(win, 10, 10)
        p.setPen(theme.TEXT)
        p.setFont(font(12, QFont.Weight.DemiBold))
        p.drawText(QRectF(16, 0, 200, 38), Qt.AlignmentFlag.AlignVCenter, "Pictures")
        p.setPen(QPen(theme.DIM, 1.1))
        cx, cy = STAGE_W - 22, 19
        p.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
        p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))
        p.drawRect(QRectF(cx - 40, cy - 5, 10, 10))
        p.drawLine(QPointF(cx - 74, cy), QPointF(cx - 64, cy))
        # address bar
        bar = QRectF(84, 42, STAGE_W - 100, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.SURFACE2)
        p.drawRoundedRect(bar, 6, 6)
        p.setPen(QPen(theme.DIM, 1.4))
        for x, d in ((22, 1), (48, -1)):  # back, forward
            p.drawLine(QPointF(x + 4 * d, 50), QPointF(x - 4 * d, 55))
            p.drawLine(QPointF(x - 4 * d, 55), QPointF(x + 4 * d, 60))
        p.setPen(theme.DIM)
        p.setFont(font(11))
        p.drawText(bar.adjusted(12, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, "This PC   ›   Pictures")
        p.setPen(QPen(theme.LINE, 1))
        p.drawLine(QPointF(0, 76), QPointF(STAGE_W, 76))
        p.drawLine(QPointF(150, 76), QPointF(150, STAGE_H - 30))
        p.drawLine(QPointF(0, STAGE_H - 30), QPointF(STAGE_W, STAGE_H - 30))
        # folders on the left
        for i, name in enumerate(("Home", "Desktop", "Downloads", "Documents", "Pictures", "Music")):
            r = QRectF(8, 88 + i * 32, 134, 28)
            if name == "Pictures":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.HOVER)
                p.drawRoundedRect(r, 6, 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(240, 190, 70))
            p.drawRoundedRect(QRectF(r.left() + 10, r.top() + 9, 14, 11), 2, 2)
            p.setPen(theme.TEXT)
            p.setFont(font(11.5, QFont.Weight.DemiBold if name == "Pictures" else QFont.Weight.Normal))
            p.drawText(r.adjusted(32, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, name)
        # files
        for i, (kind, name, lbl) in enumerate(TILES):
            r = _tile_rect(i)
            paint_file_icon(p, QRectF(r.center().x() - 27, r.top() + 8, 54, 66), kind, lbl)
            p.setPen(theme.TEXT)
            p.setFont(font(11))
            p.drawText(QRectF(r.left() - 6, r.top() + 80, r.width() + 12, 20), Qt.AlignmentFlag.AlignCenter, name)

    def _picker(self, selected: str | None):
        e = PICK_R * 1.36 + 16
        return self._pixmap(("picker", selected), 2 * e, 2 * e,
                            lambda q: paint_orbit(q, QPointF(e, e), PICK_R, 1.0, selected, 0.0, "1 HEIC")), e

    def _live(self, p: QPainter, t: float):
        # the selected file
        sel = ease_out(phase(t, 1.1, 1.3)) * (1 - phase(t, 9.4, 9.8))
        if sel > 0:
            r = _tile_rect(0).adjusted(-4, -4, 4, 4)
            p.setPen(QPen(with_alpha(theme.ACCENT, sel), 1.6))
            p.setBrush(with_alpha(theme.ACCENT, 0.12 * sel))
            p.drawRoundedRect(r, 8, 8)
        # the new file, saved next to the original
        new = ease_back(phase(t, 6.6, 7.1))
        if new > 0:
            r = _tile_rect(5)
            glow = 1 - phase(t, 7.2, 8.4)
            p.save()
            p.translate(r.center())
            p.scale(new, new)
            p.translate(-r.center())
            p.setPen(QPen(with_alpha(theme.SUCCESS, glow), 1.6))
            p.setBrush(with_alpha(theme.SUCCESS, 0.12 * glow))
            p.drawRoundedRect(r.adjusted(-4, -4, 4, 4), 8, 8)
            paint_file_icon(p, QRectF(r.center().x() - 27, r.top() + 8, 54, 66), "image")
            p.setPen(theme.TEXT)
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.drawText(QRectF(r.left() - 6, r.top() + 80, r.width() + 12, 20), Qt.AlignmentFlag.AlignCenter,
                       "beach.webp")
            p.restore()
            self._sparkles(p, r.center(), phase(t, 6.6, 7.6))
        # status bar
        status = ("6 items" if t >= 6.6 else "1 item selected   2.4 MB" if sel > 0.5 else "5 items")
        p.setPen(theme.DIM)
        p.setFont(font(11))
        p.drawText(QRectF(16, STAGE_H - 30, 300, 30), Qt.AlignmentFlag.AlignVCenter, status)
        # Ctrl + Shift
        keys = ease_out(phase(t, 1.6, 1.9)) * (1 - ease_out(phase(t, 2.55, 2.8)))
        if keys > 0:
            press = ease_out(phase(t, 2.05, 2.18)) * (1 - ease_out(phase(t, 2.4, 2.52)))
            p.save()
            p.setOpacity(p.opacity() * keys)
            p.translate(0, (1 - keys) * 10)
            paint_keycap(p, QRectF(330, 286, 92, 54), "Ctrl", press, press)
            p.setPen(theme.DIM)
            p.setFont(font(22, QFont.Weight.Bold))
            p.drawText(QRectF(422, 286, 34, 54), Qt.AlignmentFlag.AlignCenter, "+")
            paint_keycap(p, QRectF(456, 286, 104, 54), "Shift", press, press)
            p.restore()
        # the picker: pops up where you are, still while you point
        show = ease_out(phase(t, 2.6, 2.95)) * (1 - ease_in_out(phase(t, 4.35, 4.65)))
        if show > 0.01:
            pop = 0.86 + 0.14 * ease_back(phase(t, 2.6, 3.0), 1.4) - 0.06 * phase(t, 4.35, 4.65)
            hover = phase(t, 3.72, 3.9)
            p.save()
            p.translate(PICK_C)
            p.scale(pop, pop)
            p.translate(-PICK_C)
            base = p.opacity()
            for selected, a in ((None, 1.0), ("WEBP", hover)):  # the pointed-at picture lands on top
                if a > 0:
                    pm, e = self._picker(selected)
                    p.setOpacity(base * show * a)
                    if abs(pop - 1) < 0.002:  # at rest: a straight copy
                        self._blit(p, pm, PICK_C.x() - e, PICK_C.y() - e)
                    else:  # popping in or out: scaled, for a few frames only
                        p.drawPixmap(QRectF(PICK_C.x() - e, PICK_C.y() - e, 2 * e, 2 * e), pm, QRectF(pm.rect()))
            p.restore()
        # progress, then saved
        card = ease_out(phase(t, 4.7, 5.05)) * (1 - ease_in_out(phase(t, 8.8, 9.2)))
        if card > 0:
            self._card(p, card, phase(t, 5.05, 6.2), phase(t, 6.2, 6.7))
        # the pointer
        cur = self._cursor_pos(t)
        click = max(self._ripple(t, 1.05), self._ripple(t, 4.15))
        if click > 0:
            p.setPen(QPen(with_alpha(theme.ACCENT, 1 - click), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cur, 6 + 18 * click, 6 + 18 * click)
        paint_cursor(p, cur, 1.15)

    def _cursor_pos(self, t: float) -> QPointF:
        webp = orbit_layout(PICK_C, PICK_R, 0.0)["WEBP"][0]
        tile = _tile_rect(0).center()
        path = [(0.0, (620, 380)), (0.2, (620, 380)), (1.0, (tile.x() + 6, tile.y() - 2)),
                (3.0, (tile.x() + 6, tile.y() - 2)), (3.75, (webp.x() + 3, webp.y() + 4)),
                (4.4, (webp.x() + 3, webp.y() + 4)), (5.3, (640, 250)), (LOOP, (640, 250))]
        for (t0, a), (t1, b) in zip(path, path[1:]):
            if t <= t1:
                k = ease_in_out(phase(t, t0, t1))
                return QPointF(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
        return QPointF(*path[-1][1])

    @staticmethod
    def _ripple(t: float, at: float) -> float:
        k = phase(t, at, at + 0.45)
        return k if 0 < k < 1 else 0.0

    def _card(self, p: QPainter, appear: float, prog: float, done: float):
        p.save()
        p.setOpacity(p.opacity() * appear)
        r = QRectF(STAGE_W - 262, STAGE_H - 30 - 92 + (1 - appear) * 16, 246, 80)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(theme.SHADOW, 0.5))
        p.drawRoundedRect(r.adjusted(2, 6, 2, 6), theme.RADIUS_CARD, theme.RADIUS_CARD)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, theme.RADIUS_CARD, theme.RADIUS_CARD)
        ic = QPointF(r.left() + 26, r.top() + 26)
        if done > 0:
            paint_check(p, ic, 28, done)
        else:
            pen = QPen(theme.ACCENT, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(ic.x() - 9, ic.y() - 9, 18, 18), int((self.t * 360) % 360) * 16, 270 * 16)
        p.setPen(theme.TEXT)
        p.setFont(font(12.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + 50, r.top() + 12, 190, 18), Qt.AlignmentFlag.AlignVCenter,
                   "Saved beach.webp" if done > 0.3 else "Converting to WEBP")
        p.setPen(theme.DIM)
        p.setFont(font(10.5))
        p.drawText(QRectF(r.left() + 50, r.top() + 31, 190, 16), Qt.AlignmentFlag.AlignVCenter,
                   "Checked against the original" if done > 0.3 else "beach.heic")
        bar = QRectF(r.left() + 50, r.top() + 58, 178, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.TRACK)
        p.drawRoundedRect(bar, 3, 3)
        fill = ease_in_out(prog)
        if fill > 0:
            p.setBrush(mix(theme.ACCENT, theme.SUCCESS, done))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(6, bar.width() * fill), bar.height()), 3, 3)
        p.restore()

    def _sparkles(self, p: QPainter, c: QPointF, k: float):
        if not 0 < k < 1:
            return
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(8):
            a = i * math.pi / 4 + 0.3
            d = 42 + 30 * ease_out(k)
            p.setBrush(with_alpha(theme.ACCENT if i % 2 else theme.SUCCESS, 1 - k))
            s = 3.2 * (1 - k * 0.6)
            p.drawEllipse(QPointF(c.x() + d * math.cos(a), c.y() + d * math.sin(a)), s, s)
        p.restore()

    ROW_H = 96.0

    def _row_top(self, i: int) -> float:
        return (STAGE_H - self.ROW_H * len(STEPS)) / 2 + 8 + i * self.ROW_H

    def _panel_lines(self, p: QPainter, t: float, cur: int):
        """The line between steps fills as each one finishes (the only moving part of the list)."""
        for i in range(min(cur + 1, len(STEPS) - 1)):
            fill = phase(t, STEPS[i][0], STEPS[i + 1][0])
            if fill > 0:
                c = QPointF(18, self._row_top(i) + 16)
                p.setPen(QPen(theme.ACCENT, 2))
                p.drawLine(QPointF(c.x(), c.y() + 18), QPointF(c.x(), c.y() + 18 + (self.ROW_H - 36) * fill))

    def _panel(self, p: QPainter, cur: int, final: bool):
        """The four steps (a still picture per step; _panel_lines adds the progress)."""
        row_h = self.ROW_H
        for i, (start, title, detail) in enumerate(STEPS):
            y = self._row_top(i)
            c = QPointF(18, y + 16)
            if i < len(STEPS) - 1:
                p.setPen(QPen(theme.LINE, 2))
                p.drawLine(QPointF(c.x(), c.y() + 18), QPointF(c.x(), c.y() + row_h - 18))
            done_ = i < cur or (i == cur and final)
            on = i == cur
            if done_:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(theme.SUCCESS, 0.16))
                p.drawEllipse(c, 15, 15)
                paint_check(p, c, 26, 1.0, ring=False)
            else:
                p.setPen(QPen(theme.ACCENT if on else theme.LINE, 1.6))
                p.setBrush(theme.ACCENT if on else theme.SURFACE)
                p.drawEllipse(c, 15, 15)
                p.setPen(theme.ON_ACCENT if on else theme.DIM)
                p.setFont(font(13, QFont.Weight.Bold))
                p.drawText(QRectF(c.x() - 15, c.y() - 15, 30, 30), Qt.AlignmentFlag.AlignCenter, str(i + 1))
            p.setPen(theme.TEXT if (on or done_) else theme.DIM)
            p.setFont(font(16, QFont.Weight.Bold if on else QFont.Weight.DemiBold, display=True))
            p.drawText(QRectF(46, y + 2, PANEL_W - 60, 28), Qt.AlignmentFlag.AlignVCenter, title)
            p.setPen(theme.DIM)
            p.setFont(font(12.5))
            p.drawText(QRectF(46, y + 30, PANEL_W - 64, 44),
                       int(Qt.AlignmentFlag.AlignTop.value) | int(Qt.TextFlag.TextWordWrap.value), detail)

    def _caption(self, p: QPainter, t: float):
        idx = max(i for i, (start, _, _) in enumerate(CAPTIONS) if t >= start)
        start, num, text = CAPTIONS[idx]
        k = ease_out(phase(t, start, start + 0.35))
        y = STAGE_H + 16
        p.save()
        p.setOpacity(k)
        badge = QRectF(4, y, 28, 28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.ACCENT)
        p.drawEllipse(badge)
        p.setPen(theme.ON_ACCENT)
        p.setFont(font(13, QFont.Weight.Bold))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, num)
        p.setPen(theme.TEXT)
        p.setFont(font(16, QFont.Weight.DemiBold, display=True))
        p.drawText(QRectF(44, y - 2, 600, 32), Qt.AlignmentFlag.AlignVCenter, text)
        p.restore()


ORBIT_TOOLS = ("Compress", "Read text")
ORBIT_FORMATS = ("JPG", "PNG", "WEBP", "PDF", "HEIC", "AVIF")


def orbit_layout(c: QPointF, R: float, spin: float = 0.0, tools=ORBIT_TOOLS, formats=ORBIT_FORMATS):
    """Planet centres of the painted orbit: {label: (point, radius, is_tool)}.
    R is the outer orbit's radius; the inner orbit turns the other way."""
    pr = R * 0.19
    hub = R * 0.29
    ri = hub + pr + R * 0.04
    out = {}
    for rr, labels, turn, tool in ((ri, tools, -1.4 * spin, True), (R, formats, spin, False)):
        n = len(labels)
        for k, lbl in enumerate(labels):
            a = math.radians(-90 + k * 360 / n + (180 / n if not tool else 0) + turn)
            out[lbl] = (QPointF(c.x() + rr * math.cos(a), c.y() + rr * math.sin(a)), pr, tool)
    return out


def paint_orbit(p: QPainter, c: QPointF, R: float, alpha: float = 1.0, selected: str | None = None,
                spin: float = 0.0, center: str = "1 HEIC"):
    """A picture of the Orbit picker with one option highlighted (used by the demo and the welcome page)."""
    if R < 4:
        return
    p.save()
    p.setOpacity(p.opacity() * clamp(alpha))
    planets = orbit_layout(c, R, spin)
    pr = R * 0.19
    hub = R * 0.29
    ri = hub + pr + R * 0.04
    # backing disc, so the orbit reads as one object over whatever is behind it
    edge = R + pr * 1.3 + R * 0.05
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(with_alpha(theme.SHADOW, 0.45))
    p.drawEllipse(QPointF(c.x() + 3, c.y() + 9), edge + 3, edge + 3)
    p.setPen(QPen(theme.LINE, 1))
    p.setBrush(theme.BG)
    p.drawEllipse(c, edge, edge)
    # orbits
    for rr, dash in ((ri, [3, 6]), (R, [0.1, 5.5])):
        pen = QPen(with_alpha(theme.TEXT, 0.18), 1.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setDashPattern(dash)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, rr, rr)
    # tether to the highlighted option
    if selected in planets:
        pt, r, _ = planets[selected]
        ang = math.atan2(pt.y() - c.y(), pt.x() - c.x())
        d = math.hypot(pt.x() - c.x(), pt.y() - c.y())
        p.setPen(QPen(with_alpha(theme.ACCENT, 0.85), max(1.2, R * 0.016)))
        p.drawLine(QPointF(c.x() + math.cos(ang) * (hub + 2), c.y() + math.sin(ang) * (hub + 2)),
                   QPointF(c.x() + math.cos(ang) * (d - r * 1.1), c.y() + math.sin(ang) * (d - r * 1.1)))
    # planets
    for lbl, (pt, r, tool) in planets.items():
        on = lbl == selected
        rr = r * (1.12 if on else 1.0)
        if on:
            p.setPen(QPen(with_alpha(theme.ACCENT, 0.3), max(1.5, R * 0.02)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(pt, rr + R * 0.04, rr + R * 0.04)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ACCENT)
        else:
            p.setPen(QPen(theme.LINE, 1))
            p.setBrush(theme.SURFACE2)
        p.drawEllipse(pt, rr, rr)
        f = font(max(6.0, r * 0.44), QFont.Weight.Bold, display=True)
        fm = QFontMetrics(f)
        w = fm.horizontalAdvance(lbl)
        if w > rr * 1.72:  # shrink long labels to fit inside the planet
            f = font(max(5.0, r * 0.44 * rr * 1.72 / w), QFont.Weight.Bold, display=True)
        p.setFont(f)
        p.setPen(theme.ON_ACCENT if on else (theme.TEXT if selected is None else with_alpha(theme.TEXT, 0.7)))
        p.drawText(QRectF(pt.x() - rr, pt.y() - rr * 0.36, 2 * rr, rr), Qt.AlignmentFlag.AlignCenter, lbl)
        dot = QPointF(pt.x(), pt.y() - rr * 0.48)
        if tool:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ON_ACCENT if on else theme.ACCENT)
            p.drawEllipse(dot, max(1.4, r * 0.09), max(1.4, r * 0.09))
        else:
            p.setPen(QPen(theme.ON_ACCENT if on else theme.DIM, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(dot, max(1.3, r * 0.08), max(1.3, r * 0.08))
    # hub
    p.setPen(QPen(theme.LINE, 1.2))
    p.setBrush(theme.SURFACE)
    p.drawEllipse(c, hub, hub)
    p.setPen(theme.TEXT)
    p.setFont(font(max(7, R * 0.105), QFont.Weight.Bold, display=True))
    p.drawText(QRectF(c.x() - hub, c.y() - R * 0.13, 2 * hub, R * 0.13), Qt.AlignmentFlag.AlignCenter, center)
    p.setPen(theme.ACCENT if selected else theme.DIM)
    p.setFont(font(max(6, R * 0.08), QFont.Weight.DemiBold))
    p.drawText(QRectF(c.x() - hub, c.y() + R * 0.01, 2 * hub, R * 0.12), Qt.AlignmentFlag.AlignCenter,
               f"→ {selected}" if selected else "pick one")
    p.restore()


paint_wheel = paint_orbit  # older name
