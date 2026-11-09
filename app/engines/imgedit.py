"""Quick picture edits: rotate, flip, grayscale, resize, remove hidden info, stitch.

- rotl / rotr / rot180 / flip: turned the way you see the picture (the camera's
  orientation flag is applied first), saved in the same format.
- gray:   black and white (transparency kept).
- resize: smaller only: half size, or the long side to 1920 / 1280 / 1080 px.
- clean:  removes location, camera and other hidden details. JPG and PNG are
          cleaned without re-encoding (the picture data is copied byte for byte).
- stitch: several pictures, one under the other, in one long image.

Camera details and color profiles are kept unless the edit is "clean". Every
result is opened again and compared with what was expected.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageOps

from ..errors import ConversionError, VerificationError
from ..paths import long_path

EDITABLE = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp", "TIFF": ".tiff"}
RESIZE = {"Half size": 0.5, "1920 px": 1920, "1280 px": 1280, "1080 px": 1080}
ORIENTATION = 0x0112
PRIVATE_TAGS = {0x8825: "location", 0x010F: "camera maker", 0x0110: "camera model", 0x9003: "date taken",
                0x013B: "author", 0xA430: "owner", 0x8298: "copyright", 0x9286: "comment"}


def _open(src: Path) -> Image.Image:
    try:
        im = Image.open(long_path(src))
        im.load()
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"This picture can't be opened ({e}).") from e
    if im.format not in EDITABLE:
        raise ConversionError("This edit works on JPG, PNG, WEBP, BMP and TIFF pictures. Convert it to one of "
                              "those first.")
    return im


def _upright(im: Image.Image) -> Image.Image:
    """As you see it: the camera's orientation flag applied to the pixels."""
    return ImageOps.exif_transpose(im) or im


def _webp_lossless(src: Path) -> bool:
    with open(long_path(src), "rb") as f:
        head = f.read(64)
    return b"VP8L" in head


def _save(im: Image.Image, out: Path, fmt: str, src_im: Image.Image, src: Path, keep_meta: bool = True) -> None:
    kw: dict = {}
    icc = src_im.info.get("icc_profile")
    if icc and fmt != "BMP":
        kw["icc_profile"] = icc
    if keep_meta and fmt in ("JPEG", "WEBP", "PNG", "TIFF"):
        exif = src_im.getexif()
        if exif:
            exif[ORIENTATION] = 1  # the pixels are already upright
            kw["exif"] = exif.tobytes()
    if fmt == "JPEG":
        if im.mode not in ("RGB", "L", "CMYK"):
            im = im.convert("RGB")
        kw.update(quality=95, optimize=True)
    elif fmt == "WEBP":
        kw.update(lossless=True) if _webp_lossless(src) else kw.update(quality=95, method=4)
    elif fmt == "TIFF":
        kw.update(compression="tiff_lzw")
    elif fmt == "BMP" and im.mode not in ("RGB", "L", "P", "1"):
        im = im.convert("RGB")
    im.save(long_path(out), format=fmt, **kw)


def _lossless(fmt: str, src: Path) -> bool:
    return fmt in ("PNG", "BMP", "TIFF") or (fmt == "WEBP" and _webp_lossless(src))


def _verify(out: Path, want: Image.Image, fmt: str, src: Path) -> Image.Image:
    import numpy as np

    try:
        got = Image.open(long_path(out))
        got.load()
    except Exception as e:  # noqa: BLE001
        raise VerificationError(f"the new picture can't be opened: {e}") from e
    if got.size != want.size:
        raise VerificationError(f"the picture is {got.size[0]}×{got.size[1]}, expected {want.size[0]}×{want.size[1]}")
    mode = "RGBA" if "A" in want.getbands() else ("L" if want.mode in ("L", "1") else "RGB")
    a = np.asarray(got.convert(mode), dtype=np.float32)
    b = np.asarray(want.convert(mode), dtype=np.float32)
    if _lossless(fmt, src):
        if not np.array_equal(a, b):
            raise VerificationError("the pixels changed")
    else:
        mse = float(np.mean((a - b) ** 2))
        if mse > 0 and 10 * np.log10(255 ** 2 / mse) < 34:
            raise VerificationError("the picture lost too much quality")
    return got


def _transform(src: Path, out: Path, op: str, opts: dict) -> list[str]:
    im = _open(src)
    fmt = im.format
    up = _upright(im)
    if op == "rotl":
        res, what = up.transpose(Image.Transpose.ROTATE_90), "Turned 90° to the left"
    elif op == "rotr":
        res, what = up.transpose(Image.Transpose.ROTATE_270), "Turned 90° to the right"
    elif op == "rot180":
        res, what = up.transpose(Image.Transpose.ROTATE_180), "Turned upside down"
    elif op == "flip":
        res, what = up.transpose(Image.Transpose.FLIP_LEFT_RIGHT), "Mirrored left to right"
    elif op == "gray":
        alpha = up.getchannel("A") if "A" in up.getbands() else None
        res = ImageOps.grayscale(up)
        if alpha is not None:
            res.putalpha(alpha)
        what = "Black and white"
    elif op == "resize":
        choice = str(opts.get("size", "Half size"))
        if choice not in RESIZE:
            raise ConversionError(f"Unknown size: {choice}")
        w, h = up.size
        k = RESIZE[choice] if choice == "Half size" else RESIZE[choice] / max(w, h)
        if k >= 1:
            raise ConversionError(f"This picture is already {w}×{h} px, smaller than {choice}.")
        size = (max(1, round(w * k)), max(1, round(h * k)))
        # full color for resampling (a palette would band); saved in the same format
        work = up if up.mode in ("RGB", "RGBA", "L", "LA") else up.convert("RGBA" if "A" in up.getbands() else "RGB")
        res = work.resize(size, Image.Resampling.LANCZOS)
        what = f"Resized from {w}×{h} to {size[0]}×{size[1]} px"
    else:
        raise ConversionError(f"Unknown edit: {op}")
    _save(res, out, fmt, im, src)
    _verify(out, res, fmt, src)
    return [f"{what}. Checked: {res.size[0]}×{res.size[1]} px, saved as {EDITABLE[fmt][1:].upper()}."]


# ---------------------------------------------------------------- remove hidden info

def _jpeg_strip(data: bytes) -> bytes:
    """Drop EXIF/XMP (APP1), Photoshop/IPTC (APP13), comments and other app blocks;
    keep JFIF (APP0), the color profile (APP2) and Adobe color info (APP14).
    The compressed picture itself is copied unchanged."""
    if data[:2] != b"\xff\xd8":
        raise ConversionError("This JPG is damaged.")
    out = bytearray(b"\xff\xd8")
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise ConversionError("This JPG is damaged.")
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker == 0xDA:  # start of scan: the rest is the picture
            out += data[i:]
            return bytes(out)
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            out += data[i:i + 2]
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        seg = data[i:i + 2 + length]
        drop = marker == 0xFE or (0xE1 <= marker <= 0xEF and marker not in (0xE2, 0xEE))
        if not drop:
            out += seg
        i += 2 + length
    raise ConversionError("This JPG is damaged.")


def _found(im: Image.Image) -> list[str]:
    exif = im.getexif()
    found = [name for tag, name in PRIVATE_TAGS.items() if tag in exif]
    try:
        gps = exif.get_ifd(0x8825)
        if gps and "location" not in found:
            found.insert(0, "location")
    except Exception:  # noqa: BLE001
        pass
    if im.info.get("xmp") or "XML:com.adobe.xmp" in im.info:
        found.append("XMP details")
    return found


def _clean(src: Path, out: Path) -> list[str]:
    im = _open(src)
    fmt = im.format
    found = _found(im)
    orient = im.getexif().get(ORIENTATION, 1)
    if fmt == "JPEG" and orient in (1, None):
        import numpy as np

        Path(long_path(out)).write_bytes(_jpeg_strip(Path(long_path(src)).read_bytes()))
        how = "The picture data was copied unchanged."
        got = Image.open(long_path(out))
        got.load()
        if got.size != im.size or not np.array_equal(np.asarray(got), np.asarray(im)):
            raise VerificationError("the picture changed while cleaning")
    elif fmt == "PNG":
        clean = _upright(im)
        clean.info = {}
        kw = {"icc_profile": im.info["icc_profile"]} if im.info.get("icc_profile") else {}
        clean.save(long_path(out), format="PNG", **kw)  # no text, EXIF or time chunks
        how = "Saved without the hidden details; every pixel is identical."
        got = _verify(out, clean, fmt, src)
    else:
        clean = _upright(im)
        _save(clean, out, fmt, im, src, keep_meta=False)
        how = "Saved again without the hidden details."
        got = _verify(out, clean, fmt, src)
    left = _found(got)
    if left:
        raise VerificationError(f"still contains: {', '.join(left)}")
    what = ", ".join(found) if found else "no camera or location details were found, but other hidden data"
    return [f"Removed: {what}. {how}"]


# ---------------------------------------------------------------- stitch

def _stitch(sources: list[Path], out: Path) -> list[str]:
    ims = []
    for s in sources:
        im = _open(s)
        ims.append(_upright(im).convert("RGBA" if "A" in im.getbands() else "RGB"))
    width = min(2400, max(i.width for i in ims))
    scaled = [i if i.width == width else i.resize((width, max(1, round(i.height * width / i.width))),
                                                     Image.Resampling.LANCZOS) for i in ims]
    height = sum(i.height for i in scaled)
    jpg = out.suffix.lower() == ".jpg"
    if jpg and height > 65000:
        raise ConversionError("Together these pictures are too tall for one JPG. Select fewer pictures.")
    if height > 120_000:
        raise ConversionError("Together these pictures are too tall for one image. Select fewer pictures.")
    alpha = any(i.mode == "RGBA" for i in scaled) and not jpg
    sheet = Image.new("RGBA" if alpha else "RGB", (width, height), (255, 255, 255, 0) if alpha else (255, 255, 255))
    y = 0
    for i in scaled:
        sheet.paste(i.convert(sheet.mode), (0, y))
        y += i.height
    if jpg:
        sheet.save(long_path(out), format="JPEG", quality=92, optimize=True)
    else:
        sheet.save(long_path(out), format="PNG")
    _verify(out, sheet, "JPEG" if jpg else "PNG", out)
    return [f"Checked: {len(ims)} pictures, one under the other, {width}×{height} px."]


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    if fmt == "stitch":
        if len(sources) < 2:
            raise ConversionError("Select two or more pictures to stitch.")
        return _stitch(sources, out)
    if fmt == "clean":
        return _clean(sources[0], out)
    return _transform(sources[0], out, fmt, opts)

