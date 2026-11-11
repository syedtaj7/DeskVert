"""Everything Tapshift converts, counted live from the catalog, shown kind by kind.

Nothing here is hard-coded: the worlds, their file types and their actions are
read from what the picker would offer, so every new conversion shows up in the
welcome tour by itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap

from . import theme
from .fx import Clock, clamp, ease_in_out, ease_out, font, mix, phase, with_alpha


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


WORLD_COLOR = {"pictures": "image", "pdf": "pdf", "office": "doc", "ebooks": "book", "data": "data", "sound": "audio",
               "subtitles": "sub", "text": "md", "mail": "mail", "maps": "map", "models": "model", "drawings": "cad",
               "fonts": "font", "archives": "zip"}


class FormatMap(Clock):
    """Every kind of file in a list; the chosen one gets a live story of what Tapshift does with it,
    its numbers, and every format it takes and gives, as chips.

    It steps through the kinds by itself, one full story each; point at a kind to see it, click to
    keep it. The list and chips are drawn once into a picture; only the story is drawn every frame."""

    FPS = 30
    CYCLE = 5.0  # one full story per kind (the stories are five seconds long)
    LIST_W = 236
    CHIP_H, LINE = 26.0, 32.0
    picked = Signal(object)  # World

    def __init__(self, worlds: list[World], n_types: int, n_actions: int, size=QSize(980, 450), parent=None):
        super().__init__(parent)
        from types import SimpleNamespace

        from . import showcase

        self.setFixedSize(size)
        self.setMouseTracking(True)
        self.worlds, self.n_types, self.n_actions = worlds, n_types, n_actions
        self._sc = showcase
        first = {}
        for wkey, story, *_ in showcase.CARDS:
            first.setdefault(wkey, story)
        self.stories = [showcase.STORIES.get(first.get(w.key, ""), showcase.a_generic) for w in worlds]
        self.story_cards = [SimpleNamespace(cycle=showcase._short_formats(w.actions), src=(w.exts or ["FILE"])[0])
                            for w in worlds]
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
        self.f_head = font(26, QFont.Weight.Bold, display=True)
        self.f_tag = font(13)
        self.f_num = font(28, QFont.Weight.Bold, display=True)
        self.f_label = font(11, QFont.Weight.Bold)
        self.f_chip = font(11.5, QFont.Weight.DemiBold)

    def restart(self):
        super().restart()
        self.sel_since = self.cycle_from = 0.0

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._static = None

    # ------------------------------------------------------------ geometry
    @property
    def x0(self) -> float:
        return self.LIST_W + 32

    @property
    def list_top(self) -> float:
        return 84.0

    @property
    def row_h(self) -> float:
        return min(28.0, (self.height() - self.list_top - 4) / max(1, len(self.worlds)))

    def _row_rect(self, i: int) -> QRectF:
        return QRectF(0, round(self.list_top + i * self.row_h), self.LIST_W, round(self.row_h) - 2)

    def _story_rect(self) -> QRectF:
        return QRectF(self.x0, 0, 330, 165)

    def _flow(self, words: list[str], top: float, lines: int, out: bool):
        """Chips wrapped into at most ``lines`` lines; the last one says how many more there are."""
        fm = QFontMetricsF(self.f_chip)
        left, right = self.x0, self.width() - 2
        widths = [min(fm.horizontalAdvance(w) + 24, 200) for w in words]
        placed, x, line = [], left, 0
        for k, (word, wd) in enumerate(zip(words, widths)):
            if x + wd > right:
                line += 1
                x = left
            if line >= lines:
                break
            placed.append([QRectF(x, top + line * self.LINE, wd, self.CHIP_H), word])
            x += wd + 6
        more = len(words) - len(placed)
        if more > 0:
            tag = f"+{more} more"
            wd = fm.horizontalAdvance(tag) + 24
            while placed and placed[-1][0].right() + 6 + wd > right:  # make room on the last line
                placed.pop()
                more += 1
                tag = f"+{more} more"
                wd = fm.horizontalAdvance(tag) + 24
            last = placed[-1][0] if placed else QRectF(left - 6, top, 0, 0)
            placed.append([QRectF(last.right() + 6, last.top(), wd, self.CHIP_H), tag])
        return placed, more

    def _sections(self):
        """(label y, chips) for what goes in and what comes out, fitted to the height there is."""
        w = self.worlds[self.sel]
        y_in = 186.0
        ins, more_in = self._flow(w.exts, y_in + 22, 2, False)
        used = max(1, round((ins[-1][0].top() - (y_in + 22)) / self.LINE) + 1) if ins else 1
        y_out = y_in + 22 + used * self.LINE + 12
        room = max(1, int((self.height() - (y_out + 22)) // self.LINE))
        outs, more_out = self._flow(w.actions, y_out + 22, room, True)
        return (y_in, ins, more_in), (y_out, outs, more_out)

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
        k = phase(t, self.sel_since, self.sel_since + 0.6)
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

    def _mini_icon(self, p: QPainter, r: QRectF, col: QColor) -> None:
        """A small file shape in the kind's colour."""
        fold = r.width() * 0.34
        path = QPainterPath()
        path.moveTo(r.left() + 2, r.top())
        path.lineTo(r.right() - fold, r.top())
        path.lineTo(r.right(), r.top() + fold)
        path.lineTo(r.right(), r.bottom() - 2)
        path.quadTo(r.right(), r.bottom(), r.right() - 2, r.bottom())
        path.lineTo(r.left() + 2, r.bottom())
        path.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - 2)
        path.lineTo(r.left(), r.top() + 2)
        path.quadTo(r.left(), r.top(), r.left() + 2, r.top())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPath(path)
        corner = QPainterPath()
        corner.moveTo(r.right() - fold, r.top())
        corner.lineTo(r.right() - fold, r.top() + fold)
        corner.lineTo(r.right(), r.top() + fold)
        corner.closeSubpath()
        p.setBrush(QColor(255, 255, 255, 110))
        p.drawPath(corner)

    def _color(self, i: int) -> QColor:
        return self._sc.COL.get(WORLD_COLOR.get(self.worlds[i].key, ""), theme.ACCENT)

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
        # the list of kinds, each with its colour
        for i, world in enumerate(self.worlds):
            r = self._row_rect(i)
            on = i == self.sel
            if on or i == self.hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(theme.ACCENT, 0.13) if on else theme.HOVER)
                p.drawRoundedRect(r, 7, 7)
            if on:  # the marker's track; _paint_live fills it as this kind's time runs
                p.setBrush(with_alpha(theme.ACCENT, 0.3))
                p.drawRoundedRect(self._marker(r), 2, 2)
            self._mini_icon(p, QRectF(r.left() + 13, r.center().y() - 7, 11, 14), self._color(i))
            p.setFont(self.f_row)
            p.setPen(theme.ACCENT if on else theme.TEXT)
            p.drawText(r.adjusted(32, 0, -70, 0), Qt.AlignmentFlag.AlignVCenter, world.title)
            p.setFont(self.f_row_n)
            p.setPen(theme.ACCENT if on else theme.DIM)
            p.drawText(r.adjusted(0, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       f"{len(world.exts)} → {len(world.actions)}")
        # the story's frame (the story itself moves, so _paint_live draws it)
        sr = self._story_rect()
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(sr, 14, 14)
        # the chosen kind: title, what it is, its numbers
        a = ease_out(k)
        hx = sr.right() + 24
        hw = self.width() - hx
        p.save()
        p.setOpacity(a)
        self._mini_icon(p, QRectF(hx, 8, 22, 28), self._color(self.sel))
        p.setFont(self.f_head)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(hx + 34, 2, hw - 34, 40), Qt.AlignmentFlag.AlignVCenter, w.title)
        p.setFont(self.f_tag)
        p.setPen(theme.DIM)
        p.drawText(QRectF(hx, 46, hw, 40), int(Qt.AlignmentFlag.AlignTop.value) | int(Qt.TextFlag.TextWordWrap.value),
                   w.tagline + ".")
        for j, (num, what) in enumerate(((len(w.exts), "file types in"), (len(w.actions), "ways out"))):
            x = hx + j * 128
            p.setFont(self.f_num)
            p.setPen(theme.ACCENT if j else theme.TEXT)
            p.drawText(QRectF(x, 92, 120, 40), left, str(num))
            p.setFont(self.f_cap)
            p.setPen(theme.DIM)
            p.drawText(QRectF(x, 130, 120, 18), left, what)
        hint = "Kept here. Click it again to move on." if self.pinned else "Click a kind to keep it here."
        p.drawText(QRectF(hx, 148, hw, 18), left, hint)
        p.restore()
        # every format in, every result out
        (y_in, ins, _), (y_out, outs, _) = self._sections()
        for y, label_, chips, out in ((y_in, "GOES IN", ins, False), (y_out, "COMES OUT", outs, True)):
            p.save()
            p.setOpacity(a)
            p.setFont(self.f_label)
            p.setPen(theme.DIM)
            p.drawText(QRectF(self.x0, y, 200, 18), left, label_)
            p.restore()
            for idx, (r, word) in enumerate(chips):
                e = ease_out(clamp(k * 2.2 - (0.35 if out else 0.0) - idx * 0.025))
                if e <= 0:
                    continue
                rr = r.translated(0, 8 * (1 - e))
                self._chip(p, rr, word, out, e, more=word.startswith("+") and word.endswith("more"))

    def _chip(self, p: QPainter, r: QRectF, word: str, out: bool, a: float, more: bool = False) -> None:
        p.save()
        p.setOpacity(p.opacity() * a)
        if more:
            p.setPen(QPen(theme.LINE, 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
        elif out:
            p.setPen(QPen(with_alpha(theme.ACCENT, 0.5), 1.1))
            p.setBrush(mix(theme.SURFACE, theme.ACCENT, 0.08))
        else:
            p.setPen(QPen(theme.LINE, 1.1))
            p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setFont(self.f_chip)
        fm = QFontMetricsF(self.f_chip)
        readable = theme.contrast(theme.ACCENT, theme.SURFACE) >= 4.5
        p.setPen(theme.DIM if more else (theme.ACCENT if out and readable else theme.TEXT))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, fm.elidedText(word, Qt.TextElideMode.ElideRight, r.width() - 14))
        p.restore()

    def _paint_live(self, p: QPainter, t: float, k: float) -> None:
        """What moves every frame: the chosen kind's story, and the time left on it."""
        sr = self._story_rect().adjusted(6, 6, -6, -6)
        s = min(sr.width() / 300, sr.height() / 150)
        st = (t - self.sel_since) % self._sc.LOOP
        n = int((t - self.sel_since) // self._sc.LOOP)
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(sr, 10, 10)
        p.setClipPath(clip)
        p.translate(sr.center().x() - 150 * s, sr.center().y() - 75 * s)
        p.scale(s, s)
        p.setOpacity(ease_out(k) * (1 - ease_in_out(phase(st, self._sc.LOOP - 0.4, self._sc.LOOP))))
        try:
            self.stories[self.sel](p, st, n, self.story_cards[self.sel])
        except Exception:  # noqa: BLE001 - a drawing problem must not break the tour
            pass
        p.restore()
        # the chosen row's marker fills top to bottom while it waits to move on (full when kept or pointed at)
        m = self._marker(self._row_rect(self.sel))
        done = 1.0 if (self.pinned or self.inside) else clamp((t - self.cycle_from) / self.CYCLE)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.ACCENT)
        p.drawRoundedRect(QRectF(m.left(), m.top(), m.width(), max(m.width(), m.height() * done)), 2, 2)

    @staticmethod
    def _marker(r: QRectF) -> QRectF:
        return QRectF(r.left() + 1, r.top() + 4, 4, r.height() - 8)
