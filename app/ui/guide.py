"""The "How to use Deskvert" guide window, plus the sidebar navigation and
section stack shared with the Settings window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout,
                               QWidget)

from . import theme
from .chrome import ChromeWindow, label
from .demo import DemoScene
from .fx import accent_gradient, clamp, fade_in, font, mix, with_alpha

# ====================================================================== shared navigation


class NavRail(QWidget):
    """Vertical list of sections; the highlight glides to the chosen one."""

    selected = Signal(int)
    ROW = 40

    def __init__(self, items: list[str], parent=None):
        super().__init__(parent)
        self.items = items
        self.index = 0
        self._y = 0.0
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(196)
        self.setMinimumHeight(len(items) * self.ROW + 8)
        self._anim = QVariantAnimation(self, duration=260, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_y", float(v)), self.update()))

    def select(self, i: int, emit: bool = True):
        if not 0 <= i < len(self.items):
            return
        self.index = i
        self._anim.stop()
        self._anim.setStartValue(self._y)
        self._anim.setEndValue(float(i * self.ROW))
        self._anim.start()
        if emit:
            self.selected.emit(i)

    def mouseMoveEvent(self, e):
        h = int(e.position().y() // self.ROW)
        h = h if 0 <= h < len(self.items) else -1
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = int(e.position().y() // self.ROW)
        if 0 <= i < len(self.items) and i != self.index:
            self.select(i)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hl = QRectF(4, self._y + 3, self.width() - 8, self.ROW - 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(theme.ACCENT_B, 0.16 if theme.DARK else 0.10))
        p.drawRoundedRect(hl, 10, 10)
        bar = QRectF(4, self._y + 11, 3.5, self.ROW - 22)
        p.setBrush(QBrush(accent_gradient(0, bar.top(), 0, bar.bottom())))
        p.drawRoundedRect(bar, 2, 2)
        for i, text in enumerate(self.items):
            r = QRectF(20, i * self.ROW, self.width() - 24, self.ROW)
            if i == self._hover and i != self.index:
                p.setBrush(theme.HOVER)
                p.drawRoundedRect(QRectF(4, i * self.ROW + 3, self.width() - 8, self.ROW - 6), 10, 10)
            near = clamp(1 - abs(self._y / self.ROW - i))
            p.setPen(mix(theme.DIM, theme.TEXT, near))
            p.setFont(font(13, QFont.Weight.DemiBold if near > 0.5 else QFont.Weight.Normal))
            p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.end()


class Sections(QStackedWidget):
    """Section pages that cross-fade, with their items rising in."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.items: list[list[QWidget]] = []

    def add(self, page: QWidget, animate: list[QWidget]):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(theme.CARD_QSS + "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page.setStyleSheet("background: transparent;")
        scroll.setWidget(page)
        self.addWidget(scroll)
        self.items.append(animate)

    def show_section(self, i: int):
        self.setCurrentIndex(i)
        w = self.currentWidget()
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", w)
        a.setDuration(260)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.finished.connect(lambda: w.setGraphicsEffect(None))
        a.start()
        for k, item in enumerate(self.items[i]):
            fade_in(item, delay_ms=80 + k * 70, rise=10)


def section_page() -> tuple[QWidget, QVBoxLayout]:
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(8, 4, 18, 16)
    lay.setSpacing(10)
    return page, lay


def h1(text: str) -> QWidget:
    return label(text, 24, QFont.Weight.Bold, display=True)


def para(text: str) -> QWidget:
    w = label(text, 13.5, dim=True)
    w.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return w


def bullets(rows: list[tuple[str, str]]) -> QWidget:
    html = "".join(
        f"<tr><td style='padding:4px 10px 8px 0; color:{theme.rgba(theme.ACCENT_A)}; font-size:15px;'>\u25cf</td>"
        f"<td style='padding:2px 0 8px 0;'><b style='color:{theme.rgba(theme.TEXT)};'>{a}</b><br>"
        f"<span style='color:{theme.rgba(theme.DIM)};'>{b}</span></td></tr>" for a, b in rows)
    return label(f"<table cellspacing='0'>{html}</table>", 13.5)


def table(head: list[str], rows: list[list[str]]) -> QWidget:
    line = theme.rgba(theme.LINE)
    th = "".join(f"<th align='left' style='padding:8px 14px; color:{theme.rgba(theme.DIM)}; font-weight:600;"
                 f" border-bottom:1px solid {line};'>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(
        f"<td style='padding:8px 14px; border-bottom:1px solid {line}; color:{theme.rgba(theme.TEXT)};'>{c}</td>"
        for c in r) + "</tr>" for r in rows)
    return label(f"<table cellspacing='0' width='100%'><tr>{th}</tr>{body}</table>", 13)


def keys_html(*ks: str) -> str:
    style = (f"background:{theme.rgba(theme.SURFACE)}; border:1px solid {theme.rgba(theme.LINE)}; "
             f"border-radius:6px; padding:2px 8px; font-weight:600; color:{theme.rgba(theme.TEXT)};")
    return " + ".join(f"<span style='{style}'>&nbsp;{k}&nbsp;</span>" for k in ks)


# ====================================================================== guide content


def _wheel_demo() -> QWidget:
    """A live copy of the real picker: point at an option, use the arrow keys."""
    from ..catalog import offers_for
    from ..settings import Settings
    from .orbit import OrbitView

    offers, _ = offers_for([Path("C:/Pictures/beach.heic")], Settings())
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 6, 0, 6)
    orbit = OrbitView(offers, "1 HEIC", card_side="right", scale=0.8)
    row.addStretch(1)
    row.addWidget(orbit)
    row.addStretch(1)
    return holder


def build_guide_sections(sections: Sections) -> list[str]:
    names = []

    # 1. Quick start
    page, lay = section_page()
    a = h1("Quick start")
    b = para("Deskvert converts files right where they are, with one shortcut.")
    demo = DemoScene(width=560, height=308)
    c = bullets([
        ("Select one or more files", "In File Explorer or on the Desktop. Mixed selections are fine: Deskvert "
                                     "uses the biggest group of same-type files."),
        ("Tap " + keys_html("Ctrl", "Shift"), "Press both together and let go. The picker opens at your mouse "
                                              "pointer."),
        ("Pick a format", "The converted file appears next to the original. A card at the bottom-right shows "
                          "progress and the result."),
    ])
    for w in (a, b, demo, c):
        lay.addWidget(w)
    lay.addStretch(1)
    sections.add(page, [a, b, demo, c])
    names.append("Quick start")

    # 2. From your browser: the highlight
    page, lay = section_page()
    a = h1("From your browser")
    b = para("Works with Edge, Chrome, Brave, Firefox and Opera, with nothing to install in the browser. "
             "Everything is saved in <b>Downloads\\Deskvert</b>.")
    c = bullets([
        ("Drag anything in", f"Hold {keys_html('Ctrl', 'Shift')} while you drag a picture, link or file out of a "
                             "page. A circle appears: drop on it and pick a format. You always get the biggest "
                             "picture the page offers, not the small preview."),
        ("Selected text", f"Select text on a page and tap {keys_html('Ctrl', 'Shift')}: the picker offers only "
                          "what fits a selection: a clean PDF, Word, Markdown, plain text or a picture of it, each "
                          "with a line saying where it came from. Deskvert reads the selection by copying it and "
                          "then puts your clipboard back exactly as it was."),
        ("Tables to Excel", "Select a table the same way: <b>Tables</b> makes an Excel workbook, one sheet per "
                            "table, or a CSV."),
        ("Save the page", f"Tap {keys_html('Ctrl', 'Shift')} on a browser window with nothing selected: "
                          "the page as a "
                          "PDF, as one long picture, or as a QR code. It uses the Edge or Chrome already on your "
                          "PC, with a fresh, empty profile (no cookies), so pages behind a sign-in show the "
                          "sign-in page."),
        ("Just the article", "Also on the browser tap: <b>Article as PDF</b> keeps the headline, text and pictures "
                             "and leaves out menus, ads, cookie banners and comments."),
        ("All pictures on a page", "<b>All pictures</b> saves every picture on the page at the biggest size it "
                                   "offers, in one folder; icons and tiny pictures are left out."),
        ("QR code for a link", "Drag a link in and pick <b>QR code</b>. Deskvert reads the code back before saving "
                               "it, so it always scans."),
        ("Shared links become files", "Drag a Google Drive, Docs, Dropbox or OneDrive share link in: the file "
                                      "itself downloads, with its real name. It must be shared with anyone who "
                                      "has the link."),
        ("Screenshots and copied pictures", f"Press {keys_html('Win', 'Shift', 'S')}, snip, then tap "
                                            f"{keys_html('Ctrl', 'Shift')} anywhere: the snip opens in the "
                                            "picker. Copied pictures from any app work the same way."),
        ("Website icons", "Pick <b>Website icons</b> on a logo: favicon.ico, the PNG sizes phones use, and a "
                          "page that shows the lines to paste into your site."),
        ("WEBP downloads to JPG", "Optional, in Settings: pictures you download as WEBP or AVIF get a JPG copy next "
                                  "to them, by themselves. The download itself is kept."),
        ("Videos", "Dragging from YouTube or other video sites gives the thumbnail. Deskvert doesn't download "
                   "streaming video."),
    ])
    for w in (a, b, c):
        lay.addWidget(w)
    lay.addStretch(1)
    sections.add(page, [a, b, c])
    names.append("From your browser")

    # 3. The picker
    page, lay = section_page()
    a = h1("The picker")
    b = para("Tools circle on one orbit and formats on the other, and only ones that make sense for your "
             "files appear. Try it below: it's the real one.")
    wheel = _wheel_demo()
    c = bullets([
        ("Point at one", "The orbits stop and a card on the side says what it does and what the new file is "
                         "called."),
        ("Click it", "Converts straight away with the best-quality settings."),
        ("Right-click it", "Opens its options first: quality, page size, password and more."),
        ("Start typing", "Type <b>webp</b> or <b>pdf</b> to search every format. Enter converts, Tab opens options."),
        ("Yellow dot", "This choice has something to know, for example \u201ctransparent areas become white\u201d. "
                       "Point at it to read the note."),
        ("Close it", "Press Esc, click anywhere else, or tap the shortcut again."),
    ])
    for w in (a, b, wheel, c):
        lay.addWidget(w)
    lay.addStretch(1)
    sections.add(page, [a, b, wheel, c])
    names.append("The picker")

    # 4. Formats
    page, lay = section_page()
    a = h1("What converts to what")
    t = table(["You select", "You can make"], [
        ["<b>Images</b>: JPG, PNG, WEBP, HEIC, AVIF, GIF, BMP, TIFF, ICO, TGA, PSD, SVG, RAW",
         "<b>Compress</b> to a size (under 20 KB, 100 KB, 1 MB…), JPG, PNG, WEBP, HEIC, AVIF, GIF, BMP, TIFF, "
         "ICO, TGA, PDF, several images in <b>1 PDF</b>, <b>Read text</b> (OCR)"],
        ["<b>PDF</b>", "<b>Compress</b>, <b>Lock / Unlock</b> with a password, keep or remove <b>Pages</b>, "
                       "<b>Rotate</b>, page <b>Numbers</b>, <b>Watermark</b>, merge into <b>1 PDF</b>, Split, "
                       "PNG / JPG pages, TXT, <b>Searchable</b> PDF from scans (OCR), <b>Sign</b> with your name "
                       "or a picture of your signature"],
        ["<b>Word</b>: DOCX, DOC, ODT, RTF, TXT, HTML", "PDF, DOCX, ODT, RTF, TXT, DOC"],
        ["<b>Excel</b>: XLSX, XLS, ODS", "PDF, XLSX, CSV (first sheet), ODS, XLS"],
        ["<b>PowerPoint</b>: PPTX, PPT, ODP", "PDF, PPTX, ODP, PPT, or PNG / JPG slides in a new folder"],
        ["<b>Data</b>: CSV, TSV, JSON", "XLSX, JSON, CSV, Tidy or Minify JSON"],
        ["<b>Markdown</b>: MD", "PDF, HTML, DOCX (with Word)"],
        ["<b>Archives</b>: ZIP, 7Z, RAR, TAR, GZ, XZ, ISO…", "<b>Extract</b> into a folder, or repack as ZIP"],
        ["<b>Audio</b>: MP3, M4A, WAV, FLAC, WMA…", "Into each other, with a quality choice; <b>Trim</b> to keep "
                                                   "only a part"],
        ["<b>Video</b>: MP4, MOV, MKV, AVI…", "A still <b>Picture</b> of any moment, a <b>Frames sheet</b> of nine "
                                             "moments, or <b>the sound only</b> as MP3, M4A, WAV, FLAC or WMA"],
        ["<b>E-mails</b>: EML, Outlook MSG, MHTML", "PDF, HTML, TXT, Markdown, or the attachments as a ZIP (no "
                                                    "Outlook needed)"],
        ["<b>Web</b>: links (.url), saved pages (HTML)", "Page as <b>PDF</b> or one long <b>picture</b>, "
                                                         "<b>Article as PDF</b>, <b>All pictures</b>, "
                                                         "<b>QR code</b>, <b>Tables</b> to Excel or CSV"],
        ["<b>Any files</b>", "<b>ZIP</b> or 7Z, a <b>Checksum</b>, and <b>Rename</b> many files at once (as copies "
                             "with tidy names, in a new folder)"],
    ])
    b = para("Word, Excel and PowerPoint conversions use your installed Microsoft Office, so the result looks "
             "exactly like it does in Office; without Office, the free LibreOffice is used if it's installed. "
             "Text recognition uses the one built into Windows. Every tool saves "
             "a new file next to the original, such as <b>photo (compressed).jpg</b>; the original is never "
             "changed. The picker shows the full list for whatever you select.")
    for w in (a, t, b):
        lay.addWidget(w)
    lay.addStretch(1)
    sections.add(page, [a, t, b])
    names.append("Formats")

    # 5. Progress & results
    page, lay = section_page()
    a = h1("Progress and results")
    b = bullets([
        ("Progress card", "Bottom-right of your screen: which file, how far along, and a Cancel button. "
                          "It never takes focus from what you're doing."),
        ("Saved next to the original", "<b>photo.heic</b> becomes <b>photo.webp</b> in the same folder. If that "
                                       "name exists, you get <b>photo (1).webp</b>. Nothing is ever overwritten."),
        ("New folders for many files", "Slides or PDF pages as images, and split PDFs, go into a new folder "
                                       "such as <b>Report (pages PNG)</b>."),
        ("Show in folder", "Click it on the card, or find it under Recent conversions in the tray menu. Clicking "
                           "the tray icon opens Deskvert."),
        ("If something fails", "The card turns red and says why, in plain words. Your original is untouched."),
    ])
    for w in (a, b):
        lay.addWidget(w)
    lay.addStretch(1)
    sections.add(page, [a, b])
    names.append("Progress & results")

    # 6. Safety
    page, lay = section_page()
    a = h1("Your files are safe")
    b = bullets([
        ("Originals are only read", "Deskvert never edits, moves or deletes the file you converted."),
        ("Built privately, then checked", "Each result is created in a private work folder, opened again and "
                                          "compared with the original: pixels for lossless images, quality for "
                                          "lossy ones, page and slide counts, the text of documents, every cell "
                                          "of spreadsheets. Only then is it moved into place."),
        ("Camera details kept", "Photo rotation is applied, and camera details, GPS, color profile and dates "
                                "are kept when the new format supports them."),
        ("Office runs locked down", "Documents are opened read-only with macros disabled, in a hidden copy of "
                                    "Office that closes when done. Your Office settings are never changed."),
        ("Nothing leaves your computer", "No uploads, no account. It only goes online to ask GitHub whether a "
                                         "newer version exists, and to fetch something you drag in from a web "
                                         "page."),
    ])
    for w in (a, b):
        lay.addWidget(w)
    lay.addStretch(1)
    sections.add(page, [a, b])
    names.append("Your files are safe")

    # 7. Shortcut & settings
    page, lay = section_page()
    a = h1("Shortcut and settings")
    b = bullets([
        ("The tap", f"{keys_html('Ctrl', 'Shift')}: press both, let go. It's ignored if you press another key or "
                    "click while holding them (so Ctrl+Shift+T or Ctrl+Shift+click work as usual). It acts in File "
                    "Explorer, on the Desktop, on a browser window, and anywhere when you've copied a picture."),
        ("Keyboard layouts", "If Ctrl + Shift also switches your keyboard layout, choose "
                             f"{keys_html('Ctrl', 'Shift', 'Space')} in Settings instead."),
        ("Tray menu", "Right-click the Deskvert icon by the clock: recent conversions, cancel, pause the shortcut, "
                      "this guide, Settings and Quit."),
        ("Performance", "Gentle, Balanced or Faster: how much of the processor conversions may use (15%, 25% or "
                        "50%). Windows enforces the limit."),
        ("Copied files", "If nothing is selected, Deskvert uses files you copied with Ctrl + C."),
        ("Browser features", "Drag and convert, Browser pages and WEBP downloads to JPG can each be turned off "
                             "in Settings → General."),
        ("Watch folders", "Settings → General: pick a folder and what to make (PDF, JPG, Compress…). New files you "
                          "put there are converted by themselves, into a “Converted” folder inside."),
        ("Reduce motion", "Settings → General: still pictures instead of animations. Windows' own Animation effects "
                          "setting is followed too."),
    ])
    for w in (a, b):
        lay.addWidget(w)
    lay.addStretch(1)
    sections.add(page, [a, b])
    names.append("Shortcut & settings")

    # 8. Troubleshooting
    page, lay = section_page()
    a = h1("Troubleshooting")
    b = bullets([
        ("Nothing happens when I tap", "Make sure a file is selected and File Explorer is the active window. "
                                       "Check that the shortcut isn't paused (tray menu)."),
        ("\u201cCan't convert this file\u201d", "The card says why: for example the type isn't supported, or "
                                                "Word documents need Microsoft Office."),
        ("Password-protected files", "PDFs: use <b>Unlock</b> in the picker (you need the password). Office "
                                     "files: remove the password in Office first."),
        ("A scanned PDF has no text", "Use <b>Read text</b> or <b>Searchable</b> in the picker. They use Windows' "
                                      "own text recognition, in the languages installed in Windows (Settings "
                                      "→ Time & language → Language)."),
        ("Report a problem", "Tray menu \u2192 Report a problem, or the Report button on a red card. You see everything "
                             "first, with your name and folders hidden; GitHub opens in your browser to post it. "
                             "Deskvert sends nothing itself."),
        ("Still stuck?", "Tray menu \u2192 Open log folder, and include <b>app.log</b> when reporting an issue on "
                         "GitHub."),
    ])
    for w in (a, b):
        lay.addWidget(w)
    lay.addStretch(1)
    sections.add(page, [a, b])
    names.append("Troubleshooting")
    return names


class GuideWindow(ChromeWindow):
    def __init__(self):
        super().__init__("How to use Deskvert", QSize(940, 640))
        row = QHBoxLayout(self.body)
        row.setContentsMargins(0, 6, 0, 0)
        row.setSpacing(18)
        self.sections = Sections()
        names = build_guide_sections(self.sections)
        self.nav = NavRail(names)
        col = QVBoxLayout()
        col.addWidget(self.nav)
        col.addStretch(1)
        row.addLayout(col)
        row.addWidget(self.sections, 1)
        self.nav.selected.connect(self.sections.show_section)

    def present(self):
        super().present()
        self.sections.show_section(0)
