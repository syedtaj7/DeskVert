"""Batch rename: copies of the selected files with tidy new names, in a new folder.

Your originals keep their names (Tapshift never changes the files you select); delete them yourself
once you're happy with the copies. Names come from a pattern:

    {date}  the day the photo was taken (or the file was last changed): 2026-11-13
    {n}     a running number, padded to the same width (01, 02 ... 12)
    {name}  the original name

Order: by date taken (oldest first), by name (2 before 10), or as selected. Every copy is compared
with its original, byte for byte.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def taken(p: Path) -> datetime.datetime:
    """When a photo was taken (its camera date), otherwise when the file was last changed."""
    try:
        from PIL import Image

        with Image.open(long_path(p)) as im:
            exif = im.getexif()
            raw = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)  # DateTimeOriginal, DateTime
        if raw:
            return datetime.datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:  # noqa: BLE001 - not a picture, or no date inside: the file's own date
        pass
    return datetime.datetime.fromtimestamp(os.path.getmtime(long_path(p)))


def _natural(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def plan(sources: list[Path], pattern: str, order: str, start: int = 1) -> list[tuple[Path, str]]:
    """[(original, new name)] in the chosen order; names are unique and safe for Windows."""
    pattern = (pattern or "").strip() or "{date} {n}"
    if "{n}" not in pattern and "{name}" not in pattern:
        pattern += " {n}"  # without a number or the old name, names would clash
    dates = {p: taken(p) for p in sources} if "{date}" in pattern or order == "Date taken" else {}
    files = list(sources)
    if order == "Date taken":
        files.sort(key=lambda p: (dates[p], _natural(p)))
    elif order == "Name":
        files.sort(key=_natural)
    width = max(2, len(str(start + len(files) - 1)))
    used: set[str] = set()
    out = []
    for i, p in enumerate(files):
        stem = pattern.replace("{n}", str(start + i).zfill(width)).replace("{name}", p.stem)
        if "{date}" in stem:
            stem = stem.replace("{date}", dates[p].strftime("%Y-%m-%d"))
        stem = BAD.sub("_", stem).strip(" .") or f"file {start + i}"
        name, k = stem + p.suffix.lower(), 2
        while name.lower() in used:
            name, k = f"{stem} ({k}){p.suffix.lower()}", k + 1
        used.add(name.lower())
        out.append((p, name))
    return out


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    if fmt != "copies":
        raise ConversionError(f"Unknown rename: {fmt}")
    try:
        start = int(str(opts.get("start", "1")).strip() or 1)
    except ValueError as e:
        raise ConversionError("'Start at' must be a whole number.") from e
    steps = plan(sources, str(opts.get("pattern", "{date} {n}")), str(opts.get("order", "Date taken")), start)
    folder = Path(long_path(out))
    folder.mkdir(parents=True, exist_ok=True)
    for src, name in steps:
        target = folder / name
        shutil.copy2(long_path(src), target)
        a, b = Path(long_path(src)).stat().st_size, target.stat().st_size
        if a != b:
            raise VerificationError(f"the copy of {src.name} is incomplete")
        with open(long_path(src), "rb") as f1, open(target, "rb") as f2:
            while True:
                x, y = f1.read(1 << 20), f2.read(1 << 20)
                if x != y:
                    raise VerificationError(f"the copy of {src.name} differs from the original")
                if not x:
                    break
    first, last = steps[0][1], steps[-1][1]
    return [f"Checked: {len(steps)} cop{'ies' if len(steps) != 1 else 'y'}, each identical to its original "
            f"({first}" + (f" to {last})." if len(steps) > 1 else ")."),
            "Your originals keep their names; delete them yourself once you're happy with the copies."]
