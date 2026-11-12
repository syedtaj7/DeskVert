"""Apple Pages, Numbers and Keynote files: the preview Apple saves inside them.

Windows can't open iWork files, but each one carries a picture of itself:
newer files a preview of the first page (preview.jpg), older ones a full PDF
(QuickLook/Preview.pdf). Tapshift takes that out, as it is:

- jpg: the preview picture
- pdf: the full PDF when the file has one; otherwise the preview picture as a
       one-page PDF (said clearly in the note)

The rest of the document can only be read by Apple's apps.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

EXTS = {".pages": "Pages", ".numbers": "Numbers", ".key": "Keynote"}
PDF_NAMES = ("QuickLook/Preview.pdf", "preview.pdf", "Preview.pdf")
PICTURE_NAMES = ("preview.jpg", "QuickLook/Thumbnail.jpg", "preview-web.jpg", "QuickLook/Preview.jpg",
                 "preview-micro.jpg")


def _parts(src: Path) -> tuple[bytes | None, bytes | None]:
    """(full PDF, best preview picture), either may be missing."""
    app = EXTS.get(src.suffix.lower(), "iWork")
    try:
        z = zipfile.ZipFile(long_path(src))
    except zipfile.BadZipFile as e:
        raise ConversionError(f"This {app} file can't be read on Windows: it was saved without a preview, or it's "
                              "a folder package from a Mac. On the Mac, use File > Export To > PDF.") from e
    with z:
        names = {n.lower(): n for n in z.namelist()}
        pdf = next((z.read(names[n.lower()]) for n in PDF_NAMES if n.lower() in names), None)
        pic = next((z.read(names[n.lower()]) for n in PICTURE_NAMES if n.lower() in names), None)
    if pdf is None and pic is None:
        raise ConversionError(f"This {app} file has no preview saved in it. On a Mac or iPhone, export it as PDF "
                              "instead.")
    return pdf, pic


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    import pymupdf
    from PIL import Image

    src = sources[0]
    pdf, pic = _parts(src)
    if fmt == "jpg":
        if pic is None:  # only a PDF inside: its first page, as a picture
            with pymupdf.open(stream=pdf, filetype="pdf") as d:
                pic = d[0].get_pixmap(dpi=150, alpha=False).tobytes("jpeg", 92)
        try:
            im = Image.open(io.BytesIO(pic))
            im.load()
        except Exception as e:  # noqa: BLE001
            raise ConversionError("The preview inside this file is damaged.") from e
        if im.format == "JPEG":
            Path(long_path(out)).write_bytes(pic)  # exactly as Apple saved it
        else:
            im.convert("RGB").save(long_path(out), "JPEG", quality=92)
        with Image.open(long_path(out)) as back:
            back.load()
            size = back.size
        if size != im.size:
            raise VerificationError("the picture changed size")
        return [f"Checked: the preview Apple saved in the file, {size[0]}×{size[1]} px.",
                "It shows the first page only; the full document opens only in Apple's apps."]
    if fmt != "pdf":
        raise ConversionError(f"Unknown iWork conversion: {fmt}")
    if pdf is not None:
        Path(long_path(out)).write_bytes(pdf)
        try:
            with pymupdf.open(long_path(out)) as d:
                n = d.page_count
        except Exception as e:  # noqa: BLE001
            raise VerificationError(f"the PDF inside the file can't be opened ({e})") from e
        if n < 1:
            raise VerificationError("the PDF inside the file has no pages")
        return [f"Checked: the full PDF Apple saved in the file, {n} page{'s' if n != 1 else ''}."]
    import img2pdf

    try:
        Path(long_path(out)).write_bytes(img2pdf.convert(pic))
    except Exception:  # noqa: BLE001 - a preview img2pdf can't take as-is: re-save it first
        buf = io.BytesIO()
        Image.open(io.BytesIO(pic)).convert("RGB").save(buf, "JPEG", quality=92)
        Path(long_path(out)).write_bytes(img2pdf.convert(buf.getvalue()))
    with pymupdf.open(long_path(out)) as d:
        if d.page_count != 1:
            raise VerificationError("the PDF should have one page")
    return ["Checked: a one-page PDF of the preview Apple saved in the file.",
            "Newer Pages, Numbers and Keynote files only keep a preview of the first page; the full document "
            "opens only in Apple's apps."]
