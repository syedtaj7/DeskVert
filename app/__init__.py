"""Tapshift: select files, tap Ctrl + Shift, pick a format. Converted next to the original."""

__version__ = "1.1.1"

# Set this to your GitHub repository ("owner/name") before publishing a release.
GITHUB_REPO = "syedtaj7/TapShift"


def github_url(path: str = "") -> str:
    return f"https://github.com/{GITHUB_REPO}{path}"
