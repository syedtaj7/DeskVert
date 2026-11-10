"""Vector graphics.

- pdf:  SVG / SVGZ -> a vector PDF (stays sharp at any zoom); Illustrator (.ai)
        files saved with PDF content (Illustrator's default) -> PDF.
- png:  Illustrator (.ai) -> PNG.
- svgz / svg: SVG <-> SVGZ (the same drawing, gzip-compressed or not).

Drawn by MuPDF (already part of Tapshift). The result is opened again and checked.
"""

from __future__ import annotations

import gzip
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path


def _svg_bytes(src: Path) -> bytes:
    data = Path(long_path(src)).read_bytes()
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except OSError as e:
            raise ConversionError("This SVGZ file is damaged.") from e
    if b"<svg" not in data[:4096] and b"<svg" not in data:
        raise ConversionError("This isn't an SVG drawing.")
    return data


def _ai_doc(src: Path):
    import pymupdf

    data = Path(long_path(src)).read_bytes()
    if not data.startswith(b"%PDF"):
        raise ConversionError("This Illustrator file was saved without PDF content (an old or EPS-style .ai), "
                              "which needs Illustrator or Ghostscript.")
    return pymupdf.open("pdf", data)


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    import pymupdf

    src = sources[0]
    ext = src.suffix.lower()
    if fmt in ("svgz", "svg"):
        data = _svg_bytes(src)
        payload = gzip.compress(data, 9) if fmt == "svgz" else data
        Path(long_path(out)).write_bytes(payload)
        back = Path(long_path(out)).read_bytes()
        if (gzip.decompress(back) if fmt == "svgz" else back) != data:
            raise VerificationError("the drawing changed")
        return [f"Checked: the same drawing, {len(data):,} → {len(payload):,} bytes."]
    if fmt == "pdf":
        if ext == ".ai":
            doc = _ai_doc(src)
            pages = doc.page_count
            doc.save(long_path(out), garbage=3, deflate=True)
            doc.close()
        else:
            with pymupdf.open("svg", _svg_bytes(src)) as doc:
                pdf = pymupdf.open("pdf", doc.convert_to_pdf())
                pages = pdf.page_count
                pdf.set_metadata({"title": src.stem, "creator": "Tapshift"})
                pdf.save(long_path(out), garbage=3, deflate=True)
                pdf.close()
        with pymupdf.open(long_path(out)) as d:
            if d.page_count != pages:
                raise VerificationError("the PDF is broken")
        return [f"Checked: a vector PDF ({pages} page{'s' if pages != 1 else ''}), sharp at any zoom."]
    if fmt == "png":
        with _ai_doc(src) as doc:
            page = doc[0]
            zoom = 2400 / max(page.rect.width, page.rect.height)
            page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True).save(long_path(out))
        from PIL import Image

        with Image.open(long_path(out)) as im:
            if max(im.size) < 2000:
                raise VerificationError("the picture is broken")
            size = im.size
        return [f"Checked: {size[0]}×{size[1]} px, transparent background kept."]
    raise ConversionError(f"Unknown vector conversion: {fmt}")
