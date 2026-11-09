"""PDF tools (PyMuPDF).

- merge: several PDFs into one (pages copied as-is; every page's text checked)
- split: one PDF per page, in a new folder
- png / jpg: one image per page, in a new folder (200 dpi)
- txt: the PDF's text (fails clearly for scanned PDFs that have no text)
- compress: pictures re-saved at a lower resolution, file structure cleaned
- pages / rotate: keep, remove or turn chosen pages
- lock / unlock: AES-256 password
- numbers / watermark: text stamped on every page

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
    notes.append(f"Checked: {n} single-page PDF{'s' if n != 1 else ''}.")


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
    notes.append(f"Checked: {n} page image{'s' if n != 1 else ''} at {DPI} dpi.")


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


# --- Everyday PDF tools -------------------------------------------------------

def _human(n: int) -> str:
    for unit, size in (("MB", 1_000_000), ("KB", 1000)):
        if n >= size:
            return f"{n / size:.1f} {unit}" if n < size * 10 else f"{n / size:.0f} {unit}"
    return f"{n} bytes"


def _words(text: str) -> list[str]:
    return text.split()


def _save(doc, out: Path, **kw) -> None:
    kw.setdefault("garbage", 3)
    kw.setdefault("deflate", True)
    doc.save(long_path(out), **kw)


LOOK_DPI = 24  # tiny renders: enough to catch a damaged picture, cheap on long PDFs


def _looks(doc, pages=None) -> list[bytes]:
    return [doc[i].get_pixmap(dpi=LOOK_DPI, alpha=False).samples for i in (pages or range(doc.page_count))]


def _check_same(out: Path, texts: list[str], what: str, password: str | None = None,
                looks: list[bytes] | None = None) -> None:
    """The output has exactly these pages, each with its original text (and,
    if given, looking the same as before)."""
    import pymupdf

    with pymupdf.open(long_path(out)) as d:
        # Note: read needs_pass only before authenticate(); reading it afterwards
        # upsets MuPDF's decryption of later streams.
        if d.needs_pass and not (password and d.authenticate(password)):
            raise VerificationError("the new PDF can't be opened")
        if d.page_count != len(texts):
            raise VerificationError(f"{d.page_count} pages written, expected {len(texts)} ({what})")
        for i, (page, text) in enumerate(zip(d, texts)):
            if _words(page.get_text()) != _words(text):
                raise VerificationError(f"page {i + 1}'s text changed ({what})")
        if looks is not None:
            for i, (a, b) in enumerate(zip(looks, _looks(d))):
                if a != b:
                    raise VerificationError(f"page {i + 1} doesn't look the same as before ({what})")


COMPRESS_LEVELS = {  # pictures above `threshold` dpi are re-saved at `target` dpi
    "Light": (220, 260, 85),
    "Balanced": (150, 180, 75),
    "Strong": (100, 120, 60),
}


def compress(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    level = opts.get("level", "Balanced")
    target, threshold, quality = COMPRESS_LEVELS.get(level, COMPRESS_LEVELS["Balanced"])
    before = Path(long_path(src)).stat().st_size
    with _open(src) as d:
        texts = _page_texts(d)
        had_images = any(page.get_images(full=False) for page in d)
        if had_images:
            d.rewrite_images(dpi_threshold=threshold, dpi_target=target, quality=quality,
                             lossy=True, lossless=True, bitonal=False, color=True, gray=True)
        _save(d, out, garbage=4, clean=True, deflate_images=True, deflate_fonts=True, use_objstms=1)
    _check_same(out, texts, "compress")
    after = Path(long_path(out)).stat().st_size
    if after >= before * 0.98:
        raise ConversionError("This PDF is already compact; it can't be made noticeably smaller"
                              + (" at this level. Try Strong." if level != "Strong" and had_images else "."))
    saved = min(99, int((1 - after / before) * 100))
    notes.append(f"{_human(before)} → {_human(after)} ({saved}% smaller).")
    notes.append(f"Pictures reduced to {target} dpi; text and pages unchanged." if had_images
                 else "Text and pages unchanged; only the file structure was tidied.")


def _pages_arg(opts: dict, count: int, key: str = "pages") -> list[int]:
    from ..toolbox import parse_pages

    try:
        return parse_pages(str(opts.get(key, "")), count)
    except ValueError as e:
        raise ConversionError(str(e)) from e


def pages(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    with _open(src) as d:
        n = d.page_count
        chosen = _pages_arg(opts, n)
        keep = chosen if opts.get("mode", "Keep") == "Keep" else [i for i in range(n) if i not in set(chosen)]
        if not keep:
            raise ConversionError("That would remove every page.")
        if keep == list(range(n)):
            raise ConversionError("That's every page, so nothing would change.")
        texts = _page_texts(d)
        looks = _looks(d, keep)
        d.select(keep)
        _save(d, out, garbage=4)
    _check_same(out, [texts[i] for i in keep], "pages", looks=looks)
    notes.append(f"Checked: {len(keep)} of {n} pages kept, in their original order.")


TURNS = {"90° right": 90, "90° left": 270, "180°": 180}


def rotate(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    import pymupdf

    turn = TURNS.get(opts.get("turn"), 90)
    with _open(src) as d:
        n = d.page_count
        which = _pages_arg(opts, n) if str(opts.get("pages", "")).strip() else list(range(n))
        texts = _page_texts(d)
        want = []
        for i, page in enumerate(d):
            r = (page.rotation + turn) % 360 if i in set(which) else page.rotation
            if i in set(which):
                page.set_rotation(r)
            want.append(r)
        _save(d, out)
    _check_same(out, texts, "rotate")
    with pymupdf.open(long_path(out)) as d:
        if [p.rotation for p in d] != want:
            raise VerificationError("a page wasn't turned")
    notes.append(f"Checked: {len(which)} of {n} pages turned {opts.get('turn', '90° right')}.")


def lock(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    import pymupdf

    password = str(opts.get("password", ""))
    if len(password) < 4:
        raise ConversionError("Use a password of at least 4 characters.")
    with _open(src) as d:
        texts = _page_texts(d)
        looks = _looks(d)
        _save(d, out, garbage=3, encryption=pymupdf.PDF_ENCRYPT_AES_256,
              owner_pw=password, user_pw=password, permissions=-1)
    with pymupdf.open(long_path(out)) as d:
        if not d.needs_pass:
            raise VerificationError("the password wasn't applied")
        if not d.authenticate("") == 0:
            raise VerificationError("the PDF opens without the password")
    _check_same(out, texts, "lock", password, looks)
    notes.append("Locked with AES-256. The password is needed to open it; keep it somewhere safe, "
                 "because it can't be recovered.")


def unlock(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    import pymupdf

    password = str(opts.get("password", ""))
    try:
        d = pymupdf.open(long_path(src))
    except Exception as e:
        raise ConversionError(f"This PDF can't be opened; it may be damaged ({e}).") from e
    with d:
        locked = d.needs_pass  # read before authenticate(); see _check_same
        if not locked and not d.is_encrypted:
            raise ConversionError("This PDF has no password.")
        if locked and not d.authenticate(password):
            raise ConversionError("That password isn't right.")
        texts = _page_texts(d)
        looks = _looks(d)
        _save(d, out, encryption=pymupdf.PDF_ENCRYPT_NONE)
    with pymupdf.open(long_path(out)) as d:
        if d.needs_pass or d.is_encrypted:
            raise VerificationError("the password is still there")
    _check_same(out, texts, "unlock", looks=looks)
    notes.append("Password removed. Anyone with the file can now open it.")


def _contains(words: list[str], expected: list[str]) -> bool:
    from collections import Counter

    have = Counter(words)
    return all(have[w] >= c for w, c in Counter(expected).items())


def _visible(page, x: float, y: float):
    """A point on the page as you see it -> the page's own coordinates."""
    import pymupdf

    return pymupdf.Point(x, y) * page.derotation_matrix


def numbers(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    import pymupdf

    try:
        start = int(str(opts.get("start", "1")).strip() or 1)
    except ValueError as e:
        raise ConversionError("'Start at' must be a whole number.") from e
    style = opts.get("style", "1")
    position = opts.get("position", "Bottom center")
    size, margin = 10, 28
    with _open(src) as d:
        n = d.page_count
        texts = _page_texts(d)
        labels = []
        for i, page in enumerate(d):
            num = start + i
            label = {"Page 1": f"Page {num}", "Page 1 of N": f"Page {num} of {start + n - 1}"}.get(style, str(num))
            labels.append(label)
            w, h = page.rect.width, page.rect.height  # as displayed
            tw = pymupdf.get_text_length(label, fontname="helv", fontsize=size)
            x = {"Bottom right": w - margin - tw, "Top right": w - margin - tw}.get(position, (w - tw) / 2)
            y = margin + size if position == "Top right" else h - margin
            page.insert_text(_visible(page, x, y), label, fontname="helv", fontsize=size,
                             color=(0.25, 0.25, 0.25), rotate=page.rotation)
        _save(d, out)
    import pymupdf as _p

    with _p.open(long_path(out)) as d:
        if d.page_count != n:
            raise VerificationError("the page count changed")
        for i, page in enumerate(d):
            words = _words(page.get_text())
            if not _contains(words, _words(texts[i]) + _words(labels[i])):
                raise VerificationError(f"page {i + 1} is missing its number or original text")
    notes.append(f"Checked: numbered {n} page{'s' if n != 1 else ''} ({labels[0]}" + (f" to {labels[-1]}" if n > 1 else "") + ").")


WM_SIGN = 1  # PyMuPDF angles turn clockwise on screen (y points down)


def watermark(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    import math

    import pymupdf

    text = str(opts.get("text", "")).strip()
    if not text:
        raise ConversionError("Type the watermark text.")
    opacity = max(5, min(60, int(opts.get("opacity", 18)))) / 100
    diagonal = opts.get("angle", "Diagonal") == "Diagonal"
    with _open(src) as d:
        n = d.page_count
        texts = _page_texts(d)
        font = pymupdf.Font("helv")
        unit = font.text_length(text, fontsize=1) or 1
        for page in d:
            w, h = page.rect.width, page.rect.height  # as displayed
            span = math.hypot(w, h) * 0.75 if diagonal else w * 0.8
            size = max(12.0, min(span / unit, h * 0.4))
            # Work in the page's own (unrotated) space; its centre is the same point.
            box = page.rect * page.derotation_matrix
            centre = pymupdf.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
            angle = math.degrees(math.atan2(h, w)) if diagonal else 0  # rising left to right, as seen
            writer = pymupdf.TextWriter(page.rect)
            writer.append(pymupdf.Point(centre.x - unit * size / 2, centre.y + size * 0.35), text,
                          font=font, fontsize=size)
            writer.write_text(page, color=(0.45, 0.45, 0.45), opacity=opacity, overlay=True,
                              morph=(centre, pymupdf.Matrix(WM_SIGN * (angle + page.rotation))))
        _save(d, out)
    with pymupdf.open(long_path(out)) as d:
        if d.page_count != n:
            raise VerificationError("the page count changed")
        for i, page in enumerate(d):
            if not _contains(_words(page.get_text()), _words(texts[i]) + _words(text)):
                raise VerificationError(f"page {i + 1} is missing the watermark or original text")
    notes.append(f"Checked: watermark on all {n} pages at {int(opacity * 100)}% opacity; the original text is "
                 "still selectable.")


TOOLS = {
    "compress": compress,
    "pages": pages,
    "rotate": rotate,
    "lock": lock,
    "unlock": unlock,
    "numbers": numbers,
    "watermark": watermark,
}


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
    elif fmt in TOOLS:
        TOOLS[fmt](sources[0], out, opts, notes)
    else:
        raise ConversionError(f"Unknown PDF conversion: {fmt}")
    return notes
