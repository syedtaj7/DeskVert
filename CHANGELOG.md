# Changelog

## 1.3.1

### Fixes and small things
- **Clicking the Tapshift icon opens Tapshift.** Clicking the tray icon opens Settings (your latest files
  are in the tray menu under Recent conversions). Starting Tapshift again from the Start menu or a pinned
  taskbar icon brings its window to the front instead of doing nothing.
- **Maximize:** Settings, the guide and the welcome tour have a maximize button. Double-click the title bar
  to maximize or restore; it never covers the taskbar.
- **Settings → About fits the window again:** the buttons are in two rows, so nothing is cut off.

## 1.3.0

### Ready for upload forms
- **Compress → For forms:** exact-size JPGs for exam, job and ID applications: form photo (200×230 px,
  20–50 KB), passport photo (35×45 mm at 300 dpi), signature (140×60 px, 10–20 KB, empty paper trimmed),
  or your own width × height × size limit. Saved as "photo (form photo).jpg" next to the original.
- **PDF Compress to a size:** pick under 200 KB, 500 KB, 1 MB or 2 MB and get the best quality that fits.
  The search runs on a sample of pages first, so long PDFs stay quick on slow laptops.

### Updates from inside the app
- **Check for updates** (Settings → About, or the tray menu) asks GitHub for the latest version and shows
  what's new. **Download** fetches the installer with a progress bar and checks it against GitHub's SHA-256
  checksum; **Install and restart** closes Tapshift, installs the update and opens the new version.
- Tapshift only goes online when you click Check for updates. Your files are never sent anywhere.

## 1.2.1

### Orbit, floating
- **No more box:** the picker floats over your files on its own round disc with a soft shadow, instead of
  sitting inside a large dark rectangle. The side card appears next to it only while you point at something.
- **Smaller:** about 10% more compact, so it covers less of your window.
- The file name now shows in the centre, and notes (like files left out of a mixed selection) sit under
  the disc.
- Smoother opening: everything is drawn before the first frame (worst frame 11.7 ms, under the 16.7 ms
  that 60 fps allows).

## 1.2.0

### Orbit: a new picker
- **Orbit replaces the wheel.** Tools circle on one orbit and formats on the other. Point at one and the
  orbits stop, the option leans toward your pointer, and a small card on the side says what it does and
  what the new file will be called.
- **Room to grow:** shows about 20 options before a "More" button appears, instead of 7.
- **Smooth on low-end laptops:** everything is pre-drawn, motion is time-based, the animation stops when
  nothing moves, and the idle drift settles by itself after a few seconds. Windows' "Animation effects"
  setting turns the motion off.
- **Fewer warning dots:** only real cautions (like "transparent areas become white") are marked in amber.
- The welcome tour, the guide and the README show the new picker.

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
