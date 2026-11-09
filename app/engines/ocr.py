"""Text recognition (OCR) with Windows' built-in engine (Windows.Media.Ocr).

No extra download and light on the CPU: it's the same engine Windows uses
in the Photos app and the Snipping Tool. It reads the languages installed in
Windows (Settings > Time & language > Language).

- txt: the text of a picture, or of a scanned PDF (pages that already have
       text keep it as-is)
- pdf: a searchable PDF. Pictures become a PDF page; for PDFs the pages stay
       exactly as they are and an invisible text layer is added to scanned
       pages, so text can be found, selected and copied.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path
from .officeutil import text_coverage

RENDER_DPI = 300
MIN_SIDE = 1200  # small pictures are enlarged first; tiny text reads better


@dataclass
class Word:
    text: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class Page:
    lines: list[str]
    words: list[Word]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _engine():
    try:
        from winrt.windows.media.ocr import OcrEngine
    except Exception as e:  # noqa: BLE001
        raise ConversionError("Text recognition isn't available on this version of Windows.") from e
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise ConversionError("Windows has no text-recognition language installed. Add one in Settings > "
                              "Time & language > Language (the language's 'Optical character recognition' "
                              "feature).")
    return engine, OcrEngine.max_image_dimension


def _recognize(engine, max_dim: int, img) -> Page:
    """img: a Pillow image. Returns words with positions in img's pixels."""
    from PIL import Image
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    gray = img.convert("L")
    scale = 1.0
    if max(gray.size) > max_dim:
        scale = max_dim / max(gray.size)
    elif max(gray.size) < MIN_SIDE:
        scale = min(3.0, MIN_SIDE / max(gray.size))
    if scale != 1.0:
        gray = gray.resize((max(1, round(gray.width * scale)), max(1, round(gray.height * scale))),
                           Image.Resampling.LANCZOS)
    writer = DataWriter()
    writer.write_bytes(gray.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.GRAY8,
                                                    gray.width, gray.height)
    result = asyncio.run(_run(engine, bitmap))
    lines, words = [], []
    for line in result.lines:
        lines.append(line.text)
        for w in line.words:
            r = w.bounding_rect
            words.append(Word(w.text, r.x / scale, r.y / scale, r.width / scale, r.height / scale))
    return Page(lines, words)


def _score(page: Page) -> int:
    """Real-looking words: an upright page scores high, a sideways one near 0."""
    import re

    return sum(1 for w in page.words if re.fullmatch(r"[^\W\d_]{3,}[.,:;!?)]*", w.text))


def _turn_back(w: Word, turn: int, width: int, height: int) -> Word:
    """A box found on the picture turned `turn` degrees (counter-clockwise)
    -> the same box on the original picture (width x height)."""
    corners = [(w.x, w.y), (w.x + w.w, w.y + w.h)]
    if turn == 90:
        pts = [(width - y, x) for x, y in corners]
    elif turn == 270:
        pts = [(y, height - x) for x, y in corners]
    else:  # 180
        pts = [(width - x, height - y) for x, y in corners]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return Word(w.text, min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _read(engine, max_dim: int, img) -> tuple[Page, int]:
    """Read the picture; if it looks sideways or upside down, try it turned.
    Returns (page with boxes on the original picture, turn used)."""
    best, best_turn = _recognize(engine, max_dim, img), 0
    if _score(best) >= 8:
        return best, 0
    for turn in (90, 270, 180):
        page = _recognize(engine, max_dim, img.rotate(turn, expand=True))
        if _score(page) > max(_score(best) * 2, 4):
            best, best_turn = page, turn
    if best_turn:
        best.words = [_turn_back(w, best_turn, img.width, img.height) for w in best.words]
    return best, best_turn


async def _run(engine, bitmap):
    return await engine.recognize_async(bitmap)


def _load_picture(src: Path):
    from PIL import Image

    from .image import Notes, _ensure_plugins, load

    _ensure_plugins()
    frame = load(src, Notes(), multi=False).frames[0]
    if frame.mode in ("RGBA", "LA", "PA") or "transparency" in frame.info:
        rgba = frame.convert("RGBA")
        white = Image.new("RGB", rgba.size, "white")
        white.paste(rgba, mask=rgba.getchannel("A"))
        return white
    return frame.convert("RGB") if frame.mode not in ("RGB", "L") else frame


def _no_text(where: str) -> ConversionError:
    return ConversionError(f"No text was found in {where}. Text recognition needs clear, printed text; "
                           "handwriting and very small or blurry text may not be read.")


def _render(page):
    from PIL import Image

    pix = page.get_pixmap(dpi=RENDER_DPI, colorspace="gray", alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def _open_pdf(src: Path):
    from .pdf import _open

    return _open(src)


def _has_text(page) -> bool:
    return len(page.get_text().split()) >= 3


# ---------------------------------------------------------------- invisible text layer

def _add_text_layer(page, words: list[Word], px_per_pt: float) -> None:
    import pymupdf

    font = pymupdf.Font("helv")
    if page.rotation == 0:
        writer = pymupdf.TextWriter(page.rect)
    else:
        writer = None
    for w in words:
        x, y, width, height = (v / px_per_pt for v in (w.x, w.y, w.w, w.h))  # displayed page points
        unit = font.text_length(w.text, fontsize=1) or 1
        size = max(1.0, min(height * 0.9, width / unit))
        baseline = pymupdf.Point(x, y + height * 0.8)
        if writer is not None:
            writer.append(baseline, w.text, font=font, fontsize=size)
        else:
            page.insert_text(baseline * page.derotation_matrix, w.text, fontname="helv", fontsize=size,
                             rotate=page.rotation, render_mode=3)
    if writer is not None:
        writer.write_text(page, render_mode=3)  # 3 = invisible: selectable, not drawn


# ---------------------------------------------------------------- conversions

def to_text(src: Path, out: Path, notes: list[str]) -> None:
    engine, max_dim = _engine()
    if src.suffix.lower() == ".pdf":
        parts, read, kept = [], 0, 0
        with _open_pdf(src) as d:
            n = d.page_count
            for page in d:
                if _has_text(page):
                    parts.append(page.get_text().rstrip())
                    kept += 1
                else:
                    parts.append(_read(engine, max_dim, _render(page))[0].text)
                    read += 1
        if not read:
            raise ConversionError("This PDF already has text in it; use PDF → TXT instead.")
        body = "\f".join(parts)  # form feed between pages
        if not body.strip():
            raise _no_text("this PDF")
        notes.append(f"Read {read} scanned page{'s' if read != 1 else ''}"
                     + (f"; {kept} page{'s' if kept != 1 else ''} already had text." if kept else f" of {n}."))
    else:
        page, _turn = _read(engine, max_dim, _load_picture(src))
        body = page.text
        if not body.strip():
            raise _no_text("this picture")
        notes.append(f"Read {len(page.words)} words.")
    Path(long_path(out)).write_text(body + "\n", encoding="utf-8")
    if Path(long_path(out)).read_text(encoding="utf-8").split() != body.split():
        raise VerificationError("the text file doesn't match what was read")
    notes.append(f"Recognized with Windows ({engine.recognizer_language.display_name}). Check names and "
                 "numbers; recognition isn't always perfect.")


def to_pdf(src: Path, out: Path, notes: list[str]) -> None:
    import pymupdf

    engine, max_dim = _engine()
    expected = []
    if src.suffix.lower() == ".pdf":
        with _open_pdf(src) as d:
            looks = [p.get_pixmap(dpi=24, alpha=False).samples for p in d]
            read = 0
            for page in d:
                if _has_text(page):
                    continue
                result, _turn = _read(engine, max_dim, _render(page))
                if result.words:
                    _add_text_layer(page, result.words, RENDER_DPI / 72)
                    expected.append(result.text)
                read += 1
            if not read:
                raise ConversionError("This PDF already has selectable text, so it's already searchable.")
            if not expected:
                raise _no_text("this PDF")
            d.save(long_path(out), garbage=3, deflate=True)
            n = d.page_count
        with pymupdf.open(long_path(out)) as d:
            if d.page_count != n:
                raise VerificationError("the page count changed")
            if [p.get_pixmap(dpi=24, alpha=False).samples for p in d] != looks:
                raise VerificationError("a page doesn't look the same as before")
            text = "\n".join(p.get_text() for p in d)
        notes.append(f"Added searchable text to {len(expected)} scanned page{'s' if len(expected) != 1 else ''}; "
                     "the pages look exactly as before.")
    else:
        img = _load_picture(src)
        result, _turn = _read(engine, max_dim, img)
        if not result.words:
            raise _no_text("this picture")
        dpi = img.info.get("dpi", (0, 0))[0] or 0
        dpi = dpi if 72 <= dpi <= 1200 else RENDER_DPI
        d = pymupdf.open()
        page = d.new_page(width=img.width * 72 / dpi, height=img.height * 72 / dpi)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90, subsampling=0, optimize=True)
        page.insert_image(page.rect, stream=buf.getvalue())
        _add_text_layer(page, result.words, dpi / 72)
        d.save(long_path(out), garbage=3, deflate=True)
        d.close()
        expected.append(result.text)
        with pymupdf.open(long_path(out)) as d:
            text = d[0].get_text()
        notes.append(f"A one-page PDF of the picture with {len(result.words)} searchable words.")
    cov = text_coverage("\n".join(expected), text)
    if cov is not None and cov < 0.9:
        raise VerificationError(f"only {cov:.0%} of the recognized words can be found in the PDF")
    notes.append(f"Recognized with Windows ({engine.recognizer_language.display_name}). Check names and "
                 "numbers; recognition isn't always perfect.")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    notes: list[str] = []
    if fmt == "txt":
        to_text(sources[0], out, notes)
    elif fmt == "pdf":
        to_pdf(sources[0], out, notes)
    else:
        raise ConversionError(f"Unknown text recognition: {fmt}")
    return notes
