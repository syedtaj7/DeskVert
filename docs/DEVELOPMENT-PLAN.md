# File Formatter — Build Plan

> **Status (2026-11-06):** Phases 0 and 1 are done: the tray app, hotkey, Explorer/Desktop selection, popup and all image formats, with 229 automated conversion checks passing. Microsoft Office is installed, so LibreOffice won't be needed. Phase 2 (audio/video) is built and redesigned to be light. Video is only repackaged (copied, never re-encoded), and every conversion runs under a hard 25% CPU cap. Its light tests pass. Phase 3 (Office documents and PDF) is done: 17 document tests pass, and Office runs hidden, read-only, with macros disabled and under the CPU cap. PDF → Word was dropped because it isn't reliable when Word runs hidden. Next is Phase 4 (archives, data files, fonts, subtitles, e-books).

A small app that runs in the system tray all the time. You select one or more files in File Explorer (or on the Desktop), press the hotkey, a popup shows near your cursor with only the formats that make sense for those files, you pick one, and the converted file is saved **next to the original**. The original is never changed.

---

## 1. How it works for you

1. Select file(s) in Explorer or on the Desktop.
2. Press **Ctrl + Shift + Space** (the shortcut can be changed, see Decision A).
3. A popup opens at the cursor. It looks like the wheel in your screenshot when there are only a few choices and a searchable list when there are many. You can use the mouse or the keyboard (type "webp", then Enter).
4. Some formats show a small options panel, such as JPG quality, PDF page range or video resolution. Each one starts with the safest, highest-quality setting.
5. A notification shows progress, then "Saved photo.webp". Click it to open the folder.

Other ways to start a conversion:
- Right-click a file and choose **"Convert with File Formatter"**. This helps when the hotkey can't see a selection.
- If nothing is selected, the app uses files you copied with Ctrl+C.
- A tray menu with Settings, recent conversions, Pause and Quit.

---

## 2. Protecting your files (the most important part)

| Rule | What it means |
|---|---|
| **The original is never touched** | The app only reads the source file. It never overwrites, moves or deletes it. |
| **Safe write** | The output is first written to a hidden temp file in the same folder, checked, and only then renamed to its final name. A crash or power cut can't leave a half-written file. |
| **No overwriting** | If `photo.webp` already exists, the new file is saved as `photo (1).webp`. |
| **Every result is checked** | Each conversion is opened again and compared with the source (table below). If a check fails, the output is deleted and you get a clear error. |
| **Lossless when possible** | PNG, TIFF, WebP-lossless, FLAC, WAV, ZIP and 7z are bit-exact. Lossy formats use high-quality defaults. |
| **Lossy steps are flagged before they happen** | Example: "JPG has no transparency, so the background will be white." Or: "PDF to Word rebuilds the layout and complex pages may shift." You see this in the popup before you choose. |
| **Metadata is kept** | Image EXIF, ICC color profile, orientation, GPS and dates; audio tags and cover art; video chapters and subtitles where the target format supports them. The file's modified date is copied too. |

**Checks run after each conversion**

- **Images:** decodes fully; width and height match (or the size you chose); color profile kept; pixel difference measured for lossless targets (must be 0).
- **Audio/Video:** `ffprobe` checks duration (within 0.1 s), stream count, resolution, frame rate and audio channels.
- **PDF/Documents:** page count, text extracted and compared to the source, no errors on opening.
- **Archives:** same file list, sizes and CRC/hash for every entry.
- **Data (CSV/XLSX/JSON):** same rows, columns and cell values.
- **Fonts:** same glyph count and same font names.

> An honest limit: some conversions can't be perfect because the target format can't hold everything. Examples: video to GIF (256 colors), PDF to DOCX (layout has to be rebuilt), PNG with transparency to JPG. For these the app picks the best possible result, warns you first and still runs the checks. It never claims to be lossless when it isn't.

---

## 3. Supported formats

"All formats to all formats" isn't physically possible; an MP3 can't become an XLSX, for example. The popup only offers conversions that are meaningful and correct.

| Category | Formats | Engine |
|---|---|---|
| **Images** | JPG, PNG, WEBP, HEIC/HEIF, AVIF, GIF, BMP, TIFF, ICO, TGA, PSD (read), SVG (to raster), RAW camera files (CR2/NEF/ARW/DNG, read) | Pillow + pillow-heif + rawpy + resvg |
| **Images to document** | Images to PDF (one or many files merged, in selection order) | img2pdf (lossless: JPGs are embedded without re-encoding) |
| **Audio** | MP3, WAV, FLAC, AAC/M4A, OGG, OPUS, WMA, AIFF, ALAC | FFmpeg |
| **Video** | MP4, MKV, MOV, AVI, WEBM, WMV, FLV, M4V, GIF, extract audio to MP3/WAV/FLAC/M4A | FFmpeg (copies streams without re-encoding when the codec fits, so no quality loss) |
| **Word processing** | DOCX, DOC, ODT, RTF, TXT, HTML, MD to PDF / DOCX / ODT / RTF / TXT / HTML / MD / EPUB | Microsoft Word (if installed, best quality), otherwise LibreOffice; Pandoc for Markdown/HTML |
| **Spreadsheets** | XLSX, XLS, ODS, CSV, TSV, JSON to each other and to PDF | Excel or LibreOffice; openpyxl for data |
| **Presentations** | PPTX, PPT, ODP to PDF, PNG/JPG per slide | PowerPoint or LibreOffice |
| **PDF** | PDF to PNG/JPG per page, TXT, DOCX (layout rebuilt, with warning), split, merge selected PDFs | PyMuPDF, pdf2docx |
| **E-books** | EPUB, MOBI, AZW3, FB2 to EPUB / PDF / TXT / DOCX | Calibre `ebook-convert` (optional install) |
| **Archives** | ZIP, 7Z, TAR, TAR.GZ, RAR (read only, RAR is proprietary) to each other, plus extract here | 7-Zip |
| **Data** | JSON, YAML, XML, CSV, TOML to each other (where the structure fits) | Python standard library + PyYAML |
| **Fonts** | TTF, OTF, WOFF, WOFF2 | fontTools |
| **Subtitles** | SRT, VTT, ASS, SSA | pysubs2 |

Batch conversion works: select 50 HEICs, press the hotkey, choose JPG, and they convert in parallel (capped at your CPU core count).

---

## 4. Keeping it light (always running, no slowdown)

- **When idle**, the app only holds the tray icon and a keyboard listener. Target: **under 40 MB RAM and 0% CPU**. The heavy libraries load only when a conversion starts.
- **The engines run as separate programs** (FFmpeg, LibreOffice, 7-Zip) only during a conversion and close afterwards, so nothing big stays in memory.
- **The popup** is created when needed and destroyed after use. Target: opens in under 150 ms.
- **Background priority:** conversions run at "below normal" CPU priority so your laptop stays responsive while a video converts.
- **Startup:** the app starts with Windows through a per-user Startup entry. It needs no admin rights, and you can turn it off in Settings.

---

## 5. Technology

| Part | Choice | Why |
|---|---|---|
| Language | **Python 3.13** (already installed) | Has the best conversion libraries and lets us build quickly |
| UI (popup, tray, settings) | **PySide6 (Qt)** | Native-looking frameless popup with a dark theme like your screenshot, smooth animation, low memory |
| Global hotkey | Win32 `RegisterHotKey` via `ctypes` | Built into Windows, no keylogger-style hook, nearly zero cost |
| Reading the Explorer selection | Windows Shell COM (`Shell.Application`) via `pywin32` | Reads the selected files from the active Explorer window or the Desktop |
| Notifications | Windows toast notifications | Native look |
| Packaging | PyInstaller into one folder, plus an installer (Inno Setup) | Lets you run it without Python and uninstall it cleanly |

External engines, installed once with `winget`. **I'll ask before downloading each one.**

| Engine | Size | Needed for |
|---|---|---|
| FFmpeg | ~90 MB | Audio and video |
| 7-Zip | ~2 MB | Archives |
| Pandoc | ~100 MB | Markdown, HTML and EPUB documents |
| LibreOffice | ~350 MB | Office files, if Microsoft Office isn't installed |
| Calibre | ~200 MB | E-books (optional) |

---

## 6. Project structure

```
file_formatter/
  app/
    main.py              # tray icon, hotkey, single-instance lock
    hotkey.py            # RegisterHotKey listener
    selection.py         # read selected files from Explorer / Desktop / clipboard
    popup/               # wheel and list popup, options panel (PySide6)
    registry.py          # maps input format to allowed targets, with warnings
    jobs.py              # queue, worker pool, progress, cancel
    safe_write.py        # temp file, verify, rename, unique names, timestamps
    converters/          # image.py, av.py, office.py, pdf.py, archive.py, data.py, font.py, subtitle.py, ebook.py
    verify/              # one checker per category
    settings.py          # JSON settings in %APPDATA%\FileFormatter
    notify.py
  tests/
    corpus/              # sample files for each format (generated, not downloaded)
    test_matrix.py       # runs every supported conversion and checks the result
  tools/                 # engine locator / installer script
  installer/             # PyInstaller spec + Inno Setup script
```

---

## 7. Build phases

| Phase | What gets built | How I'll know it works |
|---|---|---|
| **0. Setup** | Python virtual environment, dependencies, engine installs (with your OK) | Each engine runs and reports its version |
| **1. Core** | Tray app, hotkey, Explorer/Desktop selection, popup, job queue, safe write, notifications, **images** | Hotkey on a selected HEIC creates a correct WEBP next to it; the original's hash is unchanged |
| **2. Audio/Video** | FFmpeg converters, stream copy when possible, progress bar, cancel | Duration, streams and resolution match on test clips |
| **3. Documents and PDF** | Office/LibreOffice/Pandoc, PDF tools, images to PDF, merge/split | Page counts and text match; files open in Word |
| **4. Everything else** | Archives, data, fonts, subtitles, e-books | Hashes, rows and glyph counts match |
| **5. Full test run** | Automated run of every supported conversion on generated sample files, plus edge cases: Unicode/long paths, 0-byte files, corrupted input, read-only folders, files open in another app, OneDrive placeholders | Every conversion passes or is clearly reported as unsupported |
| **6. Polish and ship** | Settings window, right-click menu entry, start with Windows, installer, idle-memory check | Clean install and uninstall; idle memory under 40 MB |

I'll show you a working build after Phase 1 so you can try it early, then continue.

---

## 8. Decisions for you (my defaults in **bold**)

- **A. Hotkey.** Pressing just Ctrl + Shift by itself is risky. On Windows it switches keyboard language when you have more than one, and it would also fire inside every other app shortcut that uses Ctrl + Shift (Ctrl+Shift+T, Ctrl+Shift+Esc and so on). **Default: Ctrl + Shift + Space.** You can change it any time in Settings. If you really want "tap Ctrl+Shift and release", I can add it as an option.
- **B. Office engine.** **Use Microsoft Word/Excel/PowerPoint if installed (best quality), otherwise install LibreOffice.**
- **C. Popup style.** **The wheel (like your screenshot) for 8 or fewer choices, and a searchable list when there are more.**
- **D. Optional engines.** **Install FFmpeg, 7-Zip and Pandoc now. Install LibreOffice only if Office is missing. Skip Calibre unless you want e-books.**
