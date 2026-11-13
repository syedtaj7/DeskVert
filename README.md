<div align="center">

<a href="https://github.com/syedtaj7/TapShift/releases/latest"><img src="docs/readme/hero.svg" width="100%" alt="Tapshift: select a file, tap Ctrl + Shift, pick a format"></a>

<br>

<a href="https://github.com/syedtaj7/TapShift/releases/latest"><img src="https://img.shields.io/badge/Download_for_Windows-34BE84?style=for-the-badge&logo=windows11&logoColor=121214&labelColor=34BE84" height="44" alt="Download for Windows"></a>

<a href="https://github.com/syedtaj7/TapShift/releases/latest"><img src="https://img.shields.io/github/v/release/syedtaj7/TapShift?style=flat-square&label=version&color=34BE84&labelColor=1C1C20" alt="Latest version"></a>
<a href="https://github.com/syedtaj7/TapShift/releases"><img src="https://img.shields.io/github/downloads/syedtaj7/TapShift/total?style=flat-square&label=downloads&color=34BE84&labelColor=1C1C20" alt="Downloads"></a>
<img src="https://img.shields.io/badge/Windows-10_%7C_11-34BE84?style=flat-square&labelColor=1C1C20" alt="Windows 10 and 11">
<a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-34BE84?style=flat-square&labelColor=1C1C20" alt="AGPL-3.0"></a>
<a href="https://github.com/syedtaj7/TapShift/actions/workflows/release.yml"><img src="https://img.shields.io/github/actions/workflow/status/syedtaj7/TapShift/release.yml?style=flat-square&label=build&labelColor=1C1C20" alt="Build"></a>

<br><br>

<img src="docs/readme/ticker.svg" width="100%" alt="Examples of what Tapshift does">

**No app to open. No upload. No account.**<br>
Tapshift waits quietly in your tray. Select files, tap <kbd>Ctrl</kbd> + <kbd>Shift</kbd>, pick what you want,<br>
and the new file appears right next to the original, checked and ready.

</div>

<img src="docs/readme/divider.svg" width="100%" alt="">

## ⚡ How it works

<img src="docs/readme/flow.svg" width="100%" alt="Select files, tap Ctrl + Shift, pick a format, saved and verified">

1. **Select** one file or many, in File Explorer or on the Desktop.
2. **Tap** <kbd>Ctrl</kbd> + <kbd>Shift</kbd>: press both, let go. Normal shortcuts like <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>T</kbd> keep working.
3. **Pick** from the orbit: tools circle on one ring, formats on the other. Related tools are grouped into a web: point at **Split** and its choices (in half, every N pages, by ranges, every page) fan out around it. A small card says what each one does and what the new file will be called. Choices that hold more open their own fan further out, like a spider's web: everything is one point away, no menus or search. Right-click for options.
4. **Done.** `photo.heic` becomes `photo.webp` in the same folder. Nothing is ever overwritten.

<img src="docs/readme/divider.svg" width="100%" alt="">

## 🌐 Straight from your browser

**New in 1.12.** Edge, Chrome, Brave, Firefox, Opera: nothing to install in the browser. Hold <kbd>Ctrl</kbd> + <kbd>Shift</kbd> while you drag anything out of a page, or tap it on a browser window.

| You do | You get |
|---|---|
| **Drag a picture** with <kbd>Ctrl</kbd> + <kbd>Shift</kbd> held, drop it on the circle | The picker for that picture: JPG, PNG, PDF, compress, crop… Always the **biggest size the page offers**, not the small preview |
| **Select some text** on a page, tap <kbd>Ctrl</kbd> + <kbd>Shift</kbd> | Choices made for a selection: a clean **PDF**, Word, Markdown, plain text or a picture of it, with a line saying where it came from |
| **Select a table** the same way | **Excel**, one sheet per table (merged cells spread out, numbers as numbers), or CSV |
| **Tap** <kbd>Ctrl</kbd> + <kbd>Shift</kbd> on a browser window with nothing selected | The page as a **PDF** or **one long picture** (made by the Edge or Chrome already on your PC), **just the article** as a clean PDF (no ads, menus or cookie banners), **every picture** on the page in one folder, or a **QR code** of its address |
| **Drag a link** in | A **QR code** that's read back before saving, so it always scans |
| **Drag a Google Drive, Docs, Dropbox or OneDrive share link** | The **file itself**, with its real name (Docs, Sheets and Slides come as Word, Excel and PowerPoint) |
| **Win + Shift + S**, then tap <kbd>Ctrl</kbd> + <kbd>Shift</kbd> | Your snip (or any copied picture) in the picker: save it as PNG, JPG, PDF, read its text… |
| Pick **Website icons** on a logo | favicon.ico, the PNG sizes phones use, a web manifest, and the lines to paste into your site |
| Turn on **WEBP downloads to JPG** (Settings) | Pictures you download as WEBP or AVIF get a JPG copy next to them, by themselves |

To read a selection, Tapshift copies it and then puts your clipboard back exactly as it was. Everything lands in **Downloads\Tapshift**, never overwriting anything. Videos on sites like YouTube are streams: dragging one gives its thumbnail, and Tapshift doesn't download streaming video.

<img src="docs/readme/divider.svg" width="100%" alt="">

## 🧰 Everyday tools

<img src="docs/readme/tools.svg" width="100%" alt="Compress images, PDF toolkit, OCR, zip and extract, data files, Markdown">

| Tool | What you get |
|---|---|
| 🗜️ **Compress images** | Pick **under 20 KB, 50 KB, 100 KB, 200 KB, 500 KB or 1 MB**, or drag a quality slider. Every choice shows the quality % and the new size *before* you click. The limit is always respected. **For forms:** exact-size JPGs for applications: photo (200×230, 20–50 KB), passport photo (35×45 mm), signature (140×60, empty paper trimmed), or your own width × height × KB. |
| 📄 **PDF toolkit** | **Sign** with your name in handwriting or a picture of your signature · **Compress** to a size limit (under 200 KB, 500 KB, 1 MB, 2 MB, or your own) at the best quality that fits, or by level · **Lock / Unlock** with an AES-256 password · **Split** in half, every N pages, by ranges or every page · keep or remove **Pages** (`1-3, 7, 10-end`) · **Reorder** or **Reverse** · **Rotate** · page **Numbers** · **2, 4, 6 or 9 pages per sheet** · **Watermark** · **Flatten** forms · **Clean info** (author, dates, hidden data) · **Grayscale** · save the **Pictures** inside · **Merge** · pictures and PDFs **combined** into one PDF · → **Markdown**, **HTML**, **EPUB**, **TIFF**, **one long image**, **CBZ** |
| 🔍 **Read text (OCR)** | Text from photos and scanned PDFs, or a **searchable PDF** that looks exactly like the scan. Uses the engine built into Windows, so nothing extra is downloaded. Sideways scans are turned upright automatically. |
| 📦 **Zip & extract** | ZIP the selected files · extract **ZIP, 7Z, RAR, TAR, GZ, BZ2, XZ, ZST, CAB, ISO** · repack any archive as a ZIP |
| 📊 **Data files** | CSV / TSV / Excel / JSON / **YAML** / **TOML** / **XML** / **JSON Lines** into each other · Excel sheets → CSV each, without Excel · **vCard contacts** ↔ CSV / Excel · **tidy** or **minify** JSON. Values like `007`, `1.50` and long IDs stay exactly as written. |
| 🗺️ **Maps** | **GeoJSON, KML, KMZ, GPX** into each other, to CSV or Excel, and a CSV with coordinates → map file |
| 🧊 **3D models** | **STL, OBJ, PLY, 3MF, GLB/glTF** into each other, plus a shaded **picture** of the model |
| 📐 **CAD** | **DXF** → **PDF**, **SVG** or **PNG**, without AutoCAD |
| 🔤 **Fonts** | **TTF / OTF ↔ WOFF**, → **EOT** |
| 🎵 **Sound & video** | **MP3, M4A, WAV, FLAC, WMA** (and AAC, OGG, Opus, AIFF in) into each other · **Trim** a recording to the part you need · the **sound from a video** (MP4, MOV, MKV, AVI, WMV...) · a **still picture** of any moment of a video, or a **frames sheet** of nine moments. Uses Windows' own converter and decoder, so nothing is downloaded and it stays light. Videos themselves aren't re-encoded. |
| ✉️ **Mail & saved pages** | **EML** and **Outlook .msg** e-mails (no Outlook needed) and **MHTML** pages → **PDF**, **HTML**, **TXT**, **Markdown**; e-mail attachments → **ZIP** |
| 📝 **Markdown** | → **PDF** (A4, with headings, tables, code and images) · **HTML** · **Word** |
| 🖼️ **Picture edits** | **Turn** left, right or upside down · **Mirror** · **Grayscale** · **Resize** (half, 1920, 1280 or 1080 px) · **Clean info**: removes location, camera and date before you share (JPG and PNG aren't re-encoded) · **Long image**: several pictures stitched one under the other |
| 📚 **E-books** | **EPUB, MOBI, FB2**, comics (**CBZ, CBR, CB7, CBT**) and XPS → **PDF**, **EPUB** or **TXT** · Markdown, HTML, TXT and PDF → **EPUB** · PDF → **CBZ**. No e-book software needed. |
| 💬 **Subtitles** | **SRT, WebVTT, ASS/SSA, SAMI, TTML, LRC, MicroDVD** into each other, saved as UTF-8 |

<img src="docs/readme/divider.svg" width="100%" alt="">

## 🔁 Every format

<img src="docs/readme/formats.svg" width="100%" alt="Supported formats">

<details>
<summary><b>See what converts to what</b></summary>
<br>

| You select | You can make |
|---|---|
| **Images:** JPG, PNG, WEBP, HEIC, AVIF, GIF, BMP, TIFF, ICO, TGA, PSD, SVG, camera RAW | JPG, PNG, WEBP, HEIC, AVIF, GIF, BMP, TIFF, ICO, TGA, PDF, several images in one PDF · Compress · Crop to a shape · Watermark · Passport photo sheet · Read text |
| **PDF** | PNG or JPG pages, text, Split, Merge · Compress · Lock / Unlock · Pages · Rotate · Numbers · Watermark · Tables to Excel · Remove blank pages · Read text · Searchable PDF |
| **Word:** DOCX, DOC, ODT, RTF, TXT, HTML | PDF, DOCX, ODT, RTF, TXT, DOC; and without Office: DOCX / ODT to TXT, Markdown, HTML |
| **Apple:** Pages, Numbers, Keynote | The preview saved inside, as PDF or JPG |
| **Excel:** XLSX, XLS, ODS | PDF, XLSX, CSV (first sheet), ODS, XLS |
| **PowerPoint:** PPTX, PPT, ODP | PDF, PPTX, ODP, PPT, PNG or JPG slides |
| **Data:** CSV, TSV, JSON | XLSX, JSON, CSV, tidy or minified JSON |
| **Databases (SQLite), settings (INI, .env, .properties), calendars (.ics)** | Excel or CSV per table; JSON or YAML; events as a table |
| **Markdown, Jupyter notebooks** | PDF, HTML, DOCX; notebooks to HTML (with charts), Markdown, Python |
| **Archives:** ZIP, 7Z, RAR, TAR, GZ, BZ2, XZ, ZST, CAB, ISO | Extract into a new folder, or repack as ZIP |
| **Audio, video** | Into each other, Trim; a still picture or a frames sheet from a video; its sound |
| **E-mails:** EML, Outlook MSG | PDF, HTML, TXT, Markdown, attachments as a ZIP |
| **Any files** | ZIP the selection · SHA-256 checksum · **Rename** many at once (tidy copies by date or number) |

- **Office documents** are converted by your installed Microsoft Office, so they look exactly as they do in Office. Office opens hidden, read-only and with macros off, and your Office settings are never changed. **No Office?** The free **LibreOffice** is used instead when it's installed (in a private profile of its own).
- **Photos** keep their rotation, camera details (EXIF), GPS and color profile. Lossless formats are checked pixel for pixel.
- **Videos** are never re-encoded (that's heavy work): Tapshift takes their sound or a still picture, through Windows' own decoder.

</details>

<img src="docs/readme/divider.svg" width="100%" alt="">

## 🛡️ Safe by design

<img src="docs/readme/safety.svg" width="100%" alt="Built in a private folder, verified, then saved next to the original">

- **Your original is never touched.** Every result is a new file, such as `report (compressed).pdf`, and nothing is overwritten.
- **Every result is checked before you see it.** The new file is opened again and compared with the original: pixels, pages, words, every spreadsheet cell. If anything is off, it's thrown away and you're told why, in plain words.
- **Private.** Everything happens on your PC. No uploads, no account, no tracking.
- **Crash-proof.** Conversions run in separate worker processes, so a damaged file can't take Tapshift down.

<img src="docs/readme/divider.svg" width="100%" alt="">

## 🍃 Light on your laptop

<img src="docs/readme/cpu.svg" width="100%" alt="CPU use stays under a hard cap">

Built for low-end laptops. Tapshift uses **no CPU while idle**. Every conversion runs under a **hard CPU limit that Windows itself enforces** (15%, 25% or 50%, your choice), at the lowest priority and in efficiency mode, so your laptop stays cool and quiet while you keep working.

<img src="docs/readme/divider.svg" width="100%" alt="">

## 📸 See it

<table>
<tr>
<td width="50%"><img src="docs/images/picker.png" alt="The Orbit picker with its side card"><br><sub><b>The picker</b>: point at an option to see what it does</sub></td>
<td width="50%"><img src="docs/images/welcome.png" alt="Welcome tour"><br><sub><b>Welcome tour</b>: a minute to get going</sub></td>
</tr>
<tr>
<td><img src="docs/images/guide.png" alt="How-to-use guide"><br><sub><b>Built-in guide</b> from the tray</sub></td>
<td><img src="docs/images/settings.png" alt="Settings"><br><sub><b>Settings</b>: shortcut, quality, CPU limit, look</sub></td>
</tr>
</table>

<img src="docs/readme/divider.svg" width="100%" alt="">

## 📥 Install

1. Download **`Tapshift-Setup-x.y.z.exe`** from the [latest release](https://github.com/syedtaj7/TapShift/releases/latest). No admin rights needed.<br>
   Prefer not to install? Get **`Tapshift-x.y.z-portable.zip`**, unzip it anywhere and run `Tapshift.exe`.
2. A short welcome tour shows you around.
3. Select a file, tap <kbd>Ctrl</kbd> + <kbd>Shift</kbd>, pick a format. That's it.

> [!NOTE]
> **"Windows protected your PC"?** Windows SmartScreen shows this for new apps that aren't widely downloaded yet. Click **More info → Run anyway**. Tapshift is open source: every release is built from this repository by GitHub Actions, and you can read every line.

### Update

Tapshift lets you know when a new version is out (it asks GitHub every few hours; turn it off in
**Settings → General → Tell me about updates**). Click **Update**, or use **Settings → About → Check for updates**
(or the tray menu). If there's a new version, Tapshift shows what's new, downloads it with a progress bar, checks it against GitHub's checksum, then installs it and restarts. The portable zip links to the download page instead.

### Uninstall

Any of these works, and each removes everything (app, settings, logs):
- **Start menu → Uninstall Tapshift**
- **Tray icon → Uninstall Tapshift…**
- **Tapshift Settings → About → Uninstall**
- **Windows Settings → Apps → Installed apps → Tapshift → Uninstall**

<img src="docs/readme/divider.svg" width="100%" alt="">

## ⌨️ Using it

| Action | How |
|---|---|
| Convert | Select files, tap <kbd>Ctrl</kbd> + <kbd>Shift</kbd>, click a format |
| Options (quality, pages, password…) | Right-click an option in the picker; tools ask when you click them |
| Every format | Point at a group: its choices fan out, and groups inside open fans of their own |
| Close the picker | <kbd>Esc</kbd>, click elsewhere, or tap the shortcut again |
| Copied files | If nothing is selected, files you copied with <kbd>Ctrl</kbd> + <kbd>C</kbd> are used |
| Watch folders | Settings → General → **Watch folders**: files you put in a chosen folder are converted by themselves (PDF, JPG, Compress...), into a "Converted" folder inside |
| Report a problem | Tray menu → **Report a problem**: you see everything first (names and folders hidden), then GitHub opens in your browser to post it. Tapshift sends nothing itself |
| Less motion | Settings → General → **Reduce motion**: still pictures instead of animations |
| Repeat the last action | Tap <kbd>Ctrl</kbd> + <kbd>Shift</kbd> twice, quickly |
| Convert from anywhere | While dragging a picture, link, table, text or file (from a browser, an e-mail, a chat...), hold <kbd>Ctrl</kbd> + <kbd>Shift</kbd> and drop it on the circle that appears |
| Save a web page | Tap <kbd>Ctrl</kbd> + <kbd>Shift</kbd> while a browser window is in front: PDF, one long picture, or a QR code |
| Convert a screenshot | Copy or snip a picture, then tap <kbd>Ctrl</kbd> + <kbd>Shift</kbd> anywhere |
| See it all | Tray icon → **Welcome tour**: the live picker, every format, and every conversion acted out |
| Many kinds of files at once | Select them all: each kind gets its own branch ("2 pictures", "1 PDF"), plus **Combine** and **ZIP** for everything |
| Right-click menu | Right-click files → **Convert with Tapshift** (Windows 11: Show more options) |
| Undo | Click **Undo** on the Saved card: the new files go to the Recycle Bin |
| Your presets and favourites | Settings → **Customize**: e.g. *WhatsApp photo* or *College PDF under 300 KB*, pinned closest to the centre. Recently used actions move there by themselves |
| Guide, settings, recent files | Right-click the Tapshift icon in the tray |

<details>
<summary><b>FAQ</b></summary>
<br>

**Ctrl + Shift switches my keyboard layout.** Choose <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>Space</kbd> in Settings → Shortcut &amp; look.

**Do I need Microsoft Office?** Only for Word, Excel and PowerPoint files (and Markdown → Word), and if you don't have it, the free [LibreOffice](https://www.libreoffice.org) does the same job once it's installed. Everything else works without either.

**Which languages can OCR read?** The languages installed in Windows (Settings → Time & language → Language). Add a language there to read it.

**Can it open password-protected files?** PDFs: yes, use **Unlock** (you need the password). Office files: remove the password in Office first.

**Is anything sent to the internet?** Your files never are: conversions happen on your PC. Tapshift goes online only for what you ask: a picture or shared file you drag in from a web page (only when the browser doesn't hand it over itself), and a page you save with the browser tap, which the Edge or Chrome on your PC opens with a fresh, empty profile (no cookies or sign-ins). Otherwise, the only thing Tapshift asks the internet is GitHub's latest version number (every few hours, unless you turn it off in Settings → General, and when you click **Check for updates**). Only if you choose does it download the installer (checked against GitHub's checksum) and install it.

**Something failed. How do I report it?** Tray menu → **Report a problem** (or **Report** on the red card). It shows exactly what would be shared, with your name and folders hidden, and opens a filled-in GitHub issue in your browser. The full log is in Settings → About → Log folder.

</details>

<img src="docs/readme/divider.svg" width="100%" alt="">

## 🛠️ Build from source

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\pythonw run.pyw                                   # run it
.venv\Scripts\python -m pytest tests -q                          # tests (gentle: 25% CPU cap)
powershell -ExecutionPolicy Bypass -File tools\build_release.ps1 # installer + portable zip
```

Building the installer also needs [Inno Setup 6](https://jrsoftware.org/isinfo.php). Pushing a tag like `v1.2.0` builds and publishes the release with GitHub Actions. `Tapshift.exe --selftest <folder>` runs real conversions in a built copy.

| Folder | What's inside |
|---|---|
| `app/` | The tray app: shortcut, picker, windows |
| `app/engines/` | The converters and tools, each with its own checks |
| `app/ui/` | The animated interface |
| `docs/readme/` | This page's animations (`python docs/readme/make_art.py` regenerates them) |

## 📜 License

Tapshift is free software under the [GNU Affero General Public License v3.0](LICENSE). Use it, share it, change it; if you distribute a modified version, share its source under the same license. It comes with no warranty. Bundled open-source components keep their own licenses; see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

<br>

<img src="docs/readme/footer.svg" width="100%" alt="Tap. Pick. Done.">
