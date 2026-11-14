"""Deskvert: select files, tap Ctrl + Shift, pick a format. Converted next to the original."""

__version__ = "1.15.0"

# Set this to your GitHub repository ("owner/name") before publishing a release.
GITHUB_REPO = "syedtaj7/DeskVert"


# Where people can support Deskvert (GitHub Sponsors)
SPONSOR_URL = "https://github.com/sponsors/syedtaj7"


def github_url(path: str = "") -> str:
    return f"https://github.com/{GITHUB_REPO}{path}"
