# Changelog

## Unreleased

- **Updates always install from inside Deskvert:** Check for updates now downloads and installs the new version
  right in the app (checked against GitHub's checksum) instead of ever sending you to the download page. A copy
  that runs without being installed gets installed by the update. An installed copy is also recognised from
  Windows' own record of it, not only from the file next to Deskvert.exe.

## 1.15.0

### New conversions
- **PDF to Word:** a PDF's new **DOCX** option makes an editable Word document with its headings, bold and
  italic, lists, pictures and tables. Made by Deskvert itself, so it works without Microsoft Office, and every
  word is checked against the PDF. Scanned PDFs need Read text first.
- **Video to GIF:** a video's new **GIF** option turns 3, 5 or 10 seconds (from the moment you pick) into a
  small looping GIF for chats and documents. Only that part of the video is decoded, so it takes a few seconds
  even on a slow laptop.
- **Picture to SVG:** a picture's new **SVG** option traces logos, icons and drawings into shapes that stay sharp
  at any size, in colour or black and white. The drawing is drawn again and compared with the picture before
  it's kept.
- **Shapefile maps:** .shp files (with the .dbf, .prj and .cpg beside them) become KML, GeoJSON, GPX, KMZ, CSV
  or Excel, with each place's details. Maps in degrees, Web Mercator or UTM are turned into longitude /
  latitude; other projections are refused with a plain message instead of being guessed.

### From the browser
- **Point at a link:** tap Ctrl + Shift with the pointer on a link to use what it points to: a link to a PDF,
  picture or other file fetches that file, and a link to a page gives that page's options. Selecting just a link
  works the same way (it used to save the link's words).
- **No more copies:** tapping Ctrl + Shift again on the same page or selection reuses what was saved a moment ago
  instead of adding "(1)", "(2)"… to Downloads\Deskvert.

### Also
- **Smaller download:** the installer is about 3.5 MB smaller and the portable zip about 9 MB smaller, with the
  new features included.
- **Support Deskvert:** a button on the About page opens Deskvert's GitHub Sponsors page.
- Every conversion now has its own page on the website, with a format finder:
  https://deskvert-website.vercel.app/convert

## 1.14.0

### Tapshift is now Deskvert
Same app, new name: Deskvert converts files right on your desktop.

- **Nothing to do:** updating from Tapshift keeps your settings, start-up, right-click and Send to entries,
  and installs over the old copy (the old program file and shortcuts are removed).
- New website: https://deskvert-website.vercel.app
- Files saved in the old `Downloads\Tapshift` folder stay there; new ones go to `Downloads\Deskvert`.

## 1.13.0

### More from the browser
- **Just the article:** tap Ctrl + Shift on a page and pick **Article as PDF**: the headline, text and pictures,
  without menus, ads, cookie banners or comments, laid out calmly with a line saying where it came from.
- **Every picture on a page:** **All pictures** saves each picture at the biggest size the page offers, in one
  folder. Icons and tiny pictures are left out; each one is opened to check it's a real picture.

### New tools
- **A still from a video:** any moment (the first frame, a tenth in, the middle, three quarters in) as a JPG at
  the video's own size, or a **frames sheet** of nine moments with their times. Windows' own decoder reads only
  the frames needed; nothing is re-encoded.
- **Trim a recording:** keep only the part between two times (MP3, M4A, WAV, FLAC, WMA stay what they are).
- **Sign a PDF:** your name in a handwriting font (or a picture of your signature) with the date, on the last
  page, the first or every page. A visible signature, not a certificate signature.
- **Outlook .msg e-mails** to PDF, HTML, text or Markdown, and their attachments as a ZIP, without Outlook.
- **Rename many files:** tidy copies in a new folder, named by date taken or a number ("2026-11-13 01.jpg",
  "Holiday 03.jpg"). Your originals keep their names.
- **Watch folders** (Settings > General): files you put in a chosen folder are converted by themselves (PDF,
  JPG, PNG, WEBP, Compress, MP3, TXT), into a "Converted" folder inside it. Only new files.

### Reach and comfort
- **No Microsoft Office? LibreOffice:** Word, Excel and PowerPoint files are converted by the free LibreOffice
  when Office isn't installed, in a private profile of its own; every result is checked the same way.
- **Report a problem** (tray menu, About, and a Report button on a red card): you see exactly what would be
  shared, with your name, folders and file names hidden, and a filled-in GitHub issue opens in your browser.
  Tapshift sends nothing itself.
- **The result card appears on the screen you're working on** (where the mouse is), not always the main one.
- **Reduce motion** (Settings > General and the tour): still pictures instead of animations, windows that
  simply appear. Windows' own Animation effects setting is followed too.
- Reading a browser selection no longer adds your own clipboard a second time to Windows' clipboard history.
- New animated cards in the gallery for all of the above.

Tapshift now converts 197 kinds of files in 171 ways.

## 1.12.0

### Straight from your browser
Edge, Chrome, Brave, Firefox, Opera: nothing to install in the browser. All of it is in the welcome tour, the
gallery and the guide.

- **Drag and convert:** hold **Ctrl + Shift** while dragging a picture, link, table, text or file out of any
  app: a **Drop to convert** circle appears under the pointer. Let go on it and the picker opens. Ctrl + Shift
  can go down before the drag or during it. Outlook attachments and other "virtual files" work too.
- **Always the biggest picture:** when a page offers several sizes of a picture, Tapshift takes the largest,
  not the small preview.
- **Selected text:** select text on a page and tap Ctrl + Shift. The picker offers only what fits a
  selection: a clean PDF, Word, Markdown, plain text or a picture of it, each with a line saying which page
  it came from. Tapshift reads the selection by copying it, then puts your clipboard back exactly as it was.
  With nothing selected, the tap is about the page itself.
- **Web tables to Excel:** select a table the same way: one sheet per table, merged cells spread out,
  numbers as numbers. Or the biggest table as CSV. Saved web pages (.html) offer **Tables** too.
- **Save the page:** tap Ctrl + Shift on a browser window with nothing selected: the page as a **PDF** or as **one
  long picture**, made by the Edge or Chrome already on your PC (a fresh, empty profile; no cookies), or a
  **QR code** of its address.
- **QR codes:** for any link (.url shortcut or dragged link). Each one is read back before it's saved, so it
  always scans.
- **Shared links become files:** Google Drive, Docs, Sheets, Slides, Dropbox and OneDrive / SharePoint share
  links download the file itself, with its real name.
- **Screenshots in a tap:** press Win + Shift + S, then tap Ctrl + Shift anywhere: the snip (or any copied
  picture) opens in the picker.
- **Website icons:** pick it on a logo for favicon.ico (16, 32, 48), the PNG sizes phones use, a web
  manifest and a page with the lines to paste into your site.
- **WEBP downloads to JPG** (off by default, Settings > General): pictures you download as WEBP or AVIF get a
  JPG copy next to them, by themselves. The download is kept.
- What you drop is saved in **Downloads\Tapshift** (never overwriting anything) and the converted file goes
  next to it. Files dragged from File Explorer are converted where they are, as usual.
- Videos playing on sites like YouTube are streams: dragging one gives its thumbnail. A video file, or a link
  straight to one (like .mp4), works, and its sound can be taken out as before.
- Each part can be turned off in Settings > General: Drag and convert, Browser pages, WEBP downloads to JPG.

### Fixes
- The picker now closes when you click the empty space around it, not only further away.
- Converting many files into a folder no longer makes a "Converted" folder inside another "Converted" folder.

Tapshift now converts 196 kinds of files in 164 ways.

## 1.11.0

### New conversions (all light, nothing new to download)
- **Word and OpenDocument without Office:** DOCX and ODT to plain text, Markdown or a web page, with headings,
  lists, tables, bold and italic. Works on PCs without Microsoft Office; with Office you get Markdown and HTML
  as extras.
- **Apple Pages, Numbers and Keynote:** the preview Apple saves inside the file, as PDF or JPG (newer files keep
  the first page; older ones a full PDF). Before, these were refused.
- **PDF tables to Excel:** every table found, one sheet each, numbers as numbers and values like 1.20 kept as
  written.
- **Remove blank pages** from a PDF (the other pages stay exactly the same).
- **Pictures:** crop to a shape (square, 4:5, 3:2, 16:9, 9:16, A4), a text watermark (across the middle or in
  the corner), and a **passport photo sheet**: 8 photos of 35×45 mm (or 6 of 2×2 inch) on a 4×6 inch print.
- **Databases (SQLite):** every table to Excel (a sheet each) or CSV, read-only.
- **Settings files:** INI, .env and .properties to JSON or YAML, every value exactly as written.
- **Calendars (.ics)** from Google, Outlook or Apple: every event as a row in Excel or CSV.
- **Jupyter notebooks:** to a web page with the results and charts, Markdown, or a Python script. Never run.
- **Subtitles out of sync?** Shift every subtitle earlier or later by a few seconds, same format.
- **Checksum** for any files or folders: a .sha256 file to check later that nothing changed.

Tapshift now converts 195 kinds of files in 160 ways.

## 1.10.0

### New
- **Folders work.** Select a folder (or several, or folders and files together) and Tapshift offers everything
  for the files inside, sub-folders included. Each new file is saved next to its original. ZIP, 7Z and TAR.GZ
  keep the folder's structure and are saved beside the folder. Up to 2,000 files at a time.
- **Send to → Tapshift.** In the right-click menu's Send to list, which is on Windows 11's short menu. The
  "Convert with Tapshift" entry now also appears on folders. Both come with the existing right-click setting.
- **Choose where new files go** (Settings > General > Save new files): next to the original, in a "Converted"
  folder beside it, or ask each time.
- **Details for a batch.** When several files are converted, the result card has a **Details** button: every
  file, failed ones first with the reason, **Show** for each new file, and **Copy the list**.
- **A shortcut that doesn't fight your keyboard.** On a PC where Ctrl + Shift already switches the keyboard
  layout, a new install starts with Ctrl + Shift + Space instead, and the tour says why.

### Behind the scenes
- Tests now run on every pull request, including a check that would have caught the invisible card of 1.9.2.

## 1.9.3

### Fixes
- **The progress and result card shows again.** In 1.9.2 the card's slide-in was cut short the moment a
  conversion reported its first file, which left it fully transparent: there, but invisible, for the whole
  conversion. It now always finishes appearing, however quickly things happen.
- Unexpected errors inside Tapshift's windows are now written to the log (Settings > About > Log folder)
  instead of disappearing silently.

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
