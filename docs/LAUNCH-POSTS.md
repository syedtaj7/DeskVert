# Launch posts (drafts)

Post these once releases are signed, so the first people who try Deskvert don't hit the SmartScreen warning.
Attach the 20-second video wherever video is allowed: `website/assets/media/deskvert-demo.mp4` (also at
https://deskvert-website.vercel.app/assets/media/deskvert-demo.mp4), with `deskvert-demo.jpg` as the picture
where only images are allowed (Product Hunt gallery, AlternativeTo screenshots).

Links used below:
- Website: https://deskvert-website.vercel.app
- Code: https://github.com/syedtaj7/DeskVert

---

## Reddit: r/software, r/Windows11

**Title:** I made a free Windows file converter that opens right at your cursor: select files, tap Ctrl + Shift, pick a format

**Post:**

I got tired of uploading files to random "convert HEIC to JPG" websites, so I built Deskvert.

How it works: select files in Explorer (or drag something out of your browser), tap Ctrl + Shift, and a small picker
opens at your cursor. Pick a format and the result is saved next to the original. That's it.

- Converts 197 kinds of files: photos (including iPhone HEIC), Word/Excel/PowerPoint to PDF, PDF to images or text,
  audio, video, e-books, archives, Outlook .msg and more
- Everyday tools too: compress a photo to a size (for upload forms), crop, read text from a picture (OCR), merge,
  lock or sign a PDF, trim a video
- Everything runs on your PC. Nothing is uploaded; no account, no ads, no analytics
- Light on old laptops, and every change can be undone
- Free and open source (AGPL-3.0)

Download: https://deskvert-website.vercel.app

It's a first public release, so I'd really like to hear what breaks or what's missing.

---

## Reddit: r/opensource

**Title:** Deskvert: an open-source, offline file converter for Windows (PySide6, AGPL-3.0)

**Post:**

Deskvert is a tray app for Windows: select files, tap Ctrl + Shift, pick a format, done. It handles 197 kinds of
files, from HEIC photos and Office documents to audio, video and e-books, and it never uploads anything.

On the open-source side:
- Python + PySide6, built and released only by GitHub Actions from the public repo, with the full test suite on
  every pull request
- Releases are code-signed through SignPath Foundation
- It updates itself, checking each download's SHA-256 before installing
- No telemetry; the one network call (the update check) can be turned off

Code: https://github.com/syedtaj7/DeskVert
Website: https://deskvert-website.vercel.app

Issues and pull requests are welcome, especially new formats and testing on unusual setups.

---

## Hacker News: Show HN

**Title:** Show HN: Deskvert – convert any file on Windows with one tap of Ctrl + Shift

**Text:**

Deskvert is a small, free Windows app: select files, tap Ctrl + Shift, and a picker opens at your cursor with the
formats that make sense for those files. Pick one and the result is saved next to the original.

I built it because converting a file on Windows usually means finding a website and uploading something personal to
it. Deskvert does it all locally: 197 input types (HEIC, Office documents, PDF, audio, video, e-books, archives,
.msg…), plus everyday tools like compressing a photo to a target size, OCR and PDF signing.

It's Python/PySide6, AGPL-3.0, built by GitHub Actions, and kept light enough for old laptops.

https://github.com/syedtaj7/DeskVert

---

## Product Hunt

**Name:** Deskvert
**Tagline (60 characters max):** Convert any file on Windows with one tap of Ctrl + Shift
**Description:** Select files, tap Ctrl + Shift, pick a format. Deskvert converts 197 kinds of files right on your
PC: photos, documents, PDFs, audio, video and more. Nothing is uploaded, and it's free and open source.
**Topics:** Windows, Productivity, Open Source

---

## AlternativeTo

**Name:** Deskvert
**Description:** Free, open-source file converter for Windows. Select files, tap Ctrl + Shift and pick a format from
a picker at your cursor. Converts 197 kinds of files (HEIC, DOCX, XLSX, PDF, MP4, EPUB, MSG and more) entirely
offline, with tools to compress, crop, read text (OCR) and sign PDFs.
**Alternative to:** CloudConvert, iLovePDF, File Converter, Format Factory
**License:** Open source (AGPL-3.0) · **Platform:** Windows
