# Third-party notices

Tapshift is licensed under the **GNU Affero General Public License v3.0** (see [LICENSE](LICENSE)).
Its complete source code is available at https://github.com/syedtaj7/TapShift.

The Windows release bundles the following open-source components, unmodified. Each remains under its own
license; license texts are in the [licenses](licenses) folder of this repository, and inside the installed
program at `_internal\licenses` (Settings > About > Licenses opens it).

| Component | Used for | License | Source |
|---|---|---|---|
| Python 3.13 | Runtime | PSF License | https://www.python.org/downloads/source/ |
| Qt 6 (via PySide6, shiboken6) | Windows, drawing | LGPL-3.0 | https://download.qt.io/official_releases/qt/ · https://code.qt.io/cgit/pyside/pyside-setup.git |
| PyMuPDF / MuPDF | PDF pages, text, split, merge, checks | AGPL-3.0 | https://github.com/pymupdf/PyMuPDF |
| Pillow | Image conversion | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| pillow-heif | HEIC/HEIF support | BSD-3-Clause | https://github.com/bigcat88/pillow_heif |
| libheif (bundled in pillow-heif) | HEIC container | LGPL-3.0 | https://github.com/strukturag/libheif |
| libde265 (bundled in pillow-heif) | HEIC decoding | LGPL-3.0 | https://github.com/strukturag/libde265 |
| x265 (bundled in pillow-heif) | HEIC encoding | GPL-2.0-or-later | https://bitbucket.org/multicoreware/x265_git |
| rawpy | Camera RAW photos | MIT | https://github.com/letmaik/rawpy |
| LibRaw (bundled in rawpy) | Camera RAW decoding | LGPL-2.1 or CDDL-1.0 | https://github.com/LibRaw/LibRaw |
| img2pdf | Lossless images to PDF | LGPL-3.0 | https://gitlab.mister-muffin.de/josch/img2pdf |
| pikepdf / qpdf | PDF writing for img2pdf | MPL-2.0 / Apache-2.0 | https://github.com/pikepdf/pikepdf · https://github.com/qpdf/qpdf |
| NumPy (with OpenBLAS) | Image comparisons | BSD-3-Clause | https://github.com/numpy/numpy |
| lxml / libxml2 | XML for pikepdf | BSD-3-Clause / MIT | https://github.com/lxml/lxml |
| pywin32 | Windows and Office integration | PSF License | https://github.com/mhammond/pywin32 |
| PyInstaller bootloader | Starting Tapshift.exe | GPL-2.0 with bootloader exception | https://github.com/pyinstaller/pyinstaller |

Image codecs bundled inside Pillow (libjpeg-turbo, libpng, zlib, libtiff, libwebp, libavif, dav1d, aom, FreeType,
Little CMS, OpenJPEG) are under BSD, zlib, MIT or similar permissive licenses; see
https://github.com/python-pillow/Pillow/blob/main/LICENSE and the Pillow wheel's license files.

**Replacing libraries (LGPL):** Qt and the other LGPL libraries ship as separate DLL files inside the
Tapshift program folder (`_internal`), so you can replace them with your own builds.

**Microsoft Office** is not included. Word, Excel and PowerPoint conversions use the copy of Office already
installed on the user's computer, under its own license.
