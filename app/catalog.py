"""Which conversions are offered for a selection of files, with warnings.

This module is deliberately lightweight (no image libraries) because it runs in
the always-on tray process every time the hotkey is pressed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .settings import Settings


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    kind: str  # "slider" | "toggle" | "choice" | "text" | "password"
    default: object
    min: int = 0
    max: int = 100
    choices: tuple = ()
    placeholder: str = ""
    required: bool = False  # text/password: must not be empty
    validate: str = ""  # name of a validator in app.toolbox.VALIDATORS


@dataclass(frozen=True)
class Target:
    key: str  # "<engine>.<format>", e.g. "image.webp"
    label: str  # shown in the picker, e.g. "WEBP"
    ext: str  # output extension, e.g. ".webp"; "*" = decided per file (same as source or by options)
    combine: bool = False  # many inputs -> one output file
    folder: str = ""  # non-empty: output is a new folder, named "<file> (<folder>)"
    suffix: str = ""  # added to the output name, e.g. " (compressed)"
    ask: bool = False  # open its options first (tools that need input, like a password)

    @property
    def engine(self) -> str:
        return self.key.split(".", 1)[0]

    @property
    def fmt(self) -> str:
        return self.key.split(".", 1)[1]


@dataclass
class Offer:
    target: Target
    caption: str
    warnings: list[str]
    options: list[Option] = field(default_factory=list)
    sources: list[Path] = field(default_factory=list)  # files this offer applies to
    skipped_same: int = 0  # selected files already in this format


# ---------------------------------------------------------------- images

RAW_EXTS = {
    ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".dng", ".orf",
    ".rw2", ".raf", ".pef", ".srw", ".x3f", ".3fr", ".erf", ".kdc", ".mrw", ".rwl", ".iiq",
}

IMAGE_EXTS: dict[str, str] = {
    ".jpg": "jpg", ".jpeg": "jpg", ".jpe": "jpg", ".jfif": "jpg",
    ".png": "png", ".apng": "png",
    ".webp": "webp",
    ".heic": "heic", ".heif": "heic", ".hif": "heic",
    ".avif": "avif",
    ".gif": "gif",
    ".bmp": "bmp", ".dib": "bmp",
    ".tif": "tiff", ".tiff": "tiff",
    ".ico": "ico",
    ".tga": "tga",
    ".psd": "psd",
    ".svg": "svg", ".svgz": "svg",
    ".jp2": "jp2", ".j2k": "jp2", ".jpf": "jp2", ".jpx": "jp2",
    ".qoi": "qoi", ".icns": "icns", ".dds": "dds", ".pcx": "pcx",
    ".ppm": "ppm", ".pgm": "ppm", ".pbm": "ppm", ".pnm": "ppm",
    ".sgi": "sgi", ".rgb": "sgi", ".xbm": "xbm", ".xpm": "xpm", ".cur": "cur",
    ".ras": "sun", ".sun": "sun", ".pcd": "pcd", ".emf": "emf", ".wmf": "emf", ".livp": "livp",
    **{e: "raw" for e in RAW_EXTS},
}

# Ordered by how often people want them (the picker keeps this order).
IMAGE_TARGETS = [
    Target("image.jpg", "JPG", ".jpg"),
    Target("image.png", "PNG", ".png"),
    Target("image.webp", "WEBP", ".webp"),
    Target("image.pdf", "PDF", ".pdf"),
    Target("image.heic", "HEIC", ".heic"),
    Target("image.avif", "AVIF", ".avif"),
    Target("image.ico", "ICO", ".ico"),
    Target("image.tiff", "TIFF", ".tiff"),
    Target("image.gif", "GIF", ".gif"),
    Target("image.bmp", "BMP", ".bmp"),
    Target("image.tga", "TGA", ".tga"),
    Target("image.jp2", "JPEG 2000", ".jp2"),
    Target("image.icns", "ICNS", ".icns"),
    Target("image.qoi", "QOI", ".qoi"),
    Target("image.dds", "DDS", ".dds"),
    Target("image.pcx", "PCX", ".pcx"),
    Target("image.ppm", "PPM", ".ppm"),
    Target("image.sgi", "SGI", ".sgi"),
    Target("image.xbm", "XBM", ".xbm"),
]
COMBINED_PDF = Target("image.pdf_combined", "1 PDF", ".pdf", combine=True)

CAN_ALPHA = {"png", "webp", "heic", "avif", "gif", "tiff", "ico", "tga", "psd", "svg", "bmp", "jp2", "qoi", "icns",
             "dds", "sgi", "xpm", "cur", "emf", "livp"}
CAN_ANIMATE = {"gif", "webp", "png", "avif"}
LOSSY_SOURCES = {"jpg", "heic", "avif"}
LOSSLESS_SOURCES = {"png", "bmp", "tiff", "gif", "tga", "ico", "psd", "svg", "raw", "qoi", "icns", "dds", "pcx",
                    "ppm", "sgi", "xbm", "xpm", "cur", "sun", "emf"}
SINGLE_FRAME_TARGETS = {"jpg", "heic", "bmp", "ico", "tga", "jp2", "icns", "qoi", "dds", "pcx", "ppm", "sgi", "xbm"}


def image_format(path: Path) -> str | None:
    return IMAGE_EXTS.get(path.suffix.lower())


def _image_offer(t: Target, srcs: set[str], n_files: int, s: Settings) -> Offer:
    f = t.fmt
    w: list[str] = []
    opts: list[Option] = []
    caption = ""

    if f in ("jpg", "bmp", "pdf", "pdf_combined") and srcs & CAN_ALPHA:
        w.append("Transparent areas become white.")
    if f in SINGLE_FRAME_TARGETS | {"pdf", "pdf_combined"} and srcs & CAN_ANIMATE:
        w.append("Animated images keep only their first frame.")
    if f == "tiff" and srcs & CAN_ANIMATE:
        w.append("Animation frames become pages.")
    if "raw" in srcs:
        w.append("RAW photos are developed with the camera's white balance (8-bit).")
    if "psd" in srcs:
        w.append("Photoshop layers are merged into one image.")
    if "svg" in srcs:
        w.append("SVG drawings are rendered as pixels (at least 1024 px).")

    if f == "jpg":
        caption = f"quality {s.jpeg_quality}"
        w.append("JPG is lossy: a small, usually invisible, quality loss.")
        opts.append(Option("quality", "Quality", "slider", s.jpeg_quality, 50, 100))
    elif f == "webp":
        lossless = srcs <= LOSSLESS_SOURCES
        caption = "lossless" if lossless else f"quality {s.webp_quality}"
        if not lossless:
            w.append("Lossy WEBP: a small, usually invisible, quality loss.")
        opts.append(Option("lossless", "Lossless (exact pixels, bigger file)", "toggle", lossless))
        opts.append(Option("quality", "Quality (when not lossless)", "slider", s.webp_quality, 50, 100))
    elif f == "heic":
        caption = f"quality {s.heic_quality}"
        w.append("HEIC is lossy: a small, usually invisible, quality loss.")
        opts.append(Option("quality", "Quality", "slider", s.heic_quality, 50, 100))
    elif f == "avif":
        caption = f"quality {s.avif_quality}"
        w.append("AVIF is lossy: a small, usually invisible, quality loss.")
        opts.append(Option("quality", "Quality", "slider", s.avif_quality, 50, 100))
    elif f == "gif":
        caption = "256 colors"
        w.append("GIF holds only 256 colors: photos are dithered and soft edges become hard.")
        opts.append(Option("dither", "Dithering (smoother gradients)", "toggle", True))
    elif f == "png":
        caption = "lossless"
    elif f == "tiff":
        caption = "lossless"
    elif f == "bmp":
        caption = "uncompressed"
    elif f == "tga":
        caption = "lossless"
    elif f == "ico":
        caption = "16-256 px"
        w.append("Icons are at most 256x256: larger images are scaled down, non-square ones padded.")
    elif f == "pdf":
        caption = "1 per image" if n_files > 1 else "lossless"
        opts.append(Option("page", "Page size", "choice", "Image size", choices=("Image size", "A4", "Letter")))
    elif f == "pdf_combined":
        caption = f"{n_files} images, 1 file"
        w.append("All selected images go into one PDF, in folder order.")
        opts.append(Option("page", "Page size", "choice", "Image size", choices=("Image size", "A4", "Letter")))

    if f in ("png", "tiff", "bmp", "tga") and srcs & LOSSY_SOURCES:
        w.append("The file will be larger: this format stores every pixel exactly.")
    return Offer(t, caption, w, opts)


def _image_offers(images: list[Path], s: Settings) -> list[Offer]:
    offers: list[Offer] = []
    if images:
        fmts = {p: image_format(p) for p in images}
        for t in IMAGE_TARGETS:
            applicable = [p for p in images if fmts[p] != t.fmt]
            if not applicable:
                continue
            o = _image_offer(t, {fmts[p] for p in applicable}, len(applicable), s)
            o.sources = applicable
            o.skipped_same = len(images) - len(applicable)
            offers.append(o)
        if len(images) >= 2:
            o = _image_offer(COMBINED_PDF, set(fmts.values()), len(images), s)
            o.sources = images
            # Put "combine into one PDF" right after the per-image PDF option.
            idx = next((i for i, x in enumerate(offers) if x.target.fmt == "pdf"), len(offers) - 1)
            offers.insert(idx + 1, o)
    return offers


# ---------------------------------------------------------------- audio / video (not supported)

MEDIA_EXTS = {
    ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts",
    ".3gp", ".ogv", ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif", ".alac",
}

# ---------------------------------------------------------------- documents (Microsoft Office + PDF)

WORD_EXTS = {".doc": "doc", ".docx": "docx", ".docm": "docx", ".dot": "doc", ".dotx": "docx", ".odt": "odt",
             ".rtf": "rtf", ".txt": "txt", ".htm": "html", ".html": "html", ".wpd": "wpd"}
EXCEL_EXTS = {".xls": "xls", ".xlsx": "xlsx", ".xlsm": "xlsx", ".xlsb": "xlsb", ".ods": "ods"}  # CSV/TSV: data tools
PPT_EXTS = {".ppt": "ppt", ".pptx": "pptx", ".pptm": "pptx", ".pps": "ppt", ".ppsx": "pptx", ".odp": "odp"}


def _doc(key, label, ext, folder=""):
    return Target(key, label, ext, folder=folder)


WORD_TARGETS = [_doc("doc.pdf", "PDF", ".pdf"), _doc("doc.docx", "DOCX", ".docx"), _doc("doc.odt", "ODT", ".odt"),
                _doc("doc.rtf", "RTF", ".rtf"), _doc("doc.txt", "TXT", ".txt"), _doc("doc.doc", "DOC", ".doc")]
EXCEL_TARGETS = [_doc("doc.pdf", "PDF", ".pdf"), _doc("doc.xlsx", "XLSX", ".xlsx"), _doc("doc.csv", "CSV", ".csv"),
                 _doc("doc.ods", "ODS", ".ods"), _doc("doc.xls", "XLS", ".xls")]
PPT_TARGETS = [_doc("doc.pdf", "PDF", ".pdf"), _doc("doc.pptx", "PPTX", ".pptx"),
               _doc("doc.png", "PNG", "", folder="slides PNG"), _doc("doc.jpg", "JPG", "", folder="slides JPG"),
               _doc("doc.odp", "ODP", ".odp"), _doc("doc.ppt", "PPT", ".ppt")]
PDF_TARGETS = [_doc("pdf.docx", "DOCX", ".docx"), _doc("pdf.png", "PNG", "", folder="pages PNG"),
               _doc("pdf.jpg", "JPG", "", folder="pages JPG"), _doc("pdf.txt", "TXT", ".txt"),
               _doc("pdf.split", "Every page", "", folder="pages")]
PDF_MERGE = Target("pdf.merge", "1 PDF", ".pdf", combine=True)


def doc_format(path: Path) -> tuple[str, str] | None:
    """('word'|'excel'|'powerpoint'|'pdf', fmt) or None."""
    e = path.suffix.lower()
    if e == ".pdf":
        return "pdf", "pdf"
    for kind, table in (("word", WORD_EXTS), ("excel", EXCEL_EXTS), ("powerpoint", PPT_EXTS)):
        if e in table:
            return kind, table[e]
    return None


_OFFICE_PROGIDS = {"word": "Word.Application", "excel": "Excel.Application", "powerpoint": "PowerPoint.Application"}
_office_cache: dict[str, bool] = {}


def libre_installed() -> bool:
    """The free LibreOffice: used for Word, Excel and PowerPoint files when Microsoft Office isn't there."""
    from .engines.libre import find_soffice

    return find_soffice() is not None


def office_installed(kind: str) -> bool:
    if kind not in _office_cache:
        try:
            import winreg

            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, _OFFICE_PROGIDS[kind] + r"\CLSID"))
            _office_cache[kind] = True
        except OSError:
            _office_cache[kind] = False
    return _office_cache[kind]


def _doc_offer(t: Target, kind: str, srcs: set[str], n: int) -> Offer:
    f = t.target_fmt if hasattr(t, "target_fmt") else t.fmt
    w: list[str] = []
    caption = {"pdf": "print layout", "docx": "Word", "odt": "OpenDocument", "rtf": "rich text", "txt": "plain text",
               "doc": "Word 97-2003", "xlsx": "Excel", "csv": "first sheet", "ods": "OpenDocument",
               "xls": "Excel 97-2003", "pptx": "PowerPoint", "odp": "OpenDocument", "ppt": "PowerPoint 97-2003",
               "png": "1 image per slide", "jpg": "1 image per slide", "split": "1 PDF per page",
               "merge": f"{n} PDFs, 1 file"}.get(f, "")
    if kind == "pdf":
        caption = {"docx": "editable", "png": "1 image per page", "jpg": "1 image per page",
                   "txt": "text only"}.get(f, caption)
        if f == "docx":
            w.append("An editable Word document: text, headings, bold, lists, pictures and tables are kept; the "
                     "exact page layout can shift. Scanned PDFs need Read text first.")
        if f == "txt":
            w.append("Only the text is kept. Scanned PDFs (pictures of pages) have no text to extract.")
        if f in ("png", "jpg"):
            w.append("Saved in a new folder next to the PDF, one image per page (200 dpi).")
        if f == "split":
            w.append("Saved in a new folder next to the PDF.")
        if f == "merge":
            w.append("Pages are copied as-is, in folder order.")
    else:
        if f == "txt":
            w.append("Plain text only: formatting, images and tables are lost.")
        if f in ("doc", "xls", "ppt"):
            w.append("Old Office format: some newer features may be simplified.")
        if f in ("odt", "ods", "odp"):
            w.append("OpenDocument: complex formatting may look slightly different.")
        if f == "csv":
            w.append("CSV holds values from the first sheet only; formulas and formatting aren't kept.")
        if f in ("png", "jpg"):
            w.append("Saved in a new folder next to the presentation, one image per slide.")
        if "xlsm" in srcs or "docm" in srcs:
            w.append("Macros aren't kept.")
        w.append("Converted by Microsoft Office itself, then checked against the original.")
    return Offer(t, caption, w, [])


def _doc_offers(files: list[Path]) -> list[Offer]:
    kinds = {p: doc_format(p) for p in files}
    groups: dict[str, list[Path]] = {}
    for p, (k, _) in kinds.items():
        groups.setdefault(k, []).append(p)
    # Mixed document types: use the biggest group (e.g. 3 Word files + 1 PDF -> Word).
    kind = max(groups, key=lambda k: len(groups[k]))
    group = groups[kind]
    libre = kind != "pdf" and not office_installed(kind)
    if libre and not libre_installed():
        return []
    targets = {"word": WORD_TARGETS, "excel": EXCEL_TARGETS, "powerpoint": PPT_TARGETS, "pdf": PDF_TARGETS}[kind]

    offers = []
    for t in targets:
        same_fmt = t.fmt
        applicable = [p for p in group if kinds[p][1] != same_fmt or t.folder]
        if not applicable:
            continue
        o = _doc_offer(t, kind, {kinds[p][1] for p in applicable} | {p.suffix.lower().lstrip(".") for p in applicable},
                       len(applicable))
        o.sources = applicable
        o.skipped_same = len(group) - len(applicable)
        if libre:
            o.warnings.append("Made by the free LibreOffice (Microsoft Office isn't installed): the layout can "
                              "differ slightly.")
        offers.append(o)
    if kind == "pdf" and len(group) >= 2:
        o = _doc_offer(PDF_MERGE, "pdf", {"pdf"}, len(group))
        o.sources = group
        offers.insert(0, o)
    return offers


def kind_of(path: Path) -> str | None:
    from . import toolbox

    e = path.suffix.lower()
    if image_format(path):
        return "image"
    if e in toolbox.ARCHIVE_EXTS:
        return "archive"
    if toolbox.data_kind(path):
        return "data"
    if e in toolbox.APPLE_EXTS:
        return "apple"
    if e in toolbox.NOTEBOOK_EXTS:
        return "notebook"
    if e in toolbox.WEBLINK_EXTS:
        return "weblink"
    if toolbox.is_web_clip(path):
        return "clip"
    if e in toolbox.MARKDOWN_EXTS:
        return "markdown"
    if e in toolbox.SUBTITLE_EXTS:
        return "subtitle"
    if e in toolbox.EBOOK_EXTS:
        return "ebook"
    if e in toolbox.AUDIO_EXTS:
        return "audio"
    if e in toolbox.VIDEO_EXTS:
        return "video"
    for kind, exts in (("font", toolbox.FONT_EXTS), ("model", toolbox.MODEL_EXTS), ("drawing", toolbox.DRAWING_EXTS),
                       ("mail", toolbox.MAIL_EXTS), ("map", toolbox.MAP_EXTS), ("vector", toolbox.VECTOR_EXTS)):
        if e in exts:
            return kind
    return "document" if doc_format(path) else None


def pick_group(paths: list[Path]) -> tuple[str | None, list[Path], list[Path]]:
    """Mixed selections: use the largest group of same-kind files."""
    groups: dict[str, list[Path]] = {}
    for p in paths:
        k = kind_of(p)
        if k:
            groups.setdefault(k, []).append(p)
    if not groups:
        return None, [], list(paths)
    order = {"image": 0, "document": 1, "data": 2, "markdown": 3, "archive": 4, "subtitle": 5, "ebook": 6, "font": 7,
             "model": 8, "drawing": 9, "mail": 10, "map": 11, "vector": 12, "audio": 13, "video": 14, "apple": 15,
             "notebook": 16, "weblink": 17, "clip": 18}
    kind = max(groups, key=lambda k: (len(groups[k]), -order[k]))
    chosen = groups[kind]
    return kind, chosen, [p for p in paths if p not in chosen]


def offers_for(paths: list[Path], s: Settings) -> tuple[list[Offer], list[Path]]:
    """Return (offers, files_left_out) for the selected files. Tools come first
    (they're the most used), then format conversions, then ZIP."""
    from . import toolbox

    kind, files, others = pick_group(paths)
    offers: list[Offer] = []
    if kind == "image":
        fmts = {p: image_format(p) for p in files}
        convs = _image_offers(files, s)
        offers = (toolbox.image_tools(files, fmts) + convs + toolbox.image_edits(files, fmts)
                  + toolbox.ocr_offers(files, fmts, pdf=False))
    elif kind == "document":
        groups: dict[str, list[Path]] = {}
        for p in files:
            groups.setdefault(doc_format(p)[0], []).append(p)
        main = max(groups, key=lambda k: len(groups[k]))
        offers = _doc_offers(files)
        if main == "pdf":
            pdfs = groups["pdf"]
            tools = toolbox.pdf_tools(pdfs)
            merge = [o for o in offers if o.target.combine]
            rest = [o for o in offers if not o.target.combine]
            offers = tools + merge + rest + toolbox.ocr_offers(pdfs, None, pdf=True)
        elif main == "word" and not office_installed("word") and not libre_installed():
            simple = [p for p in groups["word"] if p.suffix.lower() in (".txt", ".htm", ".html")]
            offers = toolbox.text_fallback_offers(simple) if simple else []
        if main == "word":
            offers = toolbox.web_table_offers(groups["word"]) + offers  # tables in web pages and web clips
            offers += toolbox.docfree_offers(groups["word"], office_installed("word"))
            offers += toolbox.text_extra_offers(groups["word"])
        if main == "excel":
            offers += toolbox.sheet_offers(groups["excel"])
        used = {p for o in offers for p in o.sources}
        others = others + [p for p in files if p not in used]
    elif kind == "data":
        offers = toolbox.data_offers(files, office_installed("excel"))
    elif kind == "markdown":
        offers = toolbox.markdown_offers(files, office_installed("word"))
    elif kind == "archive":
        offers = toolbox.archive_offers(files)
    elif kind == "subtitle":
        offers = toolbox.subtitle_offers(files)
    elif kind == "ebook":
        offers = toolbox.ebook_offers(files)
    elif kind in ("audio", "video"):
        offers = toolbox.audio_offers(files, video=kind == "video")
    elif kind == "apple":
        offers = toolbox.apple_offers(files)
    elif kind == "notebook":
        offers = toolbox.notebook_offers(files)
    elif kind == "weblink":
        offers = toolbox.weblink_offers(files)
    elif kind == "clip":
        word = next(t for t in WORD_TARGETS if t.key == "doc.docx") if office_installed("word") else None
        offers = toolbox.clip_offers(files, word)
    elif kind in ("font", "model", "drawing", "mail", "map", "vector"):
        offers = {"font": toolbox.font_offers, "model": toolbox.model_offers, "drawing": toolbox.drawing_offers,
                  "mail": toolbox.mail_offers, "map": toolbox.map_offers, "vector": toolbox.vector_offers}[kind](files)
    if paths and kind not in ("archive", "clip"):
        offers.append(toolbox.zip_offer(list(paths)))  # any files can be zipped
        offers += toolbox.pack_offers(list(paths))
    if paths and kind != "clip":
        offers.append(toolbox.hash_offer(list(paths)))  # and any files can get a checksum
        if len(paths) >= 2:
            offers.append(toolbox.rename_offer(list(paths)))  # and many files can be renamed (as copies)
    return offers, others


_COMING = {
    "Kindle book": {".azw", ".azw3", ".kfx"},
}
_NEVER = {
    "program": {".exe", ".msi", ".dll", ".bat", ".cmd", ".ps1", ".sys", ".com", ".scr"},
    "shortcut": {".lnk"},
}


def explain_unsupported(paths: list[Path]) -> tuple[str, str]:
    """(title, message) for files no offer exists for, in plain language."""
    p = paths[0]
    ext = p.suffix.lower()
    many = len(paths) > 1
    title = "Can't convert these files" if many else "Can't convert this file"
    name = f"{len(paths)} selected files" if many else f"“{p.name}”"
    dk = doc_format(p)
    if dk and dk[0] != "pdf" and not office_installed(dk[0]):
        app = {"word": "Word", "excel": "Excel", "powerpoint": "PowerPoint"}[dk[0]]
        return title, f"Converting {p.suffix.upper().lstrip('.')} files needs Microsoft {app}, which isn't installed."
    if ext == ".dwg":
        return title, (f"Converting DWG drawings needs the free ODA File Converter from opendesign.com. Install it "
                       "and Deskvert uses it by itself; nothing else to set up.")
    if ext in MEDIA_EXTS:
        return title, (f"{name} {'are audio or video files' if many else 'is an audio or video file'} Windows "
                       "can't read. Deskvert converts sound with Windows' own converter; re-encoding video isn't "
                       "offered, to keep your laptop light.")

    def a(kind: str) -> str:
        return "" if many else ("an " if kind[0] in "aeiou" else "a ")

    for kind, exts in _COMING.items():
        if ext in exts:
            return title, (f"{name} {'are' if many else 'is'} {a(kind)}{kind}{'s' if many else ''}. "
                           f"{kind[0].upper() + kind[1:]}s aren't supported yet.")
    for kind, exts in _NEVER.items():
        if ext in exts:
            return title, f"{name} {'are' if many else 'is'} {a(kind)}{kind}{'s' if many else ''}, which can't be converted to another format."
    shown = ext.upper().lstrip(".") or "no extension"
    return title, (f"Deskvert doesn't know the {shown} file type. It converts pictures, documents, PDFs, "
                   "e-books, data, subtitles, fonts, maps, 3D models, drawings, sound and archives.")


def describe_selection(paths: list[Path]) -> str:
    if len(paths) == 1:
        return paths[0].name
    exts = sorted({p.suffix.lstrip(".").upper() or "?" for p in paths})
    kinds = ", ".join(exts[:3]) + ("..." if len(exts) > 3 else "")
    return f"{len(paths)} files - {kinds}"
