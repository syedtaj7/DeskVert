"""Small sample documents, created once with the installed Office (and PyMuPDF
for PDFs) and cached, so test runs don't keep launching Office to build them."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

VERSION = "v2"
NAMES = ["report.docx", "protected.docx", "notes.txt", "budget.xlsx", "deck.pptx", "sample.pdf", "second.pdf",
         "scanned.pdf", "broken.docx"]


def cache_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home()), "Deskvert", f"test-docs-{VERSION}")


def _pdfs(folder: Path) -> None:
    import pymupdf

    for name, pages in (("sample.pdf", 3), ("second.pdf", 2)):
        d = pymupdf.open()
        for i in range(pages):
            pg = d.new_page()
            pg.insert_text((72, 90), f"{name} page {i + 1}", fontsize=20)
            pg.insert_text((72, 130), "The quick brown fox jumps over the lazy dog. Conversion accuracy matters.",
                           fontsize=11)
            pg.insert_text((72, 150), f"Invoice number {1000 + i} total amount {42.5 * (i + 1):.2f} dollars.", fontsize=11)
        d.save(str(folder / name))
        d.close()
    d = pymupdf.open()  # a "scanned" PDF: only a picture, no text
    pg = d.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100), False)
    pix.set_rect(pix.irect, (200, 200, 200))
    pg.insert_image(pymupdf.Rect(72, 72, 272, 172), pixmap=pix)
    d.save(str(folder / "scanned.pdf"))
    d.close()


def build() -> dict[str, Path]:
    folder = cache_dir()
    if (folder / "done").exists():
        return {n: folder / n for n in NAMES}
    from app.engines.officeutil import office

    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text("Meeting notes\n\nAgenda: budget review, hiring plan, launch date.\n"
                                      "Decision: ship the converter after verification passes.\n", encoding="utf-8")
    (folder / "broken.docx").write_bytes(b"PK\x03\x04 this is not really a Word file")
    _pdfs(folder)

    with office("Word.Application", "WINWORD.EXE", "Word") as oa:
        app = oa.app
        app.Visible = False
        app.DisplayAlerts = 0
        doc = app.Documents.Add()
        rng = doc.Content
        for i in range(1, 4):
            rng.InsertAfter(f"Chapter {i}: Quarterly results\r")
            for _ in range(12):
                rng.InsertAfter("Revenue grew steadily while operating costs remained stable across every region. "
                                "Customers praised reliability, speed and the careful verification of each file. ")
                rng.InsertAfter("\r")
            rng.InsertAfter("\f" if i < 3 else "")
        doc.Paragraphs(1).Style = -2  # wdStyleHeading1
        doc.SaveAs2(str(folder / "report.docx"), 16)
        doc.Password = "secret"  # password to open -> the file gets encrypted
        doc.SaveAs2(str(folder / "protected.docx"), 16)
        doc.Close(0)

    with office("Excel.Application", "EXCEL.EXE", "Excel") as oa:
        app = oa.app
        app.Visible = False
        app.DisplayAlerts = False
        wb = app.Workbooks.Add()
        ws = wb.Worksheets(1)
        ws.Name = "Sales"
        ws.Range("A1:D1").Value = ("Region", "Units", "Price", "Total")
        for r, (reg, u, p) in enumerate([("North", 120, 9.99), ("South", 85, 12.5), ("East", 240, 7.25),
                                         ("West", 60, 20.0)], start=2):
            ws.Range(f"A{r}:C{r}").Value = (reg, u, p)
            ws.Range(f"D{r}").Formula = f"=B{r}*C{r}"
        ws2 = wb.Worksheets.Add(After=ws)
        ws2.Name = "Notes"
        ws2.Range("A1").Value = "Prepared by the finance team"
        ws2.Range("B3").Value = 0.1 + 0.2
        wb.SaveAs(str(folder / "budget.xlsx"), 51)
        wb.Close(False)

    with office("PowerPoint.Application", "POWERPNT.EXE", "PowerPoint") as oa:
        app = oa.app
        pres = app.Presentations.Add(0)  # no window
        for i in range(1, 4):
            s = pres.Slides.Add(i, 2)  # ppLayoutText
            s.Shapes(1).TextFrame.TextRange.Text = f"Slide {i} title"
            s.Shapes(2).TextFrame.TextRange.Text = "Point one\rPoint two\rPoint three"
        pres.Slides(3).SlideShowTransition.Hidden = -1
        pres.SaveAs(str(folder / "deck.pptx"), 24)
        pres.Close()

    (folder / "done").write_text("ok")
    return {n: folder / n for n in NAMES}
