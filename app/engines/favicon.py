"""Website icons from a logo or picture: everything a website needs, in one folder.

favicon.ico (16, 32 and 48 px inside), favicon-16x16.png, favicon-32x32.png,
apple-touch-icon.png (180), android-chrome-192x192.png, android-chrome-512x512.png,
site.webmanifest, and "how to use.html" with the lines to paste into a page.
Pictures that aren't square are centred on a transparent square, never stretched.
Every file is opened again and its size checked.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

PNGS = {"favicon-16x16.png": 16, "favicon-32x32.png": 32, "apple-touch-icon.png": 180,
        "android-chrome-192x192.png": 192, "android-chrome-512x512.png": 512}


def _square(src: Path):
    from PIL import Image

    from .image import Notes, _ensure_plugins, load

    _ensure_plugins()  # HEIC, AVIF and friends
    try:
        frames = load(src, Notes(), multi=False).frames
    except ConversionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"This picture can't be opened ({e}).") from e
    im = frames[0].convert("RGBA")
    side = max(im.size)
    if side < 16:
        raise ConversionError("This picture is too small for icons.")
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    return sq


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    from PIL import Image

    if fmt != "set":
        raise ConversionError(f"Unknown icon set: {fmt}")
    src = sources[0]
    sq = _square(src)
    out.mkdir(parents=True, exist_ok=True)
    big = sq.resize((max(512, sq.width), max(512, sq.width)), Image.Resampling.LANCZOS) if sq.width < 512 else sq
    for name, px in PNGS.items():
        big.resize((px, px), Image.Resampling.LANCZOS).save(long_path(out / name), "PNG", optimize=True)
    big.resize((48, 48), Image.Resampling.LANCZOS).save(long_path(out / "favicon.ico"), "ICO",
                                                         sizes=[(16, 16), (32, 32), (48, 48)])
    manifest = {"name": src.stem, "short_name": src.stem[:12], "icons": [
        {"src": "/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"}],
        "theme_color": "#ffffff", "background_color": "#ffffff", "display": "standalone"}
    (out / "site.webmanifest").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "how to use.html").write_text(
        "<!-- Put these files in your website's main folder, and these lines inside <head>: -->\n"
        '<link rel="icon" type="image/x-icon" href="/favicon.ico">\n'
        '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">\n'
        '<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">\n'
        '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">\n'
        '<link rel="manifest" href="/site.webmanifest">\n', encoding="utf-8")
    for name, px in PNGS.items():
        with Image.open(long_path(out / name)) as im:
            if im.size != (px, px):
                raise VerificationError(f"{name} is the wrong size")
    with Image.open(long_path(out / "favicon.ico")) as ico:
        sizes = set(ico.info.get("sizes", set()))
        if not {(16, 16), (32, 32), (48, 48)} <= sizes:
            raise VerificationError("favicon.ico is missing a size")
    notes = ["Checked: favicon.ico (16, 32, 48 px), 5 PNG icons up to 512 px, and site.webmanifest, in a new "
             "folder. “how to use.html” has the lines to paste into your page."]
    if sq.width < 512:
        notes.append(f"The picture is {sq.width} px: the biggest icons are enlarged from it and may look soft.")
    return notes
