"""The conversions added in 1.11: each one offered for the right files, run through the same
worker path as the app, checked, and leaving the original untouched. Tiny generated inputs."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import sqlite3
import uuid
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.catalog import offers_for
from app.jobs import build_jobs
from app.menu import build_menu
from app.settings import Settings
from app.worker import run_job


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def convert(files: list[Path], label: str, options: dict | None = None, ok: bool = True) -> dict:
    offers, _ = offers_for(files, Settings())
    offer = next((o for o in offers if o.target.label == label), None)
    assert offer is not None, f"{label} not offered for {[f.name for f in files]}: {[o.target.label for o in offers]}"
    opts = {o.key: o.default for o in offer.options}
    opts.update(options or {})
    before = {f: _sha(f) for f in files}
    job = build_jobs(offer, opts, Settings())[0]
    job["id"] = uuid.uuid4().hex[:12]
    res = run_job(job)
    assert all(_sha(f) == h for f, h in before.items()), "the original changed"
    if ok:
        assert res["ok"], res.get("error")
        res["path"] = Path(res["output"])
    else:
        assert not res["ok"]
    return res


# ---------------------------------------------------------------- documents without Office

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def make_docx(path: Path) -> Path:
    body = (f'<w:document {W_NS}><w:body>'
            '<w:p><w:pPr><w:pStyle w:val="H1"/></w:pPr><w:r><w:t>Trip plan</w:t></w:r></w:p>'
            '<w:p><w:r><w:t xml:space="preserve">We leave on </w:t></w:r><w:r><w:rPr><w:b/></w:rPr>'
            '<w:t>Friday</w:t></w:r><w:r><w:t xml:space="preserve"> morning with the whole family.</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Tickets'
            '</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Snacks'
            '</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Day</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Place</w:t>'
            '</w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>Saturday</w:t></w:r></w:p></w:tc><w:tc><w:p>'
            '<w:r><w:t>Hampi</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
            '</w:body></w:document>')
    styles = (f'<w:styles {W_NS}><w:style w:type="paragraph" w:styleId="H1"><w:name w:val="heading 1"/>'
              '</w:style></w:styles>')
    numbering = (f'<w:numbering {W_NS}><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt '
                 'w:val="decimal"/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
                 '</w:numbering>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", body)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/numbering.xml", numbering)
    return path


def make_odt(path: Path) -> Path:
    content = ('<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
               'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
               'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"><office:body><office:text>'
               '<text:h text:outline-level="2">Shopping</text:h><text:p>Buy fresh <text:span>mangoes</text:span> '
               'and rice for the week.</text:p><text:list><text:list-item><text:p>Mangoes</text:p></text:list-item>'
               '<text:list-item><text:p>Rice</text:p></text:list-item></text:list></office:text></office:body>'
               '</office:document-content>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", content)
    return path


@pytest.mark.parametrize("label", ["Markdown", "HTML"])
def test_docx_without_office(tmp_path, label):
    out = convert([make_docx(tmp_path / "Trip.docx")], label)["path"]
    text = out.read_text(encoding="utf-8")
    for w in ("Trip plan", "Friday", "Tickets", "Hampi"):
        assert w in text
    if label == "Markdown":
        assert "# Trip plan" in text and "**Friday**" in text and "1. Tickets" in text and "| Day | Place |" in text
    else:
        assert "<h1>Trip plan</h1>" in text and "<strong>Friday</strong>" in text and "<ol>" in text


def test_odt_without_office(tmp_path):
    out = convert([make_odt(tmp_path / "List.odt")], "Markdown")["path"]
    text = out.read_text(encoding="utf-8")
    assert "## Shopping" in text and "mangoes" in text and "- Rice" in text


def test_not_a_word_file(tmp_path):
    bad = tmp_path / "Old.docx"
    bad.write_bytes(b"\xd0\xcf\x11\xe0 an old binary document")
    assert "can read" in convert([bad], "Markdown", ok=False)["error"]


# ---------------------------------------------------------------- Apple iWork

def test_pages_preview(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(buf, "JPEG")
    pages = tmp_path / "Letter.pages"
    with zipfile.ZipFile(pages, "w") as z:
        z.writestr("Index/Document.iwa", b"\x00" * 20)
        z.writestr("preview.jpg", buf.getvalue())
    jpg = convert([pages], "Picture")["path"]
    assert jpg.read_bytes() == buf.getvalue()  # exactly as Apple saved it
    pdf = convert([pages], "PDF")["path"]
    import pymupdf

    with pymupdf.open(pdf) as d:
        assert d.page_count == 1


def test_keynote_full_pdf(tmp_path):
    import pymupdf

    src = pymupdf.open()
    for i in range(3):
        src.new_page().insert_text((72, 72), f"Slide {i + 1}")
    key = tmp_path / "Talk.key"
    with zipfile.ZipFile(key, "w") as z:
        z.writestr("QuickLook/Preview.pdf", src.tobytes())
    with pymupdf.open(convert([key], "PDF")["path"]) as d:
        assert d.page_count == 3


# ---------------------------------------------------------------- PDF

def make_table_pdf(path: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    rows = [["Item", "Qty", "Price"], ["Apple", "3", "1.20"], ["Pear", "10", "0.80"]]
    for r, row in enumerate(rows):  # bordered cells, the way Word and Excel export tables
        for c, val in enumerate(row):
            rect = pymupdf.Rect(72 + c * 120, 100 + r * 24, 192 + c * 120, 124 + r * 24)
            page.draw_rect(rect, color=(0, 0, 0), width=0.75)
            page.insert_textbox(rect + (4, 5, -4, 0), val, fontsize=10)
    doc.new_page()  # a blank page
    doc.new_page().insert_text((72, 72), "Last page")
    doc.save(path)
    return path


def test_pdf_tables_to_excel(tmp_path):
    from openpyxl import load_workbook

    out = convert([make_table_pdf(tmp_path / "Prices.pdf")], "Tables")["path"]
    wb = load_workbook(out, read_only=True)
    rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    wb.close()
    assert rows == [["Item", "Qty", "Price"], ["Apple", 3, "1.20"], ["Pear", 10, "0.80"]]  # 1.20 as written


def test_pdf_remove_blank_pages(tmp_path):
    import pymupdf

    out = convert([make_table_pdf(tmp_path / "Prices.pdf")], "Remove blank")["path"]
    with pymupdf.open(out) as d:
        assert d.page_count == 2 and "Last page" in d[1].get_text()


def test_pdf_without_blank_pages_says_so(tmp_path):
    import pymupdf

    p = tmp_path / "Full.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Only page")
    doc.save(p)
    assert "no blank pages" in convert([p], "Remove blank", ok=False)["error"]


# ---------------------------------------------------------------- pictures

@pytest.fixture
def photo(tmp_path) -> Path:
    p = tmp_path / "Holiday.jpg"
    im = Image.new("RGB", (1200, 800))
    for x in range(0, 1200, 40):
        im.paste((x % 255, 120, 200 - x % 200), (x, 0, x + 40, 800))
    im.save(p, quality=95)
    return p


@pytest.mark.parametrize("ratio,size", [("1:1 square", (800, 800)), ("9:16 story", (450, 800)),
                                        ("4:5 portrait", (640, 800))])
def test_crop_to_shape(photo, ratio, size):
    out = convert([photo], "Crop", {"ratio": ratio})["path"]
    with Image.open(out) as im:
        assert im.size == size and im.format == "JPEG"


def test_passport_sheet(photo):
    out = convert([photo], "Passport sheet")["path"]
    with Image.open(out) as im:
        assert im.size == (1800, 1200) and round(im.info["dpi"][0]) == 300
    out = convert([photo], "Passport sheet", {"size": "2×2 inch (US)"})["path"]
    with Image.open(out) as im:
        assert im.size == (1200, 1800)


@pytest.mark.parametrize("where", ["Across the middle", "Bottom right corner"])
def test_watermark(photo, tmp_path, where):
    png = tmp_path / "Logo.png"
    Image.new("RGBA", (500, 300), (10, 120, 200, 255)).save(png)
    for src in (photo, png):
        out = convert([src], "Watermark", {"text": "© Asha 2026", "position": where})["path"]
        with Image.open(out) as a, Image.open(src) as b:
            assert a.size == b.size and a.format == b.format
            assert a.convert("RGB").tobytes() != b.convert("RGB").tobytes()


# ---------------------------------------------------------------- data

def test_sqlite_to_excel_and_csv(tmp_path):
    from openpyxl import load_workbook

    db = tmp_path / "Shop.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE items (id INTEGER, name TEXT, price REAL, pic BLOB, code INTEGER)")
    con.executemany("INSERT INTO items VALUES (?,?,?,?,?)",
                    [(1, "Tea", 2.5, b"\x89PNG....", 1234567890123456789), (2, "=SUM(A1)", None, None, 7)])
    con.execute("CREATE TABLE notes (body TEXT)")
    con.execute("INSERT INTO notes VALUES ('hello')")
    con.commit()
    con.close()
    out = convert([db], "XLSX")["path"]
    wb = load_workbook(out, read_only=True)
    sheets = {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    wb.close()
    assert sheets["items"][1] == [1, "Tea", 2.5, "(binary, 8 bytes)", "1234567890123456789"]
    assert sheets["items"][2][1] == "=SUM(A1)"  # text, never a formula
    folder = convert([db], "CSV per table")["path"]
    assert sorted(p.name for p in folder.iterdir()) == ["items.csv", "notes.csv"]


def test_not_a_database(tmp_path):
    thumbs = tmp_path / "pictures.db"
    thumbs.write_bytes(b"\x00" * 64)
    assert "isn't a SQLite database" in convert([thumbs], "XLSX", ok=False)["error"]


def test_settings_files(tmp_path):
    ini = tmp_path / "app.ini"
    ini.write_text("; comment\n[server]\nHost = example.com\nport=8080\n\n[paths]\nhome: C:\\Users\\a\n",
                   encoding="utf-8")
    assert json.loads(convert([ini], "JSON")["path"].read_text(encoding="utf-8")) == {
        "server": {"Host": "example.com", "port": "8080"}, "paths": {"home": "C:\\Users\\a"}}
    env = tmp_path / ".env"
    env.write_text('# keys\nexport API_URL=https://x.test # live\nNAME="Asha \\"A\\" Rao"\nEMPTY=\n'
                   "MULTI='line one\nline two'\n", encoding="utf-8")
    assert json.loads(convert([env], "JSON")["path"].read_text(encoding="utf-8")) == {
        "API_URL": "https://x.test", "NAME": 'Asha "A" Rao', "EMPTY": "", "MULTI": "line one\nline two"}
    props = tmp_path / "messages.properties"
    props.write_text("greeting = Hello \\\n    world\npath=C:\\\\temp\nname: caf\\u00e9\n", encoding="utf-8")
    import yaml

    assert yaml.safe_load(convert([props], "YAML")["path"].read_text(encoding="utf-8")) == {
        "greeting": "Hello world", "path": "C:\\temp", "name": "café"}


def test_calendar(tmp_path):
    ics = tmp_path / "Family.ics"
    ics.write_text("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nSUMMARY:Dentist\\, Asha\r\n"
                   "DTSTART;TZID=Asia/Kolkata:20261120T093000\r\nDTEND;TZID=Asia/Kolkata:20261120T100000\r\n"
                   "LOCATION:Clinic\r\nDESCRIPTION:Bring the old\r\n  x-ray\\nand the card\r\nBEGIN:VALARM\r\n"
                   "DESCRIPTION:Reminder\r\nEND:VALARM\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nSUMMARY:Diwali\r\n"
                   "DTSTART;VALUE=DATE:20261108\r\nRRULE:FREQ=YEARLY\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n",
                   encoding="utf-8", newline="")  # exactly these line endings
    import csv

    with open(convert([ics], "CSV")["path"], encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["Title"] for r in rows] == ["Diwali", "Dentist, Asha"]
    assert rows[0]["All day"] == "yes" and rows[0]["Repeats"] == "yearly"
    assert rows[1]["Start"] == "2026-11-20 09:30" and rows[1]["Time zone"] == "Asia/Kolkata"
    assert rows[1]["Description"] == "Bring the old x-ray\nand the card"
    convert([ics], "XLSX")


def test_notebook(tmp_path):
    png = io.BytesIO()
    Image.new("RGB", (20, 10), "red").save(png, "PNG")
    nb = {"nbformat": 4, "metadata": {"kernelspec": {"language": "python"}}, "cells": [
        {"cell_type": "markdown", "source": ["# Sales\n", "Monthly **totals** for the shop."]},
        {"cell_type": "code", "source": "total = sum([3, 4])\nprint(total)",
         "outputs": [{"output_type": "stream", "text": ["7\n"]},
                     {"output_type": "display_data", "data": {"image/png": base64.b64encode(png.getvalue()).decode(),
                                                              "text/plain": "<Figure>"}}]}]}
    p = tmp_path / "Sales.ipynb"
    p.write_text(json.dumps(nb), encoding="utf-8")
    page = convert([p], "HTML")["path"].read_text(encoding="utf-8")
    assert "Sales" in page and "total = sum" in page and "data:image/png;base64," in page
    md = convert([p], "Markdown")["path"].read_text(encoding="utf-8")
    assert "```python\ntotal = sum([3, 4])" in md and "```text\n7\n```" in md
    py = convert([p], "Python")["path"].read_text(encoding="utf-8")
    assert "# %% [markdown]\n# # Sales" in py and "print(total)" in py


# ---------------------------------------------------------------- subtitles, checksums

def test_subtitle_shift(tmp_path):
    srt = tmp_path / "Film.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:02,000\nHello\n\n2\n00:00:10,000 --> 00:00:12,500\nBye\n",
                   encoding="utf-8")
    later = convert([srt], "Shift timing", {"seconds": "+2.5"})["path"].read_text(encoding="utf-8")
    assert "00:00:03,000 --> 00:00:04,500" in later and later.count("-->") == 2
    earlier = convert([srt], "Shift timing", {"seconds": "-1"})
    assert "00:00:00,000 --> 00:00:01,000" in earlier["path"].read_text(encoding="utf-8")
    assert any("0:00" in n for n in earlier["notes"])
    from app.toolbox import validate
    from app.catalog import Option

    opt = Option("seconds", "Seconds", "text", "", validate="shift")
    assert validate(opt, "abc") and validate(opt, "0") and validate(opt, "+1,5 s") is None


def test_checksum(tmp_path):
    a = tmp_path / "photo.jpg"
    a.write_bytes(b"pixels" * 1000)
    out = convert([a], "Checksum")["path"]
    assert out.name == "photo.jpg.sha256"
    assert out.read_text() == f"{hashlib.sha256(a.read_bytes()).hexdigest()} *photo.jpg\n"
    b = tmp_path / "notes.txt"
    b.write_text("hi")
    two = convert([a, b], "Checksum")["path"]
    assert len(two.read_text().splitlines()) == 2


# ---------------------------------------------------------------- the picker still builds for every new kind

def test_picker_builds_for_new_kinds(tmp_path):
    for name in ("a.docx", "b.odt", "c.pages", "d.numbers", "e.key", "f.db", "g.ini", ".env", "h.properties",
                 "i.ics", "j.ipynb", "k.srt", "l.pdf", "m.jpg"):
        nodes, _quick, left_out = build_menu([tmp_path / name], Settings())
        assert nodes and not left_out, name


# ---------------------------------------------------------------- LibreOffice, when Office isn't installed

def test_libreoffice_does_office_files_when_office_is_missing(tmp_path, monkeypatch):
    """A stand-in soffice (it behaves like LibreOffice's command line) checks the whole path: the offers,
    the command, the private profile, and the checks on the result. The real LibreOffice isn't needed."""
    import sys

    from app import catalog
    from app.engines import libre

    fake = tmp_path / "fake_soffice.py"
    fake.write_text(
        "import sys, pathlib, pymupdf\n"
        "a = sys.argv[1:]\n"
        "assert '--headless' in a and any(x.startswith('-env:UserInstallation=file:') for x in a)\n"
        "filt = a[a.index('--convert-to') + 1]; outdir = pathlib.Path(a[a.index('--outdir') + 1]); src = pathlib.Path(a[-1])\n"
        "assert filt == 'pdf:writer_pdf_Export', filt\n"
        "d = pymupdf.open(); p = d.new_page(); p.insert_text((72, 72), src.read_text(encoding='utf-8'))\n"
        "d.save(str(outdir / (src.stem + '.pdf')))\n", encoding="utf-8")
    cmd = tmp_path / "soffice.cmd"
    cmd.write_text(f'@"{sys.executable}" "{fake}" %*\n', encoding="utf-8")
    monkeypatch.setattr(libre, "_found", [str(cmd)])
    monkeypatch.setattr(catalog, "office_installed", lambda kind: False)
    doc = tmp_path / "Letter.txt"
    doc.write_text("Dear neighbours, the garden party moves to Sunday because of the forecast rain.", encoding="utf-8")
    offers, _ = catalog.offers_for([doc], Settings())
    pdf = next(o for o in offers if o.target.key == "doc.pdf")
    assert any("LibreOffice" in w for w in pdf.warnings)
    job = build_jobs(pdf, {o.key: o.default for o in pdf.options}, Settings())[0]
    job["id"] = uuid.uuid4().hex[:12]
    res = run_job(job)
    assert res["ok"], res.get("error")
    assert any("LibreOffice" in n for n in res["notes"]) and Path(res["output"]).suffix == ".pdf"


# ---------------------------------------------------------------- PDF to Word (made by Deskvert, no Office needed)

def _report_pdf(path: Path, scanned: bool = False) -> Path:
    import pymupdf

    d = pymupdf.open()
    p = d.new_page()
    if scanned:  # only a picture of a page: no text to rebuild
        buf = io.BytesIO()
        Image.new("RGB", (300, 400), "white").save(buf, "PNG")
        p.insert_image(p.rect, stream=buf.getvalue())
    else:
        p.insert_text((72, 60), "Sales by region", fontsize=20)
        p.insert_text((72, 92), "A paragraph above the table with ordinary words in it.", fontsize=11)
        p.insert_text((72, 110), "\u2022 First point about growth", fontsize=11)
        rows = [("Region", "Sales"), ("North", "1.20"), ("South", "3.45")]
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                rect = pymupdf.Rect(72 + c * 120, 130 + r * 22, 192 + c * 120, 152 + r * 22)
                p.draw_rect(rect, color=(0, 0, 0), width=0.8)
                p.insert_text((rect.x0 + 5, rect.y1 - 7), val, fontsize=10)
        buf = io.BytesIO()
        Image.new("RGB", (200, 100), "teal").save(buf, "PNG")
        p.insert_image(pymupdf.Rect(72, 230, 272, 330), stream=buf.getvalue())
        d.new_page().insert_text((72, 80), "Second page with a few more words.", fontsize=11)
    d.save(str(path))
    return path


def test_pdf_to_word(tmp_path):
    from app.engines.pdfword import docx_text

    src = _report_pdf(tmp_path / "report.pdf")
    res = convert([src], "DOCX")
    out = res["path"]
    assert out.suffix == ".docx" and out.name == "report.docx"
    text = docx_text(out)
    for words in ("Sales by region", "ordinary words", "First point about growth", "North", "3.45", "Second page"):
        assert words in text
    with zipfile.ZipFile(out) as z:
        doc = z.read("word/document.xml").decode()
        assert any(n.startswith("word/media/") for n in z.namelist())  # the picture is inside
    assert 'w:val="Heading1"' in doc and "<w:tbl>" in doc and 'w:type="page"' in doc and "<w:numPr>" in doc
    assert "1 picture" in " ".join(res["notes"]) and "1 table" in " ".join(res["notes"])


def test_scanned_pdf_to_word_says_read_text_first(tmp_path):
    res = convert([_report_pdf(tmp_path / "scan.pdf", scanned=True)], "DOCX", ok=False)
    assert "Read text" in res["error"]


# ---------------------------------------------------------------- pictures traced into SVG

def _logo(path: Path) -> Path:
    from PIL import ImageDraw

    im = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 180, 180), fill=(22, 128, 86, 255))
    d.rectangle((70, 70, 130, 130), fill=(255, 255, 255, 255))
    d.rectangle((220, 60, 380, 140), fill=(30, 30, 30, 255))
    im.save(path)
    return path


@pytest.mark.parametrize("style", ["Colour", "Black and white"])
def test_picture_to_svg(tmp_path, style):
    res = convert([_logo(tmp_path / "logo.png")], "SVG", {"style": style})
    out = res["path"]
    assert out.name == "logo (traced).svg"
    svg = out.read_text(encoding="utf-8")
    assert svg.lstrip().startswith(("<?xml", "<svg")) and svg.count("<path") >= 2
    if style == "Colour":
        assert "rgb(22,128,86)" in svg.replace(" ", "") or "#168056" in svg.lower()
    assert "Checked:" in res["notes"][0]


def test_smooth_shading_is_not_traced(tmp_path):
    src = tmp_path / "glow.png"
    Image.radial_gradient("L").resize((300, 300)).convert("RGB").save(src)
    res = convert([src], "SVG", ok=False)
    assert "logos, icons and drawings" in res["error"]


# ---------------------------------------------------------------- Shapefiles (read without extra libraries)

def _shapefile(folder: Path, shapes: list[tuple[int, list]], rows: list[dict], prj: str | None = None) -> Path:
    """A minimal .shp + .dbf (+ .prj): shapes are (type, parts), parts a list of [(x, y), ...]."""
    import struct

    recs = b""
    for i, (kind, parts) in enumerate(shapes, 1):
        if kind == 1:
            body = struct.pack("<i2d", 1, *parts[0][0])
        else:
            pts = [p for part in parts for p in part]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            body = struct.pack("<i4d2i", kind, min(xs), min(ys), max(xs), max(ys), len(parts), len(pts))
            start = 0
            for part in parts:
                body += struct.pack("<i", start)
                start += len(part)
            body += b"".join(struct.pack("<2d", *p) for p in pts)
        recs += struct.pack(">2i", i, len(body) // 2) + body
    kind0 = shapes[0][0]
    header = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(recs)) // 2) + struct.pack("<2i4d4d", 1000, kind0,
                                                                                          0, 0, 0, 0, 0, 0, 0, 0)
    (folder / "places.shp").write_bytes(header + recs)
    fields = [("NAME", "C", 20, 0), ("POP", "N", 10, 0)]
    hdr_len = 32 + 32 * len(fields) + 1
    rec_len = 1 + sum(f[2] for f in fields)
    dbf = struct.pack("<BBBBIHH20x", 3, 126, 1, 1, len(rows), hdr_len, rec_len)
    for name, typ, length, dec in fields:
        dbf += name.encode().ljust(11, b"\0") + typ.encode() + b"\0" * 4 + bytes([length, dec]) + b"\0" * 14
    dbf += b"\r"
    for r in rows:
        dbf += b" " + r["NAME"].encode("utf-8").ljust(20) + str(r["POP"]).encode().rjust(10)
    (folder / "places.dbf").write_bytes(dbf + b"\x1a")
    (folder / "places.cpg").write_text("UTF-8")
    if prj:
        (folder / "places.prj").write_text(prj)
    return folder / "places.shp"


def test_shapefile_to_geojson_with_details(tmp_path):
    square = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]  # clockwise: an outer edge
    hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]  # counter-clockwise: a hole
    shp = _shapefile(tmp_path, [(5, [square, hole])], [{"NAME": "Parc Café", "POP": 1200}],
                     prj='GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]]]')
    res = convert([shp], "GeoJSON")
    data = json.loads(res["path"].read_text(encoding="utf-8"))
    f = data["features"][0]
    assert f["properties"] == {"NAME": "Parc Café", "POP": 1200}
    assert f["geometry"]["type"] == "Polygon" and len(f["geometry"]["coordinates"]) == 2  # the edge and its hole


def test_shapefile_points_from_utm_and_web_mercator(tmp_path):
    from app.engines.shapefile import _utm, _web_mercator

    lon, lat = _utm(33, False)(500000.0, 4649776.22)  # zone 33N central meridian, 42° north
    assert abs(lon - 15.0) < 1e-6 and abs(lat - 42.0) < 1e-5
    lon, lat = _web_mercator(20037508.342789244, 0.0)
    assert abs(lon - 180.0) < 1e-9 and abs(lat) < 1e-9
    utm = 'PROJCS["WGS_1984_UTM_Zone_33N",GEOGCS["GCS_WGS_1984"],PROJECTION["Transverse_Mercator"]]'
    shp = _shapefile(tmp_path, [(1, [[(500000.0, 4649776.22)]])], [{"NAME": "Pin", "POP": 1}], prj=utm)
    res = convert([shp], "KML")
    assert "15.0" in res["path"].read_text(encoding="utf-8") and any("UTM zone 33N" in n for n in res["notes"])


def test_shapefile_in_an_unknown_projection_is_refused(tmp_path):
    lambert = 'PROJCS["RGF93_Lambert_93",GEOGCS["GCS_RGF_1993"],PROJECTION["Lambert_Conformal_Conic"]]'
    shp = _shapefile(tmp_path, [(1, [[(700000.0, 6600000.0)]])], [{"NAME": "Paris", "POP": 2}], prj=lambert)
    res = convert([shp], "GeoJSON", ok=False)
    assert "Lambert_93" in res["error"]


# ---------------------------------------------------------------- SCC closed captions (TV captions) into subtitles

def _scc_word(b1: int, b2: int) -> str:
    odd = lambda b: b | (0x80 if bin(b).count("1") % 2 == 0 else 0)  # noqa: E731 - each byte has odd parity
    return f"{odd(b1):02x}{odd(b2):02x}"


def _scc_text(s: str) -> list[str]:
    s = s + ("\0" if len(s) % 2 else "")
    return [_scc_word(ord(s[i]), ord(s[i + 1]) if s[i + 1] != "\0" else 0) for i in range(0, len(s), 2)]


def _scc(path: Path, body: list[tuple[str, list[str]]]) -> Path:
    lines = ["Scenarist_SCC V1.0", ""]
    for tc, words in body:
        lines += [f"{tc}\t{' '.join(words)}", ""]
    path.write_text("\n".join(lines), encoding="ascii")
    return path


def test_scc_pop_on_captions_to_srt(tmp_path):
    RCL, ENM, EOC, EDM, PAC15 = (0x14, 0x20), (0x14, 0x2E), (0x14, 0x2F), (0x14, 0x2C), (0x14, 0x70)
    twice = lambda c: [_scc_word(*c), _scc_word(*c)]  # noqa: E731 - commands are sent twice
    src = _scc(tmp_path / "show.scc", [
        ("00:00:01;00", twice(RCL) + twice(ENM) + twice(PAC15) + _scc_text("Hello there.") + twice(EOC)),
        ("00:00:04;00", twice(RCL) + twice(ENM) + twice(PAC15) + [_scc_word(0x11, 0x37)] + _scc_text(" Music ")
         + [_scc_word(0x11, 0x37)] + twice(EOC)),
        ("00:00:06;00", _scc_text("Cafe") + [_scc_word(0x12, 0x21)] + twice(EDM)),  # é replaces e, then the screen clears
    ])
    from app.engines.subtitle import parse

    out = convert([src], "SRT")["path"]
    cues = parse(out.read_text(encoding="utf-8"), "srt")
    assert [c[2] for c in cues] == ["Hello there.", "♪ Music ♪"]
    assert abs(cues[0][0] - 1450) < 120 and abs(cues[0][1] - cues[1][0]) <= 1  # shown on End Of Caption, ~1.45 s
    assert abs(cues[1][1] - 6200) < 200  # until the screen is erased


def test_scc_roll_up_lines(tmp_path):
    RU2, CR = (0x14, 0x25), (0x14, 0x2D)
    twice = lambda c: [_scc_word(*c), _scc_word(*c)]  # noqa: E731
    src = _scc(tmp_path / "news.scc", [
        ("00:00:10:00", twice(RU2) + _scc_text("FIRST LINE") + twice(CR)),
        ("00:00:12:00", _scc_text("SECOND LINE") + twice(CR)),
    ])
    out = convert([src], "WebVTT")["path"]
    text = out.read_text(encoding="utf-8")
    assert "FIRST LINE" in text and "SECOND LINE" in text


def test_not_an_scc_file(tmp_path):
    bad = tmp_path / "x.scc"
    bad.write_text("hello", encoding="ascii")
    assert "Scenarist" in convert([bad], "SRT", ok=False)["error"]


# ---------------------------------------------------------------- WOFF2 web fonts

@pytest.fixture
def arial(tmp_path):
    import os
    import shutil

    src = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts" / "arial.ttf"
    if not src.exists():
        pytest.skip("Arial isn't on this PC")
    dst = tmp_path / "Arial.ttf"
    shutil.copyfile(src, dst)
    return dst


def test_woff2_round_trip(arial, tmp_path):
    res = convert([arial], "WOFF2")
    woff2 = res["path"]
    assert woff2.read_bytes()[:4] == b"wOF2" and woff2.stat().st_size < arial.stat().st_size * 0.7
    assert "every glyph" in res["notes"][0]
    back = convert([woff2], "TTF / OTF")["path"]
    from fontTools.ttLib import TTFont

    a, b = TTFont(str(arial)), TTFont(str(back))
    assert a.getGlyphOrder() == b.getGlyphOrder() and a.getBestCmap() == b.getBestCmap()


def test_woff_to_woff2(arial):
    woff = convert([arial], "WOFF")["path"]
    assert convert([woff], "WOFF2")["path"].read_bytes()[:4] == b"wOF2"
