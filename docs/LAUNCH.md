# Public launch checklist

What's ready, and what needs you (an account, a payment, or a public post).

## Ready

- Releases: every tag is built from this repository by GitHub Actions, with the full test suite on every PR and
  a self-test of the built app. Installs update themselves (with a SHA-256 check).
- In the app: **Report a problem** (names and folders hidden), Reduce motion, undo, low processor use.
- On GitHub: issue forms (`.github/ISSUE_TEMPLATE`), [SECURITY.md](../SECURITY.md), [PRIVACY.md](../PRIVACY.md),
  install notes with system requirements and checksums in the README.
- winget: manifests for the latest release in `packaging/winget/` (validated with `winget validate`).
  For a new release: `python tools/winget_manifest.py <version>`.

## Needs you

### 1. Code signing (the big one): SignPath, free for open source

Unsigned installers make Windows SmartScreen say "Windows protected your PC", and some antivirus tools warn about
unsigned apps. The release workflow is ready for SignPath Foundation's free signing: follow
[SIGNING.md](SIGNING.md) (apply, publish the code signing policy, set up the SignPath project, add four values to
GitHub). Until then releases stay unsigned and work as before.

### 2. Private vulnerability reporting: done (2026-11-14)

Turned on; SECURITY.md points people there.

### 3. A few real-world checks: done (2026-11-14)

- On a PC **without Microsoft Office but with LibreOffice**: convert a DOCX, XLSX and PPTX to PDF.
- **Firefox**: hold Ctrl + Shift and drag a picture, a link and selected text.
- **Two monitors** with different scaling: the drop circle and the result card on the second one.
- **Watch folder** and **WEBP downloads to JPG** with real downloads.

### 4. winget (after signing, ideally)

Submit `packaging/winget/manifests/...` as a pull request to
[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) (or with `wingetcreate submit`). After it's
merged: `winget install Syedtaj7.Deskvert`. Each new release needs a new manifest PR.

### 5. Repository page and website: done (2026-11-14)

Description, topics and social preview image are set. The website is https://deskvert-website.vercel.app,
verified in Google Search Console with its sitemap submitted.

### 6. Announce

Where people look for small Windows tools: r/software, r/Windows11, r/opensource, AlternativeTo, Product Hunt,
Hacker News "Show HN". Drafts are in [LAUNCH-POSTS.md](LAUNCH-POSTS.md); post them once releases are signed.
The 20-second video for posts is `website/assets/media/deskvert-demo.mp4` (made by `tools/make_promo.py`).
