"""Mixed selections: pictures and PDFs together into one PDF, in the order selected.

PDF pages are copied as they are. Each picture becomes one A4 page (portrait or
landscape to match it), fitted inside a small margin; JPEG and PNG pictures are
placed without re-encoding, other formats (HEIC, WEBP...) are saved as a
high-quality JPEG first.
"""

from __future__ import annotations

import io
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

A4 = (595, 842)
MARGIN = 24


def _picture_bytes(path: Path) -> tuple[bytes, int, int]:
    from PIL import Image

    from .image import Notes, _ensure_plugins, load

    raw = Path(long_path(path)).read_bytes()
    _ensure_plugins()
    frame = load(path, Notes(), multi=False).frames[0]  # camera rotation already applied
    w, h = frame.size
    if path.suffix.lower() in (".jpg", ".jpeg", ".png") and frame.size == Image.open(io.BytesIO(raw)).size:
        return raw, w, h
    im = frame
    if im.mode in ("RGBA", "LA", "P"):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.getchannel("A"))
        im = bg
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=92, subsampling=0)
    return buf.getvalue(), w, h


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    import pymupdf

    if fmt != "pdf":
        raise ConversionError(f"Unknown mixed conversion: {fmt}")
    result = pymupdf.open()
    expected = 0
    pics = pdfs = 0
    for src in sources:
        if src.suffix.lower() == ".pdf":
            try:
                d = pymupdf.open(long_path(src))
            except Exception as e:
                raise ConversionError(f"{src.name} can't be opened; it may be damaged.") from e
            with d:
                if d.needs_pass:
                    raise ConversionError(f"{src.name} is password-protected. Unlock it first.")
                result.insert_pdf(d)
                expected += d.page_count
                pdfs += 1
        else:
            data, w, h = _picture_bytes(src)
            pw, ph = A4 if h >= w else (A4[1], A4[0])
            page = result.new_page(width=pw, height=ph)
            s = min((pw - 2 * MARGIN) / w, (ph - 2 * MARGIN) / h)
            iw, ih = w * s, h * s
            x, y = (pw - iw) / 2, (ph - ih) / 2
            page.insert_image(pymupdf.Rect(x, y, x + iw, y + ih), stream=data)
            expected += 1
            pics += 1
    result.save(long_path(out), garbage=3, deflate=True)
    result.close()
    with pymupdf.open(long_path(out)) as d:
        if d.page_count != expected:
            raise VerificationError(f"{d.page_count} pages written, expected {expected}")
    parts = [f"{pics} picture{'s' if pics != 1 else ''}" if pics else "", f"{pdfs} PDF{'s' if pdfs != 1 else ''}" if pdfs else ""]
    return [f"Checked: {expected} pages from {' and '.join(p for p in parts if p)}, in the order you selected.",
            "Pictures are on A4 pages; PDF pages are copied as they are."]
