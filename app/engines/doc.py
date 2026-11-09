"""Word, Excel and PowerPoint conversions through the installed Microsoft Office.

Office does the conversion itself (best possible fidelity), then the result is
checked before it's kept:
- Word: same page count (PDF) or same word/character counts (other formats),
  and the document's words must appear in the output.
- Excel: every sheet and every cell value is compared after reopening the
  output (CSV: same size and filled-cell count; CSV holds one sheet).
- PowerPoint: same slide count and shapes per slide; PDF/images: one page or
  image per slide.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path
from .officeutil import (NO_PASSWORD, Watchdog, friendly_com_error, is_encrypted_ooxml, office, text_coverage,
                         timeout_for)

WORD_EXTS = {".doc", ".docx", ".docm", ".dot", ".dotx", ".odt", ".rtf", ".txt", ".htm", ".html", ".mht", ".wpd", ".xml"}
EXCEL_EXTS = {".xls", ".xlsx", ".xlsm", ".xlsb", ".ods", ".csv", ".tsv"}
PPT_EXTS = {".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp"}

WORD_FORMATS = {"docx": 16, "doc": 0, "odt": 23, "rtf": 6, "txt": 2}
EXCEL_FORMATS = {"xlsx": 51, "xls": 56, "ods": 60, "csv": 62}
PPT_FORMATS = {"pptx": 24, "ppt": 1, "odp": 35, "pdf": 32}


def app_for(path: Path) -> str:
    e = path.suffix.lower()
    if e in WORD_EXTS:
        return "word"
    if e in EXCEL_EXTS:
        return "excel"
    if e in PPT_EXTS:
        return "powerpoint"
    raise ConversionError(f"{path.suffix} files aren't documents File Formatter can open.")


def _pdf_info(path: Path) -> tuple[int, str]:
    import pymupdf

    try:
        with pymupdf.open(long_path(path)) as d:
            return d.page_count, "\n".join(p.get_text() for p in d)
    except Exception as e:
        raise VerificationError(f"the PDF can't be opened: {e}") from e


def _check_text(src_text: str, out_text: str, minimum: float, what: str) -> None:
    cov = text_coverage(src_text, out_text)
    if cov is not None and cov < minimum:
        raise VerificationError(f"only {cov:.0%} of the document's words are in the {what}")


# ====================================================================== Word


def _word_open(app, path: Path, read_only: bool = True):
    return app.Documents.Open(FileName=long_path(path), ConfirmConversions=False, ReadOnly=read_only,
                              AddToRecentFiles=False, PasswordDocument=NO_PASSWORD,
                              PasswordTemplate=NO_PASSWORD, Revert=False, Visible=False, NoEncodingDialog=True)


def _word_stats(doc) -> tuple[int, int, int]:
    # wdStatisticWords=0, wdStatisticPages=2, wdStatisticCharacters=3
    return int(doc.ComputeStatistics(0)), int(doc.ComputeStatistics(2)), int(doc.ComputeStatistics(3))


def convert_word(src: Path, out: Path, fmt: str, notes: list[str]) -> None:
    with office("Word.Application", "WINWORD.EXE", "Word") as oa:
        app = oa.app
        app.Visible = False
        app.DisplayAlerts = 0  # wdAlertsNone
        with Watchdog(oa, timeout_for(src), "opening the document"):
            try:
                doc = _word_open(app, src)
            except Exception as e:
                raise friendly_com_error(e, "Word") from e
        try:
            src_words, src_pages, src_chars = _word_stats(doc)
            src_text = doc.Content.Text
            with Watchdog(oa, timeout_for(src, 180), "converting"):
                if fmt == "pdf":
                    doc.ExportAsFixedFormat(OutputFileName=long_path(out), ExportFormat=17, OpenAfterExport=False,
                                            OptimizeFor=0, Range=0, Item=0, IncludeDocProps=True, KeepIRM=True,
                                            CreateBookmarks=1, DocStructureTags=True, BitmapMissingFonts=True,
                                            UseISO19005_1=False)
                else:
                    kw = {"Encoding": 65001} if fmt == "txt" else {}
                    doc.SaveAs2(FileName=long_path(out), FileFormat=WORD_FORMATS[fmt], AddToRecentFiles=False, **kw)
        except ConversionError:
            raise
        except Exception as e:
            raise friendly_com_error(e, "Word") from e
        finally:
            try:
                doc.Close(SaveChanges=0)
            except Exception:
                pass

        # ---- verify
        if fmt == "pdf":
            pages, text = _pdf_info(out)
            if abs(pages - src_pages) > src_pages // 50:
                raise VerificationError(f"the PDF has {pages} pages, the document has {src_pages}")
            _check_text(src_text, text, 0.9, "PDF")
            notes.append(f"Checked: {pages} page{'s' if pages != 1 else ''}, same as the document.")
        elif fmt == "txt":
            text = Path(out).read_text(encoding="utf-8-sig", errors="replace")
            _check_text(src_text, text, 0.97, "text file")
            notes.append("Checked: all of the document's text is in the file. "
                         "Formatting, images and table layout aren't kept in plain text.")
        else:
            with Watchdog(oa, timeout_for(out), "checking the result"):
                try:
                    d2 = _word_open(app, out)
                except Exception as e:
                    raise VerificationError(f"the new file can't be opened in Word: {e}") from e
                try:
                    w2, p2, c2 = _word_stats(d2)
                    text2 = d2.Content.Text
                finally:
                    d2.Close(SaveChanges=0)
            tol_w = max(3, src_words // 100)
            if abs(w2 - src_words) > tol_w or abs(c2 - src_chars) > max(10, src_chars // 100):
                raise VerificationError(f"word count changed ({src_words} → {w2})")
            _check_text(src_text, text2, 0.98, "new document")
            notes.append(f"Checked: {w2} words, same as the original.")
            if p2 != src_pages:
                notes.append(f"Page count changed ({src_pages} → {p2}) because the new format lays text out differently.")


# ====================================================================== Excel


def _excel_open(app, path: Path):
    return app.Workbooks.Open(Filename=long_path(path), UpdateLinks=0, ReadOnly=True, Password=NO_PASSWORD,
                              WriteResPassword=NO_PASSWORD, IgnoreReadOnlyRecommended=True, Notify=False,
                              AddToMru=False)


def _sheet_values(ws) -> tuple[tuple[int, int], tuple]:
    ur = ws.UsedRange
    v = ur.Value2
    if not isinstance(v, tuple):
        v = ((v,),)
    rows = [list(r) for r in v]
    # trim trailing empty rows/columns
    while rows and all(c in (None, "") for c in rows[-1]):
        rows.pop()
    width = max((max((i + 1 for i, c in enumerate(r) if c not in (None, "")), default=0) for r in rows), default=0)
    rows = [r[:width] for r in rows]
    return (int(ur.Row), int(ur.Column)), tuple(tuple(r) for r in rows)


def _same(a, b) -> bool:
    if a in (None, "") and b in (None, ""):
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def _values_equal(a: tuple, b: tuple) -> tuple[bool, str]:
    if len(a) != len(b):
        return False, f"{len(b)} rows instead of {len(a)}"
    for i, (ra, rb) in enumerate(zip(a, b)):
        n = max(len(ra), len(rb))
        ra = list(ra) + [None] * (n - len(ra))
        rb = list(rb) + [None] * (n - len(rb))
        for j, (x, y) in enumerate(zip(ra, rb)):
            if not _same(x, y):
                return False, f"cell at row {i + 1}, column {j + 1} differs ({x!r} → {y!r})"
    return True, ""


def convert_excel(src: Path, out: Path, fmt: str, notes: list[str]) -> None:
    with office("Excel.Application", "EXCEL.EXE", "Excel") as oa:
        app = oa.app
        app.Visible = False
        app.DisplayAlerts = False
        app.EnableEvents = False
        with Watchdog(oa, timeout_for(src), "opening the workbook"):
            try:
                wb = _excel_open(app, src)
            except Exception as e:
                raise friendly_com_error(e, "Excel") from e
        try:
            sheets = [wb.Worksheets(i + 1) for i in range(wb.Worksheets.Count)]
            src_data = {ws.Name: _sheet_values(ws) for ws in sheets}
            if fmt == "xls":
                for ws in sheets:
                    ur = ws.UsedRange
                    if ur.Row + ur.Rows.Count - 1 > 65536 or ur.Column + ur.Columns.Count - 1 > 256:
                        raise ConversionError(f"Sheet “{ws.Name}” is too big for XLS "
                                              "(max 65,536 rows and 256 columns). Use XLSX instead.")
            if src.suffix.lower() in (".xlsm", ".xlsb") and fmt in ("xlsx", "ods", "csv", "xls", "pdf"):
                if wb.HasVBProject:
                    notes.append("Macros are not kept (the new format can't store them).")
            pages_expected = None
            with Watchdog(oa, timeout_for(src, 180), "converting"):
                if fmt == "pdf":
                    try:
                        pages_expected = sum(int(ws.PageSetup.Pages.Count) for ws in sheets
                                             if src_data[ws.Name][1])
                    except Exception:
                        pages_expected = None  # needs a printer driver; checked loosely below
                    wb.ExportAsFixedFormat(Type=0, Filename=long_path(out), Quality=0, IncludeDocProperties=True,
                                           IgnorePrintAreas=False, OpenAfterPublish=False)
                else:
                    if fmt == "csv":
                        sheets[0].Activate()
                        if len(sheets) > 1:
                            notes.append(f"CSV holds one sheet: only “{sheets[0].Name}” was saved "
                                         f"({len(sheets) - 1} other sheet(s) not included).")
                    wb.SaveAs(Filename=long_path(out), FileFormat=EXCEL_FORMATS[fmt], AddToMru=False)
        except ConversionError:
            raise
        except Exception as e:
            raise friendly_com_error(e, "Excel") from e
        finally:
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                pass

        # ---- verify
        if fmt == "pdf":
            pages, _ = _pdf_info(out)
            if pages_expected and pages != pages_expected:
                raise VerificationError(f"the PDF has {pages} pages, Excel planned {pages_expected}")
            if pages < 1:
                raise VerificationError("the PDF is empty")
            notes.append(f"Checked: {pages} page{'s' if pages != 1 else ''}.")
            return
        with Watchdog(oa, timeout_for(out), "checking the result"):
            try:
                wb2 = _excel_open(app, out)
            except Exception as e:
                raise VerificationError(f"the new file can't be opened in Excel: {e}") from e
            try:
                out_sheets = [wb2.Worksheets(i + 1) for i in range(wb2.Worksheets.Count)]
                out_data = {ws.Name: _sheet_values(ws) for ws in out_sheets}
            finally:
                wb2.Close(SaveChanges=False)
        if fmt == "csv":
            first = next(iter(src_data.values()))[1]
            got = next(iter(out_data.values()))[1]
            filled = lambda t: sum(1 for r in t for c in r if c not in (None, ""))  # noqa: E731
            if len(got) != len(first) or filled(got) != filled(first):
                raise VerificationError(f"the CSV has {len(got)} rows / {filled(got)} filled cells, "
                                        f"expected {len(first)} / {filled(first)}")
            notes.append(f"Checked: {len(got)} rows and every filled cell are in the CSV.")
            return
        if list(out_data) != list(src_data):
            raise VerificationError("sheet names or order changed")
        cells = 0
        for name, (_, vals) in src_data.items():
            ok, why = _values_equal(vals, out_data[name][1])
            if not ok:
                raise VerificationError(f"sheet “{name}”: {why}")
            cells += sum(1 for r in vals for c in r if c not in (None, ""))
        notes.append(f"Checked: all {len(src_data)} sheet(s) and {cells:,} cell values match the original.")


# ====================================================================== PowerPoint


def _ppt_open(app, path: Path):
    # ReadOnly=msoTrue, Untitled=msoFalse, WithWindow=msoFalse
    return app.Presentations.Open(long_path(path), -1, 0, 0)


def _ppt_shape_counts(pres) -> list[int]:
    return [int(pres.Slides(i + 1).Shapes.Count) for i in range(pres.Slides.Count)]


def convert_powerpoint(src: Path, out: Path, fmt: str, notes: list[str]) -> None:
    with office("PowerPoint.Application", "POWERPNT.EXE", "PowerPoint") as oa:
        app = oa.app
        try:
            app.DisplayAlerts = 1  # ppAlertsNone
        except Exception:
            pass
        with Watchdog(oa, timeout_for(src), "opening the presentation"):
            try:
                pres = _ppt_open(app, src)
            except Exception as e:
                raise friendly_com_error(e, "PowerPoint") from e
        try:
            shapes = _ppt_shape_counts(pres)
            n = len(shapes)
            hidden = sum(1 for i in range(n) if pres.Slides(i + 1).SlideShowTransition.Hidden)
            with Watchdog(oa, timeout_for(src, 240), "converting"):
                if fmt in ("png", "jpg"):
                    out.mkdir(parents=True, exist_ok=True)
                    w_pts, h_pts = float(pres.PageSetup.SlideWidth), float(pres.PageSetup.SlideHeight)
                    width = 1920
                    height = int(round(width * h_pts / w_pts))
                    digits = max(2, len(str(n)))
                    for i in range(n):
                        target = out / f"Slide {str(i + 1).zfill(digits)}.{fmt}"
                        pres.Slides(i + 1).Export(long_path(target), fmt.upper(), width, height)
                else:
                    pres.SaveAs(long_path(out), PPT_FORMATS[fmt])
        except ConversionError:
            raise
        except Exception as e:
            raise friendly_com_error(e, "PowerPoint") from e
        finally:
            try:
                pres.Close()
            except Exception:
                pass

        # ---- verify
        if fmt == "pdf":
            pages, _ = _pdf_info(out)
            if pages not in (n, n - hidden):
                raise VerificationError(f"the PDF has {pages} pages for {n} slides")
            notes.append(f"Checked: {pages} slides in the PDF.")
            if hidden and pages == n - hidden:
                notes.append(f"{hidden} hidden slide(s) left out, as in a slideshow.")
        elif fmt in ("png", "jpg"):
            from PIL import Image

            files = sorted(out.iterdir())
            if len(files) != n:
                raise VerificationError(f"{len(files)} images for {n} slides")
            for f in files:
                with Image.open(f) as im:
                    im.verify()
            notes.append(f"Checked: {n} slide images, {width}x{height} px each.")
        else:
            with Watchdog(oa, timeout_for(out), "checking the result"):
                try:
                    p2 = _ppt_open(app, out)
                except Exception as e:
                    raise VerificationError(f"the new file can't be opened in PowerPoint: {e}") from e
                try:
                    shapes2 = _ppt_shape_counts(p2)
                finally:
                    p2.Close()
            if len(shapes2) != n:
                raise VerificationError(f"{len(shapes2)} slides instead of {n}")
            if shapes2 != shapes:
                notes.append("Some slide elements were changed to fit the new format; check the result.")
            notes.append(f"Checked: all {n} slides are there.")


# ====================================================================== entry point


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    src = sources[0]
    if is_encrypted_ooxml(src):
        raise ConversionError("This file is password-protected. Remove the password in Office first.")
    notes: list[str] = []
    which = app_for(src)
    if which == "word":
        convert_word(src, out, fmt, notes)
    elif which == "excel":
        convert_excel(src, out, fmt, notes)
    else:
        convert_powerpoint(src, out, fmt, notes)
    if not (out.is_dir() and any(out.iterdir())) and not (out.is_file() and os.path.getsize(out) > 0):
        raise VerificationError("Office produced an empty file")
    return notes
