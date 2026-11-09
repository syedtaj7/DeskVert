"""Check GitHub for a newer Tapshift, download its installer and start it.

Only runs when you ask (Settings > About > Check for updates, or the tray menu).
What it sends: one request to GitHub's public API for the latest release, and
then (if you choose) the download of that release's installer. No data about
you or your files.

Safety:
- only assets of this project's own GitHub releases are downloaded;
- the file's size and SHA-256 checksum must match what GitHub publishes;
- it must be a Windows program (starts with "MZ") before it is run.
Files downloaded by an app (not a browser) aren't marked as "from the internet",
so the installer runs without the SmartScreen prompt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import GITHUB_REPO, __version__

API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{GITHUB_REPO}/releases/download/"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "Tapshift-updater"}
CHUNK = 64 * 1024


class UpdateError(Exception):
    """A message meant for the user."""


@dataclass
class Asset:
    name: str
    url: str
    size: int
    sha256: str  # "" when GitHub didn't publish one


@dataclass
class Release:
    version: str
    page: str
    notes: list[str]
    setup: Asset | None
    portable: Asset | None


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    return parse_version(latest) > parse_version(current)


def _notes(body: str) -> list[str]:
    """The release's bullet points as plain text (max 5), for the "What's new" lines."""
    bullets: list[str] = []
    current: str | None = None
    for raw in (body or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith(("- ", "* ")):
            if current is not None:
                bullets.append(current)
            current = stripped[2:]
        elif current is not None and raw[:1].isspace() and stripped:
            current += " " + stripped  # a bullet wrapped onto the next line
        else:
            if current is not None:
                bullets.append(current)
            current = None
    if current is not None:
        bullets.append(current)
    out = []
    for line in bullets[:5]:
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)  # **bold**
        line = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", line)  # [text](link)
        line = line.replace("`", "")
        out.append(line if len(line) <= 140 else line[:137].rstrip() + "…")
    return out


def _asset(raw: dict) -> Asset | None:
    url = raw.get("browser_download_url", "")
    if not url.startswith(DOWNLOAD_PREFIX):
        return None  # only this project's own release files
    digest = raw.get("digest") or ""
    return Asset(raw.get("name", ""), url, int(raw.get("size") or 0),
                 digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "")


def fetch_latest(timeout: float = 12) -> Release:
    try:
        with urllib.request.urlopen(urllib.request.Request(API, headers=HEADERS), timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise UpdateError("GitHub is limiting requests right now. Try again in an hour.") from e
        raise UpdateError(f"GitHub answered with an error ({e.code}). Try again later.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError("Couldn't reach GitHub. Check your internet connection and try again.") from e
    except ValueError as e:
        raise UpdateError("GitHub sent an answer Tapshift couldn't read. Try again later.") from e
    version = (data.get("tag_name") or "").lstrip("vV")
    if not version:
        raise UpdateError("No release was found on GitHub.")
    assets = [a for a in (_asset(x) for x in data.get("assets") or []) if a]
    setup = next((a for a in assets if a.name.lower().startswith("tapshift-setup") and a.name.lower().endswith(".exe")),
                 None)
    portable = next((a for a in assets if a.name.lower().endswith("-portable.zip")), None)
    return Release(version, data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest",
                   _notes(data.get("body") or ""), setup, portable)


def updates_dir() -> Path:
    from .paths import _dir

    return _dir("LOCALAPPDATA", "updates")


def download(asset: Asset, progress=None, cancelled=None, timeout: float = 30) -> Path:
    """Download to %LOCALAPPDATA%\\Tapshift\\updates, then check size and SHA-256.
    ``progress(done, total)`` is called as bytes arrive; ``cancelled()`` returning True stops it."""
    folder = updates_dir()
    for old in folder.glob("*"):  # keep only the one we're fetching
        try:
            old.unlink()
        except OSError:
            pass
    final = folder / asset.name
    part = folder / (asset.name + ".part")
    h = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(urllib.request.Request(asset.url, headers=HEADERS), timeout=timeout) as r, \
                open(part, "wb") as fh:
            total = int(r.headers.get("Content-Length") or asset.size or 0)
            while True:
                if cancelled and cancelled():
                    raise UpdateError("Download cancelled.")
                chunk = r.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        part.unlink(missing_ok=True)
        raise UpdateError("The download stopped. Check your internet connection and try again.") from e
    if asset.size and done != asset.size:
        part.unlink(missing_ok=True)
        raise UpdateError("The download was incomplete. Try again.")
    if asset.sha256 and h.hexdigest() != asset.sha256:
        part.unlink(missing_ok=True)
        raise UpdateError("The downloaded file didn't match GitHub's checksum, so it was deleted. Try again.")
    with open(part, "rb") as fh:
        if fh.read(2) != b"MZ":
            part.unlink(missing_ok=True)
            raise UpdateError("The download isn't a Windows installer, so it was deleted.")
    os.replace(part, final)
    return final


def launch_installer(path: Path) -> None:
    """Run the installer quietly (a small progress window, no questions). It closes
    Tapshift, installs over it, and starts the new version (the /RELAUNCH switch)."""
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH"],
                     close_fds=True, creationflags=0x00000008)  # DETACHED_PROCESS
