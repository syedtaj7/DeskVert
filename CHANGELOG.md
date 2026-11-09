# Changelog

## 1.1.1

### Easier to uninstall
- **Uninstall Tapshift** is now in the Start menu, in the tray menu, and in Settings > About.
- Uninstalling now removes everything: settings, logs and scratch files, and the start-up entry left by
  early development builds.

## 1.1.0

### Everyday file tools
- **Compress images to a size:** pick "under 20 KB", "under 100 KB" and so on, or a quality. Each choice
  shows the quality and size before you click. Saved as JPG, WEBP or the original format.
- **PDF tools:** compress, lock and unlock with a password (AES-256), keep or remove pages, rotate, page
  numbers and watermark.
- **Text recognition (OCR):** read the text from a picture or a scanned PDF, or make a scanned PDF
  searchable. Uses the engine built into Windows; sideways scans are detected.
- **ZIP and extract:** zip the selected files, extract ZIP, 7Z, RAR, TAR, GZ, XZ, CAB and ISO archives, or
  repack any of them as a ZIP.
- **Data files:** CSV and TSV to Excel or JSON, JSON to CSV or Excel, tidy or minify JSON. Values like 007,
  1.50 and long IDs stay exactly as written.
- **Markdown:** to PDF, HTML or Word.
- Every tool saves a new file next to the original and checks it before keeping it. All of them run inside
  the same CPU limit as conversions.

## 1.0.1

### New look
- **Calmer design:** flat surfaces, one green accent color, consistent corner shapes, and no glows or gradients.
- **Welcome page:** shows the real format wheel stepping through formats.
- **Formats page:** rebuilt as an asymmetric layout.
- **Accent color choice:** green (default), orange, or your Windows accent color (Settings > Shortcut & look).
- **Clearer hints:** the format wheel's hints are now short, plain sentences.

### Fixes
- **Taskbar:** windows can now be minimized from the taskbar button, and have a minimize button.
- **Guide:** the live wheel no longer shows raw formatting tags.
- **Windows-style demo:** the "How it works" demo shows a Windows-style window instead of macOS-style dots.

### License
- **Now AGPL-3.0:** Tapshift is licensed under the GNU Affero General Public License v3.0, as required by the
  bundled PyMuPDF and x265 components. Third-party notices and license texts ship with the app
  (Settings > About > Licenses).

## 1.0.0

First public release.

### How it works
- Select files, tap **Ctrl + Shift**, then pick a format on the animated wheel.
- The converted file is saved next to the original.

### What's included
- **Formats:**
  - Images: JPG, PNG, WEBP, HEIC, AVIF, GIF, BMP, TIFF, ICO, TGA and PDF. It also reads PSD, SVG and camera RAW files.
  - Office documents, converted through Microsoft Office: Word, Excel and PowerPoint to PDF and other formats.
  - PDF tools: merge, split, pages to PNG or JPG, and text.
- **Checks on every result** before it's kept: pixels, pages, words or cell values are compared with the original.
- **Light on your laptop:** conversions have a hard CPU limit (15/25/50%), and the app uses no CPU while idle.
- **Windows:** a progress card at the bottom-right, an animated welcome tour, a How-to-use guide and a Settings window.
- **Look:** follows Windows' light or dark mode.
