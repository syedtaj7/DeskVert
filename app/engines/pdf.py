"""PDF tools (PyMuPDF).

- merge: several PDFs into one (pages copied as-is; every page's text checked)
- split: one PDF per page, in a new folder
- png / jpg: one image per page, in a new folder (200 dpi)
- txt: the PDF's text (fails clearly for scanned PDFs that have no text)
- compress: pictures re-saved at a lower resolution, file structure cleaned
- pages / rotate: keep, remove or turn chosen pages
- lock / unlock: AES-256 password
- numbers / watermark: text stamped on every page
- tables: every table found, one Excel sheet each
- blank: blank pages removed (no text, and nothing visible when drawn)

"""

from __future__ import annotations

import os
import re
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


# Gentlest first: (picture dpi, JPEG quality). Used to find the best quality that fits a size limit.
SIZE_LADDER = [(220, 85), (180, 80), (150, 75), (130, 70), (110, 65), (96, 60), (80, 55), (72, 50), (60, 45)]
SIZE_LIMITS = {"Under 200 KB": 200, "Under 500 KB": 500, "Under 1 MB": 1000, "Under 2 MB": 2000}


def _shrink_attempt(src: Path, dest: Path, dpi: int | None, quality: int, gray: bool = False) -> int:
    with _open(src) as d:
        if dpi is not None and any(page.get_images(full=False) for page in d):
            d.rewrite_images(dpi_threshold=int(dpi * 1.2), dpi_target=dpi, quality=quality, lossy=True,
                             lossless=True, bitonal=False, color=True, gray=True, set_to_gray=gray)
        _save(d, dest, garbage=4, clean=True, deflate_images=True, deflate_fonts=True, use_objstms=1)
    return Path(long_path(dest)).stat().st_size


def _picture_scale(src: Path, out: Path) -> float:
    """How big the first page's picture is now, compared with before (1.0 = same size)."""
    try:
        with _open(src) as a, _open(out) as b:
            ia, ib = a[0].get_images(full=True), b[0].get_images(full=True)
            if ia and ib:
                return b.extract_image(ib[0][0])["width"] / max(1, a.extract_image(ia[0][0])["width"])
    except Exception:
        pass
    return 1.0


def compress_to(src: Path, out: Path, limit_kb: int, notes: list[str]) -> None:
    """The best quality that fits under the limit.

    Light on slow laptops: the search runs on a sample of up to 4 pages (sizes scaled up
    to the whole document), then the whole PDF is compressed once with the chosen
    setting and its real size checked; if it's still over, the next setting is tried."""
    limit = limit_kb * 1000
    before = Path(long_path(src)).stat().st_size
    if before <= limit:
        raise ConversionError(f"This PDF is already under {_human(limit)} ({_human(before)}).")
    with _open(src) as d:
        texts = _page_texts(d)
        n = d.page_count
    trial = out.parent / "trial.pdf"
    if _shrink_attempt(src, trial, None, 0) <= limit:  # tidying alone is enough: pictures stay as they are
        os.replace(long_path(trial), long_path(out))
        label = "tidied the file structure; pictures untouched"
    else:
        probe, scale = src, 1.0
        if n > 4:
            pick = sorted({round(i * (n - 1) / 3) for i in range(4)})
            probe = out.parent / "sample.pdf"
            with _open(src) as d:
                d.select(pick)
                d.save(long_path(probe), garbage=3, deflate=True)
            scale = n / len(pick)
        budget = limit * (0.92 if probe is not src else 1.0)  # a little headroom when estimating from a sample

        def fits(dpi: int, q: int) -> bool:
            return _shrink_attempt(probe, trial, dpi, q) * scale <= budget

        dpis, qs = [dp for dp, _q in SIZE_LADDER], (90, 82, 74, 66, 58)
        # 1) the gentlest resolution where the lowest acceptable quality fits (size falls as dpi falls)
        lo, hi, di = 0, len(dpis) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if fits(dpis[mid], qs[-1]):
                di, hi = mid, mid - 1
            else:
                lo = mid + 1
        plan: list[tuple[int, int, bool]] = []
        if di is not None:
            # 2) the highest quality that fits at that resolution (size falls as quality falls)
            lo, hi, qi = 0, len(qs) - 2, len(qs) - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                if fits(dpis[di], qs[mid]):
                    qi, hi = mid, mid - 1
                else:
                    lo = mid + 1
            plan = [(dpis[di], q, False) for q in qs[qi:]] + [(dp, qs[-1], False) for dp in dpis[di + 1:]]
        plan += [(dpis[-1], 50, False), (dpis[-1], 45, True)]
        size = None
        for dpi, q, gray in plan:  # the real thing; step down only if the sample was optimistic
            size = _shrink_attempt(src, trial, dpi, q, gray)
            if size <= limit:
                os.replace(long_path(trial), long_path(out))
                k_scale = _picture_scale(src, out)
                size_word = ("full size" if k_scale > 0.97 else "half size" if k_scale > 0.4
                             else f"{max(1, round(k_scale * 100))}% size")
                label = f"pictures at {size_word}" + (" in black and white" if gray else f", quality {q}%")
                break
        else:
            raise ConversionError(
                f"The smallest this PDF gets is about {_human(size)} (pictures at {SIZE_LADDER[-1][0]} dpi, black "
                f"and white). The rest is text and fonts, which can't shrink without losing them. Try a bigger "
                f"limit, or remove pages first.")
    _check_same(out, texts, "compress")
    after = Path(long_path(out)).stat().st_size
    if after > limit:
        raise VerificationError(f"the file is {_human(after)}, over the {_human(limit)} limit")
    saved = min(99, int((1 - after / before) * 100))
    notes.append(f"{_human(before)} → {_human(after)} ({saved}% smaller), under the {_human(limit)} limit.")
    notes.append(f"Best quality that fits: {label}. Text and pages unchanged.")


def compress(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    level = opts.get("level", "Balanced")
    if opts.get("limit_kb"):  # a saved preset with its own size, e.g. "College PDF under 300 KB"
        kb = int(opts["limit_kb"])
        if not 20 <= kb <= 50_000:
            raise ConversionError("The size limit must be between 20 KB and 50 MB.")
        compress_to(src, out, kb, notes)
        return
    if level in SIZE_LIMITS:
        compress_to(src, out, SIZE_LIMITS[level], notes)
        return
    level = level.split(" ")[0]  # "Balanced (no limit)" -> "Balanced"
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



# --- More page tools ------------------------------------------------------------

def _ordered_pages(text: str, n: int) -> list[int]:
    """'3, 1, 2, 7-5' -> [2, 0, 1, 6, 5, 4] (zero-based, in the order typed; ranges may run backwards)."""
    out: list[int] = []
    for part in (text or "").replace(" ", "").lower().split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d+|end)(?:-(\d+|end))?", part)
        if not m:
            raise ConversionError(f"“{part}” isn't a page or range. Use numbers like 3, 1, 2 or 10-1.")
        a = n if m.group(1) == "end" else int(m.group(1))
        b = (n if m.group(2) == "end" else int(m.group(2))) if m.group(2) else a
        for p in (a, b):
            if not 1 <= p <= n:
                raise ConversionError(f"Page {p} doesn't exist: the PDF has {n} page{'s' if n != 1 else ''}.")
        step = 1 if b >= a else -1
        for p in range(a, b + step, step):
            if p - 1 in out:
                raise ConversionError(f"Page {p} is listed twice.")
            out.append(p - 1)
    if not out:
        raise ConversionError("Type the new order, for example 3, 1, 2.")
    return out


def _write_parts(src: Path, out_dir: Path, parts: list[list[int]], notes: list[str], what: str) -> None:
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    with _open(src) as d:
        texts = _page_texts(d)
        digits = max(2, len(str(len(parts))))
        for k, pages in enumerate(parts, 1):
            part = pymupdf.open()
            for i in pages:
                part.insert_pdf(d, from_page=i, to_page=i)
            span = f"page {pages[0] + 1}" if len(pages) == 1 else f"pages {pages[0] + 1}-{pages[-1] + 1}"
            part.save(long_path(out_dir / f"{src.stem} - part {str(k).zfill(digits)} ({span}).pdf"),
                      garbage=3, deflate=True)
            part.close()
    files = sorted(out_dir.glob("*.pdf"))
    if len(files) != len(parts):
        raise VerificationError(f"{len(files)} files for {len(parts)} parts")
    for f, pages in zip(files, parts):
        _check_same(f, [texts[i] for i in pages], what)
    notes.append(f"Checked: {len(parts)} PDFs ({', '.join(str(len(p)) for p in parts[:6])}"
                 f"{'…' if len(parts) > 6 else ''} pages), every page copied exactly.")


def split_half(src: Path, out_dir: Path, opts: dict, notes: list[str]) -> None:
    with _open(src) as d:
        n = d.page_count
    if n < 2:
        raise ConversionError("This PDF has only one page, so it can't be split.")
    mid = (n + 1) // 2
    _write_parts(src, out_dir, [list(range(0, mid)), list(range(mid, n))], notes, "split in half")


def split_every(src: Path, out_dir: Path, opts: dict, notes: list[str]) -> None:
    try:
        size = int(str(opts.get("n", "")).strip())
    except ValueError as e:
        raise ConversionError("Type how many pages each part should have, like 2.") from e
    with _open(src) as d:
        n = d.page_count
    if size < 1:
        raise ConversionError("Each part needs at least 1 page.")
    if size >= n:
        raise ConversionError(f"The PDF has {n} pages, so parts of {size} would just copy it.")
    _write_parts(src, out_dir, [list(range(i, min(n, i + size))) for i in range(0, n, size)], notes,
                 f"split every {size}")


def split_ranges(src: Path, out_dir: Path, opts: dict, notes: list[str]) -> None:
    from ..toolbox import parse_pages

    with _open(src) as d:
        n = d.page_count
    parts = []
    for chunk in str(opts.get("ranges", "")).replace(";", ",").split(","):
        if chunk.strip():
            try:
                parts.append(parse_pages(chunk, n))
            except ValueError as e:
                raise ConversionError(str(e)) from e
    if not parts:
        raise ConversionError("Type the parts, for example 1-3, 4-10, 11-end.")
    _write_parts(src, out_dir, parts, notes, "split by ranges")


def reorder(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    with _open(src) as d:
        n = d.page_count
        texts = _page_texts(d)
        if str(opts.get("order", "")).strip().lower() == "reverse":
            order = list(range(n - 1, -1, -1))
        else:
            order = _ordered_pages(str(opts.get("order", "")), n)
            order += [i for i in range(n) if i not in order]  # pages you didn't list keep their place at the end
        if order == list(range(n)):
            raise ConversionError("That's the same order as now, so nothing would change.")
        d.select(order)
        _save(d, out, garbage=4)
    _check_same(out, [texts[i] for i in order], "reorder")
    notes.append(f"Checked: all {n} pages, in the new order." if n > 1 else "Checked.")


def reverse(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    with _open(src) as d:
        if d.page_count < 2:
            raise ConversionError("This PDF has only one page.")
    reorder(src, out, {"order": "reverse"}, notes)


def pictures(src: Path, out_dir: Path, opts: dict, notes: list[str]) -> None:
    """Save the pictures inside a PDF exactly as stored (no re-encoding)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    seen: set[int] = set()
    saved = []
    with _open(src) as d:
        smasks = {img[1] for page in d for img in page.get_images(full=True) if img[1]}
        for pno, page in enumerate(d, 1):
            for k, img in enumerate(page.get_images(full=True), 1):
                xref = img[0]
                if xref in seen or xref in smasks:
                    continue
                seen.add(xref)
                info = d.extract_image(xref)
                if not info or info.get("width", 0) < 32 or info.get("height", 0) < 32:
                    continue  # icons and specks
                ext = {"jpx": "jp2"}.get(info["ext"], info["ext"])
                f = out_dir / f"Page {pno:02d} - picture {k}.{ext}"
                Path(long_path(f)).write_bytes(info["image"])
                saved.append((f, len(info["image"])))
    if not saved:
        raise ConversionError("There are no pictures in this PDF to save.")
    for f, size in saved:
        if Path(long_path(f)).stat().st_size != size:
            raise VerificationError(f"{f.name} wasn't saved completely")
    notes.append(f"Saved {len(saved)} picture{'s' if len(saved) != 1 else ''} exactly as stored in the PDF.")


def grayscale(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    with _open(src) as d:
        texts = _page_texts(d)
        d.recolor(1)
        _save(d, out, garbage=4, deflate_images=True)
    _check_same(out, texts, "grayscale")
    notes.append("Checked: every page in shades of gray; text unchanged. Good for printing and smaller uploads.")


def flatten(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    import pymupdf

    with _open(src) as d:
        annots = sum(1 for page in d for _ in page.annots())
        fields = sum(1 for page in d for _ in page.widgets())
        if not annots and not fields:
            raise ConversionError("This PDF has no form fields or comments to flatten.")
        n = d.page_count
        d.bake(annots=True, widgets=True)
        _save(d, out, garbage=3)
    with pymupdf.open(long_path(out)) as d:
        left = sum(1 for page in d for _ in page.widgets())
        if d.page_count != n or left:
            raise VerificationError("the form fields are still editable")
    what = " and ".join(x for x in (f"{fields} form field{'s' if fields != 1 else ''}" if fields else "",
                                    f"{annots} comment{'s' if annots != 1 else ''}" if annots else "") if x)
    notes.append(f"Flattened {what} into the pages: they look the same but can't be edited.")


def clean_info(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    import pymupdf

    with _open(src) as d:
        texts = _page_texts(d)
        found = [k for k, v in (d.metadata or {}).items() if v and k not in ("format", "encryption")]
        d.scrub(attached_files=False, embedded_files=False, hidden_text=False, redactions=False, remove_links=False,
                reset_fields=False, reset_responses=False, javascript=True, metadata=True, thumbnails=True,
                xml_metadata=True, clean_pages=True)
        d.set_metadata({})
        _save(d, out, garbage=4)
    _check_same(out, texts, "clean")
    with pymupdf.open(long_path(out)) as d:
        left = [k for k, v in (d.metadata or {}).items() if v and k not in ("format", "encryption")]
        if left:
            raise VerificationError(f"some details are still there ({', '.join(left)})")
    notes.append("Removed hidden details: " + (", ".join(found) if found else "none were set") +
                 "; also scripts and thumbnails. Pages unchanged.")


# pages per sheet -> (columns, rows, landscape sheet)
NUP_GRID = {2: (2, 1, True), 4: (2, 2, False), 6: (2, 3, False), 9: (3, 3, False)}


def n_up(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    """2, 4, 6 or 9 pages on each A4 sheet, in reading order. The pages stay vector,
    so text stays sharp and searchable."""
    import pymupdf
    from collections import Counter

    try:
        per = int(str(opts.get("per", "2")).split()[0])
    except ValueError:
        per = 2
    if per not in NUP_GRID:
        raise ConversionError("Choose 2, 4, 6 or 9 pages per sheet.")
    cols, rows, landscape = NUP_GRID[per]
    with _open(src) as d:
        n = d.page_count
        words = Counter(w for t in _page_texts(d) for w in _words(t))
        # Form fields and comments aren't part of a page's drawing; bake them in (in memory only,
        # the original file isn't saved) so their values show on the sheets too.
        d.bake(annots=True, widgets=True)
        result = pymupdf.open()
        W, H = (842, 595) if landscape else (595, 842)
        m, g = 18, 8  # margin, gap between pages
        cw, ch = (W - 2 * m - (cols - 1) * g) / cols, (H - 2 * m - (rows - 1) * g) / rows
        for i in range(0, n, per):
            sheet = result.new_page(width=W, height=H)
            for k, pno in enumerate(range(i, min(n, i + per))):
                r, c = divmod(k, cols)
                x, y = m + c * (cw + g), m + r * (ch + g)
                sheet.show_pdf_page(pymupdf.Rect(x, y, x + cw, y + ch), d, pno)
        result.save(long_path(out), garbage=3, deflate=True)
        result.close()
    sheets = (n + per - 1) // per
    with pymupdf.open(long_path(out)) as d:
        if d.page_count != sheets:
            raise VerificationError("wrong number of sheets")
        got = Counter(w for p in d for w in _words(p.get_text()))
        if any(got[w] < c for w, c in words.items()):
            raise VerificationError("some text is missing")
    notes.append(f"Checked: {n} pages on {sheets} A4 sheet{'s' if sheets != 1 else ''}, {per} on each.")


def two_up(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    n_up(src, out, {**opts, "per": opts.get("per", "2")}, notes)


TOOLS.update({
    "splithalf": split_half,
    "splitevery": split_every,
    "splitranges": split_ranges,
    "reorder": reorder,
    "reverse": reverse,
    "pictures": pictures,
    "gray": grayscale,
    "flatten": flatten,
    "clean": clean_info,
    "nup": n_up,
})


LONG_IMAGE_MAX_PAGES = 60


def to_tiff(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    """Every page in one multi-page TIFF (200 dpi, lossless LZW)."""
    from PIL import Image

    with _open(src) as d:
        frames = [Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
                  for pm in (page.get_pixmap(dpi=200, alpha=False) for page in d)]
    frames[0].save(long_path(out), "TIFF", compression="tiff_lzw", save_all=True, append_images=frames[1:],
                   dpi=(200, 200))
    with Image.open(long_path(out)) as im:
        if getattr(im, "n_frames", 1) != len(frames):
            raise VerificationError("pages are missing from the TIFF")
    notes.append(f"Checked: {len(frames)} page{'s' if len(frames) != 1 else ''} at 200 dpi in one TIFF.")


def long_image(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    """All pages one under the other in a single picture (good for sharing on a phone)."""
    from PIL import Image

    with _open(src) as d:
        n = d.page_count
        if n > LONG_IMAGE_MAX_PAGES:
            raise ConversionError(f"This PDF has {n} pages; one long image works for up to {LONG_IMAGE_MAX_PAGES}. "
                                  "Pick some pages first (Pages \u2192 Keep or remove).")
        width = 1080
        parts = []
        for page in d:
            zoom = width / page.rect.width
            pm = page.get_pixmap(matrix=pymupdf_matrix(zoom), alpha=False)
            parts.append(Image.frombytes("RGB", (pm.width, pm.height), pm.samples))
    gap = 12
    height = sum(im.height for im in parts) + gap * (len(parts) - 1)
    if height > 65000:
        raise ConversionError("Together these pages are too tall for one picture. Pick fewer pages first.")
    sheet = Image.new("RGB", (max(im.width for im in parts), height), (230, 230, 230))
    y = 0
    for im in parts:
        sheet.paste(im, (0, y))
        y += im.height + gap
    sheet.save(long_path(out), "JPEG", quality=90, optimize=True)
    with Image.open(long_path(out)) as im:
        if im.size != sheet.size:
            raise VerificationError("the picture is broken")
    notes.append(f"Checked: {n} page{'s' if n != 1 else ''} in one picture, {sheet.width}\u00d7{sheet.height} px.")


def pymupdf_matrix(zoom: float):
    import pymupdf

    return pymupdf.Matrix(zoom, zoom)


BULLETS = ("\u2022", "\u25e6", "\u25aa", "\u25cf", "\u2013", "-", "*", "\u00b7")


def markdown_of(d) -> str:
    """The PDF's text as Markdown: bigger text becomes headings, bold stays bold, bullets become lists.
    Light on purpose: no layout models, just the fonts and positions MuPDF reports."""
    from collections import Counter

    sizes: Counter = Counter()
    pages = []
    for page in d:
        blocks = page.get_text("dict", flags=0)["blocks"]
        pages.append(blocks)
        for b in blocks:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    if s["text"].strip():
                        sizes[round(s["size"], 1)] += len(s["text"])
    body = sizes.most_common(1)[0][0] if sizes else 11.0
    out: list[str] = []
    for blocks in pages:
        for b in blocks:
            para: list[str] = []
            for line in b.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                size = max(s["size"] for s in spans)
                level = 1 if size >= body * 1.6 else 2 if size >= body * 1.3 else 3 if size >= body * 1.12 else 0
                if level:
                    if para:
                        out.append(" ".join(para))
                        para = []
                    out.append("#" * level + " " + "".join(s["text"] for s in line["spans"]).strip())
                    continue
                text = ""
                for s in line["spans"]:
                    t = s["text"]
                    bold = bool(s["flags"] & 16) and t.strip()
                    text += f"**{t.strip()}**" + (" " if t.endswith(" ") else "") if bold else t
                text = text.strip()
                if text.startswith(BULLETS) and len(text) > 1:
                    if para:
                        out.append(" ".join(para))
                        para = []
                    out.append("- " + text.lstrip("".join(BULLETS)).strip())
                elif para and para[-1].endswith("-") and not para[-1].endswith(" -"):
                    para[-1] = para[-1][:-1] + text  # a word split over two lines
                else:
                    para.append(text)
            if para:
                out.append(" ".join(para))
        out.append("")
    md, prev = [], ""
    for chunk in out:  # blank lines between paragraphs, lists kept tight
        if chunk.startswith("- ") and prev.startswith("- "):
            md.append(chunk)
        else:
            md += ["", chunk] if md else [chunk]
        prev = chunk
    return re.sub(r"\n{3,}", "\n\n", "\n".join(md)).strip() + "\n"


def to_markdown(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    """Text with headings, lists and bold kept."""
    with _open(src) as d:
        texts = _page_texts(d)
        md = markdown_of(d)
    if not "".join(texts).strip():
        raise ConversionError("This PDF has no text in it. It's probably scanned images; try Read text first.")
    Path(long_path(out)).write_text(md, encoding="utf-8")
    from .officeutil import text_coverage

    cov = text_coverage("\n".join(texts), Path(long_path(out)).read_text(encoding="utf-8"))
    if cov is not None and cov < 0.95:
        raise VerificationError(f"only {cov:.0%} of the text made it into the Markdown")
    notes.append("Checked: all of the text, with headings, lists and bold as Markdown. Tables become text.")


def to_html(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    """One web page with every page's text and pictures (pictures saved inside the page)."""
    import re as _re

    with _open(src) as d:
        texts = _page_texts(d)
        bodies = []
        for page in d:
            x = page.get_text("xhtml")
            m = _re.search(r"(?is)<body[^>]*>(.*)</body>", x)
            bodies.append(f'<section class="page">{m.group(1) if m else x}</section>')
    page_html = ('<!DOCTYPE html><html><head><meta charset="utf-8"><title>' + src.stem.replace("<", "&lt;") +
                 '</title><style>body{max-width:860px;margin:32px auto;padding:0 18px;font-family:Segoe UI,Arial;'
                 'line-height:1.5}.page{border-bottom:1px solid #ddd;padding:12px 0 24px}img{max-width:100%}</style>'
                 '</head><body>' + "\n".join(bodies) + "</body></html>")
    Path(long_path(out)).write_text(page_html, encoding="utf-8")
    from .officeutil import text_coverage

    plain = _re.sub(r"<[^>]+>", " ", page_html)
    import html as _h

    cov = text_coverage("\n".join(texts), _h.unescape(plain))
    if cov is not None and cov < 0.97:
        raise VerificationError(f"only {cov:.0%} of the text made it into the page")
    notes.append(f"Checked: {len(bodies)} pages of text and pictures in one web page.")


TOOLS.update({"tiff": to_tiff, "longimg": long_image, "md": to_markdown, "html": to_html})

# ---------------------------------------------------------------- tables, blank pages

def _cell(v):
    """A table cell for Excel: numbers as numbers when they're plainly numbers, text otherwise."""
    from .data import _csv_value

    text = " ".join(str(v).split()) if v is not None else ""
    return _csv_value(text) if text else None


def _cell_text(page_words, box) -> str:
    """The words whose middle lies in this cell, line by line."""
    x0, y0, x1, y1 = box
    inside = [w for w in page_words if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1]
    inside.sort(key=lambda w: (w[5], w[6], w[7]))
    lines: dict[tuple[int, int], list[str]] = {}
    for w in inside:
        lines.setdefault((w[5], w[6]), []).append(w[4])
    return " ".join(" ".join(ws) for ws in lines.values())


def tables(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    """Every table PyMuPDF finds, each on its own sheet ("Page 2", "Page 2 (2)"...)."""
    from openpyxl import Workbook, load_workbook

    found: list[tuple[str, list[list]]] = []
    with _open(src) as d:
        for pno, page in enumerate(d, 1):
            try:
                tabs = page.find_tables()
            except Exception:  # noqa: BLE001 - a page the table finder can't handle: skip it
                continue
            page_words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, n): keeps "1.20" whole
            for k, t in enumerate(tabs.tables, 1):
                # The table finder gives the cells; their text comes from the page's words (the finder's own
                # text reading splits numbers like 1.20 into "1 20" and ".").
                rows = [[_cell(_cell_text(page_words, c)) if c is not None else None for c in row.cells]
                        for row in t.rows]
                rows = [r for r in rows if any(c not in (None, "") for c in r)]
                keep = [i for i in range(max((len(r) for r in rows), default=0))
                        if any(i < len(r) and r[i] not in (None, "") for r in rows)]
                rows = [[r[i] if i < len(r) else None for i in keep] for r in rows]  # no empty spacer columns
                if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                    found.append((f"Page {pno}" + (f" ({k})" if k > 1 else ""), rows))
    if not found:
        raise ConversionError("No tables were found in this PDF. Tables need lines or clear columns; scanned "
                              "pages are pictures and have none.")
    wb = Workbook(write_only=True)
    for name, rows in found[:250]:
        ws = wb.create_sheet(name[:31])
        for r in rows:
            ws.append(r)
    wb.save(long_path(out))
    def trim(r) -> list:
        r = list(r)
        while r and r[-1] in (None, ""):
            r.pop()
        return r

    back = load_workbook(long_path(out), read_only=True)
    try:
        if len(back.worksheets) != min(len(found), 250):
            raise VerificationError("a table's sheet is missing")
        for (name, rows), ws in zip(found, back.worksheets):
            if [trim(r) for r in ws.iter_rows(values_only=True)] != [trim(r) for r in rows]:
                raise VerificationError(f"the table on {name} doesn't match")
    finally:
        back.close()
    cells = sum(len(r) for _n, rows in found for r in rows)
    notes.append(f"Checked: {len(found)} table{'s' if len(found) != 1 else ''} ({cells:,} cells), one sheet each, "
                 "named after their page.")
    if len(found) > 250:
        notes.append("Only the first 250 tables were saved.")
    notes.append("Check merged cells and headings that span columns: PDFs don't store tables, so they're "
                 "reconstructed from the lines and text positions.")


BLANK_DPI = 30
BLANK_INK = 0.0015  # share of non-white pixels a page may have and still count as blank (specks, scan dust)


def _is_blank(page) -> bool:
    if page.get_text().strip():
        return False
    pix = page.get_pixmap(dpi=BLANK_DPI, colorspace="gray", alpha=False)
    data = pix.samples
    inked = sum(1 for v in data if v < 235)
    return inked <= max(1, len(data) * BLANK_INK)


def remove_blank(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    with _open(src) as d:
        blank = [i for i, page in enumerate(d) if _is_blank(page)]
        if not blank:
            raise ConversionError("This PDF has no blank pages.")
        if len(blank) == d.page_count:
            raise ConversionError("Every page of this PDF is blank.")
        keep = [i for i in range(d.page_count) if i not in blank]
        texts = [d[i].get_text() for i in keep]
        looks = _looks(d, keep)
        d.select(keep)
        _save(d, out)
    _check_same(out, texts, "blank pages removed", looks=looks)
    shown = ", ".join(str(i + 1) for i in blank[:12]) + (" and more" if len(blank) > 12 else "")
    notes.append(f"Removed {len(blank)} blank page{'s' if len(blank) != 1 else ''} (page {shown}). Checked: the "
                 f"other {len(keep)} look and read exactly as before.")


TOOLS.update({"tables": tables, "blank": remove_blank})



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
