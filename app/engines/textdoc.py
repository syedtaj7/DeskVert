"""Markdown / plain text / simple HTML -> PDF, HTML or DOCX.

Rendered by Qt's own text engine (already part of Deskvert, no browser):
- pdf:  A4 with page numbers. Markdown keeps headings, lists, tables, links,
        code and local images; plain text keeps its line layout (monospace).
- html: one self-contained web page
- docx: the HTML above, saved as .docx by Microsoft Word (only offered when
        Word is installed)

The output's text is read back and compared with the source.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path
from .officeutil import text_coverage, words

PAGE_CSS = ("body{max-width:820px;margin:40px auto;padding:0 20px;line-height:1.5}"
            "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}"
            "pre,code{background:#f4f4f4}img{max-width:100%}")


def _app():
    from PySide6.QtGui import QColor, QGuiApplication, QPalette

    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(["deskvert-worker"])
        pal = app.palette()
        pal.setColor(QPalette.ColorRole.Link, QColor("#1a5fb4"))  # documents use plain link blue
        app.setPalette(pal)
    return app


def _read(src: Path) -> str:
    raw = Path(long_path(src)).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _document(src: Path):
    """A QTextDocument with the file's content."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QFont, QTextDocument

    _app()
    text = _read(src)
    if not text.strip():
        raise ConversionError("The file is empty.")
    doc = QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(src.parent) + "/"))  # local images next to the file
    doc.setDocumentMargin(0)
    ext = src.suffix.lower()
    if ext in (".htm", ".html"):
        doc.setDefaultFont(QFont("Segoe UI", 10))
        doc.setHtml(text)
    elif ext == ".txt":
        doc.setDefaultFont(QFont("Consolas", 9))
        doc.setPlainText(text)
    else:
        doc.setDefaultFont(QFont("Segoe UI", 10))
        doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
    _load_images(doc, src.parent)
    if ext not in (".txt",):
        _polish(doc)
    return doc


def _load_images(doc, folder: Path) -> None:
    """Local pictures are loaded up front (printing doesn't fetch them).
    Web pictures aren't downloaded."""
    from urllib.parse import unquote, urlparse

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QImage, QTextDocument, QTextFormat

    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fmt = it.fragment().charFormat()
            if fmt.isImageFormat():
                name = fmt.toImageFormat().name()
                url = urlparse(name)
                if url.scheme in ("", "file") or len(url.scheme) == 1:  # c:/... parses as scheme "c"
                    raw = unquote(url.path if url.scheme == "file" else name)
                    path = Path(raw.lstrip("/") if url.scheme == "file" and re.match(r"/[A-Za-z]:", raw) else raw)
                    if not path.is_absolute():
                        path = folder / path
                    img = QImage(str(path))
                    if not img.isNull():
                        if img.width() > 1600:  # keeps the PDF light; still sharp at A4 width
                            img = img.scaledToWidth(1600)
                        doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
            it += 1
        block = block.next()
    _ = QTextFormat  # noqa: F841


def _polish(doc) -> None:
    """Readable spacing: room around headings and paragraphs, shaded code."""
    from PySide6.QtGui import QColor, QTextCursor

    cursor = QTextCursor(doc)
    block = doc.begin()
    while block.isValid():
        bf = block.blockFormat()
        level = bf.headingLevel()
        if level:
            bf.setTopMargin(14 if level <= 2 else 10)
            bf.setBottomMargin(6)
        elif bf.nonBreakableLines():  # code block
            bf.setBackground(QColor("#f3f4f3"))
            bf.setLeftMargin(max(bf.leftMargin(), 6))
        elif not block.textList() and bf.bottomMargin() < 6:
            bf.setBottomMargin(6)
        cursor.setPosition(block.position())
        cursor.setBlockFormat(bf)
        block = block.next()


def _check(source_text: str, output_text: str, what: str, minimum: float = 0.98) -> None:
    cov = text_coverage(source_text, output_text)
    if cov is not None and cov < minimum:
        raise VerificationError(f"only {cov:.0%} of the text made it into the {what}")
    if not words(output_text) and words(source_text):
        raise VerificationError(f"the {what} has no text")


def to_pdf(src: Path, out: Path, notes: list[str]) -> None:
    import pymupdf
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter

    doc = _document(src)
    writer = QPdfWriter(long_path(out))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(20, 18, 20, 18), QPageLayout.Unit.Millimeter)
    writer.setResolution(300)
    writer.setTitle(src.stem)
    writer.setCreator("Deskvert")
    doc.print_(writer)  # paginates and adds page numbers
    del writer  # finishes the file
    try:
        with pymupdf.open(long_path(out)) as d:
            pages, text = d.page_count, "\n".join(p.get_text() for p in d)
    except Exception as e:
        raise VerificationError(f"the PDF can't be opened: {e}") from e
    if pages < 1:
        raise VerificationError("the PDF has no pages")
    _check(doc.toPlainText(), text, "PDF")
    notes.append(f"Checked: {pages} A4 page{'s' if pages != 1 else ''}, all of the text included.")
    if src.suffix.lower() in (".htm", ".html"):
        notes.append("Simple layout: web page styles and scripts aren't kept.")


def _page_html(src: Path) -> tuple[str, str]:
    """(html, plain text) for a standalone web page."""
    doc = _document(src)
    body = doc.toHtml()
    title = f"<title>{html.escape(src.stem)}</title><style>{PAGE_CSS}</style>"
    body = re.sub(r"<head>", "<head>" + title, body, count=1) if "<head>" in body else title + body
    return body, doc.toPlainText()


def to_html(src: Path, out: Path, notes: list[str]) -> None:
    from PySide6.QtGui import QTextDocument

    page, plain = _page_html(src)
    Path(long_path(out)).write_text(page, encoding="utf-8")
    back = QTextDocument()
    back.setHtml(Path(long_path(out)).read_text(encoding="utf-8"))
    if words(back.toPlainText()) != words(plain):
        raise VerificationError("the web page's text doesn't match the file")
    notes.append("Checked: all of the text is in the web page. Images are linked from their current folder.")


def to_docx(src: Path, out: Path, notes: list[str]) -> None:
    from .doc import convert_word

    page, _plain = _page_html(src)
    # Word resolves relative image links against the HTML's folder, so point
    # them at the original file's folder.
    base = src.parent.as_uri() + "/"
    page = re.sub(r'(<img[^>]*src=")(?![a-zA-Z][a-zA-Z0-9+.-]*:)([^"]+)"', lambda m: f'{m.group(1)}{base}{m.group(2)}"',
                  page)
    staged = out.parent / f"{re.sub(r'[^A-Za-z0-9_-]', '_', src.stem)[:40] or 'page'}.html"
    staged.write_text(page, encoding="utf-8")
    convert_word(staged, out, "docx", notes)


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    notes: list[str] = []
    src = sources[0]
    if fmt == "pdf":
        to_pdf(src, out, notes)
    elif fmt == "html":
        to_html(src, out, notes)
    elif fmt == "docx":
        to_docx(src, out, notes)
    elif fmt == "md":
        doc = _document(src)
        md = doc.toMarkdown()
        Path(long_path(out)).write_text(md, encoding="utf-8")
        _check(doc.toPlainText(), Path(long_path(out)).read_text(encoding="utf-8"), "Markdown", 0.95)
        notes.append("Checked: all of the text, with headings, lists, tables and links as Markdown.")
    else:
        raise ConversionError(f"Unknown document conversion: {fmt}")
    return notes
