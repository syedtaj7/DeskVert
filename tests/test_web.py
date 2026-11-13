"""Browser features: web clips and tables, dragged links (pages, files, cloud links), the biggest
picture a page offers, website icons, QR codes and pages saved through the PC's own Edge/Chrome.
Network parts use a local test server only."""

from __future__ import annotations

import io
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from PIL import Image

from app import dropread
from app.catalog import offers_for
from app.jobs import build_jobs
from app.settings import Settings
from app.worker import run_job


def _png(size=(40, 30), color="red") -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


def convert(files, label, options=None, ok=True):
    offers, _ = offers_for(files, Settings())
    offer = next((o for o in offers if o.target.label == label), None)
    assert offer is not None, f"{label}: {[o.target.label for o in offers]}"
    opts = {o.key: o.default for o in offer.options}
    opts.update(options or {})
    job = build_jobs(offer, opts, Settings())[0]
    job["id"] = uuid.uuid4().hex[:12]
    res = run_job(job)
    if ok:
        assert res["ok"], res.get("error")
        res["path"] = Path(res["output"])
    return res


@pytest.fixture
def server():
    big, small = _png((1600, 1200), "blue"), _png((400, 300), "blue")
    page = (b"<!doctype html><html><head><title>Test page</title></head><body style='font-family:Arial'>"
            b"<h1>Hello from a test page</h1><p>" + b"Some words on the page. " * 40 + b"</p></body></html>")
    routes = {"/big.png": ("image/png", big, {}), "/page.html": ("text/html", page, {}),
              "/share": ("application/pdf", b"%PDF-1.4 shared", {"Content-Disposition":
                                                                  "attachment; filename*=UTF-8''Report%20Q3.pdf"}),
              "/doc.pdf": ("application/pdf", b"%PDF-1.4 direct", {})}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path not in routes:
                self.send_response(404)
                self.end_headers()
                return
            kind, body, extra = routes[self.path]
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            for k, v in extra.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", small, big
    httpd.shutdown()


# ---------------------------------------------------------------- clips and tables

CF_HTML = ("Version:0.9\r\nStartHTML:0000000105\r\nEndHTML:0000000400\r\nStartFragment:0000000141\r\n"
           "EndFragment:0000000300\r\nSourceURL:https://en.example.org/wiki/Prices\r\n<html><body>\r\n"
           "<!--StartFragment-->{}<!--EndFragment-->\r\n</body></html>")


def test_cf_html():
    frag, src = dropread.cf_html(CF_HTML.format("<p>Hi <b>there</b></p>").encode())
    assert frag == "<p>Hi <b>there</b></p>" and src == "https://en.example.org/wiki/Prices"


def test_table_clip_to_excel_and_csv(tmp_path):
    table = ("<table><tr><th>City</th><th colspan=2>Price</th></tr><tr><td>Pune</td><td>1.50</td><td>007</td></tr>"
             "<tr><td rowspan=2>Goa</td><td>42</td><td>x</td></tr><tr><td>3</td><td>y</td></tr></table>")
    d = dropread.Dropped(html=table, source="https://en.example.org/wiki/Prices", clip=True)
    (clip,), how = dropread.to_files(d, folder=tmp_path)
    assert how == "clip" and clip.name.startswith("Table from en.example.org") and clip.suffix == ".html"
    from openpyxl import load_workbook

    wb = load_workbook(convert([clip], "Tables")["path"], read_only=True)
    rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    wb.close()
    assert rows == [["City", "Price", "Price"], ["Pune", "1.50", "007"], ["Goa", 42, "x"], ["Goa", 3, "y"]]
    csv_text = convert([clip], "Table as CSV")["path"].read_text(encoding="utf-8-sig")
    assert csv_text.splitlines()[1] == "Pune,1.50,007"


def test_text_clip_to_pdf(tmp_path):
    d = dropread.Dropped(html="<h2>Recipe</h2><p>Mix the flour and the water slowly, then rest it.</p>",
                         source="https://cook.example.org/bread", clip=True)
    (clip,), _ = dropread.to_files(d, folder=tmp_path)
    labels = [o.target.label for o in offers_for([clip], Settings())[0]]
    assert "PDF" in labels and "Markdown" in labels and "Tables" not in labels
    html = clip.read_text(encoding="utf-8")
    assert "cook.example.org/bread" in html and "Mix the flour" in html


# ---------------------------------------------------------------- dragged links

def test_page_link_becomes_a_shortcut_with_page_actions(tmp_path):
    (url_file,), how = dropread.to_files(dropread.Dropped(url="https://news.example.org/story?id=7",
                                                          title="Big: news / story"), folder=tmp_path)
    assert how == "page" and url_file.name == "Big_ news _ story.url"
    from app.engines.webpage import read_url

    assert read_url(url_file) == "https://news.example.org/story?id=7"
    labels = [o.target.label for o in offers_for([url_file], Settings())[0]]
    assert labels[:5] == ["Page as PDF", "Article as PDF", "All pictures", "Page as picture", "QR code"]


def test_browser_link_blob_and_file_links(server, tmp_path):
    base, _small, _big = server
    shortcut = f"[InternetShortcut]\r\nURL={base}/doc.pdf\r\n".encode()
    files, how = dropread.to_files(dropread.Dropped(blobs=[("doc.url", shortcut)]), folder=tmp_path)
    assert how == "downloaded" and files[0].read_bytes() == b"%PDF-1.4 direct"  # a link to a file: the file


def test_cloud_links():
    assert dropread.cloud_link("https://drive.google.com/file/d/AbC_12-x/view?usp=sharing") == \
        "https://drive.usercontent.google.com/download?id=AbC_12-x&export=download&confirm=t"
    assert dropread.cloud_link("https://docs.google.com/spreadsheets/d/XYZ/edit#gid=0") == \
        "https://docs.google.com/spreadsheets/d/XYZ/export?format=xlsx"
    assert "dl=1" in dropread.cloud_link("https://www.dropbox.com/scl/fi/abc/report.pdf?rlkey=k&dl=0")
    assert dropread.cloud_link("https://1drv.ms/b/s!AbC").startswith("https://api.onedrive.com/v1.0/shares/u!")
    assert dropread.cloud_link("https://example.org/file.pdf") is None


def test_server_file_name(server, tmp_path):
    base, *_ = server
    assert dropread.download(f"{base}/share", folder=tmp_path).name == "Report Q3.pdf"


def test_biggest_picture(server, tmp_path):
    base, small, big = server
    frag = f'<img src="{base}/small.png" srcset="{base}/small.png 400w, {base}/big.png 1600w">'
    d = dropread.Dropped(blobs=[("photo.png", small)], html=frag, source=f"{base}/page.html")
    (saved,), _ = dropread.to_files(d, folder=tmp_path)
    assert Image.open(saved).size == (1600, 1200) and "1600×1200" in d.notes[0]
    plain = dropread.Dropped(blobs=[("photo.png", small)])
    (saved,), _ = dropread.to_files(plain, folder=tmp_path)
    assert Image.open(saved).size == (400, 300) and not plain.notes


# ---------------------------------------------------------------- icons, QR codes, pages

def test_website_icons(tmp_path):
    logo = tmp_path / "Logo.png"
    Image.new("RGBA", (600, 300), (20, 120, 220, 255)).save(logo)
    folder = convert([logo], "Website icons")["path"]
    names = sorted(p.name for p in folder.iterdir())
    assert names == sorted(["favicon.ico", "favicon-16x16.png", "favicon-32x32.png", "apple-touch-icon.png",
                            "android-chrome-192x192.png", "android-chrome-512x512.png", "site.webmanifest",
                            "how to use.html"])
    assert Image.open(folder / "apple-touch-icon.png").size == (180, 180)


def test_qr_from_link(tmp_path):
    from app.engines import qr
    from app.engines.webpage import write_url

    link = tmp_path / "Shop.url"
    write_url(link, "https://shop.example.org/item/42")
    out = convert([link], "QR code")["path"]
    sym = qr.make("https://shop.example.org/item/42")
    assert qr.read_back(qr.from_picture(out, sym.size)) == "https://shop.example.org/item/42"


@pytest.mark.skipif(__import__("app.engines.webpage", fromlist=["x"]).find_browser() is None,
                    reason="no Edge or Chrome")
def test_page_as_pdf_and_picture(server, tmp_path):
    import pymupdf

    from app.engines.webpage import write_url

    base, *_ = server
    link = tmp_path / "Test page.url"
    write_url(link, f"{base}/page.html")
    with pymupdf.open(convert([link], "Page as PDF")["path"]) as d:
        assert "Hello from a test page" in d[0].get_text()
    pic = Image.open(convert([link], "Page as picture")["path"])
    assert pic.size[0] == 1280 and 200 < pic.size[1] < 12000


def test_webp_download_watch(tmp_path, monkeypatch):
    """WEBP downloads to JPG: a finished new download gets one JPG job; old files, files still arriving and
    pictures that already have a JPG are left alone."""
    import os
    import time
    from types import SimpleNamespace

    from app.main import Controller

    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(dropread, "downloads_dir", lambda: downloads / "Deskvert")
    webp = io.BytesIO()
    Image.new("RGB", (30, 20), "blue").save(webp, "WEBP")
    old = downloads / "old.webp"
    old.write_bytes(webp.getvalue())
    os.utime(old, (time.time() - 3600, time.time() - 3600))  # there before the watch started
    has_jpg = downloads / "twin.webp"
    has_jpg.write_bytes(webp.getvalue())
    (downloads / "twin.jpg").write_bytes(b"x")
    new = downloads / "new.webp"
    new.write_bytes(webp.getvalue())
    (downloads / "note.txt").write_text("not a picture")

    submitted, timer = [], SimpleNamespace(starts=0)
    timer.start = lambda: setattr(timer, "starts", timer.starts + 1)
    fake = SimpleNamespace(_watch_since=time.time() - 60, _watch_seen={}, settings=Settings(), _watch_timer=timer,
                           jobs=SimpleNamespace(submit=lambda offer, opts: submitted.append(offer)))

    Controller._scan_downloads(fake)  # first look: sizes noted, nothing converted yet (could still be arriving)
    assert submitted == [] and timer.starts == 1
    Controller._scan_downloads(fake)  # same sizes: finished
    assert [o.sources for o in submitted] == [[new]] and submitted[0].target.key == "image.jpg"
    Controller._scan_downloads(fake)  # converted once only
    assert len(submitted) == 1


# ---------------------------------------------------------------- a selection on a page (a web clip)

def _clip(tmp_path, fragment="<h2>Prices</h2><p>Hello <b>big</b> world</p><ul><li>one</li><li>two</li></ul>"):
    d = dropread.Dropped(html=fragment, source="https://shop.example.org/prices", clip=True)
    return dropread.save_clip(d, tmp_path)


def test_a_selection_offers_only_what_fits_a_selection(tmp_path):
    from app import catalog

    clip = _clip(tmp_path)
    assert catalog.kind_of(clip) == "clip"
    keys = [o.target.key for o in offers_for([clip], Settings())[0]]
    assert keys[0] == "clip.pdf" and {"textdoc.md", "clip.txt", "clip.png"} <= set(keys)
    # nothing about the whole page, and no packing or e-books for a few lines of text
    assert not {k for k in keys if k.startswith(("webpage.", "archive.", "hash.", "ebook.", "qr."))}
    assert not {"doc.odt", "doc.rtf", "doc.doc", "doc.pdf", "textdoc.epub", "webtable.xlsx"} & set(keys)
    table = _clip(tmp_path, "<table><tr><th>Item</th><th>Price</th></tr><tr><td>Apple</td><td>1.20</td></tr></table>")
    keys = [o.target.key for o in offers_for([table], Settings())[0]]
    assert keys[:2] == ["webtable.xlsx", "webtable.csv"]
    plain = tmp_path / "page.html"  # an ordinary saved page is still a page
    plain.write_text("<html><body><p>hi</p></body></html>", encoding="utf-8")
    assert catalog.kind_of(plain) == "document"


def test_selection_as_text(tmp_path):
    res = convert([_clip(tmp_path)], "Text")
    text = res["path"].read_text(encoding="utf-8")
    assert text.startswith("Prices\nHello big world\n• one\n• two\n")
    assert "https://shop.example.org/prices" in text  # where it came from


def test_selection_as_pdf_and_picture(tmp_path):
    from app.engines.webpage import find_browser

    if find_browser() is None:
        pytest.skip("needs Edge or Chrome")
    import pymupdf

    clip = _clip(tmp_path)
    pdf = convert([clip], "PDF")["path"]
    with pymupdf.open(pdf) as d:
        words = "".join(p.get_text() for p in d)
    assert "Hello big world" in words and "shop.example.org" in words
    png = convert([clip], "Picture")["path"]
    with Image.open(png) as im:
        assert im.width == 2 * 924 and 100 < im.height < 2000  # twice the size, trimmed to the text


def test_reading_the_browser_selection_puts_the_clipboard_back(monkeypatch):
    """No real clipboard: Windows' calls are stood in for. The browser "copies" a selection; Deskvert reads
    it and restores what was on the clipboard before."""
    from types import SimpleNamespace

    from app import browsercopy

    html_fmt = 49300
    frag = b"<html><body><!--StartFragment--><p>Picked words</p><!--EndFragment--></body></html>"
    copied = [(html_fmt, b"Version:0.9\r\nSourceURL:https://news.example.org/a\r\n" + frag + b"\0"),
              (13, "Picked words\0".encode("utf-16-le"))]
    yours = [(13, "your own copy\0".encode("utf-16-le"))]
    state = {"seq": 5, "board": list(yours), "restored": None, "sent": 0}

    def send():
        state["sent"] += 1
        state["board"], state["seq"] = list(copied), state["seq"] + 2

    fake = SimpleNamespace(GetForegroundWindow=lambda: 77, GetAsyncKeyState=lambda vk: 0,
                           GetClipboardSequenceNumber=lambda: state["seq"],
                           RegisterClipboardFormatW=lambda name: html_fmt)
    monkeypatch.setattr(browsercopy, "user32", fake)
    monkeypatch.setattr(browsercopy, "snapshot", lambda: list(state["board"]))
    monkeypatch.setattr(browsercopy, "restore", lambda items: state.update(restored=items) or True)
    monkeypatch.setattr(browsercopy, "_send_copy", send)

    clip = browsercopy.copy_selection(77)
    assert clip.clip and "Picked words" in clip.html and clip.source == "https://news.example.org/a"
    assert state["restored"] == yours  # the clipboard is back as it was

    # nothing selected: the browser copies nothing, so there's nothing to put back and the page is used
    state["restored"] = None
    monkeypatch.setattr(browsercopy, "_send_copy", lambda: None)
    monkeypatch.setattr(browsercopy, "_wait_for_copy", lambda before, timeout=0.8: False)
    assert browsercopy.copy_selection(77) is None and state["restored"] is None
    assert browsercopy.copy_selection(12) is None  # not the window in front: never sends Ctrl+C


def test_text_copied_from_an_address_bar_is_not_a_selection():
    from app import browsercopy

    assert browsercopy.clip_from_copy([(13, "https://example.org/page\0".encode("utf-16-le"))]) is None
    clip = browsercopy.clip_from_copy([(13, "Line one\r\n\r\nLine <two>\0".encode("utf-16-le"))])
    assert clip.html == "<p>Line one</p>\n<p>Line &lt;two&gt;</p>"


def test_picker_closes_on_a_click_in_the_empty_space_around_the_web():
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from app.menu import Node
    from app.ui.orbit import OrbitView

    QApplication.instance() or QApplication([])
    view = OrbitView([Node(f"Choice {i}", "", key=f"k{i}") for i in range(5)], "Test", card_side="right")
    c = view.orbit_center()
    assert view.solid_at(c) and view.solid_at(QPointF(c.x() + view.DR * 0.6, c.y()))
    assert not view.solid_at(QPointF(view.width() - 3, 3))  # the see-through corner of the window
    assert not view.solid_at(QPointF(c.x() + view.DR + 30, c.y()))  # just outside the disc


# ---------------------------------------------------------------- a page's pictures, and its article

@pytest.fixture
def article_site():
    big = _png((800, 500), "green")
    bigger = _png((1600, 1000), "green")
    icon = _png((24, 24), "black")
    photo = _png((640, 480), "orange")
    page = ("<!doctype html><html><head><title>River walk</title>"
            "<meta property='og:image' content='/photo.png'></head><body>"
            "<header class='site-header'><nav><a href='/'>Home</a> <a href='/news'>News</a></nav></header>"
            "<div class='cookie-banner'>We use cookies. Accept all?</div>"
            "<aside class='sidebar'><p>Buy our premium plan today for a special price only this week.</p></aside>"
            "<article><h1>River walk</h1>"
            "<p>The river path starts at the old mill and follows the water for six quiet kilometres.</p>"
            "<img src='/big.png' srcset='/big.png 800w, /bigger.png 1600w' alt='The river'>"
            "<p>Halfway along there is a wooden bridge where herons wait for fish in the shallows.</p>"
            "<p>Bring water and good shoes; after rain the lower part of the path can be muddy.</p></article>"
            "<div class='ad-slot'><p>Advertisement: cheap flights to anywhere, book now and save.</p></div>"
            "<img src='/icon.png' alt=''><a href='/photo.png'>full size</a>"
            "<footer>Copyright Walks Weekly</footer></body></html>").encode()
    routes = {"/article.html": ("text/html", page), "/big.png": ("image/png", big), "/bigger.png": ("image/png", bigger),
              "/icon.png": ("image/png", icon), "/photo.png": ("image/png", photo)}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path not in routes:
                self.send_response(404)
                self.end_headers()
                return
            kind, body = routes[self.path]
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _link(tmp_path, url):
    from app.engines.webpage import write_url

    p = tmp_path / "River walk.url"
    write_url(p, url)
    return p


def test_page_pictures_and_article_offered(tmp_path):
    keys = [o.target.key for o in offers_for([_link(tmp_path, "https://example.org/a")], Settings())[0]]
    assert {"webextra.reader", "webextra.pictures"} <= set(keys)


def test_all_pictures_on_a_page(tmp_path, article_site):
    from app.engines.webpage import find_browser

    if find_browser() is None:
        pytest.skip("needs Edge or Chrome")
    res = convert([_link(tmp_path, article_site + "/article.html")], "All pictures")
    folder = res["path"]
    assert folder.is_dir() and folder.name == "River walk (pictures)"
    sizes = sorted(Image.open(f).size for f in folder.iterdir())
    assert sizes == [(640, 480), (1600, 1000)]  # the biggest version of the river; the photo once; no icon


def test_article_as_pdf_leaves_out_the_clutter(tmp_path, article_site):
    from app.engines.webpage import find_browser

    if find_browser() is None:
        pytest.skip("needs Edge or Chrome")
    import pymupdf

    pdf = convert([_link(tmp_path, article_site + "/article.html")], "Article as PDF")["path"]
    assert pdf.name == "River walk (article).pdf"
    with pymupdf.open(pdf) as d:
        text = " ".join(" ".join(p.get_text() for p in d).split())
        pictures = sum(len(p.get_images()) for p in d)
    assert "herons wait for fish" in text and "muddy" in text and pictures >= 1
    for clutter in ("cookies", "premium plan", "cheap flights", "Copyright Walks", "News"):
        assert clutter not in text, clutter
