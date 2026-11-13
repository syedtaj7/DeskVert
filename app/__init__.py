"""Deskvert: select files, tap Ctrl + Shift, pick a format. Converted next to the original."""

__version__ = "1.14.0"

# Set this to your GitHub repository ("owner/name") before publishing a release.
GITHUB_REPO = "syedtaj7/DeskVert"


def github_url(path: str = "") -> str:
    return f"https://github.com/{GITHUB_REPO}{path}"
