"""Everything Tapshift converts, counted live from the catalog, and drawn as a small universe.

Nothing here is hard-coded: the worlds, their file types and their actions are
read from what the picker would offer, so every new conversion shows up in the
welcome tour by itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetricsF, QPainter, QPen

from . import theme
from .fx import Clock, clamp, ease_back, ease_out, font, mix, phase, with_alpha


@dataclass
class World:
    key: str
    title: str
    tagline: str
    exts: list[str] = field(default_factory=list)  # file types in
    actions: list[str] = field(default_factory=list)  # what comes out (labels, as the picker shows them)


# (key, title, tagline, extension sets) — the sets come from the catalog at run time.
def _definitions():
    from .. import catalog, toolbox

    pictures = set(catalog.IMAGE_EXTS)
    office = set(catalog.WORD_EXTS) | set(catalog.EXCEL_EXTS) | set(catalog.PPT_EXTS)
    return [
        ("pictures", "Pictures", "Phone photos, screenshots, RAW, icons", pictures),
        ("pdf", "PDF", "Compress, split, protect, convert", {".pdf"}),
        ("office", "Documents", "Word, Excel, PowerPoint", office),
        ("ebooks", "E-books", "EPUB, Kindle-free, comics", set(toolbox.EBOOK_EXTS)),
        ("data", "Data", "CSV, Excel, JSON, YAML, contacts", set(toolbox.DATA_EXTS)),
        ("sound", "Sound", "Music, recordings, video soundtracks", set(toolbox.AUDIO_EXTS) | set(toolbox.VIDEO_EXTS)),
        ("subtitles", "Subtitles", "Every caption format", set(toolbox.SUBTITLE_EXTS)),
        ("text", "Markdown", "Notes into clean documents", set(toolbox.MARKDOWN_EXTS)),
        ("mail", "Mail & pages", "Saved e-mails and web pages", set(toolbox.MAIL_EXTS)),
        ("maps", "Maps", "GPS tracks, places, routes", set(toolbox.MAP_EXTS)),
        ("models", "3D models", "Print, view, share", set(toolbox.MODEL_EXTS)),
        ("drawings", "Drawings", "CAD plans, Illustrator", set(toolbox.DRAWING_EXTS) | set(toolbox.VECTOR_EXTS)),
        ("fonts", "Fonts", "Desktop and web fonts", set(toolbox.FONT_EXTS)),
        ("archives", "Archives", "Unpack, repack, shrink", set(toolbox.ARCHIVE_EXTS)),
    ]


PACK_KEYS = {"archive.zip", "archive.7z", "archive.targz"}


def gather() -> tuple[list[World], int, int]:
    """(worlds, file types in, distinct actions). Asks the catalog what it would offer for each type."""
    from ..catalog import offers_for
    from ..settings import Settings

    s = Settings()
    worlds: list[World] = []
    every_ext: set[str] = set()
    every_key: set[str] = set()
    probe = Path("C:/tapshift-tour")  # never read: offers depend on the name only
    for key, title, tagline, exts in _definitions():
        w = World(key, title, tagline, sorted(e.lstrip(".").upper() for e in exts))
        labels: dict[str, None] = {}
        for e in sorted(exts):
            try:
                offers, _ = offers_for([probe / f"sample{e}"], s)
            except Exception:  # noqa: BLE001 - the tour must open even if one probe fails
                continue
            for o in offers:
                every_key.add(o.target.key)
                if o.target.key not in PACK_KEYS:
                    labels.setdefault(o.target.label, None)
        for e in (".jpg", ".pdf"):  # actions that need two files (merge, stitch, animate...)
            if e in exts:
                offers, _ = offers_for([probe / f"a{e}", probe / f"b{e}"], s)
                for o in offers:
                    if o.target.combine:
                        every_key.add(o.target.key)
                        if o.target.key not in PACK_KEYS:
                            labels.setdefault(o.target.label, None)
        w.actions = list(labels)
        every_ext |= exts
        worlds.append(w)
    return worlds, len(every_ext), len(every_key)


# ====================================================================== the painted universe


class Universe(Clock):
    """Worlds orbit a live counter. Point at one (or watch it cycle) and its file types and
    actions burst out around the centre."""

    FPS = 30
    DRIFT_SECONDS = 8.0  # the worlds drift for a while, then hold still (no frames drawn while still)
    picked = Signal(object)  # World

    def __init__(self, worlds: list[World], n_types: int, n_actions: int, size=QSize(900, 440), parent=None):
        super().__init__(parent)
        self.setFixedSize(size)
        self.setMouseTracking(True)
        self.worlds, self.n_types, self.n_actions = worlds, n_types, n_actions
        self.sel = 0
        self.sel_since = 0.0  # when the current world was chosen (for the burst)
        self.hover = -1
        self.pinned = False
        self.user_until = 0.0  # the pointer was here recently: don't auto-cycle
        self.rot = 0.0
        self._last = None
        self.f_title = font(15, QFont.Weight.Bold, display=True)
        self.f_chip = font(11, QFont.Weight.DemiBold)
        self.f_small = font(11)
        self.f_big = font(46, QFont.Weight.Bold, display=True)
        self.positions: list[tuple[QPointF, float]] = []
        from PySide6.QtCore import QTimer

        self._cycle = QTimer(self)  # the little self-guided tour: next world every few seconds
        self._cycle.setInterval(3200)
        self._cycle.timeout.connect(self._auto_next)

    def showEvent(self, e):
        super().showEvent(e)
        self._cycle.start()

    def hideEvent(self, e):
        self._cycle.stop()
        super().hideEvent(e)

    def _auto_next(self):
        if not self.pinned and self.t > self.user_until:
            self._select((self.sel + 1) % len(self.worlds))

    def _wake(self):
        if not self._timer.isActive():
            self._last = self.t
            self._timer.start()

    # ------------------------------------------------------------ layout
    def _place(self) -> None:
        c = QPointF(self.width() * 0.5, self.height() * 0.52)
        rx, ry = self.width() * 0.43, self.height() * 0.36
        n = len(self.worlds)
        self.positions = []
        for i in range(n):
            a = self.rot + i * 2 * math.pi / n
            depth = (math.sin(a) + 1) / 2  # 0 back, 1 front
            self.positions.append((QPointF(c.x() + math.cos(a) * rx, c.y() + math.sin(a) * ry), depth))

    def _radius(self, i: int) -> float:
        depth = self.positions[i][1]
        r = 26 + 12 * depth
        if i == self.sel:
            r *= 1.0 + 0.22 * ease_back(phase(self.t, self.sel_since, self.sel_since + 0.45))
        return r

    # ------------------------------------------------------------ interaction
    def _at(self, pos: QPointF) -> int:
        best, bd = -1, 1e9
        for i, (pt, _d) in enumerate(self.positions):
            d = math.hypot(pt.x() - pos.x(), pt.y() - pos.y())
            if d < self._radius(i) + 8 and d < bd:
                best, bd = i, d
        return best

    def _select(self, i: int) -> None:
        if i != self.sel and 0 <= i < len(self.worlds):
            self.sel = i
            self.sel_since = self.t
            self.picked.emit(self.worlds[i])
            self._wake()

    def mouseMoveEvent(self, e):
        self.user_until = self.t + 4.0
        i = self._at(e.position())
        if i != self.hover:
            self._wake()
        self.hover = i
        self.setCursor(Qt.CursorShape.PointingHandCursor if i >= 0 else Qt.CursorShape.ArrowCursor)
        if i >= 0 and not self.pinned:
            self._select(i)

    def mousePressEvent(self, e):
        i = self._at(e.position())
        if i >= 0:
            self.pinned = not (self.pinned and i == self.sel)
            self._select(i)

    def leaveEvent(self, _):
        self.hover = -1
        self.user_until = self.t + 1.5

    # ------------------------------------------------------------ painting
    def paintEvent(self, _):
        t = self.t
        dt = 0.0 if self._last is None else min(0.05, t - self._last)
        self._last = t
        drifting = self.hover < 0 and t < self.DRIFT_SECONDS
        if drifting:
            self.rot += dt * 0.08  # slow drift at first; stops while you point at a world
        self._place()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        c = QPointF(self.width() * 0.5, self.height() * 0.52)
        appear = ease_out(phase(t, 0.0, 0.9))

        # orbit path
        p.setPen(QPen(with_alpha(theme.TEXT, 0.10), 1, Qt.PenStyle.DotLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, self.width() * 0.43 * appear, self.height() * 0.36 * appear)

        world = self.worlds[self.sel]
        burst = phase(t, self.sel_since, self.sel_since + 0.9)
        # threads from the chosen world to the centre
        sp, _sd = self.positions[self.sel]
        p.setPen(QPen(theme.ACCENT, 2))
        k = ease_out(burst)
        p.drawLine(sp, QPointF(sp.x() + (c.x() - sp.x()) * k, sp.y() + (c.y() - sp.y()) * k))

        # worlds, back to front
        order = sorted(range(len(self.worlds)), key=lambda i: self.positions[i][1])
        for i in order:
            if i == self.sel:
                continue
            self._world(p, i, appear)
        self._centre(p, c, world, appear)
        self._world(p, self.sel, appear)
        p.end()
        # nothing moving: stop drawing frames until something changes (a new world, the pointer)
        if not drifting and t > 1.5 and t - self.sel_since > 1.0:
            self._timer.stop()

    def _world(self, p: QPainter, i: int, appear: float) -> None:
        pt, depth = self.positions[i]
        r = self._radius(i) * ease_back(clamp(appear * 1.2 - i * 0.03))
        if r <= 1:
            return
        w = self.worlds[i]
        on = i == self.sel
        p.setPen(QPen(theme.ACCENT if on else theme.LINE, 2 if on else 1.2))
        p.setBrush(theme.ACCENT if on else mix(theme.SURFACE2, theme.SURFACE, 1 - depth))
        p.drawEllipse(pt, r, r)
        f = font(9.5 + 2.5 * depth + (1.5 if on else 0), QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(theme.ON_ACCENT if on else theme.TEXT)
        fm = QFontMetricsF(f)
        title = w.title if fm.horizontalAdvance(w.title) < r * 1.9 else w.title.split()[0]
        p.drawText(QRectF(pt.x() - r, pt.y() - r * 0.55, 2 * r, r * 0.8), Qt.AlignmentFlag.AlignCenter, title)
        p.setFont(font(8.5 + 2 * depth))
        p.setPen(with_alpha(theme.ON_ACCENT, 0.85) if on else theme.DIM)
        p.drawText(QRectF(pt.x() - r, pt.y() + r * 0.05, 2 * r, r * 0.6), Qt.AlignmentFlag.AlignCenter,
                   f"{len(w.exts)} in · {len(w.actions)} out")

    def _centre(self, p: QPainter, c: QPointF, w: World, appear: float) -> None:
        t = self.t
        # the big live count (counts up once)
        count = ease_out(phase(t, 0.2, 1.4))
        n1, n2 = int(round(self.n_types * count)), int(round(self.n_actions * count))
        box = QRectF(c.x() - 170, c.y() - 112, 340, 70)
        p.setFont(self.f_big)
        p.setPen(theme.TEXT)
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, f"{n1}  ·  {n2}")
        p.setFont(self.f_small)
        p.setPen(theme.DIM)
        p.drawText(QRectF(c.x() - 200, c.y() - 46, 400, 18), Qt.AlignmentFlag.AlignCenter,
                   "file types in  ·  ways out  ·  all on your PC")
        # the chosen world's contents, bursting out of the centre
        burst = phase(t, self.sel_since, self.sel_since + 0.9)
        p.setFont(self.f_title)
        p.setPen(theme.ACCENT)
        p.drawText(QRectF(c.x() - 220, c.y() - 22, 440, 24), Qt.AlignmentFlag.AlignCenter,
                   f"{w.title}  —  {w.tagline}")
        self._chips(p, c, w.exts[:18], c.y() + 10, theme.SURFACE2, theme.TEXT, burst, 0.0, "in")
        self._chips(p, c, w.actions[:14], c.y() + 44, theme.SURFACE, theme.ACCENT, burst, 0.25, "out")
        rest_in, rest_out = len(w.exts) - 18, len(w.actions) - 14
        if (rest_in > 0 or rest_out > 0) and burst > 0.6:
            p.setFont(self.f_small)
            p.setPen(theme.DIM)
            more = " · ".join(x for x in (f"+{rest_in} more types" if rest_in > 0 else "",
                                          f"+{rest_out} more actions" if rest_out > 0 else "") if x)
            p.drawText(QRectF(c.x() - 200, c.y() + 74, 400, 18), Qt.AlignmentFlag.AlignCenter, more)

    def _chips(self, p, c, words, y, fill, ink, burst, delay, _kind) -> None:
        p.setFont(self.f_chip)
        fm = QFontMetricsF(self.f_chip)
        widths = [fm.horizontalAdvance(w) + 16 for w in words]
        maxw = self.width() * 0.62
        rows, row, rw = [], [], 0.0
        for w, wd in zip(words, widths):
            if row and rw + wd > maxw:
                rows.append((row, rw))
                row, rw = [], 0.0
            row.append((w, wd))
            rw += wd + 6
        if row:
            rows.append((row, rw))
        rows = rows[:1]  # one tidy line each for "in" and "out"
        for row, rw in rows:
            x = c.x() - (rw - 6) / 2
            for k, (w, wd) in enumerate(row):
                s = ease_back(phase(burst, delay + k * 0.03, delay + k * 0.03 + 0.35))
                if s <= 0.01:
                    x += wd + 6
                    continue
                # chips fly out from the centre to their place
                tx, ty = x + wd / 2, y + 11
                cx, cy = c.x() + (tx - c.x()) * s, c.y() - 30 + (ty - c.y() + 30) * s
                r = QRectF(cx - wd / 2 * s, cy - 11 * s, wd * s, 22 * s)
                p.setPen(QPen(ink if ink == theme.ACCENT else theme.LINE, 1.2))
                p.setBrush(fill)
                p.drawRoundedRect(r, 11 * s, 11 * s)
                if s > 0.6:
                    p.setPen(ink)
                    p.drawText(r, Qt.AlignmentFlag.AlignCenter, w)
                x += wd + 6
