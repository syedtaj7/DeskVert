"""Report a problem: what goes into a GitHub issue, made private first.

Tapshift never sends anything itself. It fills in a new GitHub issue in your browser (you read it,
change it, and post it yourself, or not), and it can copy the same text. Before anything is shown,
your user name and folder paths are replaced (C:\\Users\\you\\... becomes %USERPROFILE%\\...) and
file names in the log are shortened to their type.
"""

from __future__ import annotations

import os
import platform
import re
import urllib.parse
from pathlib import Path

from . import __version__, github_url
from .paths import log_dir

LOG_LINES = 60
MAX_URL = 7000  # browsers and GitHub take long addresses, but not unlimited ones


def scrub(text: str) -> str:
    """Your name and folders out of a piece of text (the log keeps what happened, not where)."""
    home = os.path.expanduser("~")
    user = os.path.basename(home)
    out = text
    for path in sorted({home, home.replace("\\", "/")}, key=len, reverse=True):
        out = re.sub(re.escape(path), "%USERPROFILE%", out, flags=re.I)
    if len(user) >= 3:
        out = re.sub(rf"\b{re.escape(user)}\b", "<user>", out, flags=re.I)
    out = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<e-mail>", out)  # e-mail addresses
    # file names: keep the type ("<file>.pdf"), not the name
    out = re.sub(r"([\\/])[^\\/\r\n'\"<>|:*?]+?(\.[A-Za-z0-9]{1,5})(?=['\"\s,\]\)]|$)", r"\1<file>\2", out)
    return out


def log_tail(lines: int = LOG_LINES) -> str:
    log = log_dir() / "app.log"
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(no log yet)"
    return scrub("\n".join(text.splitlines()[-lines:]))


def system_info() -> str:
    from .catalog import libre_installed, office_installed

    office = [k for k in ("word", "excel", "powerpoint") if office_installed(k)]
    rows = [f"Tapshift {__version__}",
            f"Windows {platform.version()} ({platform.machine()})",
            "Microsoft Office: " + (", ".join(office) if office else "not installed"),
            "LibreOffice: " + ("installed" if libre_installed() else "not installed")]
    return "\n".join(rows)


def issue_body(what: str, include_log: bool = True) -> str:
    parts = ["**What happened**", what.strip() or "(describe what you did and what you expected)", "",
             "**System**", "```", system_info(), "```"]
    if include_log:
        parts += ["", "**Recent log** (names and folders hidden)", "```", log_tail(), "```"]
    return "\n".join(parts)


def issue_url(title: str, body: str) -> str:
    """A new GitHub issue, filled in. Long logs are cut from the top so the address stays usable."""
    base = github_url("/issues/new?")

    def make(b: str) -> str:
        return base + urllib.parse.urlencode({"title": title or "Problem report", "body": b})

    url = make(body)
    lines = body.split("\n")
    try:
        start = lines.index("**Recent log** (names and folders hidden)") + 2  # first line after the fence
    except ValueError:
        start = -1
    while len(url) > MAX_URL and 0 <= start < len(lines) - 2:
        del lines[start]  # the oldest log line goes first
        url = make("\n".join(lines))
    if len(url) > MAX_URL:  # still too long (a very long description): keep what fits
        url = re.sub(r"%[0-9A-Fa-f]?$", "", url[:MAX_URL])  # never end half way through an escape
    return url


def open_log_folder() -> None:
    os.startfile(str(log_dir()))  # noqa: S606 - our own folder


def log_file() -> Path:
    return log_dir() / "app.log"
