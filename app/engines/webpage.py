"""A web page, saved: as a PDF, or as one long picture of the whole page.

The page is opened by the Microsoft Edge (or Google Chrome) already on this PC, in a
private copy with its own empty profile: your browsing data, sign-ins and history are
never touched, and pages that need a sign-in come out signed-out. Nothing new is
downloaded. The browser runs inside Deskvert's processor limit and is closed after.

Links come from .url files (Windows internet shortcuts): what a link dragged out of a
browser becomes, and what Deskvert saves when you tap Ctrl+Shift on a browser window.
"""

from __future__ import annotations

import configparser
import os
import subprocess
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

CREATE_NO_WINDOW = 0x08000000
PAGE_WIDTH = 1280
MAX_HEIGHT = 12000


def read_url(path: Path) -> str:
    """The address in a .url internet shortcut."""
    text = Path(long_path(path)).read_text(encoding="utf-8-sig", errors="replace")
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(text)
        url = cp.get("InternetShortcut", "URL", fallback="").strip()
    except configparser.Error:
        url = ""
    if not url:
        raise ConversionError("This shortcut has no web address in it.")
    return url


def write_url(path: Path, url: str) -> None:
    Path(long_path(path)).write_text(f"[InternetShortcut]\r\nURL={url}\r\n", encoding="utf-8")


def find_browser() -> str | None:
    """Edge first (it's on every Windows PC), then Chrome."""
    import winreg

    for exe in ("msedge.exe", "chrome.exe"):
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                    path = winreg.QueryValue(k, None)
                if path and os.path.isfile(path.strip('"')):
                    return path.strip('"')
            except OSError:
                pass
    for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""),
                 os.environ.get("LOCALAPPDATA", "")):
        for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
            p = os.path.join(base, rel)
            if base and os.path.isfile(p):
                return p
    return None


def _run(args: list[str], out: Path, timeout: int = 90) -> None:
    exe = find_browser()
    if exe is None:
        raise ConversionError("Saving a page needs Microsoft Edge or Google Chrome, and neither is installed.")
    profile = out.parent / "browser-profile"  # a private, empty profile: your own browser data is never used
    profile.mkdir(exist_ok=True)
    cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           "--disable-extensions", "--disable-sync", "--mute-audio", "--hide-scrollbars",
           f"--user-data-dir={profile}", "--run-all-compositor-stages-before-draw",
           "--virtual-time-budget=10000", *args]
    try:
        subprocess.run(cmd, timeout=timeout, capture_output=True, creationflags=CREATE_NO_WINDOW, check=False)
    except subprocess.TimeoutExpired as e:
        raise ConversionError("The page took too long to load (over 90 seconds).") from e
    if not out.exists() or out.stat().st_size == 0:
        raise ConversionError("The browser couldn't save that page. Check the address and your internet "
                              "connection.")


def to_pdf(url: str, out: Path, notes: list[str]) -> None:
    import pymupdf

    _run([f"--print-to-pdf={out}", "--no-pdf-header-footer", url], out)
    try:
        with pymupdf.open(long_path(out)) as d:
            pages = d.page_count
            text = "".join(p.get_text() for p in d)
            pictures = sum(len(p.get_images()) for p in d)
    except Exception as e:  # noqa: BLE001
        raise VerificationError(f"the PDF can't be opened ({e})") from e
    if pages < 1 or (not text.strip() and not pictures):
        raise VerificationError("the page came out empty")
    notes.append(f"Checked: {pages} page{'s' if pages != 1 else ''}, text kept as text (searchable, sharp).")


def to_picture(url: str, out: Path, notes: list[str], width: int = PAGE_WIDTH, tall: int = MAX_HEIGHT,
               scale: int = 1) -> None:
    import numpy as np
    from PIL import Image

    raw = out.with_name("screen.png")
    _run([f"--screenshot={raw}", f"--window-size={width},{tall}",
          f"--force-device-scale-factor={scale}", url], raw)
    with Image.open(long_path(raw)) as im:
        rgb = np.asarray(im.convert("RGB"))
    # trim the empty space below the end of the page (the window was made very tall to fit it all)
    last = rgb[-1]
    same = np.all(np.abs(rgb.astype(np.int16) - last.astype(np.int16)) <= 2, axis=(1, 2))
    height = len(same)
    while height > 200 and same[height - 1]:
        height -= 1
    page = rgb[:min(len(same), height + 24)]
    if page.std() < 1:
        raise VerificationError("the page came out blank")
    Image.fromarray(page).save(long_path(out), "PNG", optimize=True)
    with Image.open(long_path(out)) as back:
        back.load()
        if back.size != (page.shape[1], page.shape[0]):
            raise VerificationError("the picture didn't save completely")
    notes.append(f"Checked: the whole page as one picture, {page.shape[1]}×{page.shape[0]} px.")
    if height >= tall * scale - 50:
        notes.append(f"Very long: the first {tall:,} px are included.")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    url = read_url(sources[0])
    if not url.lower().startswith(("http://", "https://")):
        raise ConversionError("Only web pages (http and https addresses) can be saved.")
    notes: list[str] = []
    if fmt == "pdf":
        to_pdf(url, out, notes)
    elif fmt == "png":
        to_picture(url, out, notes)
    else:
        raise ConversionError(f"Unknown page conversion: {fmt}")
    notes.append("Opened in a private, signed-out browser window: pages that need a sign-in show as signed-out.")
    return notes


CLIP_WIDTH = 924  # the clip's text column (860 px) and its margins


def clip(source: Path, out: Path, fmt: str) -> list[str]:
    """A web clip (your selection, saved as a small page) as a PDF or a picture: laid out offline."""
    import shutil

    page = out.with_name("clip.html")  # a plain name in the work folder: nothing odd in the address
    shutil.copyfile(source, page)
    notes: list[str] = []
    if fmt == "pdf":
        to_pdf(page.as_uri(), out, notes)
    elif fmt == "png":
        to_picture(page.as_uri(), out, notes, width=CLIP_WIDTH, tall=3000, scale=2)
    else:
        raise ConversionError(f"Unknown clip conversion: {fmt}")
    return notes
