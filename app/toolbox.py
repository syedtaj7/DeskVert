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
DATA_EXTS = {".csv": "csv", ".tsv": "tsv", ".json": "json"}
MARKDOWN_EXTS = {".md", ".markdown", ".mdown", ".mkd"}
# Raster images Windows OCR can read (after Tapshift decodes them).
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


def _v_password(value: str) -> str | None:
    if len(value or "") < 4:
        return "Use at least 4 characters."
    return None


VALIDATORS = {"pages": _v_pages, "pages_optional": _v_pages_optional, "int": _v_int, "password": _v_password}


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

PDF_COMPRESS = Target("pdf.compress", "Compress", ".pdf", suffix=" (compressed)")
PDF_PAGES = Target("pdf.pages", "Pages", ".pdf", suffix=" (pages)", ask=True)
PDF_LOCK = Target("pdf.lock", "Lock", ".pdf", suffix=" (locked)", ask=True)
PDF_UNLOCK = Target("pdf.unlock", "Unlock", ".pdf", suffix=" (unlocked)", ask=True)
PDF_NUMBERS = Target("pdf.numbers", "Numbers", ".pdf", suffix=" (numbered)", ask=True)
PDF_WATERMARK = Target("pdf.watermark", "Watermark", ".pdf", suffix=" (watermarked)", ask=True)
PDF_ROTATE = Target("pdf.rotate", "Rotate", ".pdf", suffix=" (rotated)", ask=True)

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
            "Shrinks the pictures inside the PDF and cleans up the file. Text stays sharp and searchable."], [
            Option("level", "How much", "choice", "Balanced", choices=("Light", "Balanced", "Strong")),
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
        offers.append(_offer(PDF_ROTATE, "turn pages", [], [
            Option("turn", "Turn", "choice", "90° right", choices=("90° right", "90° left", "180°")),
            Option("pages", "Only these pages (blank = all)", "text", "", placeholder="e.g. 2, 5-6",
                   validate="pages_optional"),
        ], unlocked))
    if locked:
        offers.insert(0, _offer(PDF_UNLOCK, "remove password", [
            "Removes the password, using the password you type. Tapshift can't open PDFs without it."], [
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
    return offers


def zip_offer(files: list[Path]) -> Offer:
    n = len(files)
    return _offer(ZIP, f"{n} file{'s' if n != 1 else ''}, 1 zip", [
        "Packs the selected files into one ZIP next to them (normal compression). Every file is checked afterwards."],
        [], files)


def data_offers(files: list[Path], excel_installed: bool) -> list[Offer]:
    kinds = {p: DATA_EXTS[p.suffix.lower()] for p in files}
    tables = [p for p in files if kinds[p] in ("csv", "tsv")]
    jsons = [p for p in files if kinds[p] == "json"]
    offers: list[Offer] = []
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
    return offers


def markdown_offers(files: list[Path], word_installed: bool) -> list[Offer]:
    offers = [
        _offer(TEXT_PDF, "A4 document", ["Headings, lists, tables, links and code are kept."], [], files),
        _offer(TEXT_HTML, "web page", ["A single web page that opens in any browser."], [], files),
    ]
    if word_installed:
        offers.append(_offer(TEXT_DOCX, "Word", ["Created by Microsoft Word from the formatted text."], [], files))
    return offers


def text_fallback_offers(files: list[Path]) -> list[Offer]:
    """TXT/HTML when Microsoft Word isn't installed: Tapshift can still make a PDF itself."""
    return [_offer(TEXT_PDF, "A4 document", ["Made by Tapshift (Microsoft Word isn't installed)."], [], files)]


def output_ext(t: Target, source: Path, options: dict) -> str:
    """The extension for targets whose format is decided per file ("*")."""
    if t.ext != "*":
        return t.ext
    if t.key == "compress.image":
        fmt = str(options.get("format", "JPG"))
        if fmt == "WEBP":
            return ".webp"
        if fmt == "Same as original" and source.suffix.lower() in (".jpg", ".jpeg", ".webp", ".avif", ".heic",
                                                                     ".heif", ".png"):
            return source.suffix.lower()
        return ".jpg"
    return source.suffix.lower()
