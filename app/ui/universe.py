"""Everything Tapshift converts, counted live from the catalog, and drawn as a map.

Nothing here is hard-coded: the worlds, their file types and their actions are
read from what the picker would offer, so every new conversion shows up in the
welcome tour by itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap

from . import theme
from .fx import Clock, clamp, ease_out, font, mix, phase, with_alpha


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


# ====================================================================== the map


class FormatMap(Clock):
    """Every kind of file in a steady list; the chosen one's formats flow in through Tapshift
    and out as everything it can become. Nothing drifts or wobbles: the list and the chips stay
    put (drawn once into a picture), and only small dots travel along the threads.

    Point at a kind to see it (it also steps through them by itself); click to keep one."""

    FPS = 30
    CYCLE = 3.6  # seconds per kind while you just watch
    LIST_W = 236
    picked = Signal(object)  # World

    def __init__(self, worlds: list[World], n_types: int, n_actions: int, size=QSize(980, 450), parent=None):
        super().__init__(parent)
        self.setFixedSize(size)
        self.setMouseTracking(True)
        self.worlds, self.n_types, self.n_actions = worlds, n_types, n_actions
        self.sel = 0
        self.sel_since = 0.0
        self.hover = -1
        self.pinned = False
        self.inside = False
        self.cycle_from = 0.0
        self._static: QPixmap | None = None
        self._static_key = None
        self.f_big = font(34, QFont.Weight.Bold, display=True)
        self.f_cap = font(11)
        self.f_row = font(13, QFont.Weight.DemiBold)
        self.f_row_n = font(11)
        self.f_head = font(22, QFont.Weight.Bold, display=True)
        self.f_tag = font(13)
        self.f_chip = font(11, QFont.Weight.DemiBold)
        self.f_hub = font(13, QFont.Weight.Bold, display=True)
        self._layout()

    def restart(self):
        super().restart()
        self.sel_since = self.cycle_from = 0.0

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout()
        self._static = None

    # ------------------------------------------------------------ geometry
    def _layout(self) -> None:
        w, h = self.width(), self.height()
        n = len(self.worlds)
        self.list_top = 84
        self.row_h = min(28.0, (h - self.list_top - 4) / max(1, n))
        self.in_cols, self.in_w, self.in_h, self.gap = 3, 66.0, 26.0, 6.0
        self.out_cols, self.out_w = 2, 150.0
        self.in_x = self.LIST_W + 28
        self.out_x = w - (self.out_cols * self.out_w + (self.out_cols - 1) * 8)
        self.in_right = self.in_x + self.in_cols * self.in_w + (self.in_cols - 1) * self.gap
        self.hub = QPointF(round((self.in_right + self.out_x) / 2), round(60 + (h - 70) / 2 + 6))
        self.hub_r = 46.0

    def _row_rect(self, i: int) -> QRectF:
        return QRectF(0, round(self.list_top + i * self.row_h), self.LIST_W, round(self.row_h) - 2)

    def _grid(self, words: list[str], x: float, cols: int, cw: float, max_rows: int = 8):
        """Chip rectangles, centred on the hub's height: (rects with words, how many left out, rows, top)."""
        cap = cols * max_rows
        shown = words if len(words) <= cap else words[:cap - 1]
        rows = max(1, (len(shown) + cols - 1) // cols)
        top = round(self.hub.y() - (rows * self.in_h + (rows - 1) * self.gap) / 2)
        step = cw + (8 if cols == 2 else self.gap)
        rects = [(QRectF(x + (k % cols) * step, top + (k // cols) * (self.in_h + self.gap), cw, self.in_h), word)
                 for k, word in enumerate(shown)]
        return rects, len(words) - len(shown), rows, top

    # ------------------------------------------------------------ interaction
    def _row_at(self, pos: QPointF) -> int:
        if 0 <= pos.x() <= self.LIST_W:
            i = int((pos.y() - self.list_top) // self.row_h)
            if 0 <= i < len(self.worlds):
                return i
        return -1

    def _select(self, i: int) -> None:
        if i != self.sel and 0 <= i < len(self.worlds):
            self.sel = i
            self.sel_since = self.t
            self.picked.emit(self.worlds[i])
        self.cycle_from = self.t

    def mouseMoveEvent(self, e):
        self.inside = True
        i = self._row_at(e.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if i >= 0 else Qt.CursorShape.ArrowCursor)
        if i != self.hover:
            self.hover = i
            if i >= 0 and not self.pinned:
                self._select(i)

    def mousePressEvent(self, e):
        i = self._row_at(e.position())
        if i >= 0:
            self.pinned = not (self.pinned and i == self.sel)
            self._select(i)

    def leaveEvent(self, _):
        self.inside = False
        self.hover = -1
        self.cycle_from = self.t

    # ------------------------------------------------------------ painting
    def paintEvent(self, _):
        t = self.t
        if not self.pinned and not self.inside and t - self.cycle_from > self.CYCLE:
            self._select((self.sel + 1) % len(self.worlds))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        k = phase(t, self.sel_since, self.sel_since + 0.45)
        count = ease_out(phase(t, 0.1, 1.2))
        if k < 1 or count < 1:  # changing: draw it all
            self._paint_static(p, k, count)
        else:  # settled: a picture of it all, drawn once
            key = (self.sel, self.hover, self.pinned, self.width(), self.height())
            if self._static is None or self._static_key != key:
                dpr = self.devicePixelRatioF()
                pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
                pm.setDevicePixelRatio(dpr)
                pm.fill(Qt.GlobalColor.transparent)
                q = QPainter(pm)
                q.setRenderHint(QPainter.RenderHint.Antialiasing)
                q.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                self._paint_static(q, 1.0, 1.0)
                q.end()
                self._static, self._static_key = pm, key
            p.drawPixmap(0, 0, self._static)
        self._paint_live(p, t, k)
        p.end()

    def _paint_static(self, p: QPainter, k: float, count: float) -> None:
        w = self.worlds[self.sel]
        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        # totals, counted live from the picker
        p.setFont(self.f_big)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(0, 0, 110, 44), left, str(int(round(self.n_types * count))))
        p.drawText(QRectF(118, 0, 118, 44), left, str(int(round(self.n_actions * count))))
        p.setFont(self.f_cap)
        p.setPen(theme.DIM)
        p.drawText(QRectF(0, 44, 110, 18), left, "file types in")
        p.drawText(QRectF(118, 44, 118, 18), left, "ways out")
        # the list of kinds
        for i, world in enumerate(self.worlds):
            r = self._row_rect(i)
            on = i == self.sel
            if on or i == self.hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(theme.ACCENT, 0.13) if on else theme.HOVER)
                p.drawRoundedRect(r, 7, 7)
            if on:
                p.setBrush(theme.ACCENT)
                p.drawRoundedRect(QRectF(r.left(), r.top() + 5, 3, r.height() - 10), 1.5, 1.5)
            p.setFont(self.f_row)
            p.setPen(theme.ACCENT if on else theme.TEXT)
            p.drawText(r.adjusted(12, 0, -70, 0), Qt.AlignmentFlag.AlignVCenter, world.title)
            p.setFont(self.f_row_n)
            p.setPen(theme.ACCENT if on else theme.DIM)
            p.drawText(r.adjusted(0, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       f"{len(world.exts)} → {len(world.actions)}")
        # the chosen kind: what goes in, what comes out
        a = ease_out(k)
        x0 = self.in_x
        p.setOpacity(a)
        p.setFont(self.f_head)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(x0, 0, self.width() - x0, 34), Qt.AlignmentFlag.AlignVCenter, w.title)
        p.setFont(self.f_tag)
        p.setPen(theme.DIM)
        hint = "   ·   kept here (click again to move on)" if self.pinned else "   ·   click a kind to keep it"
        p.drawText(QRectF(x0, 34, self.width() - x0, 22), Qt.AlignmentFlag.AlignVCenter, w.tagline + hint)
        p.setOpacity(1.0)
        ins, more_in, rows_in, top_in = self._grid(w.exts, self.in_x, self.in_cols, self.in_w)
        outs, more_out, rows_out, top_out = self._grid(w.actions, self.out_x, self.out_cols, self.out_w)
        # threads: one per row of chips, into the hub and out of it
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(theme.TEXT, 0.14 * a), 1.3))
        for path in self._threads(ins, outs):
            p.drawPath(path)
        for idx, (r, word) in enumerate(ins):
            self._chip(p, r, word, False, ease_out(clamp(k * 1.8 - idx * 0.02)))
        for idx, (r, word) in enumerate(outs):
            self._chip(p, r, word, True, ease_out(clamp(k * 1.8 - 0.25 - idx * 0.02)))
        p.setOpacity(a)
        p.setFont(self.f_cap)
        p.setPen(theme.DIM)
        if more_in > 0:
            p.drawText(QRectF(self.in_x, top_in + rows_in * (self.in_h + self.gap), 200, 18),
                       Qt.AlignmentFlag.AlignVCenter, f"+{more_in} more")
        if more_out > 0:
            p.drawText(QRectF(self.out_x, top_out + rows_out * (self.in_h + self.gap), 200, 18),
                       Qt.AlignmentFlag.AlignVCenter, f"+{more_out} more")
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.drawText(QRectF(self.in_x, 66, 200, 18), Qt.AlignmentFlag.AlignVCenter, "GOES IN")
        p.drawText(QRectF(self.out_x, 66, 200, 18), Qt.AlignmentFlag.AlignVCenter, "COMES OUT")
        p.setOpacity(1.0)
        # the hub
        p.setPen(QPen(theme.ACCENT, 2))
        p.setBrush(theme.SURFACE)
        p.drawEllipse(self.hub, self.hub_r, self.hub_r)
        p.setFont(self.f_hub)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(self.hub.x() - self.hub_r, self.hub.y() - 18, 2 * self.hub_r, 20),
                   Qt.AlignmentFlag.AlignCenter, "Tapshift")
        p.setFont(self.f_cap)
        p.setPen(theme.DIM)
        p.drawText(QRectF(self.hub.x() - self.hub_r, self.hub.y() + 2, 2 * self.hub_r, 16),
                   Qt.AlignmentFlag.AlignCenter, "and checked")

    def _chip(self, p: QPainter, r: QRectF, word: str, out: bool, a: float) -> None:
        if a <= 0:
            return
        p.save()
        p.setOpacity(p.opacity() * a)
        p.setPen(QPen(with_alpha(theme.ACCENT, 0.55) if out else theme.LINE, 1.1))
        p.setBrush(mix(theme.SURFACE, theme.ACCENT, 0.07) if out else theme.SURFACE)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setFont(self.f_chip)
        fm = QFontMetricsF(self.f_chip)
        readable = theme.contrast(theme.ACCENT, theme.SURFACE) >= 4.5
        p.setPen(theme.ACCENT if out and readable else theme.TEXT)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, fm.elidedText(word, Qt.TextElideMode.ElideRight, r.width() - 12))
        p.restore()

    def _threads(self, ins, outs) -> list[QPainterPath]:
        paths = []
        hub, hr = self.hub, self.hub_r
        for y in sorted({r.center().y() for r, _ in ins}):
            a, b = QPointF(self.in_right + 6, y), QPointF(hub.x() - hr, hub.y())
            mid = (a.x() + b.x()) / 2
            path = QPainterPath(a)
            path.cubicTo(QPointF(mid, a.y()), QPointF(mid, b.y()), b)
            paths.append(path)
        for y in sorted({r.center().y() for r, _ in outs}):
            a, b = QPointF(hub.x() + hr, hub.y()), QPointF(self.out_x - 6, y)
            mid = (a.x() + b.x()) / 2
            path = QPainterPath(a)
            path.cubicTo(QPointF(mid, a.y()), QPointF(mid, b.y()), b)
            paths.append(path)
        return paths

    def _paint_live(self, p: QPainter, t: float, k: float) -> None:
        """What moves every frame: dots along the threads, and the time left on this kind."""
        w = self.worlds[self.sel]
        ins, *_ = self._grid(w.exts, self.in_x, self.in_cols, self.in_w)
        outs, *_ = self._grid(w.actions, self.out_x, self.out_cols, self.out_w)
        p.setPen(Qt.PenStyle.NoPen)
        a = ease_out(k)
        for j, path in enumerate(self._threads(ins, outs)):
            f = (t * 0.55 + j * 0.173) % 1.0
            p.setBrush(with_alpha(theme.ACCENT, a * (0.3 + 0.7 * math.sin(math.pi * f))))
            p.drawEllipse(path.pointAtPercent(f), 3.0, 3.0)
        r = self._row_rect(self.sel)
        if self.pinned:
            p.setBrush(theme.ACCENT)
            p.drawEllipse(QPointF(r.right() - 64, r.center().y()), 3, 3)
        elif not self.inside:
            done = clamp((t - self.cycle_from) / self.CYCLE)
            p.setBrush(with_alpha(theme.ACCENT, 0.5))
            p.drawRoundedRect(QRectF(r.left() + 12, r.bottom() - 3, (r.width() - 24) * done, 2), 1, 1)
