"""Everyday file tools offered in the picker: image compression, PDF tools,
zip/extract, data files, Markdown/text documents and text recognition (OCR).

Lightweight on purpose (runs in the tray app on every shortcut press): no
image/PDF libraries are imported here; the work happens in worker processes.
"""

from __future__ import annotations

import re
from pathlib import Path

from .catalog import Offer, Option, Target

# ---------------------------------------------------------------- file kinds

ARCHIVE_EXTS = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".tbz", ".tbz2", ".xz", ".txz", ".zst", ".cab",
                ".iso"}
DATA_EXTS = {".csv": "csv", ".tsv": "tsv", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
             ".xml": "xml", ".jsonl": "jsonl", ".ndjson": "jsonl", ".vcf": "vcf",
             ".db": "sqlite", ".sqlite": "sqlite", ".sqlite3": "sqlite", ".db3": "sqlite",
             ".ini": "ini", ".properties": "properties", ".env": "env", ".ics": "ics"}
APPLE_EXTS = {".pages", ".numbers", ".key"}
NOTEBOOK_EXTS = {".ipynb"}
WEBLINK_EXTS = {".url"}  # internet shortcuts: dragged links, and pages saved with Ctrl+Shift
WORD_FREE_EXTS = {".docx", ".docm", ".dotx", ".odt"}  # read without Microsoft Word


def data_kind(p: Path) -> str | None:
    """The kind of data file (".env" files have no extension to Windows: their whole name is ".env")."""
    name = p.name.lower()
    if name == ".env" or name.startswith(".env."):
        return "env"
    return DATA_EXTS.get(p.suffix.lower())
SUBTITLE_EXTS = {".srt": "srt", ".vtt": "vtt", ".ass": "ass", ".ssa": "ass", ".smi": "sami", ".sami": "sami",
                 ".lrc": "lrc", ".ttml": "ttml", ".dfxp": "ttml", ".sub": "microdvd", ".scc": "scc"}
EBOOK_EXTS = {".epub", ".mobi", ".azw", ".azw3", ".fb2", ".cbz", ".xps", ".oxps", ".cbr", ".cb7", ".cbt"}
FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2", ".eot"}
MODEL_EXTS = {".stl", ".obj", ".ply", ".3mf", ".glb", ".gltf"}
DRAWING_EXTS = {".dxf", ".dwg"}
MAIL_EXTS = {".eml", ".msg", ".mht", ".mhtml"}
MAP_EXTS = {".geojson", ".kml", ".kmz", ".gpx", ".shp"}
VECTOR_EXTS = {".ai"}
# Sound only, through Windows' own converter (videos: their sound; the picture is never re-encoded).
from .engines.media import AUDIO_EXTS, VIDEO_EXTS  # noqa: E402  (plain sets, nothing heavy)
# Picture edits work on these (other formats: convert first).
EDIT_IMAGE_FMTS = {"jpg", "png", "webp", "bmp", "tiff"}
MARKDOWN_EXTS = {".md", ".markdown", ".mdown", ".mkd"}
# Raster images Windows OCR can read (after Deskvert decodes them).
OCR_IMAGE_FMTS = {"jpg", "png", "webp", "heic", "avif", "gif", "bmp", "tiff", "tga", "psd", "raw"}

# ---------------------------------------------------------------- page ranges


def parse_pages(text: str, count: int | None = None) -> list[int]:
    """'1-3, 7, 10-end' -> zero-based page indexes (sorted, unique).
    Raises ValueError with a message meant for the user."""
    text = (text or "").strip().lower().replace(" ", "")
    if not text:
        raise ValueError("Type the pages, for example 1-3, 7, 10-end.")
    pages: set[int] = set()
    for part in text.split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d+|end)(?:-(\d+|end))?", part)
        if not m:
            raise ValueError(f"“{part}” isn't a page or range. Use numbers like 1-3, 7, 10-end.")

        def num(s: str) -> int:
            if s == "end":
                if count is None:
                    return 10 ** 9
                return count
            return int(s)

        a = num(m.group(1))
        b = num(m.group(2)) if m.group(2) else a
        if a < 1 or b < 1:
            raise ValueError("Page numbers start at 1.")
        if a > b:
            a, b = b, a
        if count is not None:
            if a > count:
                raise ValueError(f"Page {a} doesn't exist: the PDF has {count} page{'s' if count != 1 else ''}.")
            b = min(b, count)
        if b - a > 100000:
            raise ValueError("That range is too large.")
        pages.update(range(a - 1, b))
    if not pages:
        raise ValueError("No pages selected.")
    return sorted(pages)


def _v_pages(value: str) -> str | None:
    try:
        parse_pages(value)
        return None
    except ValueError as e:
        return str(e)


def _v_pages_optional(value: str) -> str | None:
    return None if not (value or "").strip() else _v_pages(value)


def _v_int(value: str) -> str | None:
    return None if re.fullmatch(r"\d{1,6}", (value or "").strip()) else "Type a whole number, like 1."


def _v_shift(value: str) -> str | None:
    from .engines.subtitle import parse_shift

    try:
        parse_shift(value)
        return None
    except ValueError as e:
        return str(e)


def _v_password(value: str) -> str | None:
    if len(value or "") < 4:
        return "Use at least 4 characters."
    return None


def _v_file_optional(value: str) -> str | None:
    p = (value or "").strip().strip('"')
    if not p:
        return None
    if not Path(p).is_file():
        return "That file wasn't found. Right-click the picture, choose Copy as path, and paste it here."
    if Path(p).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
        return "Use a PNG or JPG picture of your signature."
    return None


def _v_time(value: str) -> str | None:
    from .engines.media import parse_time

    try:
        parse_time(value)
        return None
    except ValueError as e:
        return str(e)


VALIDATORS = {"time": _v_time, "file_optional": _v_file_optional, "pages": _v_pages, "pages_optional": _v_pages_optional, "int": _v_int,
              "password": _v_password,
              "shift": _v_shift}


def validate(opt: Option, value) -> str | None:
    """Error message for a form value, or None when it's fine."""
    if opt.kind in ("text", "password"):
        if opt.required and not str(value or "").strip():
            return f"{opt.label} is required."
        fn = VALIDATORS.get(opt.validate)
        if fn and str(value or "").strip():
            return fn(str(value))
    return None


# ---------------------------------------------------------------- targets

COMPRESS_IMAGE = Target("compress.image", "Compress", "*", suffix=" (compressed)", ask=True)

PDF_COMPRESS = Target("pdf.compress", "Compress", ".pdf", suffix=" (compressed)", ask=True)
PDF_PAGES = Target("pdf.pages", "Keep or remove", ".pdf", suffix=" (pages)", ask=True)
PDF_LOCK = Target("pdf.lock", "Lock", ".pdf", suffix=" (locked)", ask=True)
PDF_UNLOCK = Target("pdf.unlock", "Unlock", ".pdf", suffix=" (unlocked)", ask=True)
PDF_NUMBERS = Target("pdf.numbers", "Numbers", ".pdf", suffix=" (numbered)", ask=True)
PDF_WATERMARK = Target("pdf.watermark", "Watermark", ".pdf", suffix=" (watermarked)", ask=True)
PDF_SIGN = Target("pdf.sign", "Sign", ".pdf", suffix=" (signed)", ask=True)
PDF_ROTATE = Target("pdf.rotate", "Rotate", ".pdf", suffix=" (rotated)", ask=True)
PDF_SPLIT_HALF = Target("pdf.splithalf", "In half", "", folder="halves")
PDF_SPLIT_EVERY = Target("pdf.splitevery", "Every N pages", "", folder="parts", ask=True)
PDF_SPLIT_RANGES = Target("pdf.splitranges", "By ranges", "", folder="parts", ask=True)
PDF_REORDER = Target("pdf.reorder", "Reorder", ".pdf", suffix=" (reordered)", ask=True)
PDF_REVERSE = Target("pdf.reverse", "Reverse", ".pdf", suffix=" (reversed)")
PDF_PICTURES = Target("pdf.pictures", "Pictures", "", folder="pictures")
PDF_GRAY = Target("pdf.gray", "Grayscale", ".pdf", suffix=" (grayscale)")
PDF_FLATTEN = Target("pdf.flatten", "Flatten", ".pdf", suffix=" (flattened)")
PDF_CLEAN = Target("pdf.clean", "Clean info", ".pdf", suffix=" (clean)")
PDF_NUP = Target("pdf.nup", "Per sheet", ".pdf", suffix=" (per sheet)", ask=True)

IMG_ROTL = Target("imgedit.rotl", "Turn left", "*", suffix=" (rotated)")
IMG_ROTR = Target("imgedit.rotr", "Turn right", "*", suffix=" (rotated)")
IMG_ROT180 = Target("imgedit.rot180", "Upside down", "*", suffix=" (rotated)")
IMG_FLIP = Target("imgedit.flip", "Mirror", "*", suffix=" (mirrored)")
IMG_GRAY = Target("imgedit.gray", "Grayscale", "*", suffix=" (grayscale)")
IMG_RESIZE = Target("imgedit.resize", "Resize", "*", suffix=" (resized)", ask=True)
IMG_CLEAN = Target("imgedit.clean", "Clean info", "*", suffix=" (no info)")
IMG_STITCH = Target("imgedit.stitch", "Long image", "*", suffix=" (stitched)", combine=True)

SUB_VTT = Target("subtitle.vtt", "WebVTT", ".vtt")
SUB_SRT = Target("subtitle.srt", "SRT", ".srt")
SUB_TARGETS = [SUB_SRT, SUB_VTT, Target("subtitle.ass", "ASS", ".ass"), Target("subtitle.sami", "SAMI", ".smi"),
               Target("subtitle.ttml", "TTML", ".ttml"), Target("subtitle.lrc", "LRC", ".lrc"),
               Target("subtitle.microdvd", "MicroDVD", ".sub")]
EBOOK_PDF = Target("ebook.pdf", "PDF", ".pdf")
EBOOK_TXT = Target("ebook.txt", "TXT", ".txt")
EBOOK_EPUB = Target("ebook.epub", "EPUB", ".epub")
EBOOK_CBZ = Target("ebook.cbz", "CBZ", ".cbz")
PDF_TIFF = Target("pdf.tiff", "TIFF", ".tiff")
PDF_LONG = Target("pdf.longimg", "Long image", ".jpg", suffix=" (long)")
PDF_MD = Target("pdf.md", "Markdown", ".md")
PDF_HTML = Target("pdf.html", "HTML", ".html")
IMG_DPI = Target("imgedit.dpi", "Set DPI", "*", suffix=" (dpi)", ask=True)
IMG_ANIM = Target("imgedit.anim", "Animated GIF", ".gif", combine=True)
VEC_PDF = Target("vector.pdf", "Vector PDF", ".pdf")
VEC_SVGZ = Target("vector.svgz", "SVGZ", ".svgz")
VEC_SVG = Target("vector.svg", "SVG", ".svg")
VEC_PNG = Target("vector.png", "PNG", ".png")
PACK_7Z = Target("archive.7z", "7Z", ".7z", combine=True)
PACK_TGZ = Target("archive.targz", "TAR.GZ", ".tar.gz", combine=True)
TO_7Z = Target("archive.to7z", "To 7Z", ".7z")
TO_TGZ = Target("archive.totargz", "To TAR.GZ", ".tar.gz")
DATA_TOML = Target("data.toml", "TOML", ".toml")
DATA_XML = Target("data.xml", "XML", ".xml")
DATA_TSV = Target("data.tsv", "TSV", ".tsv")
DATA_SHEETS = Target("data.sheets", "CSV per sheet", "", folder="sheets")
DATA_VCF = Target("data.vcf", "vCard", ".vcf")
DATA_VCSV = Target("data.vcsv", "CSV", ".csv")
DATA_VXLSX = Target("data.vxlsx", "XLSX", ".xlsx")
FONT_WOFF = Target("font.woff", "WOFF", ".woff")
FONT_WOFF2 = Target("font.woff2", "WOFF2", ".woff2")
FONT_SFNT = Target("font.sfnt", "TTF / OTF", "*")
FONT_EOT = Target("font.eot", "EOT", ".eot")
MESH_TARGETS = [Target("mesh.stl", "STL", ".stl"), Target("mesh.obj", "OBJ", ".obj"), Target("mesh.glb", "GLB", ".glb"),
                Target("mesh.3mf", "3MF", ".3mf"), Target("mesh.ply", "PLY", ".ply"),
                Target("mesh.png", "Picture", ".png", suffix=" (preview)")]
CAD_TARGETS = [Target("cad.pdf", "PDF", ".pdf"), Target("cad.svg", "SVG", ".svg"), Target("cad.png", "PNG", ".png")]
CAD_DXF = Target("cad.dxf", "DXF", ".dxf")
MAIL_TARGETS = [Target("mail.pdf", "PDF", ".pdf"), Target("mail.html", "HTML", ".html"), Target("mail.txt", "TXT", ".txt"),
                Target("mail.md", "Markdown", ".md")]
MAIL_ZIP = Target("mail.zip", "Attachments", ".zip", suffix=" (attachments)")
GEO_TARGETS = [Target("geo.kml", "KML", ".kml"), Target("geo.geojson", "GeoJSON", ".geojson"),
               Target("geo.gpx", "GPX", ".gpx"), Target("geo.kmz", "KMZ", ".kmz"), Target("geo.csv", "CSV", ".csv"),
               Target("geo.xlsx", "XLSX", ".xlsx")]
AUDIO_TRIM = Target("media.trim", "Trim", "*", suffix=" (trimmed)", ask=True)
VIDEO_FRAME = Target("videoframe.frame", "Picture", ".jpg", suffix=" (frame)")
VIDEO_SHEET = Target("videoframe.sheet", "Frames sheet", ".jpg", suffix=" (frames)")
VIDEO_GIF = Target("videoframe.gif", "GIF", ".gif")
AUDIO_TARGETS = [Target("media.mp3", "MP3", ".mp3"), Target("media.m4a", "M4A", ".m4a"),
                 Target("media.wav", "WAV", ".wav"), Target("media.flac", "FLAC", ".flac"),
                 Target("media.wma", "WMA", ".wma")]
TEXT_EPUB = Target("ebook.epub", "EPUB", ".epub")
TEXT_MD = Target("textdoc.md", "Markdown", ".md")
DATA_YAML = Target("data.yaml", "YAML", ".yaml")
DATA_JSONL = Target("data.jsonl", "JSON Lines", ".jsonl")
MIXED_PDF = Target("mixed.pdf", "1 PDF", ".pdf", combine=True)

DOCFREE_TXT = Target("docread.txt", "TXT", ".txt")
DOCFREE_MD = Target("docread.md", "Markdown", ".md")
DOCFREE_HTML = Target("docread.html", "HTML", ".html")
IWORK_PDF = Target("iwork.pdf", "PDF", ".pdf")
IWORK_JPG = Target("iwork.jpg", "Picture", ".jpg", suffix=" (preview)")
PDF_TABLES = Target("pdf.tables", "Tables", ".xlsx", suffix=" (tables)")
PDF_BLANK = Target("pdf.blank", "Remove blank", ".pdf", suffix=" (no blank pages)")
IMG_CROP = Target("imgedit.crop", "Crop", "*", suffix=" (cropped)", ask=True)
IMG_PASSPORT = Target("imgedit.passport", "Passport sheet", ".jpg", suffix=" (passport sheet)", ask=True)
IMG_WMARK = Target("imgedit.wmark", "Watermark", "*", suffix=" (watermarked)", ask=True)
IMG_SVG = Target("imgedit.svg", "SVG", ".svg", suffix=" (traced)")
SQLITE_XLSX = Target("sqlitedb.xlsx", "XLSX", ".xlsx")
SQLITE_CSV = Target("sqlitedb.csv", "CSV per table", "", folder="tables")
CONFIG_JSON = Target("config.json", "JSON", ".json")
CONFIG_YAML = Target("config.yaml", "YAML", ".yaml")
ICS_CSV = Target("ics.csv", "CSV", ".csv")
ICS_XLSX = Target("ics.xlsx", "XLSX", ".xlsx")
NB_HTML = Target("notebook.html", "HTML", ".html")
NB_MD = Target("notebook.md", "Markdown", ".md")
NB_PY = Target("notebook.py", "Python", ".py")
SUB_SHIFT = Target("subtitle.shift", "Shift timing", "*", suffix=" (shifted)", ask=True)
HASH = Target("hash.sha256", "Checksum", ".sha256", combine=True)
RENAME = Target("rename.copies", "Rename", "", combine=True, folder="renamed", suffix=" (renamed)", ask=True)
PAGE_PDF = Target("webpage.pdf", "Page as PDF", ".pdf")
PAGE_PNG = Target("webpage.png", "Page as picture", ".png")
PAGE_READER = Target("webextra.reader", "Article as PDF", ".pdf", suffix=" (article)")
PAGE_PICTURES = Target("webextra.pictures", "All pictures", "", folder="pictures")
QR_PNG = Target("qr.png", "QR code", ".png", suffix=" (QR code)")
CLIP_PDF = Target("clip.pdf", "PDF", ".pdf")  # a web clip (selected text), laid out by Edge / Chrome
CLIP_PNG = Target("clip.png", "Picture", ".png")
CLIP_TXT = Target("clip.txt", "Text", ".txt")
WEB_TABLES = Target("webtable.xlsx", "Tables", ".xlsx", suffix=" (tables)")
WEB_TABLE_CSV = Target("webtable.csv", "Table as CSV", ".csv", suffix=" (table)")
FAVICON = Target("favicon.set", "Website icons", "", folder="website icons")

OCR_TXT = Target("ocr.txt", "Read text", ".txt", suffix=" (text)")
OCR_PDF = Target("ocr.pdf", "Searchable", ".pdf", suffix=" (searchable)")

ZIP = Target("archive.zip", "ZIP", ".zip", combine=True)
EXTRACT = Target("archive.extract", "Extract", "", folder="extracted")
TO_ZIP = Target("archive.tozip", "To ZIP", ".zip")

DATA_XLSX = Target("data.xlsx", "XLSX", ".xlsx")
DATA_JSON = Target("data.json", "JSON", ".json")
DATA_CSV = Target("data.csv", "CSV", ".csv")
DATA_TIDY = Target("data.tidy", "Tidy", ".json", suffix=" (tidy)")
DATA_MINIFY = Target("data.minify", "Minify", ".json", suffix=" (min)")

TEXT_PDF = Target("textdoc.pdf", "PDF", ".pdf")
TEXT_HTML = Target("textdoc.html", "HTML", ".html")
TEXT_DOCX = Target("textdoc.docx", "DOCX", ".docx")

COMPRESS_TARGETS_KB = (20, 50, 100, 200, 500, 1000)

# Upload-form presets shown in the Compress panel (the sizes live in engines/compress.py).
FORM_PRESET_ROWS = [
    ("photo", "Form photo", "200×230 px · 20–50 KB · exam & job forms", "form photo"),
    ("passport", "Passport photo", "35×45 mm (413×531 px) · up to 100 KB", "passport photo"),
    ("signature", "Signature", "140×60 px · 10–20 KB · trims the empty paper", "signature"),
]


# ---------------------------------------------------------------- offers


def _offer(t: Target, caption: str, warnings: list[str], options: list[Option], sources: list[Path]) -> Offer:
    o = Offer(t, caption, warnings, options)
    o.sources = list(sources)
    return o


def image_tools(images: list[Path], fmts: dict[Path, str]) -> list[Offer]:
    srcs = [p for p in images if fmts[p] not in ("svg",)]
    if not srcs:
        return []
    many = len(srcs) > 1
    return [_offer(COMPRESS_IMAGE, "choose a size", [
        "Pick a size limit (like under 100 KB) or a quality. You'll see the quality and size before choosing.",
        "Saves a smaller copy next to the original; the original isn't changed."
        + (" Each image is compressed separately." if many else ""),
    ], [
        Option("format", "Save as", "choice", "JPG", choices=("JPG", "WEBP", "Same as original")),
    ], srcs)]


def image_edits(images: list[Path], fmts: dict[Path, str]) -> list[Offer]:
    """Rotate, mirror, grayscale, resize, remove hidden info; several pictures can be stitched."""
    srcs = [p for p in images if fmts.get(p) in EDIT_IMAGE_FMTS]
    if not srcs:
        return _svg_offers(images, fmts)
    offers = [
        _offer(IMG_ROTL, "90° left", ["Turned the way you see it, saved in the same format."], [], srcs),
        _offer(IMG_ROTR, "90° right", ["Turned the way you see it, saved in the same format."], [], srcs),
        _offer(IMG_ROT180, "180°", ["Turned the way you see it, saved in the same format."], [], srcs),
        _offer(IMG_FLIP, "left to right", ["A mirror image, saved in the same format."], [], srcs),
        _offer(IMG_GRAY, "black and white", ["Transparent areas stay transparent."], [], srcs),
        _offer(IMG_RESIZE, "smaller", ["Makes a smaller copy; the original isn't changed."], [
            Option("size", "New size", "choice", "1920 px", choices=("Half size", "1920 px", "1280 px", "1080 px")),
        ], srcs),
        _offer(IMG_CLEAN, "location & camera", [
            "Removes location, camera, date and other hidden details before you share a photo. JPG and PNG "
            "pictures aren't re-encoded: the picture stays exactly the same."], [], srcs),
    ]
    offers += [
        _offer(IMG_CROP, "square, 4:5, 16:9...", ["Cut to that shape from the middle; saved in the same format."], [
            Option("ratio", "Shape", "choice", "1:1 square", choices=("1:1 square", "4:5 portrait", "3:2 photo",
                                                                      "16:9 wide", "9:16 story", "A4 page")),
        ], srcs),
        _offer(IMG_SVG, "traced, any size", [
            "Traces the picture into shapes, so it stays sharp at any size: best for logos, icons and drawings."], [
            Option("detail", "Picture", "choice", "Logo or icon", choices=("Logo or icon", "Drawing",
                                                                           "Photo (big file)")),
            Option("style", "Colours", "choice", "Colour", choices=("Colour", "Black and white")),
        ], srcs),
        _offer(IMG_WMARK, "your text on it", ["White text with a thin dark edge, readable on any picture."], [
            Option("text", "Text", "text", "", placeholder="e.g. © Asha Rao 2026", required=True),
            Option("position", "Where", "choice", "Across the middle", choices=("Across the middle",
                                                                                 "Bottom right corner")),
            Option("opacity", "Strength %", "slider", 30, 10, 80),
        ], srcs),
        _offer(FAVICON, "favicon and app icons", [
            "favicon.ico and every icon size a website needs (up to 512 px), in a new folder, with the lines to "
            "paste into your page."], [], srcs),
        _offer(IMG_PASSPORT, "print 4×6 sheet", [
            "Several passport photos on one 4×6 inch sheet to print at a photo shop or at home. The photo is cut "
            "from the middle: start with a picture where the face is centred."], [
            Option("size", "Photo size", "choice", "35×45 mm (India, UK, EU)",
                   choices=("35×45 mm (India, UK, EU)", "2×2 inch (US)")),
        ], srcs),
    ]
    dpi_ok = [p for p in srcs if fmts.get(p) in ("jpg", "png", "tiff", "bmp")]
    if dpi_ok:
        offers.append(_offer(IMG_DPI, "print resolution", [
            "Sets the print size (dots per inch) without changing a single pixel. JPG isn't re-encoded."], [
            Option("dpi", "Resolution", "choice", "300 dpi", choices=("72 dpi", "96 dpi", "150 dpi", "200 dpi",
                                                                       "300 dpi", "600 dpi")),
        ], dpi_ok))
    if len(srcs) >= 2:
        offers.append(_offer(IMG_STITCH, f"{len(srcs)} in one", [
            "One under the other, in the order selected (like a long screenshot)."], [], srcs))
        offers.append(_offer(IMG_ANIM, f"{len(srcs)} frames", ["A looping animation, in the order selected."], [
            Option("delay", "Each picture", "choice", "1 s", choices=("0.3 s", "0.5 s", "1 s", "2 s", "3 s")),
        ], srcs))
    return offers + _svg_offers(images, fmts)


def _svg_offers(images: list[Path], fmts: dict[Path, str]) -> list[Offer]:
    svgs = [p for p in images if fmts.get(p) == "svg"]
    offers = []
    if svgs:
        offers.append(_offer(VEC_PDF, "sharp at any zoom", ["A vector PDF: lines and text stay sharp."], [], svgs))
        offers.append(_offer(FAVICON, "favicon and app icons", [
            "favicon.ico and every icon size a website needs, drawn sharp from the SVG, in a new folder."], [], svgs))
        plain = [p for p in svgs if p.suffix.lower() == ".svg"]
        packed = [p for p in svgs if p.suffix.lower() == ".svgz"]
        if plain:
            offers.append(_offer(VEC_SVGZ, "compressed", ["The same drawing, gzip-compressed."], [], plain))
        if packed:
            offers.append(_offer(VEC_SVG, "uncompressed", ["The same drawing, as plain SVG."], [], packed))
    return offers


SUB_CAPTIONS = {"srt": "TVs, VLC, editors", "vtt": "web players", "ass": "styled (Aegisub)", "sami": "older players",
                "ttml": "broadcast, Netflix", "lrc": "song lyrics", "microdvd": "frame-based"}


def subtitle_offers(files: list[Path]) -> list[Offer]:
    kinds = {p: SUBTITLE_EXTS[p.suffix.lower()] for p in files}
    offers = []
    for t in SUB_TARGETS:
        srcs = [p for p in files if kinds[p] != t.fmt]
        if srcs:
            offers.append(_offer(t, SUB_CAPTIONS.get(t.fmt, ""), ["Saved as UTF-8; timings are kept."], [], srcs))
    shiftable = [p for p in files if kinds[p] != "scc"]  # SCC is read, not written
    if not shiftable:
        return offers
    offers.append(_offer(SUB_SHIFT, "out of sync?", [
        "Moves every subtitle earlier or later by the same amount; the format stays the same."], [
        Option("seconds", "Seconds (+ later, − earlier)", "text", "", placeholder="e.g. +2.5 or -1", required=True,
               validate="shift"),
    ], shiftable))
    return offers


def ebook_offers(files: list[Path]) -> list[Offer]:
    comics = {".cbz", ".cbr", ".cb7", ".cbt"}
    offers = [_offer(EBOOK_PDF, "A5 pages", ["Laid out on A5 pages; pictures included. Locked (DRM) books can't be "
                                             "opened."], [], files)]
    books = [p for p in files if p.suffix.lower() not in comics | {".cbr"}]
    remake = [p for p in books if p.suffix.lower() != ".epub"]
    if remake:
        offers.append(_offer(EBOOK_EPUB, "e-reader book", ["A reflowable EPUB with chapters, for any e-reader."], [],
                             remake))
    if books:
        offers.append(_offer(EBOOK_TXT, "just the words", ["All the text, without pictures or layout."], [], books))
    return offers


def font_offers(files: list[Path]) -> list[Offer]:
    desk = [p for p in files if p.suffix.lower() in (".ttf", ".otf")]
    web = [p for p in files if p.suffix.lower() in (".woff", ".woff2", ".eot")]
    offers = []
    to_woff2 = [p for p in files if p.suffix.lower() != ".woff2"]
    to_woff = [p for p in files if p.suffix.lower() != ".woff"]
    if to_woff2:
        offers.append(_offer(FONT_WOFF2, "smallest for web pages", [
            "The web's smallest font format; every glyph is checked against the original."], [], to_woff2))
    if to_woff:
        offers.append(_offer(FONT_WOFF, "for web pages", ["Every table copied exactly, compressed."], [], to_woff))
    if desk:
        offers.append(_offer(FONT_EOT, "old Internet Explorer", ["Every table copied exactly."], [], desk))
    if web:
        offers.append(_offer(FONT_SFNT, "install on a PC", ["An installable desktop font, every table exact."], [],
                             web))
    return offers


def model_offers(files: list[Path]) -> list[Offer]:
    exts = {p: p.suffix.lower().lstrip(".") for p in files}
    out = []
    for t in MESH_TARGETS:
        srcs = [p for p in files if exts[p] != t.fmt and not (t.fmt == "glb" and exts[p] == "gltf")]
        if srcs:
            out.append(_offer(t, "shaded preview" if t.fmt == "png" else "3D model",
                              ["The shape is converted; colors and textures aren't."], [], srcs))
    return out


def drawing_offers(files: list[Path]) -> list[Offer]:
    from .engines.oda import find_oda

    dwg = [p for p in files if p.suffix.lower() == ".dwg"]
    if dwg and find_oda() is None:  # DWG needs the free ODA File Converter: without it, only the DXF files
        files = [p for p in files if p.suffix.lower() != ".dwg"]
        dwg = []
    if not files:
        return []
    via = " DWG drawings are read through the free ODA File Converter." if dwg else ""
    offers = [_offer(t, {"pdf": "vector", "svg": "for the web", "png": "picture"}[t.fmt],
                     ["Drawn without AutoCAD: lines, arcs, text and blocks. Hatch fills aren't drawn." + via], [], files)
              for t in CAD_TARGETS]
    if dwg:
        offers.append(_offer(CAD_DXF, "open CAD format", ["The drawing as an AutoCAD 2018 DXF, which most CAD and "
                                                          "design programs open." + via], [], dwg))
    return offers


def mail_offers(files: list[Path]) -> list[Offer]:
    offers = [_offer(t, {"pdf": "A4 document", "html": "one page", "txt": "just the text", "md": "Markdown"}[t.fmt],
                     ["Scripts never run; web pictures aren't downloaded."], [], files) for t in MAIL_TARGETS]
    eml = [p for p in files if p.suffix.lower() in (".eml", ".msg")]
    if eml:
        offers.append(_offer(MAIL_ZIP, "in a ZIP", ["The e-mail's attachments, in one ZIP."], [], eml))
    return offers


def map_offers(files: list[Path]) -> list[Offer]:
    exts = {p: p.suffix.lower().lstrip(".") for p in files}
    return [_offer(t, "map data", ["Longitude / latitude (WGS 84). GPX has no areas: they become tracks."], [],
                   [p for p in files if exts[p] != t.fmt]) for t in GEO_TARGETS
            if any(exts[p] != t.fmt for p in files)]


def vector_offers(files: list[Path]) -> list[Offer]:
    return [_offer(VEC_PDF, "Illustrator as PDF", ["Works with .ai files saved with PDF content (the default)."], [],
                   files),
            _offer(VEC_PNG, "picture", ["Transparent background kept."], [], files)]


AUDIO_CAPTIONS = {"mp3": "plays everywhere", "m4a": "smaller, Apple", "wav": "lossless, editing",
                  "flac": "lossless, smaller", "wma": "Windows Media"}


def audio_offers(files: list[Path], video: bool) -> list[Offer]:
    """Music and recordings into each other; for videos, just their sound. Light: Windows' own converter."""
    exts = {p: p.suffix.lower().lstrip(".") for p in files}
    lossy = [Option("quality", "Quality", "choice", "High (192 kbps)",
                    choices=("High (192 kbps)", "Medium (128 kbps)", "Small (96 kbps)"))]
    offers = []
    for t in AUDIO_TARGETS:
        srcs = [p for p in files if exts[p] != t.fmt]
        if not srcs:
            continue
        cap = "the sound only" if video else AUDIO_CAPTIONS[t.fmt]
        why = ("Takes only the sound; the video itself isn't touched, so it's quick and light."
               if video else "Made by Windows' own converter; nothing to download.")
        offers.append(_offer(t, cap, [why], lossy if t.fmt in ("mp3", "m4a", "wma") else [], srcs))
    if video:  # a still from the video: only the frames needed are decoded, nothing is re-encoded
        offers.insert(0, _offer(VIDEO_GIF, "a short clip", [
            "A few seconds as a looping GIF for chats and documents, 10 pictures a second, no sound. Only that part "
            "of the video is decoded."], [
            Option("start", "Start at", "text", "0:00", placeholder="e.g. 0:30", required=True, validate="time"),
            Option("length", "Length", "choice", "5 seconds", choices=("3 seconds", "5 seconds", "10 seconds")),
            Option("size", "Size", "choice", "Medium (480 px wide)",
                   choices=("Small (320 px wide)", "Medium (480 px wide)", "Large (640 px wide)")),
        ], files))
        offers.insert(0, _offer(VIDEO_SHEET, "9 moments", [
            "Nine moments across the video in one picture, each with its time; quick, nothing is re-encoded."],
            [], files))
        offers.insert(0, _offer(VIDEO_FRAME, "a still", [
            "One moment of the video as a JPG at its full size; quick, nothing is re-encoded."],
            [Option("moment", "Which moment", "choice", "A tenth in",
                    choices=("A tenth in", "The middle", "First frame", "Three quarters in"))], files))
    else:
        offers.insert(0, _offer(AUDIO_TRIM, "keep a part", [
            "Keeps only the part between the two times; the same kind of file (OGG and others become M4A)."], [
            Option("start", "Start", "text", "0:00", placeholder="e.g. 0:30", required=True, validate="time"),
            Option("end", "End (empty: to the end)", "text", "", placeholder="e.g. 2:15", validate="time"),
        ] + lossy, files))
    return offers


def pack_offers(files: list[Path]) -> list[Offer]:
    n = len(files)
    return [_offer(PACK_7Z, f"{n} file{'s' if n != 1 else ''}, smaller", ["7-Zip format, made by Windows' own tar."],
                   [], files),
            _offer(PACK_TGZ, f"{n} file{'s' if n != 1 else ''}", ["For Linux and Mac users."], [], files)]


def sheet_offers(files: list[Path]) -> list[Offer]:
    """Excel workbooks read without Excel."""
    books = [p for p in files if p.suffix.lower() in (".xlsx", ".xlsm")]
    if not books:
        return []
    return [_offer(DATA_SHEETS, "every sheet", ["One CSV per sheet, values as Excel last calculated them."], [], books),
            _offer(DATA_JSON, "records", ["The first sheet; the first row names the fields."], [], books),
            _offer(DATA_YAML, "records", ["The first sheet; the first row names the fields."], [], books),
            _offer(DATA_XML, "records", ["The first sheet; the first row names the fields."], [], books)]


def _csv_header(p: Path) -> list[str]:
    import csv

    try:
        with open(p, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
            line = f.readline(4096)
        return next(csv.reader([line], delimiter="\t" if p.suffix.lower() == ".tsv" else ","), [])
    except OSError:
        return []


def ocr_offers(files: list[Path], fmts: dict[Path, str] | None, pdf: bool) -> list[Offer]:
    if pdf:
        srcs = files
    else:
        srcs = [p for p in files if (fmts or {}).get(p) in OCR_IMAGE_FMTS]
    if not srcs:
        return []
    note = "Uses Windows' own text recognition, offline. Works best on clear, straight scans."
    offers = [_offer(OCR_TXT, "text recognition", [note], [], srcs)]
    if pdf:
        offers.append(_offer(OCR_PDF, "for scans", [
            "Adds an invisible text layer to scanned pages so you can search and copy the text. "
            "Pages look exactly the same.", note], [], srcs))
    return offers


def pdf_is_encrypted(path: Path) -> bool:
    """Cheap check (reads the start and the end of the file) for a password-protected PDF."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 65536))
            tail = f.read()
        return b"/Encrypt" in head or b"/Encrypt" in tail
    except OSError:
        return False


def pdf_tools(pdfs: list[Path]) -> list[Offer]:
    locked = [p for p in pdfs if pdf_is_encrypted(p)]
    unlocked = [p for p in pdfs if p not in locked]
    offers: list[Offer] = []
    if unlocked:
        offers.append(_offer(PDF_COMPRESS, "smaller file", [
            "Pick a size limit (like under 200 KB for a form) or a level. Text stays sharp and searchable."], [
            Option("level", "Size", "choice", "Balanced (no limit)",
                   choices=("Under 200 KB", "Under 500 KB", "Under 1 MB", "Under 2 MB", "Light (no limit)",
                            "Balanced (no limit)", "Strong (no limit)")),
        ], unlocked))
        offers.append(_offer(PDF_PAGES, "keep or remove", [], [
            Option("mode", "Pages to", "choice", "Keep", choices=("Keep", "Remove")),
            Option("pages", "Pages", "text", "", placeholder="e.g. 1-3, 7, 10-end", required=True,
                   validate="pages"),
        ], unlocked))
        offers.append(_offer(PDF_LOCK, "add password", [
            "Protects the PDF with a password (AES-256 encryption). Keep the password safe: it can't be recovered."], [
            Option("password", "Password", "password", "", placeholder="at least 4 characters", required=True,
                   validate="password"),
        ], unlocked))
        offers.append(_offer(PDF_NUMBERS, "on every page", [], [
            Option("position", "Position", "choice", "Bottom center", choices=("Bottom center", "Bottom right",
                                                                              "Top right")),
            Option("style", "Style", "choice", "1", choices=("1", "Page 1", "Page 1 of N")),
            Option("start", "Start at", "text", "1", placeholder="1", validate="int"),
        ], unlocked))
        offers.append(_offer(PDF_WATERMARK, "text stamp", [], [
            Option("text", "Watermark text", "text", "CONFIDENTIAL", placeholder="e.g. CONFIDENTIAL",
                   required=True),
            Option("opacity", "Opacity %", "slider", 18, 5, 60),
            Option("angle", "Direction", "choice", "Diagonal", choices=("Diagonal", "Horizontal")),
        ], unlocked))
        offers.append(_offer(PDF_SIGN, "your signature", [
            "A visible signature: your name in a handwriting font (or a picture of your signature), with the date. "
            "It isn't a certificate-based digital signature."], [
            Option("name", "Your name", "text", "", placeholder="e.g. Asha Rao", required=True),
            Option("pages", "On", "choice", "Last page", choices=("Last page", "First page", "Every page")),
            Option("position", "Where", "choice", "Bottom right", choices=("Bottom right", "Bottom left")),
            Option("date", "Add today's date", "toggle", True),
            Option("picture", "Or a picture of your signature (optional)", "text", "",
                   placeholder="right-click the picture > Copy as path, then paste", validate="file_optional"),
        ], unlocked))
        offers.append(_offer(PDF_ROTATE, "turn pages", [], [
            Option("turn", "Turn", "choice", "90° right", choices=("90° right", "90° left", "180°")),
            Option("pages", "Only these pages (blank = all)", "text", "", placeholder="e.g. 2, 5-6",
                   validate="pages_optional"),
        ], unlocked))
        offers.append(_offer(PDF_SPLIT_HALF, "two PDFs", ["Saved as two PDFs in a new folder next to it."], [],
                             unlocked))
        offers.append(_offer(PDF_SPLIT_EVERY, "equal parts", ["Saved in a new folder next to it."], [
            Option("n", "Pages in each part", "text", "2", placeholder="e.g. 2", required=True, validate="int"),
        ], unlocked))
        offers.append(_offer(PDF_SPLIT_RANGES, "your parts", ["Each range becomes its own PDF, in a new folder."], [
            Option("ranges", "Parts", "text", "", placeholder="e.g. 1-3, 4-10, 11-end", required=True,
                   validate="pages"),
        ], unlocked))
        offers.append(_offer(PDF_REORDER, "new page order", [], [
            Option("order", "New order", "text", "", placeholder="e.g. 3, 1, 2 (others follow)", required=True,
                   validate="pages"),
        ], unlocked))
        offers.append(_offer(PDF_REVERSE, "last page first", [], [], unlocked))
        offers.append(_offer(PDF_LONG, "one picture", ["All pages one under the other (up to 60 pages)."], [],
                             unlocked))
        offers.append(_offer(PDF_TIFF, "multi-page", ["Every page at 200 dpi in one TIFF, lossless."], [], unlocked))
        offers.append(_offer(PDF_MD, "text + headings", ["Text, headings, lists and tables as Markdown."], [],
                             unlocked))
        offers.append(_offer(PDF_HTML, "web page", ["Every page's text and pictures in one web page."], [],
                             unlocked))
        offers.append(_offer(EBOOK_EPUB, "e-book", ["A reflowable EPUB made from the text (layout not kept)."], [],
                             unlocked))
        offers.append(_offer(EBOOK_CBZ, "comic archive", ["Pages as pictures for comic readers."], [], unlocked))
        offers.append(_offer(PDF_NUP, "pages on a sheet", [
            "Puts several pages on each A4 sheet, in reading order. The pages stay sharp (vector)."], [
            Option("per", "Pages per sheet", "choice", "2", choices=("2", "4", "6", "9")),
        ], unlocked))
        offers.append(_offer(PDF_FLATTEN, "lock in form fields", [
            "Form fields and comments become part of the page: they look the same but can't be edited."], [],
            unlocked))
        offers.append(_offer(PDF_CLEAN, "remove hidden details", [
            "Removes the author, title, software and other hidden details, plus scripts. Pages are unchanged."], [],
            unlocked))
        offers.append(_offer(PDF_PICTURES, "save the pictures", ["Saved exactly as stored, in a new folder."], [],
                             unlocked))
        offers.append(_offer(PDF_GRAY, "black and white", [], [], unlocked))
        offers.append(_offer(PDF_TABLES, "into Excel", [
            "Every table found, one Excel sheet each. Works on PDFs made from documents; scanned pages have no "
            "tables to find."], [], unlocked))
        offers.append(_offer(PDF_BLANK, "empty pages out", [
            "Removes pages with nothing on them (no text, nothing visible). The other pages stay exactly as they "
            "are."], [], unlocked))
    if locked:
        offers.insert(0, _offer(PDF_UNLOCK, "remove password", [
            "Removes the password, using the password you type. Deskvert can't open PDFs without it."], [
            Option("password", "Current password", "password", "", required=True),
        ], locked))
    return offers


def archive_offers(files: list[Path]) -> list[Offer]:
    offers = [_offer(EXTRACT, "into a folder", [
        "Extracts into a new folder next to the archive. Uses Windows' built-in tools; nothing is overwritten."],
        [], files)]
    non_zip = [p for p in files if p.suffix.lower() != ".zip"]
    if non_zip:
        offers.append(_offer(TO_ZIP, "repack", ["Re-packs the archive as a standard ZIP that opens everywhere."],
                             [], non_zip))
    non_7z = [p for p in files if p.suffix.lower() != ".7z"]
    if non_7z:
        offers.append(_offer(TO_7Z, "repack, smaller", ["Re-packs the archive as 7Z."], [], non_7z))
    non_tgz = [p for p in files if not p.name.lower().endswith((".tar.gz", ".tgz"))]
    if non_tgz:
        offers.append(_offer(TO_TGZ, "repack", ["Re-packs the archive as TAR.GZ (Linux and Mac)."], [], non_tgz))
    return offers


def zip_offer(files: list[Path]) -> Offer:
    n = len(files)
    return _offer(ZIP, f"{n} file{'s' if n != 1 else ''}, 1 zip", [
        "Packs the selected files into one ZIP next to them (normal compression). Every file is checked afterwards."],
        [], files)


def data_offers(files: list[Path], excel_installed: bool) -> list[Offer]:
    kinds = {p: data_kind(p) for p in files}
    offers_extra: list[Offer] = []
    dbs = [p for p in files if kinds[p] == "sqlite"]
    if dbs:
        offers_extra += [
            _offer(SQLITE_XLSX, "one sheet per table", ["Opened read-only: the database can't change."], [], dbs),
            _offer(SQLITE_CSV, "every table", ["One CSV per table, in a new folder. Read-only."], [], dbs)]
    settings_files = [p for p in files if kinds[p] in ("ini", "env", "properties")]
    if settings_files:
        offers_extra += [
            _offer(CONFIG_JSON, "settings as JSON", ["Every key and value, exactly as written."], [], settings_files),
            _offer(CONFIG_YAML, "settings as YAML", ["Every key and value, exactly as written."], [], settings_files)]
    cals = [p for p in files if kinds[p] == "ics"]
    if cals:
        offers_extra += [
            _offer(ICS_XLSX, "events in Excel", ["One row per event: title, start, end, place..."], [], cals),
            _offer(ICS_CSV, "events table", ["One row per event: title, start, end, place..."], [], cals)]
    tables = [p for p in files if kinds[p] in ("csv", "tsv")]
    jsons = [p for p in files if kinds[p] == "json"]
    other = [p for p in files if kinds[p] in ("yaml", "toml", "xml", "jsonl")]
    vcards = [p for p in files if kinds[p] == "vcf"]
    offers: list[Offer] = []
    if vcards:
        offers.append(_offer(DATA_VCSV, "contacts table", ["Names, phones, emails, company and more."], [], vcards))
        offers.append(_offer(DATA_VXLSX, "contacts in Excel", ["Names, phones, emails, company and more."], [],
                             vcards))
    structured = other + jsons + tables
    for t, cap in ((DATA_TOML, "settings file"), (DATA_XML, "same data")):
        srcs = [p for p in structured if kinds[p] != t.fmt]
        if srcs:
            offers.append(_offer(t, cap, ["Every value is kept (tables become records)."], [], srcs))
    if tables:
        csvs = [p for p in tables if kinds[p] == "csv"]
        tsvs = [p for p in tables if kinds[p] == "tsv"]
        if csvs:
            offers.append(_offer(DATA_TSV, "tab separated", ["Every cell the same."], [], csvs))
        if tsvs:
            offers.append(_offer(DATA_CSV, "comma separated", ["Every cell the same."], [], tsvs))
        offers.append(_offer(DATA_YAML, "records", ["The first row names the fields."], [], tables))
        from .engines.geo import csv_columns

        maps = [p for p in tables if kinds[p] == "csv" and csv_columns(_csv_header(p))]
        for t in GEO_TARGETS[:4]:
            if maps:
                offers.append(_offer(t, "map from coordinates", ["Uses the longitude / latitude (or WKT) column."],
                                     [], maps))
        heads = {p: [h.strip().lower() for h in _csv_header(p)] for p in tables}
        people = [p for p in tables if any(h in ("name", "full name", "first name", "phone", "mobile", "email",
                                                 "e-mail") for h in heads[p])]
        if people:
            offers.append(_offer(DATA_VCF, "phone contacts", ["One contact per row (name, phone, email...)."], [],
                                 people))
    if other:
        offers.append(_offer(DATA_JSON, "same data", ["Every value is kept; dates become text like 2026-11-09."],
                             [], other))
        not_yaml = [p for p in other if kinds[p] != "yaml"]
        if not_yaml:
            offers.append(_offer(DATA_YAML, "easy to read", ["Every value is kept."], [], not_yaml))
        offers.append(_offer(DATA_CSV, "table", ["Works with a list of records."], [], other))
        offers.append(_offer(DATA_XLSX, "Excel workbook", ["Works with a list of records."], [], other))
    if jsons:
        offers.append(_offer(DATA_YAML, "easy to read", ["Every value is kept, numbers exactly as written."], [],
                             jsons))
        offers.append(_offer(DATA_JSONL, "one record per line", ["Works with a list (like a list of records)."],
                             [], jsons))
    if tables:
        offers.append(_offer(DATA_XLSX, "Excel workbook", [
            "Numbers become real numbers; values like 007 or 1.50 stay exactly as written."], [], tables))
        offers.append(_offer(DATA_JSON, "list of records", ["Uses the first row as field names."], [], tables))
        if excel_installed:
            from .catalog import _doc

            offers.append(_offer(_doc("doc.pdf", "PDF", ".pdf"), "print layout",
                                 ["Converted by Microsoft Excel."], [], tables))
    if jsons:
        offers.append(_offer(DATA_CSV, "table", [
            "Works with a list of records. Nested values are kept as JSON text in their cell."], [], jsons))
        offers.append(_offer(DATA_XLSX, "Excel workbook", ["Works with a list of records."], [], jsons))
        offers.append(_offer(DATA_TIDY, "easy to read", ["Re-indents the JSON. The data is unchanged."], [], jsons))
        offers.append(_offer(DATA_MINIFY, "smallest", ["Removes spaces and line breaks. The data is unchanged."],
                             [], jsons))
    return offers_extra + offers


def markdown_offers(files: list[Path], word_installed: bool) -> list[Offer]:
    offers = [
        _offer(TEXT_PDF, "A4 document", ["Headings, lists, tables, links and code are kept."], [], files),
        _offer(TEXT_HTML, "web page", ["A single web page that opens in any browser."], [], files),
    ]
    if word_installed:
        offers.append(_offer(TEXT_DOCX, "Word", ["Created by Microsoft Word from the formatted text."], [], files))
    offers.append(_offer(TEXT_EPUB, "e-book", ["A reflowable EPUB; headings become chapters."], [], files))
    return offers


WEB_CLIP_MARK = b'<meta name="generator" content="Deskvert web clip">'


def is_web_clip(p: Path) -> bool:
    """Text or a table taken from a web page (saved by Deskvert as a small .html with a marker)."""
    if p.suffix.lower() not in (".html", ".htm"):
        return False
    try:
        with open(p, "rb") as f:
            head = f.read(2048)
        return WEB_CLIP_MARK in head
    except OSError:
        return False


def clip_offers(files: list[Path], word: Target | None) -> list[Offer]:
    """Only what makes sense for a piece of a page: the text as a document, a picture of it, its tables."""
    out = web_table_offers(files)
    if out:
        out[0] = _offer(WEB_TABLES, "into Excel", ["Every table in your selection, one sheet each."], [], files)
    out.append(_offer(CLIP_PDF, "clean, searchable", ["Just your selection, laid out like the page; text stays "
                                                       "text."], [], files))
    if word is not None:
        out.append(_offer(word, "to edit", ["Made by Microsoft Word, headings and lists kept."], [], files))
    out.append(_offer(TEXT_MD, "for notes", ["Headings, lists, tables and links kept."], [], files))
    out.append(_offer(CLIP_TXT, "just the words", ["Plain text, one paragraph per line."], [], files))
    out.append(_offer(CLIP_PNG, "to share", ["Your selection as one picture, sharp at twice the size."], [], files))
    return out


def weblink_offers(files: list[Path]) -> list[Offer]:
    """Web page links: the page saved by the browser already on this PC, or a QR code."""
    how = ["Opened in a private, signed-out Edge or Chrome window (your browser data isn't used)."]
    return [_offer(PAGE_PDF, "the whole page", ["Text stays text: sharp and searchable."] + how, [], files),
            _offer(PAGE_READER, "just the article", ["The headline, text and pictures without menus, ads, cookie "
                                                     "banners or comments; calm to read and print."] + how, [], files),
            _offer(PAGE_PICTURES, "in a folder", ["Every picture on the page at the biggest size it offers; icons "
                                                  "and tiny pictures are left out."] + how, [], files),
            _offer(PAGE_PNG, "one long picture", ["The whole page as one picture, like a full screenshot."] + how,
                   [], files),
            _offer(QR_PNG, "scan with a phone", ["A QR code that opens this page; checked by reading it back."], [],
                   files)]


def has_table(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return b"<table" in f.read(4_000_000).lower()
    except OSError:
        return False


def web_table_offers(files: list[Path]) -> list[Offer]:
    pages = [p for p in files if p.suffix.lower() in (".htm", ".html", ".mht", ".mhtml") and has_table(p)]
    if not pages:
        return []
    return [_offer(WEB_TABLES, "into Excel", ["Every table, one sheet each; merged cells spread out as they look."],
                   [], pages),
            _offer(WEB_TABLE_CSV, "the biggest table", ["Every cell as on the page."], [], pages)]


def text_extra_offers(files: list[Path]) -> list[Offer]:
    """TXT / HTML documents: an e-book, and HTML as Markdown (no Word needed)."""
    texts = [p for p in files if p.suffix.lower() in (".txt", ".htm", ".html")]
    out = []
    if texts:
        out.append(_offer(TEXT_EPUB, "e-book", ["A reflowable EPUB; headings become chapters."], [], texts))
    pages = [p for p in files if p.suffix.lower() in (".htm", ".html")]
    if pages:
        out.append(_offer(TEXT_MD, "Markdown", ["Headings, lists, tables and links kept."], [], pages))
    return out


def docfree_offers(files: list[Path], word_installed: bool) -> list[Offer]:
    """Word and OpenDocument text read directly: no Office needed."""
    docs = [p for p in files if p.suffix.lower() in WORD_FREE_EXTS]
    if not docs:
        return []
    why = ["Read directly, without Microsoft Office: text, headings, lists and tables. Pictures and page layout "
           "aren't included."]
    offers = [] if word_installed else [_offer(DOCFREE_TXT, "just the words", why, [], docs)]
    return offers + [_offer(DOCFREE_MD, "headings, lists, tables", why, [], docs),
                     _offer(DOCFREE_HTML, "web page", why, [], docs)]


def apple_offers(files: list[Path]) -> list[Offer]:
    why = ["Takes out the preview Apple saves inside the file. Newer files only keep the first page; the full "
           "document opens only in Apple's apps."]
    return [_offer(IWORK_PDF, "Apple's preview", why, [], files),
            _offer(IWORK_JPG, "first page", why, [], files)]


def notebook_offers(files: list[Path]) -> list[Offer]:
    why = ["Read only, never run."]
    return [_offer(NB_HTML, "with the results", why + ["Notes, code, text results and charts, in one page."], [],
                   files),
            _offer(NB_MD, "notes and code", why, [], files),
            _offer(NB_PY, "the code", why + ["Notes become comments; results aren't included."], [], files)]


def rename_offer(files: list[Path]) -> Offer:
    n = len(files)
    return _offer(RENAME, f"{n} file{'s' if n != 1 else ''}, tidy names", [
        "Copies with new names in a new folder, e.g. “2026-11-13 01.jpg”. Your originals keep their names."], [
        Option("pattern", "Name", "text", "{date} {n}", placeholder="{date} {n}, Holiday {n}, {name} {n}",
               required=True),
        Option("order", "Order", "choice", "Date taken", choices=("Date taken", "Name", "As selected")),
        Option("start", "Start at", "text", "1", placeholder="1", validate="int"),
    ], files)


def hash_offer(files: list[Path]) -> Offer:
    n = len(files)
    return _offer(HASH, "SHA-256" if n == 1 else f"{n} files, SHA-256", [
        "A small .sha256 file listing each file's fingerprint, to check later that nothing changed (after a "
        "download, a copy or a backup)."], [], files)


def text_fallback_offers(files: list[Path]) -> list[Offer]:
    """TXT/HTML when Microsoft Word isn't installed: Deskvert can still make a PDF itself."""
    return [_offer(TEXT_PDF, "A4 document", ["Made by Deskvert (Microsoft Word isn't installed)."], [], files)]


def output_ext(t: Target, source: Path, options: dict) -> str:
    """The extension for targets whose format is decided per file ("*")."""
    if t.ext != "*":
        return t.ext
    if t.key == "font.sfnt":
        from .engines.font import desktop_ext

        return desktop_ext(source)
    if t.key == "media.trim":  # the same kind of file when Windows can write it, otherwise M4A
        from .engines.media import trim_ext

        return trim_ext(source)
    if t.key == "imgedit.stitch":  # JPG when the pictures are photos, PNG otherwise
        return ".jpg" if source.suffix.lower() in (".jpg", ".jpeg") else ".png"
    if t.key == "compress.image":
        fmt = str(options.get("format", "JPG"))
        if fmt == "WEBP":
            return ".webp"
        if fmt == "Same as original" and source.suffix.lower() in (".jpg", ".jpeg", ".webp", ".avif", ".heic",
                                                                     ".heif", ".png"):
            return source.suffix.lower()
        return ".jpg"
    return source.suffix.lower()
