"""Word, Excel and PowerPoint files on PCs without Microsoft Office: through LibreOffice, when it's installed.

LibreOffice (free) is run on its own, invisibly, with a private, empty profile in Tapshift's work
folder: a LibreOffice you have open is never touched, and nothing is changed in your settings. It
runs inside Tapshift's processor limit, like everything else.

Every result is checked before it's kept: a PDF must open with pages (and the document's words,
when Tapshift can read them), other formats must open as what they claim to be.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

CREATE_NO_WINDOW = 0x08000000
_found: list = []

# (kind, format) -> LibreOffice's export filter
FILTERS = {
    ("word", "pdf"): "pdf:writer_pdf_Export", ("word", "docx"): "docx:MS Word 2007 XML",
    ("word", "odt"): "odt:writer8", ("word", "rtf"): "rtf:Rich Text Format", ("word", "doc"): "doc:MS Word 97",
    ("word", "txt"): "txt:Text (encoded):UTF8",
    ("excel", "pdf"): "pdf:calc_pdf_Export", ("excel", "xlsx"): "xlsx:Calc MS Excel 2007 XML",
    ("excel", "ods"): "ods:calc8", ("excel", "xls"): "xls:MS Excel 97",
    ("excel", "csv"): "csv:Text - txt - csv (StarCalc):44,34,76,1",
    ("powerpoint", "pdf"): "pdf:impress_pdf_Export", ("powerpoint", "pptx"): "pptx:Impress MS PowerPoint 2007 XML",
    ("powerpoint", "odp"): "odp:impress8", ("powerpoint", "ppt"): "ppt:MS PowerPoint 97",
}
ZIP_PARTS = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml", "pptx": "ppt/presentation.xml",
             "odt": "content.xml", "ods": "content.xml", "odp": "content.xml"}
OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")


def find_soffice() -> str | None:
    """LibreOffice's soffice.exe, if it's installed (looked up once)."""
    if _found:
        return _found[0]
    path = None
    try:
        import winreg

        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\soffice.exe") as k:
                    p = winreg.QueryValue(k, None).strip('"')
                if p and os.path.isfile(p):
                    path = p
                    break
            except OSError:
                pass
    except ImportError:
        pass
    if path is None:
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
                     os.environ.get("LOCALAPPDATA", "") + r"\Programs"):
            p = os.path.join(base, "LibreOffice", "program", "soffice.exe")
            if base and os.path.isfile(p):
                path = p
                break
    _found.append(path)
    return path


def _source_text(src: Path) -> str:
    """The document's words, when Tapshift can read them itself (to check the result)."""
    e = src.suffix.lower()
    try:
        if e in (".docx", ".docm", ".dotx"):
            from .docread import read_docx

            return read_docx(src)[1]
        if e == ".odt":
            from .docread import read_odt

            return read_odt(src)[1]
        if e == ".txt":
            return Path(long_path(src)).read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""
    return ""


def _run(soffice: str, src: Path, filt: str, outdir: Path, work: Path, timeout: float) -> Path:
    inp = work / ("input" + src.suffix.lower())  # a plain name: nothing odd for LibreOffice's command line
    shutil.copyfile(long_path(src), inp)
    profile = work / "lo-profile"
    profile.mkdir(exist_ok=True)
    outdir.mkdir(exist_ok=True)
    cmd = [soffice, "--headless", "--invisible", "--norestore", "--nologo", "--nolockcheck", "--nodefault",
           "--nofirststartwizard", f"-env:UserInstallation={profile.as_uri()}",
           "--convert-to", filt, "--outdir", str(outdir), str(inp)]
    try:
        subprocess.run(cmd, timeout=timeout, capture_output=True, creationflags=CREATE_NO_WINDOW, check=False)
    except subprocess.TimeoutExpired as e:
        raise ConversionError("LibreOffice took too long with this file.") from e
    ext = filt.split(":", 1)[0]
    made = outdir / f"input.{ext}"
    if not made.exists() or made.stat().st_size == 0:
        raise ConversionError("LibreOffice couldn't convert this file (it may be damaged or password-protected).")
    return made


def _check(made: Path, fmt: str, src_text: str) -> str:
    """Opens the result again; returns a short "Checked: ..." note."""
    from .officeutil import text_coverage

    if fmt == "pdf":
        import pymupdf

        try:
            with pymupdf.open(long_path(made)) as d:
                pages = d.page_count
                text = "\n".join(p.get_text() for p in d)
                pictures = sum(len(p.get_images()) for p in d)
        except Exception as e:  # noqa: BLE001
            raise VerificationError(f"the PDF can't be opened ({e})") from e
        if pages < 1 or (not text.strip() and not pictures):
            raise VerificationError("the PDF came out empty")
        cov = text_coverage(src_text, text) if src_text else None
        if cov is not None and cov < 0.9:
            raise VerificationError(f"only {cov:.0%} of the document's words are in the PDF")
        return f"Checked: {pages} page{'s' if pages != 1 else ''}" + (", all of the text." if cov else ".")
    if fmt in ZIP_PARTS:
        try:
            with zipfile.ZipFile(long_path(made)) as z:
                if ZIP_PARTS[fmt] not in z.namelist() or z.testzip() is not None:
                    raise VerificationError(f"the {fmt.upper()} file is incomplete")
        except zipfile.BadZipFile as e:
            raise VerificationError(f"the {fmt.upper()} file is broken") from e
        if fmt in ("docx", "odt") and src_text:
            from .docread import read_docx, read_odt

            back = (read_docx if fmt == "docx" else read_odt)(made)[1]
            cov = text_coverage(src_text, back)
            if cov is not None and cov < 0.95:
                raise VerificationError(f"only {cov:.0%} of the document's words are in the new file")
        return f"Checked: the {fmt.upper()} file opens and is complete."
    head = Path(long_path(made)).read_bytes()[:16]
    if fmt in ("doc", "xls", "ppt"):
        if not head.startswith(OLE_MAGIC):
            raise VerificationError(f"the {fmt.upper()} file is broken")
        return f"Checked: the {fmt.upper()} file opens."
    if fmt == "rtf" and not head.startswith(b"{\\rtf"):
        raise VerificationError("the RTF file is broken")
    if fmt in ("txt", "csv"):
        body = Path(long_path(made)).read_text(encoding="utf-8", errors="replace")
        if not body.strip():
            raise VerificationError("the new file is empty")
        cov = text_coverage(src_text, body) if src_text and fmt == "txt" else None
        if cov is not None and cov < 0.95:
            raise VerificationError(f"only {cov:.0%} of the document's words are in the text file")
    return f"Checked: the {fmt.upper()} file opens."


def convert(src: Path, out: Path, fmt: str, kind: str, notes: list[str]) -> None:
    from .officeutil import timeout_for

    soffice = find_soffice()
    if soffice is None:
        raise ConversionError("This needs Microsoft Office or the free LibreOffice, and neither is installed.")
    work = out.parent / "libreoffice"
    work.mkdir(exist_ok=True)
    src_text = _source_text(src)
    timeout = timeout_for(src, 180)
    if kind == "powerpoint" and fmt in ("png", "jpg"):  # slides as pictures: the PDF, then each page drawn
        import pymupdf

        pdf = _run(soffice, src, FILTERS[("powerpoint", "pdf")], work / "out", work, timeout)
        Path(long_path(out)).mkdir(parents=True, exist_ok=True)
        with pymupdf.open(long_path(pdf)) as d:
            for i, page in enumerate(d, 1):
                pix = page.get_pixmap(dpi=150)
                target = Path(long_path(out)) / f"Slide {i}.{fmt}"
                pix.save(str(target)) if fmt == "png" else pix.pil_save(str(target), "JPEG", quality=90)
            n = d.page_count
        if n < 1:
            raise VerificationError("no slides came out")
        notes.append(f"Checked: {n} slide{'s' if n != 1 else ''}, one picture each.")
    else:
        filt = FILTERS.get((kind, fmt))
        if filt is None:
            raise ConversionError(f"LibreOffice can't make {fmt.upper()} from this file.")
        made = _run(soffice, src, filt, work / "out", work, timeout)
        notes.append(_check(made, fmt, src_text))
        shutil.move(str(made), long_path(out))
    notes.append("Made by LibreOffice (Microsoft Office isn't installed); the layout can differ slightly from "
                 "Office's.")
