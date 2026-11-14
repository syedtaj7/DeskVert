"""Image conversion with Pillow (+ pillow-heif, rawpy, Qt for SVG, img2pdf).

Pipeline for every conversion:
  1. load      - decode the source; apply EXIF rotation to the pixels; keep
                 EXIF / ICC color profile / XMP / DPI; keep all frames when the
                 target can hold animation or pages.
  2. prepare   - adapt pixels to what the target can store (e.g. flatten
                 transparency for JPG, 256-color palette for GIF). Each change
                 is reported as a note.
  3. save      - encode with the highest-fidelity settings.
  4. verify    - decode the output again and compare it with the prepared
                 pixels: identical for lossless formats, a minimum PSNR for
                 lossy ones. Size, frame count and color profile are checked
                 too. Any mismatch raises VerificationError and the output is
                 discarded.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageSequence

from ..catalog import RAW_EXTS, image_format
from ..errors import ConversionError, VerificationError
from ..lowimpact import engine_threads
from ..paths import long_path

Image.MAX_IMAGE_PIXELS = 600_000_000  # allow big panoramas, still block decompression bombs

MULTI_FRAME_TARGETS = {"png", "webp", "avif", "gif", "tiff"}
EXIF_TARGETS = {"jpg", "png", "webp", "heic", "avif", "tiff"}
ICC_TARGETS = {"jpg", "png", "webp", "heic", "avif", "tiff"}
LOSSY_MIN_PSNR = 30.0  # dB; catches broken encodes (shifted/garbled pixels), not taste
last_psnr: float | None = None  # for diagnostics/tests

_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}

_plugins_ready = False


def _ensure_plugins() -> None:
    global _plugins_ready
    if not _plugins_ready:
        import pillow_heif

        pillow_heif.options.DECODE_THREADS = engine_threads()
        pillow_heif.register_heif_opener()
        _plugins_ready = True


class Notes(list):
    def add(self, text: str) -> None:
        if text not in self:
            self.append(text)


@dataclass
class Loaded:
    frames: list[Image.Image]
    durations: list[int] = field(default_factory=list)
    loop: int = 0
    exif: bytes | None = None
    icc: bytes | None = None
    xmp: bytes | str | None = None
    dpi: tuple | None = None


# ------------------------------------------------------------------ metadata


def _exif_with_orientation_reset(raw: bytes) -> bytes:
    """Set the EXIF Orientation tag to 1 by patching the bytes in place, so all
    other EXIF data (camera, GPS, dates...) is preserved exactly."""
    data = bytearray(raw)
    base = 6 if data[:6] == b"Exif\x00\x00" else 0
    if len(data) < base + 8:
        return bytes(data)
    order = data[base:base + 2]
    if order == b"II":
        endian = "little"
    elif order == b"MM":
        endian = "big"
    else:
        return bytes(data)
    rd = lambda off, n: int.from_bytes(data[off:off + n], endian)  # noqa: E731
    ifd = base + rd(base + 4, 4)
    if ifd + 2 > len(data):
        return bytes(data)
    count = rd(ifd, 2)
    for i in range(count):
        entry = ifd + 2 + i * 12
        if entry + 12 > len(data):
            break
        if rd(entry, 2) == 0x0112:  # Orientation, SHORT
            data[entry + 8:entry + 10] = (1).to_bytes(2, endian)
            break
    return bytes(data)


_XMP_ORIENT = re.compile(rb"(tiff:Orientation\s*=\s*[\"'])\d([\"'])|(<tiff:Orientation>)\d(</tiff:Orientation>)")


def _xmp_orientation_reset(xmp):
    if not xmp:
        return xmp
    as_bytes = xmp.encode("utf-8") if isinstance(xmp, str) else bytes(xmp)
    fixed = _XMP_ORIENT.sub(lambda m: (m.group(1) or m.group(3)) + b"1" + (m.group(2) or m.group(4)), as_bytes)
    return fixed.decode("utf-8", "replace") if isinstance(xmp, str) else fixed


_TIFF_KEEP_TAGS = (270, 271, 272, 305, 306, 315, 33432)  # description, make, model, software, date, artist, copyright


def _exif_from_tiff(im: Image.Image) -> bytes | None:
    try:
        src = im.getexif()
        ex = Image.Exif()
        for tag in _TIFF_KEEP_TAGS:
            if tag in src:
                ex[tag] = src[tag]
        return ex.tobytes() if len(ex) else None
    except Exception:
        return None


# ------------------------------------------------------------------ loading


def _open_raw(path: Path, notes: Notes) -> Loaded:
    import rawpy

    with open(long_path(path), "rb") as fh, rawpy.imread(fh) as raw:  # file object: safe with non-ASCII paths
        rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
    notes.add("RAW developed with the camera's white balance.")
    return Loaded([Image.fromarray(rgb, "RGB")])


def _open_svg(path: Path, notes: Notes) -> Loaded:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    _app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 - needed for fonts
    r = QSvgRenderer(long_path(path))
    if not r.isValid():
        raise ConversionError("This SVG file can't be read or is damaged.")
    w, h = r.defaultSize().width(), r.defaultSize().height()
    if w <= 0 or h <= 0:
        vb = r.viewBoxF()
        w, h = (vb.width(), vb.height()) if vb.width() > 0 else (1024, 1024)
    scale = max(1.0, 1024 / max(w, h))
    W, H = max(1, round(w * scale)), max(1, round(h * scale))
    img = QImage(W, H, QImage.Format.Format_RGBA8888)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    r.render(p, QRectF(0, 0, W, H))
    p.end()
    data = bytes(img.constBits())
    pil = Image.frombuffer("RGBA", (W, H), data, "raw", "RGBA", img.bytesPerLine(), 1).copy()
    notes.add(f"SVG drawn at {W}x{H} px.")
    return Loaded([pil])


def load(path: Path, notes: Notes, multi: bool) -> Loaded:
    ext = path.suffix.lower()
    if ext in RAW_EXTS:
        return _open_raw(path, notes)
    if ext in (".svg", ".svgz"):
        return _open_svg(path, notes)

    _ensure_plugins()
    if ext == ".livp":
        import zipfile

        with zipfile.ZipFile(long_path(path)) as z:
            name = next((n for n in z.namelist() if n.lower().endswith((".heic", ".heif", ".jpg", ".jpeg"))), None)
            if name is None:
                raise ConversionError("This Live Photo has no picture inside.")
            im = Image.open(io.BytesIO(z.read(name)))
        notes.add("The still photo of the Live Photo was converted (not its video).")
    else:
        im = Image.open(long_path(path))
    try:
        fmt = (im.format or "").upper()
        if fmt == "WMF":  # Windows metafile (EMF / WMF): drawn by Windows at print resolution
            im.load(dpi=200)
        n = getattr(im, "n_frames", 1)
        can_multi = fmt in ("GIF", "WEBP", "PNG", "AVIF", "TIFF")
        if n > 1 and can_multi and not multi:
            notes.add("Only the first page was converted." if fmt == "TIFF" else "Animation removed: only the first frame was kept.")

        info = im.info
        exif = info.get("exif")
        orientation = 1
        try:
            orientation = int(im.getexif().get(0x0112, 1) or 1)
        except Exception:
            pass
        if exif:
            exif = _exif_with_orientation_reset(exif)
        elif fmt == "TIFF":
            exif = _exif_from_tiff(im)
        xmp = _xmp_orientation_reset(info.get("xmp"))
        method = _TRANSPOSE.get(orientation)
        if fmt in ("HEIF", "AVIF"):
            method = None  # these decoders already return upright pixels

        frames, durations = [], []
        if n > 1 and can_multi and multi:
            for fr in ImageSequence.Iterator(im):
                frames.append(fr.copy())
                durations.append(int(fr.info.get("duration", info.get("duration", 100)) or 100))
        else:
            im.load()
            frames.append(im.copy())
        if method is not None:
            frames = [f.transpose(method) for f in frames]
            notes.add("Rotation from the camera's orientation tag applied to the pixels.")
        if fmt == "PNG":
            _note_png_16bit_color(path, notes)
        return Loaded(
            frames=frames,
            durations=durations,
            loop=int(info.get("loop", 0) or 0),
            exif=exif,
            icc=info.get("icc_profile") or None,
            xmp=xmp,
            dpi=info.get("dpi"),
        )
    finally:
        im.close()


def _note_png_16bit_color(path: Path, notes: Notes) -> None:
    try:
        with open(long_path(path), "rb") as f:
            head = f.read(26)
        if head[24] == 16 and head[25] in (2, 6):
            notes.add("16-bit color was reduced to 8-bit (not supported yet for color images).")
    except Exception:
        pass


# ------------------------------------------------------------------ pixel preparation


def _canonical(f: Image.Image) -> Image.Image:
    m = f.mode
    if m in ("P", "PA"):
        return f.convert("RGBA" if (m == "PA" or "transparency" in f.info) else "RGB")
    if m in ("L", "RGB") and "transparency" in f.info:
        return f.convert("LA" if m == "L" else "RGBA")
    if m == "1":
        return f.convert("L")
    if m in ("La",):
        return f.convert("LA")
    if m in ("RGBa",):
        return f.convert("RGBA")
    if m in ("RGBX", "YCbCr", "LAB", "HSV"):
        return f.convert("RGB")
    if m == "F":
        return Image.fromarray(np.clip(np.asarray(f), 0, 65535).astype(np.uint16))
    if m == "I":
        a = np.asarray(f)
        if a.min() >= 0 and a.max() <= 65535:
            return Image.fromarray(a.astype(np.uint16))
        return Image.fromarray(np.clip(a, 0, 65535).astype(np.uint16))
    if m.startswith("I;16"):
        return Image.fromarray(np.asarray(f).astype(np.uint16))
    return f


def _is_16bit(f: Image.Image) -> bool:
    return f.mode.startswith("I")


def _to_8bit(f: Image.Image) -> Image.Image:
    a = np.asarray(f).astype(np.uint32)
    return Image.fromarray((a >> 8).astype(np.uint8), "L")


def _has_alpha(f: Image.Image) -> bool:
    return f.mode in ("RGBA", "LA")


def _alpha_is_opaque(f: Image.Image) -> bool:
    return f.getchannel("A").getextrema()[0] == 255


def _flatten(f: Image.Image, notes: Notes) -> Image.Image:
    """Remove the alpha channel; transparent areas become white."""
    base_mode = "L" if f.mode == "LA" else "RGB"
    if _alpha_is_opaque(f):
        return f.convert(base_mode)
    notes.add("Transparent areas were filled with white.")
    bg = Image.new(base_mode, f.size, 255 if base_mode == "L" else (255, 255, 255))
    bg.paste(f.convert(base_mode), mask=f.getchannel("A"))
    return bg


def _cmyk_to_rgb(f: Image.Image, icc: bytes | None, notes: Notes) -> tuple[Image.Image, bytes | None]:
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            dst = ImageCms.createProfile("sRGB")
            out = ImageCms.profileToProfile(
                f, src, dst, renderingIntent=ImageCms.Intent.PERCEPTUAL, outputMode="RGB"
            )
            notes.add("CMYK colors converted to RGB using the embedded color profile.")
            return out, ImageCms.ImageCmsProfile(dst).tobytes()
        except Exception:
            pass
    notes.add("CMYK colors converted to RGB.")
    return f.convert("RGB"), None


def prepare(f: Image.Image, fmt: str, icc: bytes | None, notes: Notes) -> tuple[Image.Image, bytes | None]:
    """Adapt one frame to what ``fmt`` can store. Returns (frame, icc_profile)."""
    f = _canonical(f)
    if f.mode == "CMYK" and fmt not in ("jpg", "tiff"):
        f, icc = _cmyk_to_rgb(f, icc, notes)
    if _is_16bit(f) and fmt not in ("png", "tiff"):
        f = _to_8bit(f)
        notes.add("16-bit grayscale was reduced to 8-bit (the format can't hold more).")
    if fmt in ("jpg", "pdf", "bmp") and _has_alpha(f):
        # BMP technically has an alpha variant, but Windows and most apps ignore
        # it, so the result would look different from the source. Flatten instead.
        f = _flatten(f, notes)
    if fmt in ("webp", "heic", "avif", "ico", "bmp", "tga", "qoi", "dds", "jp2", "sgi"):
        if f.mode in ("L", "1"):
            f = f.convert("RGB")
        elif f.mode in ("LA", "PA"):
            f = f.convert("RGBA")
        elif f.mode == "P":
            f = f.convert("RGBA" if _has_alpha(f) else "RGB")
    if fmt in ("pcx", "ppm", "xbm") and _has_alpha(f):
        f = _flatten(f, notes)
    if fmt in ("pcx", "ppm") and f.mode not in ("RGB", "L"):
        f = f.convert("RGB")
    if fmt == "xbm":
        f = f.convert("L").point(lambda v: 255 if v >= 128 else 0).convert("1")
        notes.add("XBM holds black and white only, so the picture became black and white.")
    return f, icc


# ------------------------------------------------------------------ GIF palette


def _to_gif_frame(f: Image.Image, dither: bool, notes: Notes) -> Image.Image:
    transparent = False
    if _has_alpha(f):
        rgba = f.convert("RGBA")
        alpha = rgba.getchannel("A")
        if alpha.getextrema()[0] < 255:
            transparent = True
            hist = alpha.histogram()
            if sum(hist[1:255]):
                notes.add("Semi-transparent pixels became fully solid or fully clear (GIF limit).")
        rgb = rgba.convert("RGB")
        mask = np.asarray(alpha) < 128
    else:
        rgb = f.convert("RGB")
        mask = None
    max_colors = 255 if transparent else 256

    a = np.asarray(rgb, dtype=np.uint32)
    key = (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]
    if mask is not None:
        key_visible = key[~mask]
    else:
        key_visible = key.ravel()
    uniq = np.unique(key_visible)
    if len(uniq) <= max_colors:
        # Few enough colors: build an exact palette, no quality loss at all.
        idx = np.searchsorted(uniq, key).clip(0, max(len(uniq) - 1, 0)).astype(np.uint8)
        palette = []
        for k in uniq.tolist():
            palette += [(k >> 16) & 255, (k >> 8) & 255, k & 255]
        p = Image.fromarray(idx, "P")
    else:
        notes.add("Reduced to 256 colors" + (" with dithering." if dither else "."))
        q = rgb.quantize(
            colors=max_colors,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE,
        )
        palette = list(q.getpalette() or [])[: max_colors * 3]
        p = q
    palette += [0] * (768 - len(palette))
    if transparent:
        t_index = 255
        idx = np.array(p, dtype=np.uint8)
        idx[mask] = t_index
        p = Image.fromarray(idx, "P")
        p.info["transparency"] = t_index
    p.putpalette(palette)
    return p


# ------------------------------------------------------------------ saving


def _psnr_floor(quality: int) -> float:
    return LOSSY_MIN_PSNR if quality >= 80 else 24.0


def _save(frames, durations, loop, fmt, out: Path, meta: Loaded, icc, opts: dict, notes: Notes) -> tuple[bool, float]:
    """Encode. Returns (is_lossless, min_psnr_for_verification)."""
    first, rest = frames[0], frames[1:]
    common = {}
    if meta.exif and fmt in EXIF_TARGETS:
        common["exif"] = meta.exif
    if icc and fmt in ICC_TARGETS:
        common["icc_profile"] = icc
    if meta.xmp and fmt in ("jpg", "png", "webp", "avif", "heic"):
        common["xmp"] = meta.xmp
    if meta.dpi and fmt in ("jpg", "png", "tiff", "bmp"):
        common["dpi"] = tuple(round(float(x)) or 72 for x in meta.dpi[:2])
    anim = {}
    if rest:
        anim = dict(save_all=True, append_images=rest, duration=durations or 100, loop=loop)
    path = long_path(out)

    if fmt == "jpg":
        q = int(opts.get("quality", 92))
        first.save(path, "JPEG", quality=q, subsampling=0 if q >= 90 else 2, optimize=True, **common)
        return False, _psnr_floor(q)
    if fmt == "png":
        first.save(path, "PNG", compress_level=6, **common, **anim)
        return True, 0
    if fmt == "webp":
        if max(first.size) > 16383:
            raise ConversionError("WEBP images can be at most 16383 px wide or tall.")
        lossless = bool(opts.get("lossless", False))
        q = int(opts.get("quality", 92))
        if lossless:
            first.save(path, "WEBP", lossless=True, quality=100, method=4, exact=True, **common, **anim)
        else:
            first.save(path, "WEBP", quality=q, method=5, **common, **anim)
        return lossless, _psnr_floor(q)
    if fmt == "heic":
        q = int(opts.get("quality", 90))
        first.save(path, "HEIF", quality=q, **common)
        return False, _psnr_floor(q)
    if fmt == "avif":
        q = int(opts.get("quality", 88))
        sub = "4:4:4" if q >= 85 else "4:2:0"  # full color resolution at high quality
        first.save(path, "AVIF", quality=q, speed=6, subsampling=sub, max_threads=engine_threads(), **common, **anim)
        return False, _psnr_floor(q)
    if fmt == "gif":
        first.save(path, "GIF", disposal=2, optimize=False, **anim)
        return True, 0
    if fmt == "bmp":
        first.save(path, "BMP", **common)
        return True, 0
    if fmt == "tiff":
        if rest:
            anim = dict(save_all=True, append_images=rest)
        first.save(path, "TIFF", compression="tiff_lzw", **common, **anim)
        return True, 0
    if fmt == "tga":
        first.save(path, "TGA", rle=True)
        return True, 0
    if fmt == "jp2":
        first.save(path, "JPEG2000", irreversible=False)  # the lossless kind of JPEG 2000
        return True, 0
    if fmt in ("qoi", "dds", "pcx", "ppm", "sgi", "xbm"):
        first.save(path, {"qoi": "QOI", "dds": "DDS", "pcx": "PCX", "ppm": "PPM", "sgi": "SGI", "xbm": "XBM"}[fmt])
        return True, 0
    raise ConversionError(f"Unknown image format: {fmt}")


# ------------------------------------------------------------------ verification


def _pixels(im: Image.Image, mode: str) -> np.ndarray:
    a = np.array(im.convert(mode) if im.mode != mode else im)
    if mode == "RGBA":
        a[a[..., 3] == 0, :3] = 0  # color under fully transparent pixels is meaningless
    return a


def _premultiply(a: np.ndarray) -> np.ndarray:
    out = a.astype(np.uint16)
    alpha = out[..., 3:4]
    out[..., :3] = (out[..., :3] * alpha + 127) // 255
    return out.astype(np.uint8)


def _compare(out: Image.Image, ref: Image.Image, lossless: bool, min_psnr: float, what: str = "image") -> None:
    if out.size != ref.size:
        raise VerificationError(f"{what} size is {out.size[0]}x{out.size[1]}, expected {ref.size[0]}x{ref.size[1]}")
    if _is_16bit(ref) or _is_16bit(out):
        a = np.asarray(out).astype(np.int64)
        b = np.asarray(ref).astype(np.int64)
        if a.shape != b.shape or not np.array_equal(a, b):
            raise VerificationError(f"{what} pixels differ from the source")
        return
    if ref.mode == "CMYK" and lossless:
        mode = "CMYK"
    elif _has_alpha(ref) or "A" in out.mode or "transparency" in out.info:
        mode = "RGBA"
    else:
        mode = "RGB"
    a, b = _pixels(out, mode), _pixels(ref, mode)
    if lossless:
        if not np.array_equal(a, b):
            raise VerificationError(f"{what} pixels differ from the source")
        return
    if mode == "RGBA":
        # Compare what is visible: color weighted by opacity, plus the opacity.
        a = _premultiply(a)
        b = _premultiply(b)
    # Lossy: compare at up to ~2 MP to keep memory and time low.
    scale = max(1, int((ref.size[0] * ref.size[1] / 2_000_000) ** 0.5))
    if scale > 1:
        size = (max(1, ref.size[0] // scale), max(1, ref.size[1] // scale))
        a = np.asarray(Image.fromarray(a).resize(size, Image.Resampling.BOX))
        b = np.asarray(Image.fromarray(b).resize(size, Image.Resampling.BOX))
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    psnr = 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)
    global last_psnr
    last_psnr = psnr
    if psnr < min_psnr:
        raise VerificationError(f"{what} looks different from the source (PSNR {psnr:.1f} dB)")


def _verify(out: Path, fmt: str, refs: list[Image.Image], lossless: bool, min_psnr: float, icc, meta: Loaded, notes: Notes) -> None:
    _ensure_plugins()
    try:
        im = Image.open(long_path(out))
        im.load()
    except Exception as e:
        raise VerificationError(f"the new file can't be opened: {e}") from e
    try:
        n_out = getattr(im, "n_frames", 1)
        if len(refs) > 1:
            if fmt == "tiff" and n_out != len(refs):
                raise VerificationError(f"{n_out} pages written, expected {len(refs)}")
            if n_out < 2:
                raise VerificationError("the animation was lost")
        _compare(im, refs[0], lossless, min_psnr)
        if fmt == "tiff" and len(refs) > 1:
            for i in range(1, len(refs)):
                im.seek(i)
                _compare(im, refs[i], True, 0, what=f"page {i + 1}")
            im.seek(0)
        if icc and fmt in ICC_TARGETS and not im.info.get("icc_profile"):
            raise VerificationError("the color profile was lost")
        if meta.exif and fmt in EXIF_TARGETS:
            try:
                if not len(im.getexif()):
                    notes.add("Camera details (EXIF) couldn't be copied to this format.")
            except Exception:
                pass
    finally:
        im.close()


# ------------------------------------------------------------------ ICO


def _convert_ico(src: Path, out: Path, notes: Notes) -> None:
    meta = load(src, notes, multi=False)
    f, _ = prepare(meta.frames[0], "ico", meta.icc, notes)
    f = f.convert("RGBA")
    w, h = f.size
    if w != h:
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(f, ((side - w) // 2, (side - h) // 2))
        f = canvas
        notes.add("Padded to a square with transparent edges.")
    if f.width > 256:
        f = f.resize((256, 256), Image.Resampling.LANCZOS)
        notes.add("Scaled down to 256x256 (the largest icon size).")
    sizes = [s for s in (16, 24, 32, 48, 64, 128, 256) if s <= f.width]
    if f.width not in sizes:
        sizes.append(f.width)
    f.save(long_path(out), "ICO", sizes=[(s, s) for s in sizes])
    with Image.open(long_path(out)) as im:
        im.load()
        got = sorted(im.info.get("sizes", set()))
        if max(got, default=(0, 0))[0] != f.width:
            raise VerificationError("icon sizes are missing")
        _compare(im, f, True, 0)


def _convert_icns(src: Path, out: Path, notes: Notes) -> None:
    """A macOS app icon: square, every size up to 1024 px."""
    meta = load(src, notes, multi=False)
    f, _ = prepare(meta.frames[0], "png", meta.icc, notes)
    f = f.convert("RGBA")
    w, h = f.size
    if w != h:
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(f, ((side - w) // 2, (side - h) // 2))
        f = canvas
        notes.add("Padded to a square with transparent edges.")
    if f.width != 1024:
        if f.width < 512:
            notes.add(f"The picture is only {f.width} px; the larger icon sizes are enlarged from it.")
        f = f.resize((1024, 1024), Image.Resampling.LANCZOS)
    f.save(long_path(out), "ICNS")
    with Image.open(long_path(out)) as im:
        im.load()
        if im.size != (1024, 1024):
            raise VerificationError("the largest icon size is missing")
        _compare(im, f, False, 40)


# ------------------------------------------------------------------ PDF


def _jpeg_passthrough_ok(path: Path) -> bool:
    try:
        with Image.open(long_path(path)) as im:
            if im.format != "JPEG" or im.mode not in ("L", "RGB", "CMYK"):
                return False
            return int(im.getexif().get(0x0112, 1) or 1) in (1, 3, 6, 8)
    except Exception:
        return False


def _convert_pdf(sources: list[Path], out: Path, opts: dict, notes: Notes) -> None:
    import img2pdf

    pages: list[bytes] = []
    expect: list[tuple[str, object]] = []
    for src in sources:
        if image_format(src) == "jpg" and _jpeg_passthrough_ok(src):
            with open(long_path(src), "rb") as fh:
                data = fh.read()
            pages.append(data)
            expect.append(("raw", data))
            continue
        meta = load(src, notes, multi=(image_format(src) == "tiff"))
        for frame in meta.frames:
            f, icc = prepare(frame, "pdf", meta.icc, notes)
            if f.mode == "CMYK":
                f, icc = _cmyk_to_rgb(f, icc, notes)
            buf = io.BytesIO()
            f.save(buf, "PNG", icc_profile=icc) if icc else f.save(buf, "PNG")
            pages.append(buf.getvalue())
            expect.append(("pixels", f))

    page = opts.get("page", "Image size")
    layout = None
    if page in ("A4", "Letter"):
        size = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297)) if page == "A4" else (img2pdf.in_to_pt(8.5), img2pdf.in_to_pt(11))
        layout = img2pdf.get_layout_fun(size, fit=img2pdf.FitMode.into, auto_orient=True)
    # img2pdf's own PDF writer, always: a leftover pikepdf folder from an older install must never be picked up
    pdf = img2pdf.convert(pages, layout_fun=layout or img2pdf.default_layout_fun, rotation=img2pdf.Rotation.ifvalid,
                          engine=img2pdf.Engine.internal)
    with open(long_path(out), "wb") as fh:
        fh.write(pdf)
    _verify_pdf(out, expect)


def _verify_pdf(out: Path, expect: list) -> None:
    import pymupdf

    try:
        doc = pymupdf.open(long_path(out))
    except Exception as e:
        raise VerificationError(f"the PDF can't be opened: {e}") from e
    with doc:
        if doc.page_count != len(expect):
            raise VerificationError(f"PDF has {doc.page_count} pages, expected {len(expect)}")
        for i, (page, (kind, data)) in enumerate(zip(doc, expect)):
            imgs = page.get_images(full=True)
            if len(imgs) != 1:
                raise VerificationError(f"page {i + 1} has no image")
            xref = imgs[0][0]
            if kind == "raw":
                if doc.xref_stream_raw(xref) != data:
                    raise VerificationError(f"page {i + 1}: embedded photo differs from the original")
            else:
                pix = pymupdf.Pixmap(doc, xref)
                mode = {1: "L", 3: "RGB"}.get(pix.n)
                if mode is None:
                    raise VerificationError(f"page {i + 1}: unexpected color format")
                got = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                _compare(got, data, True, 0, what=f"page {i + 1}")


# ------------------------------------------------------------------ entry point


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    notes = Notes()
    if fmt in ("pdf", "pdf_combined"):
        _convert_pdf(sources, out, opts, notes)
        return list(notes)
    src = sources[0]
    if fmt == "ico":
        _convert_ico(src, out, notes)
        return list(notes)
    if fmt == "icns":
        _convert_icns(src, out, notes)
        return list(notes)

    meta = load(src, notes, multi=fmt in MULTI_FRAME_TARGETS)
    frames, icc = [], meta.icc
    for fr in meta.frames:
        f, icc = prepare(fr, fmt, meta.icc, notes)
        if fmt == "gif":
            f = _to_gif_frame(f, bool(opts.get("dither", True)), notes)
        frames.append(f)
    if len({f.mode for f in frames}) > 1:  # mixed frame modes (e.g. GIF frame 0 is P, others RGBA)
        target_mode = "RGBA" if any(_has_alpha(f) for f in frames) else frames[0].mode
        if fmt != "gif":
            frames = [f.convert(target_mode) if f.mode != target_mode else f for f in frames]
    lossless, min_psnr = _save(frames, meta.durations, meta.loop, fmt, out, meta, icc, opts, notes)
    _verify(out, fmt, frames, lossless, min_psnr, icc, meta, notes)
    return list(notes)
