"""Orbit: the picker shown when you tap the shortcut.

Tools circle on one orbit and formats on the other. Point at one and the
drift stops, the option leans toward the pointer, and a small card on the
side says what it does. Holds up to ~20 options before adding a "More" planet,
so new tools and converters can keep joining without a redesign.

Built to stay smooth on low-end laptops:
- planets, hub, orbits and the side card are drawn once into pixmaps, so a
  frame is a handful of blits;
- the frame clock runs only while something moves (60 fps for motion, 30 fps
  for the slow idle drift) and stops completely when everything is still;
- motion is time-based, so a late frame never makes anything jump or crawl;
- Windows' "Show animations" setting (Accessibility) turns the motion off.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ..catalog import Offer
from . import theme
from .fx import display_family

# ---------------------------------------------------------------- what each option does (short on purpose)

BLURBS = {
    "compress.image": "Pick a size, or a form photo preset",
    "image.jpg": "Smaller photo that opens anywhere",
    "image.png": "Lossless, keeps transparency",
    "image.webp": "Small and sharp, made for the web",
    "image.pdf": "One page per picture",
    "image.pdf_combined": "All the pictures in one PDF",
    "image.heic": "Small files, full photo quality",
    "image.avif": "The smallest modern photo format",
    "image.ico": "A Windows icon, 16 to 256 px",
    "image.tiff": "Lossless, for print and archives",
    "image.gif": "Simple animation, 256 colors",
    "image.bmp": "Plain, uncompressed bitmap",
    "image.tga": "Uncompressed, for games and 3D",
    "ocr.txt": "Copy the words out of a picture or scan",
    "ocr.pdf": "Make a scan searchable",
    "archive.zip": "Pack everything into one .zip",
    "archive.extract": "Unpack into a new folder",
    "archive.tozip": "Repack as a standard ZIP",
    "pdf.compress": "Smaller PDF, even under 200 KB",
    "pdf.pages": "Keep or remove pages",
    "pdf.lock": "Needs a password to open",
    "pdf.unlock": "Removes the password",
    "pdf.numbers": "Numbers on every page",
    "pdf.watermark": "Text stamped on every page",
    "pdf.rotate": "Turn pages the right way up",
    "pdf.merge": "Join the PDFs in folder order",
    "pdf.png": "Each page as a PNG image",
    "pdf.jpg": "Each page as a JPG image",
    "pdf.txt": "All the text, without layout",
    "pdf.split": "One PDF per page",
    "pdf.splithalf": "Two PDFs: first half and second half",
    "pdf.splitevery": "Parts of the same size, like 2 pages each",
    "pdf.splitranges": "Your own parts, like 1-3 and 4-10",
    "pdf.reorder": "Pages in the order you type",
    "pdf.reverse": "Last page first",
    "pdf.nup": "2, 4, 6 or 9 pages on each A4 sheet",
    "imgedit.rotl": "Turned 90° to the left",
    "imgedit.rotr": "Turned 90° to the right",
    "imgedit.rot180": "Turned upside down",
    "imgedit.flip": "A mirror image",
    "imgedit.gray": "Black and white",
    "imgedit.resize": "A smaller copy: half, or 1920 px and less",
    "imgedit.clean": "No location or camera details, ready to share",
    "imgedit.stitch": "One long picture, one under the other",
    "subtitle.vtt": "Subtitles for web video players",
    "subtitle.srt": "Subtitles for TVs, VLC and editors",
    "ebook.pdf": "The book on A5 pages",
    "ebook.txt": "All the words, without layout",
    "data.yaml": "Easy-to-read data, same values",
    "data.jsonl": "One record per line",
    "data.toml": "A settings file, same values",
    "data.xml": "Same data as XML",
    "data.tsv": "Tab separated, every cell the same",
    "data.sheets": "Every sheet as its own CSV",
    "data.vcf": "Contacts for phones and Outlook",
    "data.vcsv": "Contacts as a table",
    "data.vxlsx": "Contacts in Excel",
    "subtitle.ass": "Styled subtitles (Aegisub)",
    "subtitle.sami": "SAMI subtitles for older players",
    "subtitle.ttml": "TTML for broadcast and streaming",
    "subtitle.lrc": "Timed song lyrics",
    "subtitle.microdvd": "Frame-based subtitles",
    "ebook.epub": "A reflowable e-book with chapters",
    "ebook.cbz": "Pages as pictures for comic readers",
    "pdf.tiff": "Every page in one TIFF",
    "pdf.longimg": "All pages in one tall picture",
    "pdf.md": "Text and headings as Markdown",
    "pdf.html": "Text and pictures as a web page",
    "imgedit.dpi": "Print size, without touching pixels",
    "imgedit.anim": "Pictures as a looping GIF",
    "vector.pdf": "Vector PDF, sharp at any zoom",
    "vector.svgz": "The same drawing, compressed",
    "vector.svg": "The same drawing, uncompressed",
    "vector.png": "A picture of the drawing",
    "archive.7z": "One small 7Z archive",
    "archive.targz": "One TAR.GZ for Linux and Mac",
    "archive.to7z": "The archive as 7Z",
    "archive.totargz": "The archive as TAR.GZ",
    "font.woff": "Web font for pages",
    "font.eot": "Web font for old Internet Explorer",
    "font.sfnt": "An installable desktop font",
    "mesh.stl": "For 3D printing",
    "mesh.obj": "For 3D apps like Blender",
    "mesh.glb": "For the web, AR and games",
    "mesh.3mf": "For modern 3D printers",
    "mesh.ply": "For 3D scanning tools",
    "mesh.png": "A shaded picture of the model",
    "cad.pdf": "The drawing as a vector PDF",
    "cad.svg": "The drawing for the web",
    "cad.png": "A picture of the drawing",
    "mail.pdf": "The page or e-mail as a PDF",
    "mail.html": "One self-contained web page",
    "mail.txt": "Just the text",
    "mail.md": "Text with headings as Markdown",
    "mail.zip": "The attachments in one ZIP",
    "geo.kml": "For Google Earth and Maps",
    "geo.geojson": "For web maps and GIS",
    "geo.gpx": "For GPS apps and watches",
    "geo.kmz": "Compressed KML",
    "geo.csv": "One row per place",
    "geo.xlsx": "Places in Excel",
    "textdoc.md": "The page as Markdown",
    "media.mp3": "Sound that plays everywhere",
    "media.m4a": "Smaller sound, great on iPhone",
    "media.wav": "Lossless sound for editing",
    "media.flac": "Lossless sound, smaller than WAV",
    "media.wma": "Windows Media sound",
    "pdf.flatten": "Form fields can't be changed any more",
    "pdf.clean": "Removes author and other hidden details",
    "pdf.pictures": "Saves the pictures inside the PDF",
    "pdf.gray": "Black and white, smaller to upload",
    "mixed.pdf": "Pictures and PDFs in one PDF, in your order",
    "doc.pdf": "Looks exactly like it does in Office",
    "doc.docx": "Modern Word document",
    "doc.doc": "Older Word, for older apps",
    "doc.odt": "OpenDocument, for LibreOffice",
    "doc.rtf": "Simple formatted text",
    "doc.txt": "Just the words",
    "doc.xlsx": "Modern Excel workbook",
    "doc.xls": "Older Excel, for older apps",
    "doc.csv": "First sheet as plain values",
    "doc.ods": "OpenDocument spreadsheet",
    "doc.pptx": "Modern PowerPoint",
    "doc.ppt": "Older PowerPoint",
    "doc.odp": "OpenDocument slides",
    "doc.png": "Each slide as a PNG image",
    "doc.jpg": "Each slide as a JPG image",
    "data.xlsx": "Opens straight in Excel",
    "data.json": "Rows as a list of records",
    "data.csv": "A table that opens anywhere",
    "data.tidy": "Indented and easy to read",
    "data.minify": "Smallest, without spaces",
    "textdoc.pdf": "A clean A4 document",
    "textdoc.html": "A web page",
    "textdoc.docx": "Edit it in Word",
    "docread.txt": "Just the words, no Office needed",
    "docread.md": "Headings and lists, no Office needed",
    "docread.html": "A web page, no Office needed",
    "iwork.pdf": "The PDF preview Apple keeps inside",
    "iwork.jpg": "The first page, as a picture",
    "pdf.tables": "Every table, one Excel sheet each",
    "pdf.blank": "Take out the empty pages",
    "imgedit.crop": "Square, 4:5, 16:9 and more",
    "imgedit.passport": "Passport photos on one 4×6 print",
    "imgedit.wmark": "Your name or © on the picture",
    "sqlitedb.xlsx": "Every table in Excel, read-only",
    "sqlitedb.csv": "One CSV per table",
    "config.json": "Settings as JSON",
    "config.yaml": "Settings as YAML",
    "ics.xlsx": "Every event as a row in Excel",
    "ics.csv": "Every event as a row",
    "notebook.html": "Notes, code and charts in one page",
    "notebook.md": "Notes and code as Markdown",
    "notebook.py": "Just the code, as a script",
    "subtitle.shift": "Fix subtitles that are out of sync",
    "hash.sha256": "A fingerprint to check files later",
    "webpage.pdf": "The whole page, sharp and searchable",
    "webpage.png": "The whole page as one long picture",
    "qr.png": "A code any phone camera opens",
    "media.trim": "Keep only the part you need",
    "pdf.sign": "Your signature on the page",
    "rename.copies": "Tidy names, as copies in a new folder",
    "videoframe.frame": "One moment of the video, as a picture",
    "videoframe.sheet": "Nine moments in one picture",
    "webextra.reader": "Just the article: no ads, menus or banners",
    "webextra.pictures": "Every picture on the page, biggest size",
    "clip.pdf": "Just your selection, as a clean PDF",
    "clip.png": "Your selection as one sharp picture",
    "clip.txt": "Only the words, no formatting",
    "webtable.xlsx": "Every table on the page, in Excel",
    "webtable.csv": "The biggest table, as CSV",
    "favicon.set": "favicon.ico and every app icon size",
}

TOOL_ENGINES = {"compress", "archive", "ocr"}


def is_tool(o: Offer) -> bool:
    t = o.target
    return t.engine in TOOL_ENGINES or bool(t.suffix) or t.ask or t.combine or t.key == "pdf.split"


def blurb(o: Offer) -> str:
    return BLURBS.get(o.target.key) or f"Save as {o.target.label}"


def out_name(o: Offer, suffix: str | None = None) -> str:
    """The name the new file (or folder) will get, for the side card."""
    if not o.sources:
        return ""
    t, src, n = o.target, o.sources[0], len(o.sources)
    if suffix:
        from dataclasses import replace

        t = replace(t, suffix=suffix)
    if t.folder:
        return f"{src.stem} ({t.folder})"
    try:
        from ..toolbox import output_ext

        ext = output_ext(t, src, {op.key: op.default for op in o.options})
    except Exception:
        ext = t.ext if t.ext != "*" else src.suffix
    if t.combine:
        stem = f"{src.stem} and {n - 1} more" if n > 1 else src.stem
        return stem + t.suffix + ext
    name = src.stem + t.suffix + ext
    return name + (f"  +{n - 1} more" if n > 1 else "")


CAUTIONS = ("become white", "become hard", "scaled down", "padded", "only the text", "can't be recovered",
            "dithered", " lost", "removed", "not kept")


def real_warning(o: Offer) -> str:
    """The first note that is a real caution (something is lost or can't be undone).
    Plain notes like "uses the first row as field names" don't get the amber dot."""
    import re

    for w in o.warnings:
        for sentence in re.split(r"(?<=[.!?])\s+", w):
            if any(c in sentence.lower() for c in CAUTIONS):
                return sentence  # just the cautionary sentence, not the whole note
    return ""


def animations_enabled() -> bool:
    """Windows' Animation effects, and Tapshift's own Reduce motion setting."""
    from .fx import motion_ok

    return motion_ok()


# ---------------------------------------------------------------- springs

class Spring:
    """A damped spring toward ``t``. ``step`` returns True while it is still moving."""

    __slots__ = ("v", "t", "vel")

    def __init__(self, v: float):
        self.v = self.t = float(v)
        self.vel = 0.0

    def snap(self, v: float | None = None) -> None:
        if v is not None:
            self.t = v
        self.v, self.vel = self.t, 0.0

    def step(self, dt: float, k: float, d: float, motion: bool = True) -> bool:
        if not motion:
            moved = self.v != self.t
            self.v, self.vel = self.t, 0.0
            return moved
        if abs(self.t - self.v) < 1e-3 and abs(self.vel) < 1e-3:
            self.v, self.vel = self.t, 0.0
            return False
        n = int(dt / 0.008) + 1  # sub-steps keep stiff springs stable on slow frames
        h = dt / n
        for _ in range(n):
            self.vel += (k * (self.t - self.v) - d * self.vel) * h
            self.v += self.vel * h
        return True


class _Planet:
    __slots__ = ("r", "sw", "s", "a", "mx", "my", "delay", "ring", "base", "x", "y", "hx", "hy", "ang")

    def __init__(self, ring: int, base: float, delay: float):
        self.ring, self.base, self.delay = ring, base, delay
        self.r, self.sw, self.s, self.a = Spring(0), Spring(140), Spring(0.4), Spring(0)
        self.mx, self.my = Spring(0), Spring(0)
        self.x = self.y = self.hx = self.hy = self.ang = 0.0


def _font(px: float, weight=QFont.Weight.Normal, display=False, mono=False) -> QFont:
    if mono:
        f = QFont("Cascadia Mono")
        f.setStyleHint(QFont.StyleHint.Monospace)
        if not QFontMetrics(f).inFont("a"):
            f = QFont("Consolas")
    else:
        f = QFont(display_family() if display else theme.FONT)
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(weight)
    return f


def warm_fonts() -> None:
    """Load the picker's fonts once, at startup: the first text drawn in a new
    font costs ~25 ms, which would otherwise land on the first hover."""
    pm = QPixmap(8, 8)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    for f in (_font(12, QFont.Weight.DemiBold, display=True), _font(19, QFont.Weight.Bold, display=True),
              _font(12.5), _font(11), _font(11, mono=True), _font(9.5, QFont.Weight.Bold, mono=True),
              _font(10.5, QFont.Weight.DemiBold)):
        p.setFont(f)
        p.drawText(0, 6, "Ag→1")
        QFontMetrics(f).horizontalAdvance("Ag→1")
    p.end()


def _alpha(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlphaF(max(0.0, min(1.0, a)))
    return out


# ---------------------------------------------------------------- the widget

class OrbitView(QWidget):
    """The picker as a web: options circle the selection; a branch (like Split) opens a fan
    of its choices further out when you point at it. Signals carry menu nodes."""

    activated = Signal(object)  # a leaf Node to run
    options_requested = Signal(object)
    dismissed = Signal()  # a click on empty space around the web: close the picker
    hovered = Signal(object)  # Node or None

    MAX_SCALE = 1.16
    DRIFT_SECONDS = 6.0
    KID = 0.94  # a branch's choices: nearly full size, so their names stay easy to read
    AIM_MS = 140  # heading for an open fan: if the pointer stops on the way, decide after this long
    AIM_DEG = 38  # "heading for the fan": moving within this angle of one of its choices

    def __init__(self, nodes, center_title: str, card_side: str = "right", scale: float = 1.0,
                 note: str = "", quick=None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # No background: the orbit floats over the desktop on its own disc.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.motion = animations_enabled()
        self.center_title = center_title
        self.note = note or "Point to explore  ·  right-click for options"
        self.side = card_side
        k = scale
        self.D, self.HUB, self.GAP = 64 * k, 100 * k, 12 * k
        self.CARD_W, self.CARD_GAP = round(218 * k + 10 * (1 - k)), round(22 * k)
        self._layout(_as_nodes(nodes), _as_nodes(quick or []))
        self.hover = -1
        self.open = -1  # index of the branch whose fan is out
        self.inside = False
        self.kbd = False
        self._exit: dict | None = None
        self._t = 0.0
        self.rot = [0.0, 0.0, 0.0, 0.0]  # inner ring, outer ring, fans, fans of fans (fans don't drift)
        self.sub = -1  # a choice inside the open fan that is itself a branch, with its own fan further out
        self.frame_ms = 16  # 60 fps in the real picker; the welcome tour asks for 30
        self.l2 = self.n_top  # where that second fan's choices start in self.items
        self.speed = Spring(1.0 if self.motion else 0.0)
        self.ring_a = Spring(0.0)
        self.hub_s = Spring(0.75)
        self.disc_s = Spring(0.9 * self.DR_closed / self.DR)
        self._disc_pix: QPixmap | None = None
        self._note_pix: QPixmap | None = None
        self.card_a, self.card_y, self.card_dx = Spring(0), Spring(0), Spring(0)
        self.card_pix: QPixmap | None = None
        self.card_old: QPixmap | None = None
        self.card_mix = 1.0
        self._cards: dict[int, QPixmap] = {}
        self._planet_pix: dict[tuple[int, bool], QPixmap] = {}
        self._hub_pix: dict[int, QPixmap] = {}
        self._rings_pix: QPixmap | None = None
        warm = []
        for n in self.items:
            warm.append(n)
            warm += list(n.children)
            for c in n.children:
                warm += list(c.children)
        self._warm = warm[::-1]  # pre-drawn after the opening, first planet first
        self._dpr = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._last = time.perf_counter()
        # Hover intent: a fan doesn't snap shut when the pointer crosses a neighbour on its way out.
        # Like a good desktop menu: moving towards the open fan keeps it, moving anywhere else
        # switches at once. No waiting either way.
        self._pos = QPointF(-1, -1)
        self._trail: list[tuple[float, QPointF]] = []
        self._aim = QTimer(self)
        self._aim.setSingleShot(True)
        self._aim.setInterval(self.AIM_MS)
        self._aim.timeout.connect(self._aim_done)

    # ------------------------------------------------------------ layout
    def _cap(self, r: float) -> int:
        return max(1, int(2 * math.pi * r / (self.D + 10)))

    def _layout(self, nodes: list, quick: list) -> None:
        """Your quick picks (favourites, recents, presets) on the inner orbit; everything else outside.
        If too many, the rest go into a "More" branch."""
        D, HUB, GAP = self.D, self.HUB, self.GAP
        r_in = HUB / 2 + D / 2 + GAP
        r_out = r_in + D * 1.18 + GAP
        rings = [list(quick), list(nodes)] if quick else [list(nodes)]
        cap_last = self._cap(r_out if quick else max(r_in, r_out if len(nodes) > self._cap(r_in) else r_in))
        last = rings[-1]
        if len(last) > cap_last:
            extra = last[cap_last - 1:]
            kids = [leaf for n in extra for leaf in (n.children if n.children else [n])]
            from ..menu import Node

            rings[-1] = last[: cap_last - 1] + [Node("More", f"{len(kids)} more", children=kids, key="branch:more")]
        if len(rings) == 1:
            m = len(rings[0])
            self.radii = [max(r_in, m * (D + 12) / (2 * math.pi))]
        else:
            self.radii = [r_in, max(r_out, len(rings[1]) * (D + 12) / (2 * math.pi))]
        self.items: list = []
        self.ps: list[_Planet] = []
        order = 0
        for ri, ring in enumerate(rings):
            m = max(1, len(ring))
            for j, node in enumerate(ring):
                base = -90 + j * 360 / m + (180 / m if ri == 1 else 0)
                self.items.append(node)
                self.ps.append(_Planet(ri, base, 0.03 + order * 0.028))
                order += 1
        self.n_top = len(self.items)
        self.DC = D * self.KID
        self.RC = self.radii[-1] + D * 1.3  # where a branch's choices fan out
        has_fans = any(n.children for n in self.items)
        nested = any(c.children for n in self.items for c in n.children)
        self.RC2 = self.RC + D * 1.25  # a fan's own fans open further out still
        # The disc everything sits on; with branches it reaches past the fans, so their choices
        # sit on a solid background (never on the desktop showing through).
        outer = self.RC2 if nested else self.RC
        self.DR = (outer + self.DC / 2 * self.MAX_SCALE + 12) if has_fans else self.radii[-1] + D / 2 + 18
        # The disc breathes with the web: snug around the rings when closed, wider as fans open.
        self.DR_closed = min(self.DR, self.radii[-1] + D / 2 * self.MAX_SCALE + 18)
        self.DR_l1 = min(self.DR, self.RC + self.DC / 2 * self.MAX_SCALE + 12)
        self.E = self.DR + 22
        S = 2 * self.E
        self.NOTE_H = 34
        self.ox = (self.CARD_W + self.CARD_GAP) if self.side == "left" else 0
        self.setFixedSize(QSize(int(S + self.CARD_GAP + self.CARD_W) + 4, int(S + self.NOTE_H)))

    def orbit_center(self) -> QPointF:
        return QPointF(self.ox + self.E, self.E)

    def solid_at(self, pos: QPointF) -> bool:
        """Is this point on the picker itself (its disc, the note under it, or the side card while it shows),
        rather than the empty, see-through space around it?"""
        c = self.orbit_center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        r = self.DR * max(0.5, self.disc_s.v)
        if dx * dx + dy * dy <= r * r:
            return True
        if pos.y() >= 2 * self.E - 6 and abs(dx) <= self.E * 0.6:  # the note under the web
            return True
        if self.card_a.v > 0.05:  # the side card, while it's showing
            x0 = 0 if self.side == "left" else self.ox + 2 * self.E + self.CARD_GAP
            if x0 - 4 <= pos.x() <= x0 + self.CARD_W + 4:
                return True
        return False

    def node_at(self, i: int):
        return self.items[i] if 0 <= i < len(self.items) else None

    # ------------------------------------------------------------ fans
    def open_branch(self, i: int) -> None:
        if i == self.open or not (0 <= i < self.n_top) or not self.items[i].children:
            return
        self.close_branch()
        self.open = i
        self.l2 = self.n_top + len(self.items[i].children)
        kids = self.items[i].children
        m = len(kids)
        ang = math.degrees(self.ps[i].ang)
        step = math.degrees((self.DC + 20) / self.RC)  # room between choices, even when one is hovered
        r0 = self.radii[self.ps[i].ring]
        for k, kid in enumerate(kids):
            pl = _Planet(2, ang + (k - (m - 1) / 2) * step, self._t + k * 0.025)
            pl.r.snap(r0)
            pl.sw.snap(0)
            pl.s.snap(0.5 if self.motion else 1)
            pl.a.snap(0 if self.motion else 1)
            self.items.append(kid)
            self.ps.append(pl)
        self._wake()

    def open_sub(self, k: int) -> None:
        """A choice in the open fan that is a branch itself: its choices fan out further."""
        if k == self.sub or not (self.n_top <= k < self.l2) or not self.items[k].children:
            return
        self.close_sub()
        self.sub = k
        kids = self.items[k].children
        m = len(kids)
        ang = self.ps[k].base
        step = math.degrees((self.DC + 20) / self.RC2)
        for j, kid in enumerate(kids):
            pl = _Planet(3, ang + (j - (m - 1) / 2) * step, self._t + j * 0.025)
            pl.r.snap(self.RC)
            pl.sw.snap(0)
            pl.s.snap(0.5 if self.motion else 1)
            pl.a.snap(0 if self.motion else 1)
            self.items.append(kid)
            self.ps.append(pl)
        self._wake()

    def close_sub(self) -> None:
        if self.sub < 0:
            return
        del self.items[self.l2:]
        del self.ps[self.l2:]
        self.sub = -1
        if self.hover >= self.l2:
            self.set_hover(-1)
        self._wake()

    def close_branch(self) -> None:
        if self.open < 0:
            return
        self.close_sub()
        del self.items[self.n_top:]
        del self.ps[self.n_top:]
        self.open = -1
        self.l2 = self.n_top
        if self.hover >= self.n_top:
            self.set_hover(-1)
        self._wake()

    def _in_fan(self, pos: QPointF) -> bool:
        """The pointer is between the branch and its choices: keep the fan open."""
        if self.open < 0:
            return False
        c = self.orbit_center()
        d = math.hypot(pos.x() - c.x(), pos.y() - c.y())
        r0 = self.radii[self.ps[self.open].ring]
        if not (r0 - self.D * 0.6 <= d <= (self.RC2 if self.sub >= 0 else self.RC) + self.DC):
            return False
        a = math.degrees(math.atan2(pos.y() - c.y(), pos.x() - c.x()))
        kids = self.ps[self.n_top:]
        pad = math.degrees((self.DC * 0.75) / self.RC)  # half a choice beyond each end
        lo = min(p.base for p in kids) - pad
        hi = max(p.base for p in kids) + pad
        mid = (lo + hi) / 2
        return abs(((a - mid + 180) % 360) - 180) <= (hi - lo) / 2

    # ------------------------------------------------------------ pixmap caches
    def _check_dpr(self) -> float:
        dpr = self.devicePixelRatioF()
        if dpr != self._dpr:
            self._dpr = dpr
            self._planet_pix.clear()
            self._hub_pix.clear()
            self._cards.clear()
            self._rings_pix = None
            self._disc_pix = None
            self._note_pix = None
            self.__dict__.pop("_card_shadows", None)
            self.__dict__.pop("_disc_sizes", None)
        return dpr

    def _new_pix(self, w: float, h: float) -> QPixmap:
        pm = QPixmap(max(1, math.ceil(w * self._dpr)), max(1, math.ceil(h * self._dpr)))
        pm.setDevicePixelRatio(self._dpr)
        pm.fill(Qt.GlobalColor.transparent)
        return pm

    @staticmethod
    def _painter(pm: QPixmap) -> QPainter:
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        return p

    def _planet_size(self) -> float:
        return self.D * self.MAX_SCALE + 12

    def _planet_pixmap(self, node, on: bool) -> QPixmap:
        key = (id(node), on)
        pm = self._planet_pix.get(key)
        if pm is not None:
            return pm
        L = self._planet_size()
        pm = self._new_pix(L, L)
        p = self._painter(pm)
        c = QPointF(L / 2, L / 2)
        R = self.D / 2 * self.MAX_SCALE
        branch = bool(node.children)
        if on:
            p.setPen(QPen(_alpha(theme.ACCENT, 0.30), 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, R + 4, R + 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ACCENT)
            p.drawEllipse(c, R, R)
        else:
            pen = QPen(theme.DIM if branch else theme.LINE, 1.2)
            if branch:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(theme.SURFACE2)
            p.drawEllipse(c, R - 0.6, R - 0.6)
        text_c = theme.ON_ACCENT if on else theme.TEXT
        lines, f = self._fit_label(node.label, R * 2 * 0.78)
        fm = QFontMetrics(f)
        lh = fm.height() * 0.92
        top = c.y() - (len(lines) * lh) / 2 + 5 * self.D / 72
        dot_y = top - 7 * self.D / 72
        if branch:  # three little dots: there's more inside
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ON_ACCENT if on else theme.ACCENT)
            for dx in (-6, 0, 6):
                p.drawEllipse(QPointF(c.x() + dx * self.D / 72, dot_y), 1.8, 1.8)
            p.setFont(_font(9.5 * self.D / 72, QFont.Weight.DemiBold))
            p.setPen(_alpha(theme.ON_ACCENT, 0.8) if on else theme.DIM)
            p.drawText(QRectF(c.x() - R, top + lh * len(lines) - 1, 2 * R, 14), Qt.AlignmentFlag.AlignHCenter,
                       f"{len(node.children)} choices")
        elif node.tool:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ON_ACCENT if on else theme.ACCENT)
            p.drawEllipse(QPointF(c.x(), dot_y), 3.0, 3.0)
        else:
            p.setPen(QPen(theme.ON_ACCENT if on else theme.DIM, 1.3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(c.x(), dot_y), 2.8, 2.8)
        p.setFont(f)
        p.setPen(text_c)
        for k, line in enumerate(lines):
            w = fm.horizontalAdvance(line)
            p.drawText(QPointF(c.x() - w / 2, top + fm.ascent() * 0.92 + k * lh), line)
        if node.offer is not None and node.preset is None and real_warning(node.offer):
            wc = QPointF(c.x() + R * 0.70, c.y() - R * 0.70)
            p.setPen(QPen(theme.BG, 2))
            p.setBrush(theme.WARN)
            p.drawEllipse(wc, 4.5, 4.5)
        if node.preset is not None:  # your preset: a small star-like accent mark
            wc = QPointF(c.x() + R * 0.70, c.y() - R * 0.70)
            p.setPen(QPen(theme.BG, 2))
            p.setBrush(theme.ACCENT)
            p.drawEllipse(wc, 4.5, 4.5)
        p.end()
        self._planet_pix[key] = pm
        return pm

    def _fit_label(self, label: str, max_w: float) -> tuple[list[str], QFont]:
        k = self.D / 72
        for px in (13.5, 12.5, 11.5):
            f = _font(px * k, QFont.Weight.DemiBold, display=True)
            fm = QFontMetrics(f)
            if fm.horizontalAdvance(label) <= max_w:
                return [label], f
            if " " in label:
                a, b = label.split(" ", 1)
                if max(fm.horizontalAdvance(a), fm.horizontalAdvance(b)) <= max_w:
                    return [a, b], f
        f = _font(11 * k, QFont.Weight.DemiBold, display=True)
        return [QFontMetrics(f).elidedText(label, Qt.TextElideMode.ElideRight, int(max_w))], f

    def _hub_pixmap(self) -> QPixmap:
        node = self.node_at(self.hover)
        key = id(node) if node is not None else -1
        pm = self._hub_pix.get(key)
        if pm is not None:
            return pm
        H = self.HUB
        pm = self._new_pix(H + 4, H + 4)
        p = self._painter(pm)
        c = QPointF((H + 4) / 2, (H + 4) / 2)
        p.setPen(QPen(theme.LINE, 1.2))
        p.setBrush(theme.SURFACE)
        p.drawEllipse(c, H / 2, H / 2)
        k = self.D / 72
        f = _font(12.5 * k, QFont.Weight.Bold, display=True)
        fm = QFontMetrics(f)
        title = fm.elidedText(self.center_title, Qt.TextElideMode.ElideMiddle, int(H - 22 * k))
        p.setFont(f)
        p.setPen(theme.TEXT)
        p.drawText(QPointF(c.x() - fm.horizontalAdvance(title) / 2, c.y() - 2 * k), title)
        if node is not None:
            sub, col = (f"{node.label} ▸" if node.children else f"→ {node.label}"), theme.ACCENT
        else:
            sub, col = "pick one", theme.DIM
        f = _font(10.5 * k, QFont.Weight.DemiBold)
        fm = QFontMetrics(f)
        sub = fm.elidedText(sub, Qt.TextElideMode.ElideRight, int(H - 26 * k))
        p.setFont(f)
        p.setPen(col)
        p.drawText(QPointF(c.x() - fm.horizontalAdvance(sub) / 2, c.y() + 15 * k), sub)
        p.end()
        self._hub_pix[key] = pm
        return pm

    def _disc_pixmap(self) -> QPixmap:
        """Soft shadow and the disc, drawn once at full size (it's scaled down while the web is closed)."""
        if self._disc_pix is not None:
            return self._disc_pix
        from PySide6.QtGui import QRadialGradient

        S = 2 * self.E
        pm = self._new_pix(S, S)
        p = self._painter(pm)
        c = QPointF(self.E, self.E)
        R = self.DR
        g = QRadialGradient(QPointF(c.x(), c.y() + 7), R + 20)
        edge = R / (R + 20)
        g.setColorAt(0.0, _alpha(theme.SHADOW, theme.SHADOW.alphaF() * 0.9))
        g.setColorAt(edge * 0.94, _alpha(theme.SHADOW, theme.SHADOW.alphaF() * 0.8))
        g.setColorAt(1.0, _alpha(theme.SHADOW, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(c.x(), c.y() + 7), R + 20, R + 20)
        p.setPen(QPen(theme.LINE, 1.2))
        p.setBrush(theme.BG)
        p.drawEllipse(c, R, R)
        p.end()
        self._disc_pix = pm
        return pm

    def _disc_at(self, k: float) -> QPixmap:
        """The disc drawn once at a resting size (closed web, one fan open...), so a still picker
        never rescales the big image on every frame."""
        cache = self.__dict__.setdefault("_disc_sizes", {})
        pm = cache.get(k)
        if pm is None:
            pm = self._new_pix(2 * self.E, 2 * self.E)
            p = self._painter(pm)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            ds = 2 * self.E * k
            p.drawPixmap(QRectF(self.E - ds / 2, self.E - ds / 2, ds, ds), self._disc_pixmap(),
                         QRectF(self._disc_pixmap().rect()))
            p.end()
            cache[k] = pm
        return pm

    def _card_shadow(self, w: float, h: float) -> QPixmap:
        """A smooth soft shadow for the side card (many faint layers, drawn once per size)."""
        key = (round(w), round(h))
        cache = self.__dict__.setdefault("_card_shadows", {})
        pm = cache.get(key)
        if pm is not None:
            return pm
        pad = 16
        pm = self._new_pix(w + 2 * pad, h + 2 * pad)
        p = self._painter(pm)
        p.setPen(Qt.PenStyle.NoPen)
        base = theme.SHADOW.alphaF()
        for k in range(pad):
            grow = pad - k
            p.setBrush(_alpha(theme.SHADOW, base * 0.07 * (k + 1) / pad))
            p.drawRoundedRect(QRectF(pad - grow, pad - grow, w + 2 * grow, h + 2 * grow), 12 + grow, 12 + grow)
        p.end()
        cache[key] = pm
        return pm

    def _note_pixmap(self) -> QPixmap:
        if self._note_pix is not None:
            return self._note_pix
        f = _font(11.5)
        fm = QFontMetrics(f)
        text = fm.elidedText(self.note, Qt.TextElideMode.ElideRight, int(2 * self.E - 40))
        w, h = fm.horizontalAdvance(text) + 26, 24
        pm = self._new_pix(w + 2, h + 2)
        p = self._painter(pm)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(_alpha(theme.BG, 0.94))
        p.drawRoundedRect(QRectF(1, 1, w, h), h / 2, h / 2)
        p.setFont(f)
        p.setPen(theme.DIM)
        p.drawText(QRectF(1, 1, w, h), Qt.AlignmentFlag.AlignCenter, text)
        p.end()
        self._note_pix = pm
        return pm

    def _rings_pixmap(self) -> QPixmap:
        if self._rings_pix is not None:
            return self._rings_pix
        S = 2 * self.E
        pm = self._new_pix(S, S)
        p = self._painter(pm)
        c = QPointF(self.E, self.E)
        for ri, r in enumerate(self.radii):
            pen = QPen(_alpha(theme.TEXT, 0.16 if theme.DARK else 0.20), 1.3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setDashPattern([0.1, 5.5] if ri == len(self.radii) - 1 else [3, 6])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r, r)
        p.end()
        self._rings_pix = pm
        return pm

    def _card_pixmap(self, node) -> QPixmap:
        pm = self._cards.get(id(node))
        if pm is not None:
            return pm
        W, pad = self.CARD_W, 14
        inner = W - 2 * pad
        f_tag = _font(9.5, QFont.Weight.Bold, mono=True)
        f_tag.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        f_title = _font(19, QFont.Weight.Bold, display=True)
        f_body = _font(12.5)
        f_meta = _font(11, mono=True)
        f_small = _font(11)
        o = node.offer
        if node.children:
            names = ", ".join(c.label for c in node.children[:4]) + ("…" if len(node.children) > 4 else "")
            tag, title, cap, text = "GROUP", node.label, f"{len(node.children)} choices", names
            meta, warn, hint = "", "", "Point at it to open"
        elif node.key.startswith("more:"):
            tag, title, cap, text = "LIST", node.label, node.caption, node.blurb or "Every option, with search"
            meta, warn, hint = "", "", "Point at it to open"
        elif o is None:
            tag, title, cap, text, meta, warn, hint = "", node.label, node.caption, node.blurb, "", "", ""
        else:
            tag = "PRESET" if node.preset is not None else ("TOOL" if node.tool else "FORMAT")
            title, cap = node.label, node.caption or o.caption
            text = node.blurb or blurb(o)
            meta = out_name(o, (node.preset or {}).get("name_suffix"))
            warn = "" if node.preset is not None else real_warning(o)
            hint = ("Ready: no questions" if node.preset is not None else
                    "Asks for details first" if o.target.ask else ("Right-click for options" if o.options else ""))
        fm_body = QFontMetrics(f_body)
        body_lines = self._wrap(text, fm_body, inner, 2) if text else []
        h = pad + 13 + 6 + 24 + 6 + len(body_lines) * (fm_body.height() + 1)
        if meta:
            h += 10 + 15
        warn_lines = self._wrap(warn, QFontMetrics(f_small), inner - 14, 2) if warn else []
        if warn_lines:
            h += 8 + len(warn_lines) * (QFontMetrics(f_small).height())
        if hint:
            h += 8 + 15
        h += pad
        pm = self._new_pix(W + 2, h + 2)
        p = self._painter(pm)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(QRectF(0.5, 0.5, W, h), 12, 12)
        y = pad
        p.setFont(f_tag)
        p.setPen(theme.ACCENT if tag in ("TOOL", "PRESET", "GROUP") else theme.DIM)
        p.drawText(QRectF(pad, y, inner, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tag)
        if cap:
            fc = _font(10.5, QFont.Weight.DemiBold)
            fmc = QFontMetrics(fc)
            cap = fmc.elidedText(cap, Qt.TextElideMode.ElideRight, int(inner * 0.62))
            cw = fmc.horizontalAdvance(cap) + 14
            r = QRectF(pad + inner - cw, y - 3, cw, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.SURFACE2)
            p.drawRoundedRect(r, 10, 10)
            p.setFont(fc)
            p.setPen(theme.DIM)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, cap)
        y += 13 + 6
        p.setFont(f_title)
        p.setPen(theme.TEXT)
        fmt = QFontMetrics(f_title)
        p.drawText(QPointF(pad, y + fmt.ascent()), fmt.elidedText(title, Qt.TextElideMode.ElideRight, inner))
        y += 24 + 6
        p.setFont(f_body)
        p.setPen(theme.TEXT)
        for line in body_lines:
            p.drawText(QPointF(pad, y + fm_body.ascent()), line)
            y += fm_body.height() + 1
        if meta:
            y += 10
            p.setFont(f_meta)
            fmm = QFontMetrics(f_meta)
            p.setPen(theme.ACCENT)
            p.drawText(QPointF(pad, y + fmm.ascent()), "→")
            p.setPen(theme.DIM)
            p.drawText(QPointF(pad + 16, y + fmm.ascent()),
                       fmm.elidedText(meta, Qt.TextElideMode.ElideMiddle, inner - 16))
            y += 15
        if warn_lines:
            y += 8
            fms = QFontMetrics(f_small)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.WARN)
            p.drawEllipse(QPointF(pad + 4, y + fms.height() / 2), 3.5, 3.5)
            p.setFont(f_small)
            p.setPen(theme.WARN)
            for line in warn_lines:
                p.drawText(QPointF(pad + 14, y + fms.ascent()), line)
                y += fms.height()
        if hint:
            y += 8
            p.setFont(f_small)
            p.setPen(theme.DIM)
            p.drawText(QPointF(pad, y + QFontMetrics(f_small).ascent()), hint)
        p.end()
        self._cards[id(node)] = pm
        return pm

    @staticmethod
    def _wrap(text: str, fm: QFontMetrics, width: int, max_lines: int) -> list[str]:
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if fm.horizontalAdvance(trial) <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[: max_lines - 1] + [fm.elidedText(" ".join(lines[max_lines - 1:]), Qt.TextElideMode.ElideRight, width)]
        return lines

    # ------------------------------------------------------------ clock
    def showEvent(self, e):
        super().showEvent(e)
        self._t = 0.0
        self.close_branch()
        hub_r = self.HUB / 2 * 0.6
        for p in self.ps:
            p.r.snap(hub_r)
            p.sw.snap(140 if self.motion else 0)
            p.s.snap(0.4 if self.motion else 1)
            p.a.snap(0 if self.motion else 1)
        self.ring_a.snap(0 if self.motion else 1)
        self.hub_s.snap(0.75 if self.motion else 1)
        self.disc_s.snap(0.9 if self.motion else 1)
        # Draw the base images now, while the window is still fully transparent, so the
        # opening animation's frames only copy finished images.
        self._check_dpr()
        self._disc_pixmap()
        self._note_pixmap()
        self._hub_pixmap()
        for n in self.items:
            self._planet_pixmap(n, False)
        self._wake()

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def _wake(self) -> None:
        if not self._timer.isActive():
            self._last = time.perf_counter()
            self._timer.start(16)

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = min(0.05, max(0.0, now - self._last))
        self._last = now
        self._t += dt
        m = self.motion
        busy = False
        ex = self._exit
        # The drift stops when you point at the orbit, and by itself after a few seconds,
        # so a popup left open goes back to using no CPU at all.
        still = (self.hover >= 0 or self.open >= 0 or self.inside or self.kbd or ex is not None or not m
                 or self._t > self.DRIFT_SECONDS)
        self.speed.t = 0.0 if still else 1.0
        busy |= self.speed.step(dt, 38, 12, m)
        if m:
            self.rot[0] -= dt * 11 * self.speed.v
            self.rot[1] += dt * 7 * self.speed.v
        drifting = self.speed.v > 0.003
        self.ring_a.t = 0.0 if ex else 1.0
        busy |= self.ring_a.step(dt, 120, 20, m)
        self.hub_s.t = 1.08 if ex else 1.0
        busy |= self.hub_s.step(dt, 220, 16, m)
        reach = self.DR_closed if self.open < 0 else (self.DR_l1 if self.sub < 0 else self.DR)
        self.disc_s.t = (1.04 if ex else 1.0) * reach / self.DR
        busy |= self.disc_s.step(dt, 200, 17, m)
        c = self.orbit_center()
        for i, p in enumerate(self.ps):
            if self._t < p.delay and ex is None:
                busy = True
                continue
            kid = i >= self.n_top
            rr = self.RC2 if p.ring == 3 else (self.RC if kid else self.radii[p.ring])
            h = i == self.hover
            if ex is not None:
                if i == ex["i"]:
                    p.r.t, p.s.t, p.a.t, p.mx.t, p.my.t = 0.0, 1.2, 0.0, 0.0, 0.0
                else:
                    p.r.t, p.s.t, p.a.t = rr * 1.25, 0.8, 0.0
            else:
                p.r.t, p.sw.t = rr, 0.0
                p.s.t = 1.12 if h else 1.0
                p.a.t = 1.0  # always fully opaque: the hovered one is lifted and coloured instead
            chosen = ex is not None and i == ex["i"]
            busy |= p.r.step(dt, 90 if chosen else (170 if kid else 120), 14 if not kid else 17, m)
            busy |= p.sw.step(dt, 60, 12, m)
            busy |= p.s.step(dt, 260, 18, m)
            busy |= p.a.step(dt, 30 if chosen else 180, 11 if chosen else 22, m)
            busy |= p.mx.step(dt, 220, 17, m)
            busy |= p.my.step(dt, 220, 17, m)
            a = math.radians(p.base + self.rot[p.ring] + p.sw.v)
            p.ang = a
            p.hx, p.hy = c.x() + math.cos(a) * p.r.v, c.y() + math.sin(a) * p.r.v
            p.x, p.y = p.hx + p.mx.v, p.hy + p.my.v
        # side card follows the hovered planet
        if 0 <= self.hover < len(self.ps) and ex is None:
            pm = self.card_pix
            ch = pm.height() / self._dpr if pm is not None else 120
            self.card_y.t = max(4.0, min(self.height() - ch - 4, self.ps[self.hover].y - ch / 2))
            self.card_a.t = 1.0
        else:
            self.card_a.t = 0.0
        busy |= self.card_y.step(dt, 210, 22, m)
        busy |= self.card_a.step(dt, 260, 26, m)
        busy |= self.card_dx.step(dt, 260, 22, m)
        if self.card_mix < 1.0:
            self.card_mix = min(1.0, self.card_mix + dt / 0.12) if m else 1.0
            busy = True
        if ex is not None:
            ex["t"] += dt
            busy = True
            if ex["t"] >= ex["dur"] and not ex.get("fired"):
                ex["fired"] = True
                QTimer.singleShot(0, ex["done"])
        self.update()
        # Pre-draw one hover image per quiet frame, so hovering never draws on the spot.
        if self._warm and self._t > 0.5 and ex is None:
            self._check_dpr()
            n = self._warm.pop()
            self._planet_pixmap(n, False)
            self._planet_pixmap(n, True)
            self._card_pixmap(n)
            busy = True if self._warm else busy
        if not (busy or drifting):
            self._timer.stop()
            return
        want = self.frame_ms if busy else 33  # idle drift doesn't need 60 fps
        if self._timer.interval() != want:
            self._timer.setInterval(want)

    # ------------------------------------------------------------ painting
    def paintEvent(self, _):
        self._check_dpr()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = self.orbit_center()
        ra = max(0.0, min(1.0, self.ring_a.v))
        disc = self._disc_pixmap()
        ds = 2 * self.E * self.disc_s.v
        p.setOpacity(1.0 if self._exit is None else max(0.0, 1 - self._exit["t"] / self._exit["dur"]))
        if abs(self.disc_s.v - 1.0) < 1e-3:  # at rest: a plain copy, no rescaling of the big image
            p.drawPixmap(QPointF(c.x() - self.E, c.y() - self.E), disc)
        elif abs(self.disc_s.v - self.disc_s.t) < 1e-3:  # at rest at a smaller size: a ready-made copy
            p.drawPixmap(QPointF(c.x() - self.E, c.y() - self.E), self._disc_at(round(self.disc_s.t, 3)))
        else:
            p.drawPixmap(QRectF(c.x() - ds / 2, c.y() - ds / 2, ds, ds), disc, QRectF(disc.rect()))
        p.drawPixmap(QPointF(c.x() - self.E, c.y() - self.E), self._rings_pixmap())  # orbits at their true size
        note = self._note_pixmap()
        nw = note.width() / self._dpr
        p.setOpacity(ra)
        p.drawPixmap(QPointF(c.x() - nw / 2, 2 * self.E + self.NOTE_H - note.height() / self._dpr - 2), note)
        if ra > 0.01:
            p.setOpacity(ra)
            # tether from the hub to the hovered top-level option (or the open branch)
            t = self.hover if 0 <= self.hover < self.n_top else self.open
            if 0 <= t < len(self.ps):
                pl = self.ps[t]
                ang = math.atan2(pl.y - c.y(), pl.x - c.x())
                d = math.hypot(pl.x - c.x(), pl.y - c.y())
                r0, r1 = self.HUB / 2 + 3, d - self.D / 2 * pl.s.v - 3
                if r1 > r0:
                    p.setPen(QPen(_alpha(theme.ACCENT, 0.85 * ra), 2))
                    p.drawLine(QPointF(c.x() + math.cos(ang) * r0, c.y() + math.sin(ang) * r0),
                               QPointF(c.x() + math.cos(ang) * r1, c.y() + math.sin(ang) * r1))
            # the web: threads from the open branch to each choice, and a thread through the choices
            webs = []
            if self.open >= 0 and len(self.ps) > self.n_top:
                webs.append((self.open, self.n_top, self.l2))
            if self.sub >= 0 and len(self.ps) > self.l2:
                webs.append((self.sub, self.l2, len(self.ps)))
            for bi, lo, hi in webs:
                b = self.ps[bi]
                kids = self.ps[lo:hi]
                for k, kp in enumerate(kids):
                    on = lo + k == self.hover or lo + k == self.sub
                    p.setPen(QPen(_alpha(theme.ACCENT if on else theme.TEXT, (0.95 if on else 0.32) * kp.a.v),
                                  2 if on else 1.3))
                    p.drawLine(QPointF(b.x, b.y), QPointF(kp.x, kp.y))
                pen = QPen(_alpha(theme.TEXT, 0.14 * min(kp.a.v for kp in kids)), 1.0)
                pen.setStyle(Qt.PenStyle.DotLine)
                p.setPen(pen)
                for a1, a2 in zip(kids, kids[1:]):
                    p.drawLine(QPointF(a1.x, a1.y), QPointF(a2.x, a2.y))
        # planets (the hovered one last, on top); the open branch's choices are drawn smaller
        L = self._planet_size()
        order = [i for i in range(len(self.ps)) if i != self.hover] + ([self.hover] if self.hover >= 0 else [])
        for i in order:
            pl = self.ps[i]
            a = max(0.0, min(1.0, pl.a.v))
            if a < 0.01:
                continue
            node = self.items[i]
            pm = self._planet_pixmap(node, i == self.hover or i == self.open or i == self.sub)
            size = L * pl.s.v / self.MAX_SCALE * (self.KID if i >= self.n_top else 1.0)
            p.setOpacity(a)
            p.drawPixmap(QRectF(pl.x - size / 2, pl.y - size / 2, size, size), pm, QRectF(pm.rect()))
        hub = self._hub_pixmap()
        hs = (self.HUB + 4) * self.hub_s.v
        p.setOpacity(1.0 if self._exit is None else max(0.0, 1 - self._exit["t"] / self._exit["dur"]))
        p.drawPixmap(QRectF(c.x() - hs / 2, c.y() - hs / 2, hs, hs), hub, QRectF(hub.rect()))
        # side card + leader line
        ca = max(0.0, min(1.0, self.card_a.v))
        if ca > 0.01 and self.card_pix is not None and 0 <= self.hover < len(self.ps):
            pl = self.ps[self.hover]
            scale = self.KID if self.hover >= self.n_top else 1.0
            cw = self.CARD_W
            right = self.side == "right"
            cx = (self.ox + 2 * self.E + self.CARD_GAP if right else 0) + self.card_dx.v
            cy = self.card_y.v
            ch = self.card_pix.height() / self._dpr
            edge_x = cx if right else cx + cw
            px = pl.x + (1 if right else -1) * (self.D / 2 * pl.s.v * scale + 2)
            p.setOpacity(ca)
            p.setPen(QPen(_alpha(theme.ACCENT, 0.55), 1.4))
            ly = max(cy + 14, min(cy + ch - 14, pl.y))
            p.drawLine(QPointF(px, pl.y), QPointF(edge_x, ly))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.ACCENT)
            p.drawEllipse(QPointF(edge_x, ly), 3, 3)
            sh = self._card_shadow(cw, ch)
            p.drawPixmap(QPointF(cx - 16, cy - 16 + 6), sh)
            if self.card_old is not None and self.card_mix < 1:
                p.setOpacity(ca * (1 - self.card_mix))
                p.drawPixmap(QPointF(cx, cy), self.card_old)
            p.setOpacity(ca * (self.card_mix if self.card_old is not None else 1))
            p.drawPixmap(QPointF(cx, cy), self.card_pix)
        p.end()

    # ------------------------------------------------------------ interaction
    def set_hover(self, i: int) -> None:
        if i == self.hover:
            return
        prev = self.hover
        self.hover = i
        node = self.node_at(i)
        if node is not None:
            self._check_dpr()
            new = self._card_pixmap(node)
            if prev >= 0 and self.card_a.v > 0.05:
                self.card_old, self.card_mix = self.card_pix, 0.0
            else:  # appearing: start next to the planet, slide in from the orbit side
                ch = new.height() / self._dpr
                self.card_y.snap(max(4.0, min(self.height() - ch - 4, self.ps[i].y - ch / 2)))
                self.card_dx.snap(-12 if self.side == "right" else 12)
                self.card_dx.t = 0
                self.card_old, self.card_mix = None, 1.0
            self.card_pix = new
        self.hovered.emit(node)
        self._wake()

    def _nearest(self, pos: QPointF) -> int:
        best, bd = -1, 1e9
        kid_best, kid_d = -1, 1e9
        for i, pl in enumerate(self.ps):
            kid = i >= self.n_top
            if pl.a.v < 0.2 and not kid:
                continue
            reach = (self.DC * 0.8) if kid else self.D * 0.62  # choices are easy to land on
            d = math.hypot(pl.hx - pos.x(), pl.hy - pos.y()) / reach
            if kid and d < kid_d:
                kid_best, kid_d = i, d
            if d < bd:
                best, bd = i, d
        if kid_d <= 1.0:  # an open fan's choices win over the ring they sit beside
            return kid_best
        return best if bd <= 1.0 else -1

    def mouseMoveEvent(self, e):
        if self._exit is not None:
            return
        pos = e.position()
        c = self.orbit_center()
        self.inside = math.hypot(pos.x() - c.x(), pos.y() - c.y()) < self.E
        self.kbd = False
        self._pos = pos
        now = time.perf_counter()
        self._trail = [(ts, q) for ts, q in self._trail if now - ts < 0.12] + [(now, pos)]
        self._route(pos, self._nearest(pos))
        i = self.hover
        for k, pl in enumerate(self.ps):
            if k == i:
                pl.mx.t = max(-14.0, min(14.0, (pos.x() - pl.hx) * 0.3))
                pl.my.t = max(-14.0, min(14.0, (pos.y() - pl.hy) * 0.3))
            else:
                pl.mx.t = pl.my.t = 0.0
        self._wake()

    def _heading_to_fan(self, pos: QPointF) -> bool:
        """Is the pointer moving towards the open branch's choices (or back to the branch)?"""
        if self.open < 0 or len(self._trail) < 2:
            return False
        now = self._trail[-1][0]
        prev = next((q for ts, q in reversed(self._trail) if now - ts >= 0.025), self._trail[0][1])
        vx, vy = pos.x() - prev.x(), pos.y() - prev.y()
        speed = math.hypot(vx, vy)
        if speed < 2.5:
            return False  # standing still is not heading anywhere
        c = self.orbit_center()
        # where the choices end up (they may still be flying out) and the branch itself
        targets = []
        for k in range(self.n_top, len(self.ps)):
            r = self.RC2 if k >= self.l2 else self.RC
            targets.append((c.x() + math.cos(math.radians(self.ps[k].base)) * r,
                            c.y() + math.sin(math.radians(self.ps[k].base)) * r))
        targets.append((self.ps[self.open].hx, self.ps[self.open].hy))
        if self.sub >= 0:
            targets.append((self.ps[self.sub].hx, self.ps[self.sub].hy))
        for tx, ty in targets:
            dx, dy = tx - pos.x(), ty - pos.y()
            d = math.hypot(dx, dy)
            if d < 1:
                return True
            cos = (vx * dx + vy * dy) / (speed * d)
            if cos >= math.cos(math.radians(self.AIM_DEG)):
                return True
        return False

    def _heading_to_sub(self, pos: QPointF) -> bool:
        """Moving towards the second fan's choices?"""
        if self.sub < 0 or len(self._trail) < 2:
            return False
        now = self._trail[-1][0]
        prev = next((q for ts, q in reversed(self._trail) if now - ts >= 0.025), self._trail[0][1])
        vx, vy = pos.x() - prev.x(), pos.y() - prev.y()
        speed = math.hypot(vx, vy)
        if speed < 2.5:
            return False
        c = self.orbit_center()
        for k in range(self.l2, len(self.ps)):
            a = math.radians(self.ps[k].base)
            dx, dy = c.x() + math.cos(a) * self.RC2 - pos.x(), c.y() + math.sin(a) * self.RC2 - pos.y()
            d = math.hypot(dx, dy)
            if d < 1 or (vx * dx + vy * dy) / (speed * d) >= math.cos(math.radians(self.AIM_DEG)):
                return True
        return False

    def _route(self, pos: QPointF, i: int, stopped: bool = False) -> None:
        """Decide what the pointer is on, with an open fan given the benefit of the doubt only
        while the pointer is actually travelling towards it."""
        if self.open < 0:
            if 0 <= i < self.n_top and self.items[i].children:
                self.open_branch(i)
            self.set_hover(i)
            return
        if i >= self.n_top or i == self.open:  # on the branch or one of its choices
            self._aim.stop()
            if self.n_top <= i < self.l2:  # a choice in the first fan
                if self.sub >= 0 and i != self.sub and not stopped and self._heading_to_sub(pos):
                    self._aim.start()  # crossing a neighbour on the way out to the open second fan
                    return
                if self.items[i].children:
                    self.open_sub(i)  # a branch inside the fan: its own fan opens further out
                elif self.sub >= 0:
                    if not stopped and self._heading_to_sub(pos):
                        self._aim.start()  # crossing a neighbour on the way out to the second fan
                        return
                    self.close_sub()
            elif i == self.open and self.sub >= 0:
                self.close_sub()  # back on the branch: fold the second fan away
            self.set_hover(i)
            return
        if i < 0 and self._in_fan(pos):  # in a gap between the choices: nothing to change
            return
        if not stopped and self._heading_to_fan(pos):
            self._aim.start()  # crossing something on the way to the fan; re-check if the pointer stops
            return
        self._aim.stop()
        self.close_branch()
        if 0 <= i < self.n_top and self.items[i].children:
            self.open_branch(i)
        self.set_hover(i)

    def _aim_done(self) -> None:
        if self._exit is not None or self.kbd:
            return
        if not self.underMouse():
            self.close_branch()
            self.set_hover(-1)
            return
        self._route(self._pos, self._nearest(self._pos), stopped=True)
        self._wake()

    def leaveEvent(self, _):
        self.inside = False
        for pl in self.ps:
            pl.mx.t = pl.my.t = 0.0
        if not self.kbd:
            self._aim.stop()
            self.close_branch()
            self.set_hover(-1)
        self._wake()

    def mouseReleaseEvent(self, e):
        if self._exit is not None:
            return
        i = self._nearest(e.position())
        if i < 0 and self.open >= 0 and self._in_fan(e.position()) and self.hover >= self.n_top:
            i = self.hover  # clicked in a gap of the fan while one of its choices is lit
        node = self.node_at(i)
        if node is None:
            if not self.solid_at(e.position()):
                self.dismissed.emit()  # empty space around the web: like clicking anywhere else
            return
        self._aim.stop()
        if node.children:  # a branch only opens; its choices do the work
            self.open_branch(i) if i < self.n_top else self.open_sub(i)
            return
        if e.button() == Qt.MouseButton.RightButton:
            self.options_requested.emit(node)
        elif e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(node)

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        arrows = (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Up)
        in_fan = self.hover >= self.n_top
        if k in arrows:
            step = 1 if k in (Qt.Key.Key_Right, Qt.Key.Key_Down) else -1
            self.kbd = True
            if in_fan:
                lo, hi = (self.l2, len(self.items)) if self.hover >= self.l2 else (self.n_top, self.l2)
                n = hi - lo
                nxt = lo + (self.hover - lo + step) % n
                if lo == self.n_top and self.sub >= 0 and nxt != self.sub:
                    self.close_sub()
                self.set_hover(nxt)
            else:
                n = self.n_top
                if n:
                    self.close_branch()
                    self.set_hover((self.hover + step) % n if self.hover >= 0 else (0 if step > 0 else n - 1))
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.hover >= 0:
            node = self.items[self.hover]
            if node.children:
                self.kbd = True
                if self.hover < self.n_top:
                    self.open_branch(self.hover)
                    self.set_hover(self.n_top)  # its first choice
                else:
                    self.open_sub(self.hover)
                    self.set_hover(self.l2)
            else:
                self.activated.emit(node)
        elif k in (Qt.Key.Key_Escape, Qt.Key.Key_Backspace) and self.sub >= 0:
            b = self.sub
            self.close_sub()
            self.set_hover(b)
        elif k in (Qt.Key.Key_Escape, Qt.Key.Key_Backspace) and self.open >= 0:
            b = self.open
            self.close_branch()
            self.set_hover(b)
        elif k == Qt.Key.Key_Menu and self.hover >= 0 and not self.items[self.hover].children:
            self.options_requested.emit(self.items[self.hover])
        else:
            e.ignore()

    def play_exit(self, node, done) -> None:
        """The chosen planet falls into the hub while the others fly out; then ``done``."""
        if not self.motion or not self.isVisible() or node not in self.items:
            done()
            return
        self._exit = {"i": self.items.index(node), "t": 0.0, "dur": 0.2, "done": done}
        self.card_a.t = 0.0
        self._wake()


def _as_nodes(items) -> list:
    """Accept menu nodes, or plain offers (older callers), as the picker's items."""
    from ..menu import Node, _leaf

    out = []
    for x in items or []:
        if isinstance(x, Node):
            out.append(x)
        elif x is not None:
            out.append(_leaf(x))
    return out
