"""Generates sample files covering the tricky cases (EXIF rotation, color
profiles, transparency, 16-bit, CMYK, animation, multi-page, odd names)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageDraw


def _gradient(w: int, h: int) -> Image.Image:
    x = np.linspace(0, 255, w, dtype=np.float64)
    y = np.linspace(0, 255, h, dtype=np.float64)
    r = np.tile(x, (h, 1))
    g = np.tile(y[:, None], (1, w))
    b = (r * 0.5 + g * 0.5)
    arr = np.dstack([r, g, b]).astype(np.uint8)
    im = Image.fromarray(arr, "RGB")
    d = ImageDraw.Draw(im)
    d.rectangle([w // 4, h // 4, w // 2, h // 2], fill=(220, 30, 40))
    d.ellipse([w // 2, h // 3, w - 20, h - 20], fill=(20, 160, 90))
    return im


def _srgb_icc() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _exif(orientation: int = 1) -> bytes:
    ex = Image.Exif()
    ex[0x010F] = "TestCam"  # Make
    ex[0x0110] = "Model X"  # Model
    ex[0x0132] = "2024:05:06 07:08:09"  # DateTime
    ex[0x0112] = orientation
    return ex.tobytes()


def build(folder: Path) -> dict[str, Path]:
    import pillow_heif

    pillow_heif.register_heif_opener()
    folder.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    icc = _srgb_icc()
    base = _gradient(320, 200)

    def p(name):
        out[name] = folder / name
        return out[name]

    base.save(p("photo_rot6.jpg"), "JPEG", quality=95, exif=_exif(6), icc_profile=icc)
    base.save(p("plain.jpg"), "JPEG", quality=90)
    base.convert("CMYK").save(p("cmyk.jpg"), "JPEG", quality=95)

    rgba = base.convert("RGBA")
    a = np.zeros((200, 320), dtype=np.uint8)
    a[:, :] = np.linspace(0, 255, 320, dtype=np.uint8)[None, :]
    a[:50, :] = 0  # fully transparent band with hidden color underneath
    rgba.putalpha(Image.fromarray(a, "L"))
    rgba.save(p("alpha.png"), "PNG", icc_profile=icc, exif=_exif(1))

    pal = base.quantize(64)
    pal.info["transparency"] = 3
    pal.save(p("palette_trns.png"), transparency=3)

    g16 = (np.tile(np.linspace(0, 65535, 300), (120, 1))).astype(np.uint16)
    Image.fromarray(g16).save(p("gray16.png"))
    base.convert("L").save(p("gray.png"))
    base.convert("1").save(p("bilevel.png"))

    frames = []
    for i in range(5):
        f = Image.new("RGBA", (120, 90), (0, 0, 0, 0))
        d = ImageDraw.Draw(f)
        d.ellipse([10 + i * 15, 20, 50 + i * 15, 60], fill=(255, 40 * i, 0, 255))
        frames.append(f)
    frames[0].save(p("anim.gif"), save_all=True, append_images=frames[1:], duration=80, loop=0, disposal=2)
    frames[0].save(p("anim.webp"), save_all=True, append_images=frames[1:], duration=80, loop=0, lossless=True)
    frames[0].save(p("anim.png"), save_all=True, append_images=frames[1:], duration=80, loop=0)

    pages = [_gradient(200, 150), _gradient(200, 150).transpose(Image.Transpose.FLIP_LEFT_RIGHT), Image.new("RGB", (200, 150), "navy")]
    pages[0].save(p("pages.tiff"), save_all=True, append_images=pages[1:], compression="tiff_lzw")

    base.save(p("photo.heic"), "HEIF", quality=90, exif=_exif(1))
    rgba.save(p("alpha.avif"), "AVIF", quality=90)
    base.save(p("plain.bmp"))
    rgba.save(p("icon.ico"), sizes=[(16, 16), (32, 32), (64, 64)])
    rgba.save(p("alpha.tga"))
    rgba.save(p("alpha.webp"), "WEBP", lossless=True, exact=True)
    base.save(p("photo.webp"), "WEBP", quality=90)

    p("drawing.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">'
        '<rect width="200" height="100" rx="12" fill="#6d5ae6"/>'
        '<circle cx="50" cy="50" r="30" fill="#ffd166"/>'
        '<text x="95" y="60" font-size="28" fill="white" font-family="Segoe UI">Hi</text></svg>',
        encoding="utf-8",
    )
    base.save(p("Фото 写真 é.png"))
    base.save(p("tall_portrait.jpg"), "JPEG", quality=93, exif=_exif(8))

    # Broken inputs
    data = (folder / "plain.jpg").read_bytes()
    p("truncated.jpg").write_bytes(data[: len(data) // 3])
    p("empty.png").write_bytes(b"")
    p("not_really.png").write_bytes(b"hello, I am text")
    return out
