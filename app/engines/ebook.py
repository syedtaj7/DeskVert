"""E-books and comics.

- pdf / txt: EPUB, MOBI, FB2, CBZ and XPS (read by MuPDF) -> PDF on A5 pages, or
  just the text. Comic archives CBR, CB7 and CBT are unpacked with Windows'
  own tar and their pictures become the PDF's pages.
- epub: a reflowable EPUB 3 book (with a table of contents) from MOBI, FB2,
  another EPUB, a PDF, Markdown, HTML or plain text.
- cbz:  a PDF's pages as pictures in a comic archive (for comic readers).

DRM-protected (store-locked) books can't be opened. Every result is opened
again and its text (or page count) compared with the source.
"""

from __future__ import annotations

import base64
import html
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path
from .officeutil import text_coverage, words

A5 = (420, 595)  # points
FONT_SIZE = 11
IMG_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp", "image/svg+xml": "svg"}
COMIC_ARCHIVES = {".cbr", ".cb7", ".cbt"}
PICTURES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _open(src: Path):
    import pymupdf

    try:
        doc = pymupdf.open(long_path(src))
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"This book can't be opened ({e}). It may be damaged or locked (DRM).") from e
    if doc.needs_pass:
        doc.close()
        raise ConversionError("This book is locked (DRM), so it can't be converted.")
    if doc.is_reflowable:
        doc.layout(width=A5[0], height=A5[1], fontsize=FONT_SIZE)
    if doc.page_count < 1:
        doc.close()
        raise ConversionError("This book has no pages.")
    return doc


def _text(doc) -> str:
    return "\n".join(page.get_text() for page in doc)


# ---------------------------------------------------------------- PDF / TXT

def to_pdf(src: Path, out: Path, notes: list[str]) -> None:
    import pymupdf

    with _open(src) as doc:
        source_text = _text(doc)
        pages = doc.page_count
        data = doc.convert_to_pdf()
        title = (doc.metadata or {}).get("title") or src.stem
    with pymupdf.open("pdf", data) as pdf:
        pdf.set_metadata({"title": title, "creator": "Deskvert"})
        pdf.save(long_path(out), garbage=3, deflate=True)
    with pymupdf.open(long_path(out)) as d:
        if d.page_count != pages:
            raise VerificationError(f"the PDF has {d.page_count} pages, expected {pages}")
        got = _text(d)
    if words(source_text):
        cov = text_coverage(source_text, got)
        if cov is not None and cov < 0.98:
            raise VerificationError(f"only {cov:.0%} of the book's text is in the PDF")
        notes.append(f"Checked: {pages} pages, all of the text included.")
    else:
        notes.append(f"Checked: {pages} pages (pictures only, like a comic).")


def to_txt(src: Path, out: Path, notes: list[str]) -> None:
    with _open(src) as doc:
        text = _text(doc)
    if not words(text):
        raise ConversionError("This book has no text to save (it may be pictures only, like a comic).")
    Path(long_path(out)).write_text(text, encoding="utf-8")
    if Path(long_path(out)).read_text(encoding="utf-8") != text:
        raise VerificationError("the text file doesn't match the book")
    notes.append(f"Checked: {len(words(text)):,} words saved as plain text (UTF-8).")


# ---------------------------------------------------------------- comics

def _natural(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


def comic_to_pdf(src: Path, out: Path, notes: list[str]) -> None:
    import pymupdf

    from .archive import _run_tar

    tmp = out.parent / f"comic-{uuid.uuid4().hex[:8]}"
    tmp.mkdir()
    try:
        _run_tar(["-xf", str(src), "-C", str(tmp)])
        pics = sorted((p for p in tmp.rglob("*") if p.suffix.lower() in PICTURES and p.is_file()), key=_natural)
        if not pics:
            raise ConversionError("No pictures were found in this comic archive.")
        pdf = pymupdf.open()
        for p in pics:
            try:
                img = pymupdf.open(long_path(p))
                rect = img[0].rect
                img.close()
            except Exception:  # noqa: BLE001
                continue
            page = pdf.new_page(width=rect.width, height=rect.height)
            page.insert_image(page.rect, filename=long_path(p))  # JPEGs are stored as they are
        if pdf.page_count == 0:
            raise ConversionError("The pictures in this comic couldn't be read.")
        n = pdf.page_count
        pdf.set_metadata({"title": src.stem, "creator": "Deskvert"})
        pdf.save(long_path(out), garbage=3, deflate=True)
        pdf.close()
    finally:
        shutil.rmtree(long_path(tmp), ignore_errors=True)
    with pymupdf.open(long_path(out)) as d:
        if d.page_count != n:
            raise VerificationError("pages are missing")
    notes.append(f"Checked: {n} pages, one picture each, in reading order.")
    if n < len(pics):
        notes.append(f"{len(pics) - n} file(s) in the archive weren't readable pictures and were skipped.")


def pdf_to_cbz(src: Path, out: Path, notes: list[str]) -> None:
    import pymupdf

    with pymupdf.open(long_path(src)) as d:
        if d.needs_pass:
            raise ConversionError("This PDF is password-protected. Remove the password first.")
        n = d.page_count
        with zipfile.ZipFile(long_path(out), "w", zipfile.ZIP_STORED) as z:  # pictures don't compress further
            for i, page in enumerate(d):
                z.writestr(f"{i + 1:04d}.jpg", page.get_pixmap(dpi=150, alpha=False).tobytes("jpeg", jpg_quality=90))
    with zipfile.ZipFile(long_path(out)) as z:
        if z.testzip() is not None or len(z.namelist()) != n:
            raise VerificationError("the comic archive is incomplete")
    notes.append(f"Checked: {n} pages as pictures (150 dpi) in the comic archive.")


# ---------------------------------------------------------------- EPUB

def _xhtml(fragment: str) -> str:
    """Well-formed XHTML for an HTML fragment (EPUB readers are strict)."""
    from lxml import etree
    from lxml import html as lh

    root = lh.fromstring(f"<div>{fragment}</div>")
    for bad in root.xpath("//script|//style|//meta|//link|//head|//title"):
        bad.drop_tree()
    out = etree.tostring(root, method="xml", encoding="unicode")
    return out[len("<div>"):-len("</div>")] if out.startswith("<div>") and out.endswith("</div>") else out


def _page(title: str, body: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8"/><title>'
            f'{html.escape(title)}</title><style>body{{font-family:serif;line-height:1.5}}img{{max-width:100%}}'
            f'</style></head><body>{body}</body></html>')


def write_epub(out: Path, title: str, chapters: list[tuple[str, str]], images: dict[str, tuple[str, bytes]]) -> None:
    book_id = f"urn:uuid:{uuid.uuid4()}"
    items, spine, navs = [], [], []
    for i, (ctitle, body) in enumerate(chapters, 1):
        items.append(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{i}"/>')
        navs.append(f'<li><a href="c{i}.xhtml">{html.escape(ctitle)}</a></li>')
    for k, (name, (mime, _data)) in enumerate(images.items()):
        items.append(f'<item id="i{k}" href="{name}" media-type="{mime}"/>')
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           'unique-identifier="bookid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="bookid">{book_id}</dc:identifier><dc:title>{html.escape(title)}</dc:title>'
           '<dc:language>en</dc:language><meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata>'
           '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
           '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>' + "".join(items) +
           '</manifest><spine toc="ncx">' + "".join(spine) + "</spine></package>")
    nav = _page(title, f'<nav epub:type="toc"><h1>{html.escape(title)}</h1><ol>{"".join(navs)}</ol></nav>')
    ncx = ('<?xml version="1.0" encoding="utf-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           f'<head><meta name="dtb:uid" content="{book_id}"/></head><docTitle><text>{html.escape(title)}</text>'
           '</docTitle><navMap>' + "".join(
               f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{html.escape(t)}</text></navLabel>'
               f'<content src="c{i}.xhtml"/></navPoint>' for i, (t, _b) in enumerate(chapters, 1)) + "</navMap></ncx>")
    container = ('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    with zipfile.ZipFile(long_path(out), "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")  # first and uncompressed
        z.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, zipfile.ZIP_DEFLATED)
        for i, (ctitle, body) in enumerate(chapters, 1):
            z.writestr(f"OEBPS/c{i}.xhtml", _page(ctitle, body), zipfile.ZIP_DEFLATED)
        for name, (_mime, data) in images.items():
            z.writestr(f"OEBPS/{name}", data, zipfile.ZIP_STORED)


def _split_chapters(body: str, fallback: str) -> list[tuple[str, str]]:
    """Split at top-level headings (h1, or h2 when there's no h1)."""
    level = "h1" if re.search(r"(?i)<h1[\s>]", body) else ("h2" if re.search(r"(?i)<h2[\s>]", body) else None)
    if level is None:
        return [(fallback, body)]
    parts = re.split(rf"(?i)(?=<{level}[\s>])", body)
    chapters = []
    for part in parts:
        if not part.strip():
            continue
        m = re.search(rf"(?is)<{level}[^>]*>(.*?)</{level}>", part)
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
        if chapters and not m:
            chapters[-1] = (chapters[-1][0], chapters[-1][1] + part)
        else:
            chapters.append((t or fallback, part))
    return chapters or [(fallback, body)]


def _data_uri_images(body: str, images: dict) -> str:
    def sub(m):
        mime, b64 = m.group(1), m.group(2)
        ext = IMG_EXT.get(mime)
        if not ext:
            return m.group(0)
        name = f"img{len(images) + 1}.{ext}"
        images[name] = (mime, base64.b64decode(b64))
        return name
    return re.sub(r"data:(image/[\w.+-]+);base64,([A-Za-z0-9+/=\s]+)", sub, body)


def _file_images(body: str, folder: Path, images: dict) -> str:
    def sub(m):
        ref = m.group(2)
        if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", ref) and not re.match(r"[A-Za-z]:[\\/]", ref):
            return m.group(0)  # web or data address
        p = Path(ref) if Path(ref).is_absolute() else folder / ref
        ext = p.suffix.lower().lstrip(".").replace("jpeg", "jpg")
        mime = next((k for k, v in IMG_EXT.items() if v == ext), None)
        if mime is None or not p.is_file():
            return m.group(0)
        name = f"img{len(images) + 1}.{ext}"
        images[name] = (mime, Path(long_path(p)).read_bytes())
        return f'{m.group(1)}"{name}"'
    return re.sub(r'(src\s*=\s*)["\']([^"\']+)["\']', sub, body, flags=re.I)


def _body_of(page_html: str) -> str:
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", page_html)
    return m.group(1) if m else page_html


def to_epub(src: Path, out: Path, notes: list[str]) -> None:
    ext = src.suffix.lower()
    images: dict[str, tuple[str, bytes]] = {}
    title = src.stem
    if ext in (".md", ".markdown", ".mdown", ".mkd", ".txt", ".htm", ".html"):
        from .textdoc import _document

        doc = _document(src)
        source_text = doc.toPlainText()
        body = _file_images(_body_of(doc.toHtml()), src.parent, images)
    elif ext == ".pdf":
        import pymupdf

        from .pdf import markdown_of

        with pymupdf.open(long_path(src)) as d:
            if d.needs_pass:
                raise ConversionError("This PDF is password-protected. Remove the password first.")
            source_text = _text(d)
            md = markdown_of(d)
            title = (d.metadata or {}).get("title") or title
        from PySide6.QtGui import QTextDocument

        from .textdoc import _app

        _app()
        q = QTextDocument()
        q.setMarkdown(md)
        body = _body_of(q.toHtml())
        notes.append("Made from the PDF's text; its layout and pictures aren't kept.")
    else:  # MOBI, FB2, EPUB, XPS: MuPDF's reading of the book
        with _open(src) as d:
            source_text = _text(d)
            title = (d.metadata or {}).get("title") or title
            body = "".join(_body_of(page.get_text("xhtml")) for page in d)
        body = _data_uri_images(body, images)
    if not words(source_text):
        raise ConversionError("There's no text to make a book from.")
    chapters = [(t, _xhtml(b)) for t, b in _split_chapters(body, title)]
    write_epub(out, title, chapters, images)
    with _open(out) as d:
        got = _text(d)
    cov = text_coverage(source_text, got)
    if cov is not None and cov < 0.95:
        raise VerificationError(f"only {cov:.0%} of the text made it into the book")
    notes.insert(0, f"Checked: {len(chapters)} chapter{'s' if len(chapters) != 1 else ''}"
                    f"{f', {len(images)} pictures' if images else ''}, all of the text included.")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    notes: list[str] = []
    src = sources[0]
    if src.suffix.lower() in (".azw", ".azw3"):  # Kindle books: read into one well-formed page first
        from .kindle import to_html

        page, _title = to_html(src)
        work = out.parent / "kindle"
        work.mkdir(parents=True, exist_ok=True)
        src = work / (re.sub(r"[^\w .-]", "_", sources[0].stem)[:60] + ".xhtml")
        src.write_text(page, encoding="utf-8")
        notes.append("Read from the Kindle book without Kindle software.")
    if fmt == "pdf":
        (comic_to_pdf if src.suffix.lower() in COMIC_ARCHIVES else to_pdf)(src, out, notes)
    elif fmt == "txt":
        to_txt(src, out, notes)
    elif fmt == "epub":
        to_epub(src, out, notes)
    elif fmt == "cbz":
        pdf_to_cbz(src, out, notes)
    else:
        raise ConversionError(f"Unknown e-book conversion: {fmt}")
    return notes
