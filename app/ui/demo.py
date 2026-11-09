"""An animated, looping demo of how Tapshift works (used in the welcome tour
and the guide). Everything is painted, so it's crisp at any size and costs
nothing when not on screen."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen

from . import theme
from .fx import (Clock, accent_gradient, clamp, ease_back, ease_in_out, ease_out, font, mix, paint_check,
                 paint_cursor, paint_file_icon, paint_keycap, phase, with_alpha)

LOOP = 10.0

CAPTIONS = [
    (0.0, "1", "Select a file in File Explorer"),
    (1.7, "2", "Tap Ctrl + Shift together"),
    (3.0, "3", "Pick a format on the wheel"),
    (5.0, "4", "Done: saved right next to the original"),
]


class DemoScene(Clock):
    def __init__(self, parent=None, width: int = 600, height: int = 330):
        super().__init__(parent)
        self.setFixedSize(QSize(width, height))

    # coordinates are designed for 600x330 and scaled to the widget size
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        sx, sy = self.width() / 600, self.height() / 330
        p.scale(sx, sy)
        t = self.t % LOOP
        fade = ease_out(phase(t, 0, 0.5)) * (1 - ease_in_out(phase(t, LOOP - 0.6, LOOP)))
        p.setOpacity(fade)

        # ---------------- explorer window
        win = QRectF(18, 14, 380, 232)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(win, theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)
        # Windows-style title bar: folder name on the left, window controls on the right.
        p.setPen(theme.TEXT)
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.drawText(QRectF(win.left() + 14, win.top(), 200, 34), Qt.AlignmentFlag.AlignVCenter, "Pictures")
        ctl = QPen(theme.DIM, 1.1)
        p.setPen(ctl)
        cx, cy = win.right() - 18, win.top() + 17
        p.drawLine(QPointF(cx - 4, cy - 4), QPointF(cx + 4, cy + 4))
        p.drawLine(QPointF(cx + 4, cy - 4), QPointF(cx - 4, cy + 4))
        p.drawRect(QRectF(cx - 32, cy - 4, 8, 8))
        p.drawLine(QPointF(cx - 60, cy), QPointF(cx - 52, cy))
        p.setPen(QPen(theme.LINE, 1))
        p.drawLine(QPointF(win.left(), win.top() + 34), QPointF(win.right(), win.top() + 34))

        tiles = [("image", "beach.heic", ""), ("doc", "report.docx", "DOC"), ("slides", "pitch.pptx", "PPT")]
        new_in = ease_back(phase(t, 7.0, 7.5))
        positions = []
        for i in range(4):
            x = win.left() + 22 + i * 90
            positions.append(QRectF(x, win.top() + 52, 76, 106))
        selected = ease_out(phase(t, 1.05, 1.3)) * (1 - phase(t, 8.6, 9.0))
        for i, (kind, name, lbl) in enumerate(tiles):
            r = positions[i]
            if i == 0 and selected > 0:
                p.setPen(QPen(with_alpha(theme.ACCENT_A, selected), 1.6))
                p.setBrush(with_alpha(theme.ACCENT_A, 0.14 * selected))
                p.drawRoundedRect(r.adjusted(-6, -6, 6, 6), theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)
            paint_file_icon(p, QRectF(r.left() + 12, r.top() + 4, 52, 64), kind, lbl)
            p.setPen(theme.TEXT)
            p.setFont(font(10.5))
            p.drawText(QRectF(r.left() - 8, r.top() + 74, r.width() + 16, 20), Qt.AlignmentFlag.AlignCenter, name)
        if new_in > 0:
            r = positions[3]
            p.save()
            c = r.center()
            p.translate(c)
            p.scale(new_in, new_in)
            p.translate(-c)
            p.setPen(QPen(with_alpha(theme.SUCCESS, 1 - phase(t, 7.6, 8.6)), 1.6))
            p.setBrush(with_alpha(theme.SUCCESS, 0.14 * (1 - phase(t, 7.6, 8.6))))
            p.drawRoundedRect(r.adjusted(-6, -6, 6, 6), theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)
            paint_file_icon(p, QRectF(r.left() + 12, r.top() + 4, 52, 64), "image")
            p.setPen(theme.TEXT)
            p.setFont(font(10.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(r.left() - 8, r.top() + 74, r.width() + 16, 20), Qt.AlignmentFlag.AlignCenter, "beach.webp")
            p.restore()
            self._sparkles(p, positions[3].center(), phase(t, 7.0, 8.0))

        # ---------------- keycaps
        keys_in = ease_out(phase(t, 1.5, 1.8)) * (1 - ease_out(phase(t, 3.0, 3.3)))
        if keys_in > 0:
            press = ease_out(phase(t, 2.0, 2.15)) * (1 - ease_out(phase(t, 2.45, 2.6)))
            p.save()
            p.setOpacity(fade * keys_in)
            p.translate(0, (1 - keys_in) * 12)
            paint_keycap(p, QRectF(118, 186, 82, 48), "Ctrl", press, press)
            p.setPen(theme.DIM)
            p.setFont(font(20, QFont.Weight.Bold))
            p.drawText(QRectF(200, 186, 30, 48), Qt.AlignmentFlag.AlignCenter, "+")
            paint_keycap(p, QRectF(230, 186, 96, 48), "Shift", press, press)
            p.restore()

        # ---------------- wheel
        wheel_in = ease_back(phase(t, 2.65, 3.05), 1.3) * (1 - ease_in_out(phase(t, 4.55, 4.85)))
        hover = phase(t, 3.75, 3.85) > 0
        if wheel_in > 0.01:
            self._wheel(p, QPointF(452, 130), 108 * wheel_in, wheel_in, hover, phase(t, 4.35, 4.55))

        # ---------------- progress card
        card_in = ease_out(phase(t, 4.9, 5.3)) * (1 - ease_in_out(phase(t, 8.7, 9.2)))
        if card_in > 0:
            self._card(p, card_in, phase(t, 5.3, 6.5), phase(t, 6.55, 7.1))

        # ---------------- cursor
        cur = self._cursor_pos(t)
        click = max(self._ripple(t, 1.1), self._ripple(t, 4.4))
        if click > 0:
            p.setPen(QPen(with_alpha(theme.ACCENT_A, 1 - click), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cur, 6 + 18 * click, 6 + 18 * click)
        paint_cursor(p, cur, 1.15)

        # ---------------- caption
        p.setOpacity(fade)
        self._caption(p, t)
        p.end()

    # ------------------------------------------------------------- pieces
    def _cursor_pos(self, t: float) -> QPointF:
        path = [(0.0, (330, 300)), (0.4, (330, 300)), (1.05, (70, 110)), (2.9, (70, 110)),
                (3.75, (518, 166)), (4.6, (518, 166)), (5.6, (560, 300)), (LOOP, (560, 300))]
        for (t0, a), (t1, b) in zip(path, path[1:]):
            if t <= t1:
                k = ease_in_out(phase(t, t0, t1))
                return QPointF(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
        return QPointF(*path[-1][1])

    @staticmethod
    def _ripple(t: float, at: float) -> float:
        k = phase(t, at, at + 0.45)
        return k if 0 < k < 1 else 0.0

    def _wheel(self, p: QPainter, c: QPointF, R: float, alpha: float, hover: bool, chosen: float):
        paint_wheel(p, c, R, alpha, "WEBP" if hover else None)


    def _card(self, p: QPainter, appear: float, prog: float, done: float):
        p.save()
        p.setOpacity(p.opacity() * appear)
        x = 600 - (1 - appear) * 40
        r = QRectF(x - 236, 196, 220, 76)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(theme.SHADOW, 0.5))
        p.drawRoundedRect(r.adjusted(2, 6, 2, 6), theme.RADIUS_CARD, theme.RADIUS_CARD)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, theme.RADIUS_CARD, theme.RADIUS_CARD)
        ic = QPointF(r.left() + 24, r.top() + 24)
        if done > 0:
            paint_check(p, ic, 26, done)
        else:
            pen = QPen(theme.ACCENT_A, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            spin = int((self.t * 360) % 360)
            p.drawArc(QRectF(ic.x() - 9, ic.y() - 9, 18, 18), spin * 16, 270 * 16)
        p.setPen(theme.TEXT)
        p.setFont(font(12, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + 46, r.top() + 12, 170, 18), Qt.AlignmentFlag.AlignVCenter,
                   "Saved beach.webp" if done > 0.3 else "Converting to WEBP")
        p.setPen(theme.DIM)
        p.setFont(font(10))
        p.drawText(QRectF(r.left() + 46, r.top() + 30, 170, 14), Qt.AlignmentFlag.AlignVCenter,
                   "Checked: identical to the original" if done > 0.3 else "beach.heic")
        bar = QRectF(r.left() + 46, r.top() + 54, 156, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.TRACK)
        p.drawRoundedRect(bar, 3, 3)
        fill = ease_in_out(prog)
        if fill > 0:
            fr = QRectF(bar.left(), bar.top(), max(6, bar.width() * fill), bar.height())
            if done > 0:
                p.setBrush(mix(theme.ACCENT_A, theme.SUCCESS, done))
            else:
                p.setBrush(QBrush(accent_gradient(fr.left(), 0, fr.right(), 0)))
            p.drawRoundedRect(fr, 3, 3)
        p.restore()

    def _sparkles(self, p: QPainter, c: QPointF, k: float):
        if not 0 < k < 1:
            return
        p.save()
        for i in range(8):
            a = i * math.pi / 4 + 0.3
            d = 30 + 34 * ease_out(k)
            pos = QPointF(c.x() + d * math.cos(a), c.y() + d * math.sin(a))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(theme.ACCENT_A if i % 2 else theme.SUCCESS, 1 - k))
            s = 3.2 * (1 - k * 0.6)
            p.drawEllipse(pos, s, s)
        p.restore()

    def _caption(self, p: QPainter, t: float):
        idx = max(i for i, (start, _, _) in enumerate(CAPTIONS) if t >= start)
        start, num, text = CAPTIONS[idx]
        k = ease_out(phase(t, start, start + 0.35))
        y = 292 + (1 - k) * 8
        p.save()
        p.setOpacity(p.opacity() * k)
        badge = QRectF(18, y, 26, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(accent_gradient(badge.left(), badge.top(), badge.right(), badge.bottom())))
        p.drawEllipse(badge)
        p.setPen(theme.ON_ACCENT)
        p.setFont(font(12, QFont.Weight.Bold))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, num)
        p.setPen(theme.TEXT)
        p.setFont(font(15, QFont.Weight.DemiBold, display=True))
        p.drawText(QRectF(56, y - 2, 520, 30), Qt.AlignmentFlag.AlignVCenter, text)
        p.restore()


def paint_wheel(p: QPainter, c: QPointF, R: float, alpha: float = 1.0, selected: str | None = None,
                labels: tuple = ("JPG", "PNG", "WEBP", "PDF", "HEIC", "AVIF"), center: str = "1 HEIC"):
    """A picture of the format wheel with one format highlighted (used by the demo and the welcome page)."""
    hover = selected is not None
    if True:
        n = len(labels)
        span = 360 / n
        r = R * 0.42
        p.save()
        p.setOpacity(p.opacity() * clamp(alpha))
        glow = QRectF(c.x() - R - 14, c.y() - R - 14, 2 * R + 28, 2 * R + 28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(theme.SHADOW, 0.5))
        p.drawEllipse(glow.adjusted(4, 10, 4, 10))
        p.setBrush(theme.BG)
        p.setPen(QPen(theme.LINE, 1))
        p.drawEllipse(c, R + 8, R + 8)
        outer = QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R)
        inner = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        for i, lbl in enumerate(labels):
            mid = 90 - i * span
            start = mid + span / 2
            path = QPainterPath()
            path.arcMoveTo(outer, start)
            path.arcTo(outer, start, -span)
            path.arcTo(inner, start - span, span)
            path.closeSubpath()
            on = lbl == selected
            if on:
                p.fillPath(path, theme.ACCENT)
            else:
                p.fillPath(path, theme.SLICE)
            p.setPen(QPen(theme.SLICE_EDGE, 2.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            a = math.radians(mid)
            rr = (r + R) / 2
            pos = QPointF(c.x() + rr * math.cos(a), c.y() - rr * math.sin(a))
            p.setPen(theme.ON_ACCENT if on else theme.TEXT)
            p.setFont(font(max(7, R * 0.12), QFont.Weight.Bold))
            p.drawText(QRectF(pos.x() - 30, pos.y() - 10, 60, 20), Qt.AlignmentFlag.AlignCenter, lbl)
        p.setPen(QPen(theme.LINE, 1.2))
        p.setBrush(theme.CENTER)
        p.drawEllipse(c, r - 5, r - 5)
        p.setPen(theme.TEXT)
        p.setFont(font(max(7, R * 0.11), QFont.Weight.Bold))
        p.drawText(QRectF(c.x() - r, c.y() - 14, 2 * r, 16), Qt.AlignmentFlag.AlignCenter, center)
        p.setPen(theme.ACCENT if hover else theme.DIM)
        p.setFont(font(max(6, R * 0.085), QFont.Weight.DemiBold))
        p.drawText(QRectF(c.x() - r, c.y() + 1, 2 * r, 14), Qt.AlignmentFlag.AlignCenter,
                   f"→ {selected}" if hover else "convert to")
        p.restore()
