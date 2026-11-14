# PyInstaller recipe for Deskvert (one-folder, windowed).
# Build with:  tools\build_release.ps1   (or: pyinstaller deskvert.spec --noconfirm)

import re
from pathlib import Path

ROOT = Path(SPECPATH)
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "app" / "__init__.py").read_text()).group(1)

hidden = [
    # engines are imported by name inside worker processes
    "app.engines.image", "app.engines.doc", "app.engines.pdf", "app.engines.officeutil", "app.selftest",
    "app.engines.compress", "app.engines.archive", "app.engines.data", "app.engines.textdoc", "app.engines.ocr",
    "app.toolbox", "app.menu", "app.engines.mixed", "app.ui.customize", "app.ui.universe", "app.ui.showcase", "app.ui.results", "app.engines.docread", "app.engines.iwork", "app.engines.sqlitedb",
    "app.engines.config", "app.engines.ics", "app.engines.notebook", "app.engines.hash", "app.dropread", "app.browserurl", "app.browsercopy", "app.engines.clip", "app.engines.webextra", "app.engines.videoframe", "app.engines.libre", "app.engines.msgfile", "app.engines.rename", "app.watch",
    "app.report", "app.ui.report", "app.ui.dropzone", "app.engines.qr", "app.engines.webpage",
    "app.engines.webtable", "app.engines.favicon", "win32com.server.util", "win32com.server.policy",
    "app.ui.onboarding", "app.engines.imgedit", "app.history", "app.ui.history", "app.engines.pdfword", "app.engines.shapefile",
    "app.engines.subtitle", "app.engines.ebook", "yaml", "tomllib", "xml.etree.ElementTree",
    "app.engines.geo", "app.engines.font", "app.engines.mesh", "app.engines.cad", "app.engines.mail",
    "app.engines.vector", "lxml", "lxml.html", "lxml.etree", "email", "quopri", "app.engines.media",
    "winrt.windows.media.transcoding", "winrt.windows.media.mediaproperties", "winrt.windows.storage",
    "winrt.windows.storage.fileproperties", "app.updater", "app.ui.update_ui", "app.ui.orbit", "pillow_heif", "rawpy", "img2pdf", "pymupdf", "numpy", "openpyxl", "vtracer",
    # Windows' built-in text recognition (pywinrt projections)
    "winrt.runtime", "winrt.system", "winrt.windows.foundation", "winrt.windows.foundation.collections",
    "winrt.windows.globalization", "winrt.windows.graphics.imaging", "winrt.windows.media.ocr",
    "winrt.windows.storage.streams",
    "win32com", "win32com.client", "win32com.shell", "pythoncom", "pywintypes", "win32clipboard", "win32con",
    "win32gui", "win32process", "PySide6.QtSvg",
]

a = Analysis(
    ["run.pyw"],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "assets" / "deskvert.ico"), "assets"),
           # License texts and third-party notices travel with the app (AGPL/GPL/LGPL obligations).
           (str(ROOT / "LICENSE"), "licenses"),
           (str(ROOT / "THIRD-PARTY-NOTICES.md"), "licenses"),
           (str(ROOT / "licenses" / "*.txt"), "licenses")],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "onnxruntime", "pymupdf4llm", "pymupdf_layout", "pymupdf.layout", "networkx",
              "google.protobuf", "flatbuffers", "PySide6.QtWebEngineCore", "PySide6.QtQuick", "PySide6.QtQml",
              "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtNetwork", "PySide6.QtPdf",
              # img2pdf only uses pikepdf when it's there and writes PDFs itself otherwise (tested without it);
              # pywin32's MFC UI and lxml's objectify / schematron aren't used either
              "pikepdf", "win32ui", "pythonwin", "dde", "lxml.objectify", "lxml.isoschematron"],
    noarchive=False,
)
# Not needed: Qt's software OpenGL fallback (Deskvert only draws 2D) and Qt's UI translations (English UI).
a.binaries = [b for b in a.binaries if not b[0].lower().endswith("opengl32sw.dll")]
a.datas = [d for d in a.datas if not (d[0].replace("\\", "/").find("/translations/") >= 0 and d[0].endswith(".qm"))]
# PyMuPDF 2.x ships AI layout models (onnxruntime) Deskvert never uses; newer PyInstaller hooks collect them.
# Keep them out on every build machine, so the app stays the same small size.
_HEAVY = ("pymupdf/layout", "onnxruntime", "networkx", "google/protobuf", "flatbuffers", "pymupdf4llm")
a.datas = [d for d in a.datas if not any(h in d[0].replace("\\", "/").lower() for h in _HEAVY)]
a.binaries = [b for b in a.binaries if not any(h in b[0].replace("\\", "/").lower() for h in _HEAVY)]
# A smaller download: MuPDF's C++ headers and link libraries (only for compiling), pikepdf's qpdf, the Qt
# touch-over-network plugin (the only user of Qt6Network) and two Qt display plugins Windows never uses here
# (qwindows draws the app; qoffscreen draws pictures in the background).
_SLIM = ("pymupdf/mupdf-devel", "pikepdf", "qtuiotouchplugin", "qt6network", "platforms/qdirect2d",
         "platforms/qminimal", "pythonwin", "win32ui")
a.datas = [d for d in a.datas if not any(h in d[0].replace("\\", "/").lower() for h in _SLIM)]
a.binaries = [b for b in a.binaries if not any(h in b[0].replace("\\", "/").lower() for h in _SLIM)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Deskvert",
    icon=str(ROOT / "assets" / "deskvert.ico"),
    console=False,
    version=str(ROOT / "tools" / "version_info.txt"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Deskvert")
