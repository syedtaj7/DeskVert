# Changelog

## 1.9.2

### The result card, rebuilt
- **Nothing cut off any more:** long file names are shortened in the middle (the full name shows when you point
  at it) and every line of the message fits; before, the name and the "Checked against the original" line
  could be clipped.
- **Before and after:** see what changed at a glance, e.g. HEIC 2.4 MB → WEBP 380 KB, −84 %.
- **More to do from it:** **Open** the new file, **Copy** it (then paste it straight into a chat, an e-mail or a
  folder; pictures paste as pictures too), **Show in folder**, or **Undo**.
- **Alive:** it slides in, the check mark draws itself, the progress bar glides and shimmers while it works, and
  a ring around the close button shows when it will go away (pointing at the card holds it). It slides away
  when done.

## 1.9.1

### New
- **Know when there's an update.** Tapshift asks GitHub for the newest version number a minute and a half after
  it starts and then every six hours. When there's a new version, a card with an **Update** button appears
  (once a day at most for the same version) and the tray menu says **Update to Tapshift x.y.z**. Nothing about
  you or your files is sent. Turn it off in Settings > General > Tell me about updates (or in the tour).

### Fixes
- **About page:** when an update was found while the page was still sliding in, its notes covered the text
  below. Page items now follow the layout while they animate, so nothing overlaps.
- **Welcome tour opens at once:** the first page is up in a fraction of a second (it used to wait for every
  page to be built and every format to be counted). Pages are now built when needed, and formats are counted
  in the background.
- **The live picker on the first page** only steps aside when your pointer is on the circle itself, not when
  it's merely nearby, and picks up again shortly after you leave.

### The tour
- **Every format, one shortcut**, redesigned: each kind of file gets a live story of what Tapshift does with it,
  its numbers, and every format it takes and gives as chips (no more "+20 more" on the results). The list has
  a colour for each kind, and a quiet marker shows when it will move on.
- **Fast, and safe:** power moves and the safety promises share one page.
- The "Try it here" page is gone; the first page already has the real picker to play with.

## 1.9.0

### The welcome tour, redone
- **Watch them work:** a new scrolling gallery where every kind of conversion acts itself out, all playing at
  once: a PDF shrinks while its size counts down, pages fly together to merge, a scan line turns a photo of a
  page into text, a waveform squeezes into an MP3, a route draws itself on a map, files drop into a ZIP...
  30 of them, one section per kind of file. A new kind of file gets its own section automatically.
- **How it works** is now steady: a File Explorer window where a file is selected, Ctrl + Shift is tapped,
  the picker pops up and the new file appears next to the original, with the four steps listed alongside.
  Nothing spins or shimmers any more.
- **Every format, one shortcut** replaces the drifting wheel with a map: every kind of file in a list, and for
  the one you point at, what goes in and what comes out, flowing through Tapshift. Counted live.
- **Undo** has a proper story: click Undo, the new file drops into the Recycle Bin, the original stays.
- **Safe by design** is animated: the original stays locked while a copy slides out, both files are
  compared, nothing reaches the internet, and the processor gauge never passes its limit.
- **Make it yours** now has 12 options: shortcut, start with Windows, appearance, accent color, picker size,
  performance, photo quality, recent actions in the centre, right-click menu, keeping the original's date,
  using copied files, and two files at a time.

### New
- **Picker size** (Compact / Normal / Large) in Settings > Shortcut and look, and in the tour. The picker still
  shrinks to fit small screens.
- **Photo quality** in one word (Smaller / High / Best) in the tour; Settings > Quality keeps the exact numbers.

### Light
- Every tour page uses about 1 to 3.5 % of the whole processor while it animates (measured on a 12-thread
  laptop), and the gallery only redraws the cards you can see.

## 1.8.0

### Fixes
- **Ctrl + Shift keeps working.** After the shortcut listener restarted (finishing the welcome tour, or
  touching the shortcut setting), Windows kept calling the old, freed listener, so taps stopped after the
  first one. Each listener now has a window of its own, and choosing the same shortcut no longer restarts it.

### The web, all the way down
- **No more "More…", no search box, no typing.** Groups that hold many choices open fans of their own,
  further out, like a spider's web: pictures → More formats → Everyday / Pro / Classic / Vector; PDF →
  Convert → As images / As text / As e-book; mixed selections → each kind → All. Everything is one point
  away.
- Moving towards an open fan keeps it open across both levels, and the disc **breathes with the web**:
  snug around the rings when closed, growing as fans open.

### A brand-new welcome tour
- **The real picker, live:** a ghost cursor drives it (opening Split, then Convert → As images...). Move
  your mouse onto it and you take over.
- **A universe of formats:** every kind of file Tapshift handles, orbiting a live count (counted from what
  the picker offers, so new conversions appear by themselves). Point at a world to see what goes in and
  what comes out.
- **Try it here:** pick a sample (photo, PDF, song, GPS track, 3D model, contacts, subtitles, e-book, font,
  drawing) and play with its real web. Nothing is converted.
- **Power moves:** tap twice to repeat, the right-click menu, Undo, and presets, each with a small
  animation. Updated safety page, same setup and finish.
- Light: animations only run on the page you're looking at, and stop when there's nothing to move.

## 1.7.0

### Sound, the light way
- **Music and recordings:** MP3, M4A, WAV, FLAC and WMA into each other (AAC, OGG, Opus, AIFF and AMR are
  read too, where Windows can). High, medium or small quality for MP3, M4A and WMA.
- **The sound from a video:** MP4, MOV, MKV, AVI, WMV, 3GP, WebM and more → MP3, M4A, WAV, FLAC or WMA.
  Only the sound is touched; the picture is never decoded or re-encoded.
- Made by **Windows' own converter** (Media Foundation): nothing to download, about a quarter of a
  second of processor time per minute of sound. Every result's length is checked against the original.
- Re-encoding video (smaller videos, 720p, WebM, GIF) isn't offered: it's the heavy kind of work
  Tapshift keeps off low-end laptops.

### Fixes
- **The installer is back to its usual size.** 1.6.0's GitHub build accidentally included PyMuPDF's AI
  layout models (about 40 MB) that Tapshift never uses; every build now leaves them out.

## 1.6.0

### Many more formats, still light
Everything below runs on what Tapshift already has (no video, audio, Office-sized or AI engines), and
every result is opened again and checked before it's saved.
- **Pictures:** JPEG 2000, ICNS (Mac icons), QOI, DDS, PCX, PPM, SGI and XBM, and opening CUR, XPM, Sun
  Raster, Photo CD, Windows metafiles (EMF / WMF) and Apple Live Photos (LIVP). **Set DPI** (print size,
  without touching a pixel) and **Animated GIF** from several pictures. SVG → **vector PDF** and SVG ↔ SVGZ.
- **PDF →** Markdown, HTML, EPUB, a multi-page TIFF, one long image, or a CBZ comic.
- **E-books:** MOBI, FB2, Markdown, HTML, TXT and PDF → EPUB; comic archives CBR, CB7 and CBT → PDF.
- **Subtitles:** ASS/SSA, SAMI, TTML, LRC and MicroDVD join SRT and WebVTT, all into each other.
- **Data:** → TOML and XML; CSV ↔ TSV; Excel sheets → CSV, JSON, YAML or XML without Excel;
  **vCard contacts** ↔ CSV / Excel (including old phones' encoded names).
- **Maps:** GeoJSON, KML, KMZ, GPX and CSV with coordinates, into each other and to Excel.
- **3D models:** STL, OBJ, PLY, 3MF and GLB/glTF into each other, and a shaded picture.
- **CAD:** DXF drawings → PDF, SVG or PNG.
- **Fonts:** TTF / OTF ↔ WOFF, and EOT.
- **Mail and saved pages:** EML and MHTML → PDF, HTML, TXT or Markdown; e-mail attachments → ZIP.
- **Archives:** pack files as **7Z** or **TAR.GZ** too, and repack any archive as 7Z or TAR.GZ.
- **Illustrator** (.ai, saved with PDF content) → PDF or PNG.

### Picker
- Big groups stay readable: a fan shows at most 8 choices, and the rest are behind **More…** (the list
  with search). ZIP, 7Z and TAR.GZ sit together under **Pack**.

## 1.5.0

### A snappier web
- **No more waiting.** The picker now follows where your pointer is heading: moving towards an open
  branch's choices keeps them open (even across other options), and moving anywhere else switches
  straight away. The 0.35 s pause and the 0.8 s linger are gone.

### New tools
- **Picture edits** (pictures → Edit): turn left, right or upside down, mirror, grayscale, resize (half
  size, or 1920 / 1280 / 1080 px), **Clean info** (removes location, camera and date before sharing;
  JPG and PNG are cleaned without re-encoding), and **Long image** (several pictures stitched one under
  the other). Camera details and color profiles are kept for the other edits.
- **PDF pages per sheet:** 2, 4, 6 or 9 pages on each A4 sheet (replaces "2 per page").
- **E-books:** EPUB, MOBI, FB2, CBZ comics and XPS → PDF (A5 pages) or TXT, with nothing extra to install.
  Locked (DRM) books can't be converted.
- **Subtitles:** SRT → WebVTT and WebVTT → SRT, timings kept to the millisecond.
- **More data formats:** YAML, TOML, XML and JSON Lines → JSON, YAML, CSV or Excel; JSON → YAML or
  JSON Lines. Numbers keep their exact digits (2.50 stays 2.50).

## 1.4.1

### Fixes
- **Settings → Shortcut and look works right away.** Appearance (auto, dark, light) and the accent color
  apply the moment you pick them: no restart, and Settings stays on the same page. Changing the shortcut
  shows a confirmation with the new keys.
- **Far choices in the web are easy to reach.** An open branch now stays out while you move to any of its
  choices, even the farthest one: crossing a neighbouring option on the way no longer closes it, and the
  fan waits a moment (0.8 s) after the pointer leaves before folding away. To switch to another option
  while a branch is open, rest on it briefly.
- **Everything is fully readable.** Options are never faded or see-through; a branch's choices are drawn
  nearly full size on the picker's own solid disc instead of over the desktop, and the side card's text is
  solid.
- **Fits small screens:** on small laptop screens or with a big Windows zoom, the picker shrinks to fit
  instead of being cut off.

## 1.4.0

### The picker becomes a web
- **Grouped tools fan out:** related tools share one node. Point at **Split** and its choices (in half,
  every N pages, by ranges, every page) open around it, joined by threads; the same for **Pages**,
  **Protect**, **Convert** and **Text**. The picker stays small however many tools join.
- **Many kinds of files at once:** select pictures and PDFs together and each kind gets its own branch
  ("2 pictures", "1 PDF"), plus **Combine** (everything in one PDF, in the order selected) and **ZIP**.
- **Repeat the last action:** tap Ctrl + Shift twice, quickly.
- **Your inner ring:** favourites, your own presets and recently used actions sit closest to the centre.

### Customize (new Settings page)
- **Your presets:** one tap does it all, e.g. *WhatsApp photo* (JPG under 300 KB), *College PDF* (under
  300 KB) or *Exam photo* (200×230 px under 50 KB). Make your own: a picture under a size, a picture at an
  exact size, or a PDF under a size.
- **Favourites:** pin the actions you use most. **Recently used near the centre** can be turned off.

### More PDF tools
- Split **in half**, **every N pages** or **by ranges** (`1-3, 4-end`) into a folder of parts.
- **Reorder** pages (`3, 1, 2` or `reverse`), **Reverse**, **2 per page** (A4 landscape),
  **Grayscale**, **Flatten** (fills form fields and notes into the page), **Clean info** (removes the
  author, dates and hidden data), and save the **Pictures** inside a PDF.
- **Compress** accepts any size limit from a preset.

### Also new
- **Right-click menu:** right-click files → **Convert with Tapshift** (on Windows 11 under Show more
  options). Turn it off in Settings → General. Removed when you uninstall.
- **Undo:** the Saved card has an **Undo** button that moves the new files to the Recycle Bin.

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
