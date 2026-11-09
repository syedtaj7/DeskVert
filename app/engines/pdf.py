"""PDF tools (PyMuPDF).

- merge: several PDFs into one (pages copied as-is; every page's text checked)
- split: one PDF per page, in a new folder
- png / jpg: one image per page, in a new folder (200 dpi)
- txt: the PDF's text (fails clearly for scanned PDFs that have no text)

"""

from __future__ import annotations

from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path


DPI = 200


def _open(path: Path):
    import pymupdf

    try:
        doc = pymupdf.open(long_path(path))
    except Exception as e:
        raise ConversionError(f"This PDF can't be opened; it may be damaged ({e}).") from e
    if doc.needs_pass:
        doc.close()
        raise ConversionError("This PDF is password-protected. Remove the password first.")
    return doc


def _page_texts(doc) -> list[str]:
    return [p.get_text() for p in doc]


def merge(sources: list[Path], out: Path, notes: list[str]) -> None:
    import pymupdf

    result = pymupdf.open()
    expected: list[str] = []
    for src in sources:
        with _open(src) as d:
            result.insert_pdf(d)
            expected += _page_texts(d)
    result.save(long_path(out), garbage=3, deflate=True)
    result.close()
    with _open(out) as d:
        if d.page_count != len(expected):
            raise VerificationError(f"{d.page_count} pages written, expected {len(expected)}")
        for i, (a, b) in enumerate(zip(expected, _page_texts(d))):
            if a.split() != b.split():
                raise VerificationError(f"page {i + 1}'s text differs from the original")
    notes.append(f"Checked: {len(expected)} pages from {len(sources)} PDFs, in folder order.")


def split(src: Path, out_dir: Path, notes: list[str]) -> None:
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    with _open(src) as d:
        n = d.page_count
        texts = _page_texts(d)
        digits = max(2, len(str(n)))
        for i in range(n):
            part = pymupdf.open()
            part.insert_pdf(d, from_page=i, to_page=i)
            part.save(long_path(out_dir / f"{src.stem} - page {str(i + 1).zfill(digits)}.pdf"), garbage=3, deflate=True)
            part.close()
    files = sorted(out_dir.glob("*.pdf"))
    if len(files) != n:
        raise VerificationError(f"{len(files)} files for {n} pages")
    for i, f in enumerate(files):
        with _open(f) as p:
            if p.page_count != 1 or p[0].get_text().split() != texts[i].split():
                raise VerificationError(f"page {i + 1} wasn't copied correctly")
    notes.append(f"Checked: {n} single-page PDFs.")


def to_images(src: Path, out_dir: Path, fmt: str, notes: list[str]) -> None:
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    with _open(src) as d:
        n = d.page_count
        digits = max(2, len(str(n)))
        sizes = []
        for i, page in enumerate(d):
            pix = page.get_pixmap(dpi=DPI, alpha=False)
            target = out_dir / f"Page {str(i + 1).zfill(digits)}.{fmt}"
            if fmt == "png":
                pix.save(long_path(target))
            else:
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img.save(long_path(target), "JPEG", quality=92, subsampling=0, dpi=(DPI, DPI))
            sizes.append((pix.width, pix.height))
    files = sorted(out_dir.iterdir())
    if len(files) != n:
        raise VerificationError(f"{len(files)} images for {n} pages")
    for f, size in zip(files, sizes):
        with Image.open(f) as im:
            im.load()
            if im.size != size:
                raise VerificationError(f"{f.name} has the wrong size")
    notes.append(f"Checked: {n} page images at {DPI} dpi.")


def to_text(src: Path, out: Path, notes: list[str]) -> None:
    with _open(src) as d:
        texts = _page_texts(d)
    body = "\f".join(t.rstrip() for t in texts)  # form feed between pages
    if not body.strip():
        raise ConversionError("This PDF has no text in it. It's probably scanned images, and reading text "
                              "from images (OCR) isn't supported.")
    Path(long_path(out)).write_text(body, encoding="utf-8")
    back = Path(long_path(out)).read_text(encoding="utf-8")
    if back.split() != body.split():
        raise VerificationError("the text file doesn't match the PDF's text")
    notes.append(f"Checked: text from all {len(texts)} pages. Layout and images aren't included.")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    notes: list[str] = []
    if fmt == "merge":
        merge(sources, out, notes)
    elif fmt == "split":
        split(sources[0], out, notes)
    elif fmt in ("png", "jpg"):
        to_images(sources[0], out, fmt, notes)
    elif fmt == "txt":
        to_text(sources[0], out, notes)

    else:
        raise ConversionError(f"Unknown PDF conversion: {fmt}")
    return notes
