"""`Deskvert.exe --selftest <folder>`: runs real conversions through the same
worker processes the app uses, and writes selftest.json into <folder>.
Used to check a built release (everything bundled, workers start, engines work)."""

from __future__ import annotations

import json
import os
import multiprocessing as mp
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def _avi(path: Path, w: int = 96, h: int = 64, n: int = 20, fps: int = 10) -> Path:
    """A tiny uncompressed AVI (a red bar that grows), for the video-still check."""
    import struct

    row = w * 3
    pad = (4 - row % 4) % 4
    size = (row + pad) * h
    frames = [(bytes((40, 40, 40)) * w + b"\0" * pad) * (h // 2)
              + (bytes((0, 0, min(255, i * 12))) * w + b"\0" * pad) * (h - h // 2) for i in range(n)]

    def chunk(tag, data):
        return tag + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")

    avih = struct.pack("<IIIIIIIIIIIIII", 1000000 // fps, size * fps, 0, 0x10, n, 0, 1, size, w, h, 0, 0, 0, 0)
    strh = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"vids", b"DIB ", 0, 0, 0, 0, 1, fps, 0, n, size, 0xFFFFFFFF, 0,
                       0, 0, w, h)
    strf = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, size, 0, 0, 0, 0)
    strl = chunk(b"LIST", b"strl" + chunk(b"strh", strh) + chunk(b"strf", strf))
    hdrl = chunk(b"LIST", b"hdrl" + chunk(b"avih", avih) + strl)
    movi = chunk(b"LIST", b"movi" + b"".join(chunk(b"00db", f) for f in frames))
    idx, off = b"", 4
    for f in frames:
        idx += struct.pack("<4sIII", b"00db", 0x10, off, len(f))
        off += 8 + len(f) + (len(f) % 2)
    body = b"AVI " + hdrl + movi + chunk(b"idx1", idx)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def _make_extras(folder: Path) -> dict[str, Path]:
    """Small files for the everyday tools: a CSV, JSON, Markdown and a picture of text."""
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    files = {"csv": folder / "Prices.csv", "json": folder / "Settings.json", "md": folder / "Read me.md",
             "scan": folder / "Receipt.png", "srt": folder / "Film.srt", "yaml": folder / "Config.yaml",
             "epub": folder / "Story.epub", "geo": folder / "Places.geojson", "obj": folder / "Cube.obj",
             "dxf": folder / "Plan.dxf", "eml": folder / "Hello.eml", "csvpeople": folder / "People.csv",
             "wav": folder / "Tone.wav"}
    import math
    import struct
    import wave

    with wave.open(str(files["wav"]), "wb") as w:  # 2 seconds of a quiet tone
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 22050)))
                               for i in range(22050 * 2)))
    files["geo"].write_text('{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point",'
                            '"coordinates":[77.59,12.97]},"properties":{"name":"Bengaluru"}}]}', encoding="utf-8")
    cube_v = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    cube_f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7),
              (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    files["obj"].write_text("".join(f"v {x} {y} {z}\n" for x, y, z in cube_v) +
                            "".join(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in cube_f), encoding="utf-8")
    files["dxf"].write_text("\n".join(["0", "SECTION", "2", "ENTITIES", "0", "LINE", "8", "0", "10", "0", "20", "0",
                                       "11", "50", "21", "0", "0", "CIRCLE", "8", "0", "10", "25", "20", "10", "40",
                                       "8", "0", "TEXT", "8", "0", "10", "5", "20", "25", "40", "4", "1", "Room",
                                       "0", "ENDSEC", "0", "EOF"]) + "\n", encoding="utf-8")
    files["eml"].write_bytes(b"From: Asha <asha@example.com>\r\nTo: ravi@example.com\r\nSubject: Hello\r\n"
                             b"Content-Type: text/plain; charset=utf-8\r\n\r\nHi Ravi, the trip photos are ready. "
                             b"See you on Sunday at the station.\r\n")
    files["csvpeople"].write_text("Name,Phone,Email\nAsha Rao,+91 98765 43210,asha@example.com\n", encoding="utf-8")
    files["srt"].write_text("1\n00:00:01,000 --> 00:00:03,500\n<i>Hello</i> there\n\n"
                            "2\n00:01:02,250 --> 00:01:04,000\nSecond line\n", encoding="utf-8")
    files["yaml"].write_text("name: Deskvert\nprice: 0.10\nreleased: 2026-11-09\nusers:\n  - {id: 1}\n  - {id: 2}\n",
                             encoding="utf-8")
    import zipfile

    with zipfile.ZipFile(files["epub"], "w") as z:  # a tiny EPUB 2 book
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:'
                   'tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="c.opf" media-type="application/'
                   'oebps-package+xml"/></rootfiles></container>')
        z.writestr("c.opf", '<?xml version="1.0"?><package version="2.0" xmlns="http://www.idpf.org/2007/opf" '
                   'unique-identifier="i"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Story'
                   '</dc:title><dc:identifier id="i">s1</dc:identifier><dc:language>en</dc:language></metadata>'
                   '<manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/></manifest><spine>'
                   '<itemref idref="a"/></spine></package>')
        z.writestr("a.xhtml", '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Chapter'
                   '</h1><p>' + " ".join(f"Line {i} of a quiet story about a river." for i in range(60)) +
                   '</p></body></html>')
    files["csv"].write_text("item,qty,price\nApple,3,1.20\nPear,10,0.8\n", encoding="utf-8")
    files["json"].write_text('{"name":"Deskvert","tools":["zip","ocr"],"ratio":1.10}', encoding="utf-8")
    files["md"].write_text("# Read me\n\nA **short** document with a list:\n\n- one\n- two\n", encoding="utf-8")
    img = QImage(1400, 500, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setPen(QColor("black"))
    p.setFont(QFont("Arial", 40))
    for i, line in enumerate(("Corner Bakery receipt", "Two coffees and one croissant", "Total paid 9.40")):
        p.drawText(60, 120 + i * 120, line)
    p.end()
    img.save(str(files["scan"]))
    # 1.11: documents without Office, databases, settings, calendars, notebooks
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    files["docx"] = folder / "Letter.docx"
    with zipfile.ZipFile(files["docx"], "w") as z:
        z.writestr("word/document.xml", f'<w:document {w}><w:body><w:p><w:r><w:t>Dear Ravi, the photos from the '
                   'trip to Hampi are ready to pick up on Sunday.</w:t></w:r></w:p></w:body></w:document>')
    import sqlite3

    files["db"] = folder / "Shop.db"
    con = sqlite3.connect(files["db"])
    con.execute("CREATE TABLE items (name TEXT, price REAL)")
    con.executemany("INSERT INTO items VALUES (?, ?)", [("Tea", 2.5), ("Rice", 1.25)])
    con.commit()
    con.close()
    files["ini"] = folder / "App.ini"
    files["ini"].write_text("[server]\nhost = example.com\nport = 8080\n", encoding="utf-8")
    files["ics"] = folder / "Family.ics"
    files["ics"].write_bytes(b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Dentist\r\nDTSTART:20261120T093000\r\n"
                             b"END:VEVENT\r\nEND:VCALENDAR\r\n")
    files["ipynb"] = folder / "Sales.ipynb"
    files["ipynb"].write_text('{"nbformat": 4, "metadata": {}, "cells": [{"cell_type": "markdown", "source": '
                              '"# Sales for the month of November"}, {"cell_type": "code", "source": '
                              '"print(3 + 4)", "outputs": [{"output_type": "stream", "text": "7"}]}]}',
                              encoding="utf-8")
    files["page"] = folder / "Prices page.html"  # a saved web page with a table (1.12)
    files["page"].write_text("<html><body><h1>Prices</h1><table><tr><th>Item</th><th>Price</th></tr>"
                             "<tr><td>Apple</td><td>1.20</td></tr><tr><td>Pear</td><td>0.80</td></tr></table>"
                             "</body></html>", encoding="utf-8")
    files["link"] = folder / "Deskvert.url"
    files["link"].write_text("[InternetShortcut]\nURL=https://github.com/syedtaj7/DeskVert\n", encoding="utf-8")
    return files


def run(folder: Path) -> int:
    from PySide6.QtGui import QGuiApplication

    from .catalog import offers_for
    from .jobs import build_jobs
    from .main import make_samples
    from .settings import Settings
    from .worker import init_worker, run_job

    _app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    folder.mkdir(parents=True, exist_ok=True)
    samples = make_samples(folder / "samples")
    s = Settings()
    plan = [("Sunset.png", "JPG"), ("Sunset.png", "WEBP"), ("Sunset.png", "HEIC"), ("Mountains.jpg", "PDF"),
            ("Mountains.jpg", "ICO")]
    from .catalog import office_installed

    if office_installed("word"):
        plan.append(("Meeting notes.txt", "PDF"))  # Microsoft Word, through COM automation
    extras = _make_extras(folder / "samples")
    results = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"), initializer=init_worker,
                             initargs=(25,)) as pool:

        def case(files: list[Path], label: str, options: dict | None = None, name: str = "",
                 expect_fail: bool = False) -> Path | None:
            name = name or f"{files[0].name}->{label}"
            offers, _ = offers_for(files, s)
            offer = next((o for o in offers if o.target.label == label), None)
            if offer is None:
                results.append({"case": name, "ok": False, "error": "not offered"})
                return None
            return run(offer, options, name, expect_fail)

        def run(offer, options: dict | None, name: str, expect_fail: bool = False) -> Path | None:
            opts = {o.key: o.default for o in offer.options}
            opts.update(options or {})
            job = build_jobs(offer, opts, s)[0]
            job["id"] = uuid.uuid4().hex[:12]
            r = pool.submit(run_job, job).result(timeout=300)
            ok = bool(r.get("ok")) != expect_fail and (not expect_fail or "Unexpected" not in (r.get("error") or ""))
            results.append({"case": name, "ok": ok, "output": r.get("output"),
                            "error": r.get("error"), "notes": r.get("notes")})
            return Path(r["output"]) if r.get("ok") else None

        for name, label in plan:
            case([samples / name], label)
        case([samples / "Mountains.jpg"], "Compress", {"format": "JPG", "mode": "size", "target_kb": 50})
        case([samples / "Mountains.jpg"], "Compress", {"format": "JPG", "mode": "preset", "preset": "photo",
                                                       "name_suffix": " (form photo)"}, name="Mountains.jpg->Form photo")
        # PDF tools on the PDF we just made
        pdf = next((Path(r["output"]) for r in results if r["case"] == "Mountains.jpg->PDF" and r["ok"]), None)
        if pdf:
            for label in ("PNG", "Every page"):
                case([pdf], label, name=f"pdf->{label}")
            case([pdf], "Numbers", name="pdf->Numbers")
            locked = case([pdf], "Lock", {"password": "selftest"}, name="pdf->Lock")
            if locked:
                case([locked], "Unlock", {"password": "selftest"}, name="pdf->Unlock")
            # A picture and a PDF combined into one 2-page PDF, then the page tools on it
            from .toolbox import MIXED_PDF
            from .catalog import Offer

            mixed = Offer(MIXED_PDF, "into 1 PDF", [])
            mixed.sources = [pdf, samples / "Sunset.png"]
            two = run(mixed, {}, "pdf+png->1 PDF")
            if two:
                for label in ("In half", "Reverse", "Grayscale", "Clean info", "Pictures"):  # Flatten needs form fields; tested separately
                    case([two], label, name=f"2-page pdf->{label}")
                case([two], "Per sheet", {"per": "4"}, name="2-page pdf->4 per sheet")
        # Zip and extract, data, Markdown, text recognition
        zipped = case([samples / "Sunset.png", samples / "Mountains.jpg"], "ZIP", name="2 images->ZIP")
        if zipped:
            case([zipped], "Extract", name="zip->Extract")
        case([extras["csv"]], "XLSX")
        case([extras["json"]], "Tidy")
        case([extras["md"]], "PDF")
        case([extras["scan"]], "Read text")
        # Picture edits, subtitles, other data formats, e-books
        case([samples / "Mountains.jpg"], "Turn right")
        case([samples / "Mountains.jpg"], "Clean info")
        case([samples / "Sunset.png", samples / "Mountains.jpg"], "Long image", name="2 images->Long image")
        case([extras["srt"]], "WebVTT")
        case([extras["yaml"]], "JSON")
        case([extras["epub"]], "PDF")
        # 1.6: maps, 3D, CAD, mail, contacts, more data, fonts, archives, picture formats
        case([extras["geo"]], "KML")
        case([extras["obj"]], "STL")
        case([extras["obj"]], "GLB")
        case([extras["dxf"]], "PDF")
        case([extras["eml"]], "PDF")
        case([extras["csvpeople"]], "vCard")
        case([extras["json"]], "TOML")
        case([extras["md"]], "EPUB")
        case([extras["srt"]], "ASS")
        case([extras["wav"]], "MP3")
        case([extras["wav"]], "M4A")
        case([samples / "Sunset.png"], "QOI")
        case([samples / "Mountains.jpg"], "Set DPI", {"dpi": "300 dpi"})
        case([samples / "Sunset.png", samples / "Mountains.jpg"], "7Z", name="2 images->7Z")
        # 1.11: new conversions (each engine bundled and working)
        case([extras["docx"]], "Markdown", name="docx->Markdown (no Office)")
        case([extras["db"]], "XLSX", name="sqlite->XLSX")
        case([extras["ini"]], "JSON", name="ini->JSON")
        case([extras["ics"]], "CSV", name="ics->CSV")
        case([extras["ipynb"]], "HTML", name="ipynb->HTML")
        case([extras["srt"]], "Shift timing", {"seconds": "+1.5"}, name="srt->Shift timing")
        case([samples / "Mountains.jpg"], "Crop", {"ratio": "1:1 square"})
        case([samples / "Mountains.jpg"], "Passport sheet")
        case([samples / "Mountains.jpg"], "Watermark", {"text": "Deskvert"})
        case([samples / "Mountains.jpg"], "Checksum")
        # 1.12: from the browser (saved page tables, QR codes for links, website icons)
        case([extras["page"]], "Tables", name="html table->Tables (XLSX)")
        case([extras["link"]], "QR code", name="url->QR code")
        case([samples / "Sunset.png"], "Website icons", name="png->Website icons")
        # 1.13: video stills, trimming, signing, renaming (Windows' own decoders, nothing re-encoded)
        case([_avi(folder / "samples" / "Clip.avi")], "Picture", name="avi->Picture (video still)")
        case([extras["wav"]], "Trim", {"start": "0:00.5", "end": "0:01.5"}, name="wav->Trim")
        case([samples / "Sunset.png", samples / "Mountains.jpg"], "Rename", {"pattern": "Photo {n}", "order": "Name"},
             name="2 images->Rename (copies)")
        if pdf:
            case([pdf], "Remove blank", name="pdf->Remove blank (none, must say so)", expect_fail=True)
        # 1.15: PDF to Word (made by Deskvert), video to GIF, a logo traced into SVG (vtracer + Qt SVG)
        import pymupdf
        from PIL import Image, ImageDraw

        report_pdf = folder / "samples" / "Report.pdf"
        with pymupdf.open() as d:
            page = d.new_page()
            page.insert_text((72, 72), "Quarterly report", fontsize=20)
            page.insert_text((72, 104), "Sales grew in every region this quarter, led by the north.", fontsize=11)
            d.save(str(report_pdf))
        case([report_pdf], "DOCX", name="pdf->DOCX (Word)")
        case([_avi(folder / "samples" / "Clip2.avi")], "GIF", {"start": "0:00", "length": "3 seconds"},
             name="avi->GIF")
        logo = Image.new("RGBA", (240, 120), (0, 0, 0, 0))
        ImageDraw.Draw(logo).ellipse((10, 10, 110, 110), fill=(22, 128, 86, 255))
        ImageDraw.Draw(logo).rectangle((130, 30, 230, 90), fill=(30, 30, 30, 255))
        logo.save(folder / "samples" / "Logo.png")
        case([folder / "samples" / "Logo.png"], "SVG", name="png->SVG (traced)")
        arial = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts" / "arial.ttf"
        if arial.exists():  # a copy: the new font goes next to it, never into Windows' own Fonts folder
            import shutil

            font = folder / "samples" / "arial.ttf"
            shutil.copyfile(arial, font)
            case([font], "WOFF", name="arial.ttf->WOFF")
    # 1.12: drag and convert (the drop target's COM pieces are bundled; a dropped picture is saved and named)
    try:
        import win32com.server.util  # noqa: F401 - loaded only when the drop circle first appears

        from . import browsercopy, browserurl, dropread, report, watch  # noqa: F401
        from .ui import report as report_window  # noqa: F401
        from .ui import dropzone  # noqa: F401

        png = (folder / "samples" / "Sunset.png").read_bytes()
        saved = dropread.save("dropped.jpg", png, folder / "dropped")  # a misnamed picture: named for what it is
        ok = saved.suffix == ".png" and saved.read_bytes() == png
        results.append({"case": "drag and convert pieces", "ok": ok, "output": str(saved), "error": None if ok else
                        "the dropped picture wasn't saved as PNG", "notes": []})
    except Exception as e:  # noqa: BLE001
        results.append({"case": "drag and convert pieces", "ok": False, "error": repr(e), "notes": []})
    report = {"ok": all(r["ok"] for r in results), "seconds": round(time.perf_counter() - t0, 1),
              "frozen": bool(getattr(sys, "frozen", False)), "results": results}
    (folder / "selftest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
