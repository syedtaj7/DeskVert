"""E-books and comics: EPUB, MOBI, FB2, CBZ and XPS -> PDF or plain text.

Read and laid out by MuPDF (already part of Tapshift), so no e-book software is
needed. Books are set on A5-sized pages, a comfortable size for reading on a
screen or printing two to a sheet. DRM-protected books (bought from a store
that locks them) can't be opened.

The result is opened again: the PDF must have every page and the book's text.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path
from .officeutil import text_coverage, words

A5 = (420, 595)  # points
FONT_SIZE = 11


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


def to_pdf(src: Path, out: Path, notes: list[str]) -> None:
    import pymupdf

    with _open(src) as doc:
        source_text = _text(doc)
        pages = doc.page_count
        data = doc.convert_to_pdf()
        title = (doc.metadata or {}).get("title") or src.stem
    with pymupdf.open("pdf", data) as pdf:
        pdf.set_metadata({"title": title, "creator": "Tapshift"})
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
    back = Path(long_path(out)).read_text(encoding="utf-8")
    if back != text:
        raise VerificationError("the text file doesn't match the book")
    notes.append(f"Checked: {len(words(text)):,} words saved as plain text (UTF-8).")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    notes: list[str] = []
    if fmt == "pdf":
        to_pdf(sources[0], out, notes)
    elif fmt == "txt":
        to_txt(sources[0], out, notes)
    else:
        raise ConversionError(f"Unknown e-book conversion: {fmt}")
    return notes
