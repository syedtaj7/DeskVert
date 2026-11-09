"""Image compression: to a size limit ("under 100 KB") or to a chosen quality.

- estimate(): a quick preview for the Compress panel. File sizes are measured
  on a small copy (about 1 megapixel), so it takes a fraction of a second even
  on slow laptops; the full-size numbers are predictions, labelled "about".
- convert(): finds the highest quality whose file is guaranteed to be under
  the limit. It only shrinks the picture's dimensions when quality alone can't
  get there, and never goes below 40% quality before resizing.

"KB" means 1,000 bytes, so "under 20 KB" also passes stricter upload forms.
Camera details (EXIF) are removed to save space, colors are converted to
standard sRGB (so they look the same without an embedded color profile).
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageCms

from ..errors import ConversionError, VerificationError
from ..lowimpact import engine_threads
from ..paths import long_path
from .image import Notes, _ensure_plugins, load, prepare

QUALITY_FLOOR = 55  # below this, shrink the picture instead of lowering quality further (looks better)
PROXY_SIDE = 1024
SCALES = (1.0, 0.85, 0.72, 0.6, 0.5, 0.42, 0.35, 0.28, 0.22, 0.17, 0.13, 0.1, 0.075, 0.05)
KB = 1000

_PIL = {".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".avif": "AVIF", ".heic": "HEIF", ".heif": "HEIF",
        ".png": "PNG"}


def human(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1000:
        return f"{n / 1000:.0f} KB"
    return f"{int(n)} bytes"


# ---------------------------------------------------------------- pixels


def _to_srgb(img: Image.Image, icc: bytes | None) -> Image.Image:
    if not icc or img.mode not in ("RGB", "RGBA"):
        return img
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        dst = ImageCms.createProfile("sRGB")
        if img.mode == "RGBA":
            alpha = img.getchannel("A")
            rgb = ImageCms.profileToProfile(img.convert("RGB"), src, dst, outputMode="RGB")
            rgb.putalpha(alpha)
            return rgb
        return ImageCms.profileToProfile(img, src, dst, outputMode="RGB")
    except Exception:
        return img


def _source_image(path: Path, out_ext: str, notes: Notes) -> Image.Image:
    _ensure_plugins()
    meta = load(path, notes, multi=False)
    key = {".jpg": "jpg", ".jpeg": "jpg", ".webp": "webp", ".avif": "avif", ".heic": "heic", ".heif": "heic",
           ".png": "png"}[out_ext]
    img, icc = prepare(meta.frames[0], key, meta.icc, notes)
    if img.mode not in ("RGB", "RGBA", "L", "LA"):
        img = img.convert("RGBA" if "A" in img.mode else "RGB")
    if img.mode.startswith("I"):
        img = img.convert("L")
    return _to_srgb(img, icc)


def encode(img: Image.Image, out_ext: str, quality: int) -> bytes:
    fmt = _PIL[out_ext]
    q = max(1, min(100, int(quality)))
    buf = io.BytesIO()
    if fmt == "JPEG":
        im = img.convert("RGB") if img.mode not in ("RGB", "L") else img
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True, subsampling=0 if q >= 90 else 2)
    elif fmt == "WEBP":
        img.save(buf, "WEBP", quality=q, method=4)
    elif fmt == "AVIF":
        img.save(buf, "AVIF", quality=q, speed=8, max_threads=engine_threads())
    elif fmt == "HEIF":
        img.save(buf, "HEIF", quality=q)
    else:  # PNG: lossless, or fewer colors at lower "quality"
        if q >= 95:
            img.save(buf, "PNG", optimize=True)
        else:
            colors = 256 if q >= 80 else 128 if q >= 60 else 64 if q >= 40 else 32
            src = img if img.mode in ("RGB", "RGBA") else img.convert("RGBA" if "A" in img.mode else "RGB")
            method = Image.Quantize.FASTOCTREE if src.mode == "RGBA" else Image.Quantize.MEDIANCUT
            src.quantize(colors=colors, method=method, dither=Image.Dither.FLOYDSTEINBERG).save(buf, "PNG",
                                                                                                optimize=True)
    return buf.getvalue()


def _scaled(img: Image.Image, s: float) -> Image.Image:
    if s >= 0.999:
        return img
    w, h = max(1, round(img.width * s)), max(1, round(img.height * s))
    return img.resize((w, h), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------- preview


def _curve_qualities(out_ext: str) -> list[int]:
    if out_ext in (".avif", ".heic", ".heif"):
        return [92, 80, 65, 50, 35, 20]  # slower encoders: fewer samples
    if out_ext == ".png":
        return [100, 85, 65, 45, 30]
    return [95, 90, 85, 80, 75, 70, 60, 50, 40, 30, 20, 10]


def _interp(curve: list[tuple[int, int]], q: float) -> float:
    pts = sorted(curve)
    if q <= pts[0][0]:
        return pts[0][1]
    for (q0, b0), (q1, b1) in zip(pts, pts[1:]):
        if q <= q1:
            return b0 + (b1 - b0) * (q - q0) / max(1, q1 - q0)
    return pts[-1][1]


def estimate(path: Path, out_ext: str) -> dict:
    notes = Notes()
    out_ext = out_ext.lower()
    img = _source_image(path, out_ext, notes)
    W, H = img.size
    p = min(1.0, PROXY_SIDE / max(W, H))
    proxy = _scaled(img, p)
    curve = [(q, len(encode(proxy, out_ext, q))) for q in _curve_qualities(out_ext)]
    full_area = W * H
    proxy_area = proxy.width * proxy.height

    def raw_est(q: float, s: float) -> float:
        # bytes grow slightly slower than pixel count
        return _interp(curve, q) * ((full_area * s * s) / proxy_area) ** 0.9

    # The small copy hides fine detail and noise, so it compresses better than the
    # real picture. One real measurement corrects the prediction (about 0.3 s).
    factor = 1.0
    if p < 0.999:
        cal_s = 1.0 if out_ext in (".jpg", ".jpeg", ".webp", ".png") else 0.5
        cal_q = 75 if out_ext != ".png" else 85
        actual = len(encode(_scaled(img, cal_s), out_ext, cal_q))
        factor = max(0.5, min(4.0, actual / max(1.0, raw_est(cal_q, cal_s))))

    def est(q: float, s: float) -> float:
        # Full correction at full size, fading to none at the small copy's size
        # (shrinking averages the noise away, just like the small copy did).
        if p >= 0.999 or s <= p:
            return raw_est(q, s)
        import math

        weight = math.log(s / p) / math.log(1 / p)
        return raw_est(q, s) * factor ** weight

    qs = [q for q, _ in curve]
    q_hi, q_lo = max(qs), min(qs)

    def plan(limit: int) -> dict | None:
        budget = limit * 0.95
        for s in SCALES:
            if est(QUALITY_FLOOR, s) <= budget or s == SCALES[-1]:
                lo, hi = (QUALITY_FLOOR if s > SCALES[-1] else q_lo), q_hi
                if est(lo, s) > budget:
                    if s == SCALES[-1]:
                        return None
                    continue
                for _ in range(20):
                    mid = (lo + hi) / 2
                    if est(mid, s) <= budget:
                        lo = mid
                    else:
                        hi = mid
                return {"kb": limit // KB, "quality": int(lo), "width": round(W * s), "height": round(H * s),
                        "bytes": int(est(lo, s)), "resized": s < 0.999}
        return None

    size = path.stat().st_size
    targets = []
    for kb in (20, 50, 100, 200, 500, 1000):
        if kb * KB >= size and out_ext == path.suffix.lower():
            continue  # already under this size
        t = plan(kb * KB)
        if t is not None and t["quality"] >= 95 and not t["resized"] and kb * KB > size:
            continue  # pointless: bigger than the original would be
        targets.append(t if t is not None else {"kb": kb, "impossible": True})
    slider = [(q, int(est(q, 1.0))) for q in range(10, 101, 5)]
    return {"ok": True, "width": W, "height": H, "bytes": size, "ext": out_ext, "targets": targets,
            "quality_curve": slider, "exact": p >= 0.999}


# ---------------------------------------------------------------- compression


def _psnr(a: Image.Image, b: Image.Image) -> float:
    import numpy as np

    if a.size != b.size:
        b = b.resize(a.size)
    mode = "RGBA" if "A" in a.mode else "RGB"
    x = np.asarray(a.convert(mode), dtype=np.float64)
    y = np.asarray(b.convert(mode), dtype=np.float64)
    mse = float(np.mean((x - y) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def _best_under(img: Image.Image, out_ext: str, limit: int, start_scale: float = 1.0) -> tuple[bytes, int, float]:
    """Highest quality (then largest size) whose encoding is <= limit bytes."""
    qmax = 95 if out_ext != ".png" else 100
    scales = [s for s in SCALES if s <= start_scale + 1e-9] or [SCALES[-1]]
    for i, s in enumerate(scales):
        im = _scaled(img, s)
        floor = QUALITY_FLOOR if i < len(scales) - 1 else 5
        data = encode(im, out_ext, floor)
        if len(data) > limit:
            continue
        best, best_q = data, floor
        lo, hi = floor + 1, qmax
        while lo <= hi:  # binary search on quality
            mid = (lo + hi) // 2
            d = encode(im, out_ext, mid)
            if len(d) <= limit:
                best, best_q, lo = d, mid, mid + 1
            else:
                hi = mid - 1
        return best, best_q, s
    raise ConversionError(f"This picture can't be made smaller than {human(limit)} while staying recognizable. "
                          "Try a bigger size limit.")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    src = sources[0]
    out_ext = out.suffix.lower()
    notes = Notes()
    img = _source_image(src, out_ext, notes)
    original = src.stat().st_size
    mode = opts.get("mode", "size")
    if mode == "quality":
        q = int(opts.get("quality", 80))
        data, scale = encode(img, out_ext, q), 1.0
        limit = None
    else:
        limit = int(opts.get("target_kb", 100)) * KB
        if original <= limit and out_ext == src.suffix.lower():
            raise ConversionError(f"This image is already under {human(limit)} ({human(original)}).")
        # Start near the predicted scale so big photos don't need many full-size encodes.
        guess = 1.0
        try:
            pre = estimate(src, out_ext)
            match = next((t for t in pre["targets"] if t.get("kb") == limit // KB and not t.get("impossible")), None)
            if match:
                guess = min(1.0, (match["width"] / img.width) * 1.25)
        except Exception:
            pass
        data, q, scale = _best_under(img, out_ext, limit, guess)
        if guess < 1.0 and scale == guess and q > 80:
            # The guess may have been too cautious: try one size up.
            try:
                d2, q2, s2 = _best_under(img, out_ext, limit, min(1.0, guess * 1.2))
                if s2 > scale:
                    data, q, scale = d2, q2, s2
            except ConversionError:
                pass
    with open(long_path(out), "wb") as fh:
        fh.write(data)

    # ---- verify
    try:
        with Image.open(long_path(out)) as check:
            check.load()
            got = check.copy()
    except Exception as e:
        raise VerificationError(f"the compressed image can't be opened: {e}") from e
    expected = _scaled(img, scale)
    if got.size != expected.size:
        raise VerificationError("the compressed image has the wrong size")
    if limit is not None and len(data) > limit:
        raise VerificationError(f"the file is {human(len(data))}, over the {human(limit)} limit")
    if _psnr(expected, got) < 16:
        raise VerificationError("the compressed image looks broken")

    saved = 100 * (1 - len(data) / max(1, original))
    q_used = q if limit is not None else int(opts.get("quality", 80))
    line = f"{human(original)} → {human(len(data))}"
    line += f" ({min(99, int(saved))}% smaller)." if saved > 0 else " (not smaller; the original was already compact)."
    line += f" Quality {q_used}%"
    line += f", resized to {got.width}x{got.height}." if scale < 0.999 else "."
    result = [line, "Camera details removed (smaller and more private); colors converted to standard sRGB."]
    return result + [n for n in notes if "Rotation" not in n]
