"""Writes the winget manifests for a published release (to submit to microsoft/winget-pkgs).

    python tools/winget_manifest.py 1.13.0

Reads the installer's SHA-256 from the GitHub release (via the `gh` command) and writes
packaging/winget/manifests/s/Syedtaj7/Deskvert/<version>/ (the folder layout winget-pkgs uses).
Submitting is a separate, manual step: see docs/LAUNCH.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "syedtaj7/DeskVert"
ID = "Syedtaj7.Deskvert"
SCHEMA = "1.9.0"


def release_info(version: str) -> tuple[str, str, str]:
    """(installer url, SHA-256 in capitals, release date YYYY-MM-DD)."""
    out = subprocess.run(["gh", "release", "view", f"v{version}", "--repo", REPO, "--json", "assets,publishedAt"],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    setup = next(a for a in data["assets"] if a["name"] == f"Deskvert-Setup-{version}.exe")
    digest = (setup.get("digest") or "").removeprefix("sha256:")
    if len(digest) != 64:
        raise SystemExit("GitHub didn't give a SHA-256 for the installer; download it and use Get-FileHash.")
    return setup["url"], digest.upper(), data["publishedAt"][:10]


def write(version: str) -> Path:
    url, sha, date = release_info(version)
    folder = ROOT / "packaging" / "winget" / "manifests" / "s" / "Syedtaj7" / "Deskvert" / version
    folder.mkdir(parents=True, exist_ok=True)
    head = f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.{{kind}}.{SCHEMA}.schema.json\n\n"
    files = {
        f"{ID}.yaml": ("version", f"""PackageIdentifier: {ID}
PackageVersion: {version}
DefaultLocale: en-US
ManifestType: version
ManifestVersion: {SCHEMA}
"""),
        f"{ID}.installer.yaml": ("installer", f"""PackageIdentifier: {ID}
PackageVersion: {version}
InstallerType: inno
Scope: user
InstallModes:
- interactive
- silent
- silentWithProgress
UpgradeBehavior: install
ReleaseDate: {date}
Installers:
- Architecture: x64
  InstallerUrl: {url}
  InstallerSha256: {sha}
ManifestType: installer
ManifestVersion: {SCHEMA}
"""),
        f"{ID}.locale.en-US.yaml": ("defaultLocale", f"""PackageIdentifier: {ID}
PackageVersion: {version}
PackageLocale: en-US
Publisher: Deskvert
PublisherUrl: https://github.com/syedtaj7
PublisherSupportUrl: https://github.com/{REPO}/issues
PrivacyUrl: https://github.com/{REPO}/blob/main/PRIVACY.md
PackageName: Deskvert
PackageUrl: https://github.com/{REPO}
License: AGPL-3.0-only
LicenseUrl: https://github.com/{REPO}/blob/main/LICENSE
ShortDescription: Select files, tap Ctrl + Shift, pick a format. A light file converter that lives in the tray.
Description: |-
  Deskvert converts files right where they are. Select files in File Explorer, tap Ctrl + Shift, and pick a
  format or a tool from the picker that opens at your mouse. Pictures, PDFs, Office documents, e-mails, sound,
  data, e-books and more: 197 kinds of files in 171 ways. Works straight from the browser too: drag a picture
  or a table in, or save a page as a PDF. Every result is checked before it's saved, originals are never
  changed, and nothing is uploaded.
Moniker: deskvert
Tags:
- converter
- file-converter
- image-converter
- pdf
- compress
- ocr
- heic
- webp
- tray
ReleaseNotesUrl: https://github.com/{REPO}/releases/tag/v{version}
ManifestType: defaultLocale
ManifestVersion: {SCHEMA}
"""),
    }
    for name, (kind, body) in files.items():
        (folder / name).write_text(head.replace("{kind}", kind) + body, encoding="utf-8", newline="\n")
    return folder


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(write(sys.argv[1].lstrip("v")))
