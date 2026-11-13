"""Drag and convert: the Ctrl+Shift-while-dragging gesture, reading every kind of drop through a
real Windows data object (built like the ones browsers, Explorer and Outlook hand over), saving
without overwriting, and fetching dragged web addresses (from a local test server)."""

from __future__ import annotations

import io
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from PIL import Image

from app import dropread
from app.hotkey import DragGesture


# ---------------------------------------------------------------- the gesture

def test_gesture_drag_first_then_keys():
    g = DragGesture()
    assert g.update(True, True, (100, 100)) is True  # already dragging when Ctrl+Shift go down
    assert g.update(True, True, (300, 300)) is False  # once per hold
    assert g.update(False, True, (300, 300)) is False
    assert g.update(True, True, (300, 300)) is True  # a new hold


def test_gesture_keys_first_then_drag():
    g = DragGesture()
    assert g.update(True, False, (100, 100)) is False
    assert g.update(True, True, (100, 100)) is False  # button down, not moved yet
    assert g.update(True, True, (104, 103)) is False
    assert g.update(True, True, (112, 100)) is True  # moved: a drag


def test_gesture_ctrl_shift_click_is_not_a_drag():
    g = DragGesture()
    for state in [(True, False, (5, 5)), (True, True, (5, 5)), (True, True, (6, 5)), (True, False, (6, 5))]:
        assert g.update(*state) is False


# ---------------------------------------------------------------- a Windows data object, like a browser's

def _png(color="red", size=(30, 20)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


def _descriptor(names_sizes) -> bytes:
    out = struct.pack("<I", len(names_sizes))
    for name, size in names_sizes:
        d = bytearray(dropread.FILEDESCRIPTORW_SIZE)
        struct.pack_into("<I", d, 0, dropread.FD_FILESIZE)
        struct.pack_into("<II", d, 64, 0, size)
        enc = name.encode("utf-16-le")
        d[72:72 + len(enc)] = enc
        out += bytes(d)
    return out


def _hdrop(paths) -> bytes:
    names = "\0".join(str(p) for p in paths) + "\0\0"
    return struct.pack("<IiiII", 20, 0, 0, 0, 1) + names.encode("utf-16-le")


def data_object(formats: dict, streams: set | None = None):
    """A COM IDataObject serving {format id or name: bytes | {index: bytes}}."""
    import pythoncom
    import win32clipboard
    from win32com.server.util import NewEnum, wrap

    table = {}
    for k, v in formats.items():
        table[win32clipboard.RegisterClipboardFormat(k) if isinstance(k, str) else k] = v
    as_stream = {win32clipboard.RegisterClipboardFormat(k) if isinstance(k, str) else k for k in (streams or ())}

    class DataObject:
        _com_interfaces_ = [pythoncom.IID_IDataObject]
        _public_methods_ = ["GetData", "GetDataHere", "QueryGetData", "GetCanonicalFormatEtc", "SetData",
                            "EnumFormatEtc", "DAdvise", "DUnadvise", "EnumDAdvise"]

        def GetData(self, fe):  # noqa: N802
            cf, _target, _aspect, index, tymed = fe
            if cf not in table:
                raise pythoncom.com_error(-2147221404, "no such format", None, -1)  # DV_E_FORMATETC
            value = table[cf]
            if isinstance(value, dict):
                value = value.get(index, value.get(0))
            medium = pythoncom.STGMEDIUM()
            if cf in as_stream and tymed & pythoncom.TYMED_ISTREAM:
                stream = pythoncom.CreateStreamOnHGlobal()
                stream.Write(value)
                stream.Seek(0, 0)
                medium.set(pythoncom.TYMED_ISTREAM, stream)
            else:
                medium.set(pythoncom.TYMED_HGLOBAL, value)
            return medium

        def QueryGetData(self, fe):  # noqa: N802
            return None if fe[0] in table else -2147221404

        def EnumFormatEtc(self, direction):  # noqa: N802
            fmts = [(cf, None, 1, -1, pythoncom.TYMED_HGLOBAL) for cf in table]
            return NewEnum(fmts, iid=pythoncom.IID_IEnumFORMATETC)

    return wrap(DataObject(), pythoncom.IID_IDataObject)


def test_read_real_files(tmp_path):
    a, b = tmp_path / "a.jpg", tmp_path / "b.pdf"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    got = dropread.read(data_object({dropread.CF_HDROP: _hdrop([a, b]), "UniformResourceLocatorW":
                                     "https://example.test/x\0".encode("utf-16-le")}))
    assert got.files == [a, b] and not got.blobs and not got.url  # files win; nothing is fetched


def test_read_browser_picture_virtual_file():
    pic = _png()
    padded = pic + b"\0" * 300  # memory comes in whole pages: the real size trims it
    got = dropread.read(data_object({"FileGroupDescriptorW": _descriptor([("cat.png", len(pic))]),
                                     "FileContents": padded,
                                     "UniformResourceLocatorW": "https://example.test/cat.png\0".encode("utf-16-le")}))
    assert got.blobs == [("cat.png", pic)] and not got.url  # the browser's own bytes: no download


def test_youtube_thumbnail_is_called_what_it_is(tmp_path):
    pic = _png()
    got = dropread.read(data_object({"FileGroupDescriptorW": _descriptor([("hq720.png", len(pic))]),
                                     "FileContents": pic,
                                     "UniformResourceLocatorW": "https://www.youtube.com/watch?v=abc\0".encode("utf-16-le")}))
    assert got.blobs and got.from_video_site == "YouTube"  # the thumbnail is kept, and named for what it is
    link_only = dropread.Dropped(url="https://youtu.be/abc", link="https://youtu.be/abc")
    (shortcut,), how = dropread.to_files(link_only, folder=tmp_path)  # a page: save it or make a QR code
    assert how == "page" and shortcut.suffix == ".url" and link_only.from_video_site == "YouTube"
    assert dropread.Dropped(url="https://example.test/a.jpg").from_video_site == ""


def test_read_outlook_attachments_as_streams():
    one, two = b"%PDF-1.7 first", b"%PDF-1.7 second one"
    got = dropread.read(data_object({"FileGroupDescriptorW": _descriptor([("Invoice.pdf", len(one)),
                                                                           ("Receipt.pdf", len(two))]),
                                     "FileContents": {0: one, 1: two}}, streams={"FileContents"}))
    assert got.blobs == [("Invoice.pdf", one), ("Receipt.pdf", two)]


def test_read_picture_pixels_and_urls():
    pic = _png()
    assert dropread.read(data_object({"PNG": pic})).blobs == [("picture.png", pic)]
    bmp = io.BytesIO()
    Image.new("RGB", (8, 6), "blue").save(bmp, "BMP")
    got = dropread.read(data_object({dropread.CF_DIB: bmp.getvalue()[14:]}))
    assert got.blobs and Image.open(io.BytesIO(got.blobs[0][1])).size == (8, 6)
    url = dropread.read(data_object({"UniformResourceLocatorW": "https://example.test/p.jpg\0".encode("utf-16-le")}))
    assert url.url == "https://example.test/p.jpg"
    html = '<html><body><img alt="x" src="https://example.test/a.webp?x=1&amp;y=2"></body></html>'
    assert dropread.read(data_object({"HTML Format": html.encode()})).url == "https://example.test/a.webp?x=1&y=2"
    assert dropread.read(data_object({dropread.CF_UNICODETEXT: "just words\0".encode("utf-16-le")})).empty


# ---------------------------------------------------------------- saving

def test_save_names_by_content_and_never_overwrites(tmp_path):
    webp = io.BytesIO()
    Image.new("RGB", (4, 4)).save(webp, "WEBP")
    first = dropread.save("photo.jpg", webp.getvalue(), tmp_path)  # a .jpg link that really sends WEBP
    assert first.name == "photo.webp"
    second = dropread.save("photo.jpg", webp.getvalue(), tmp_path)
    assert second.name == "photo (1).webp" and first.read_bytes() == second.read_bytes()
    assert dropread.save('bad:na*me?.png', _png(), tmp_path).name == "bad_na_me_.png"
    assert dropread.save("IMG.JPEG", b"\xff\xd8\xff\xe0 jpeg", tmp_path).name == "IMG.JPEG"


def test_sniff():
    assert dropread.sniff(b"\x00\x00\x00\x1cftypavif") == ".avif"
    assert dropread.sniff(b"\x00\x00\x00\x18ftypheic") == ".heic"
    assert dropread.sniff(b"\x00\x00\x00\x18ftypisom") == ".mp4"
    assert dropread.sniff(b"RIFF\x00\x00\x00\x00WAVEfmt ") == ".wav"
    assert dropread.sniff(b"<svg xmlns='http://www.w3.org/2000/svg'/>") == ".svg"
    assert dropread.sniff(b"plain text") == ""


# ---------------------------------------------------------------- fetching dragged web addresses

@pytest.fixture
def server():
    pic = _png("green")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            routes = {"/pic": ("image/png", pic), "/page": ("text/html", b"<!doctype html><p>hi</p>"),
                      "/photo.jpg": ("image/jpeg", b"\xff\xd8\xff\xe0" + b"j" * 50)}
            if self.path not in routes:
                self.send_response(403)
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

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", pic
    httpd.shutdown()


def test_download(server, tmp_path):
    base, pic = server
    got = dropread.download(f"{base}/pic", folder=tmp_path)
    assert got.suffix == ".png" and got.read_bytes() == pic  # no extension in the link: named from the content
    assert dropread.download(f"{base}/photo.jpg", folder=tmp_path).name == "photo.jpg"
    with pytest.raises(dropread.DropError, match="web page"):
        dropread.download(f"{base}/page", folder=tmp_path)
    with pytest.raises(dropread.DropError, match="refused"):
        dropread.download(f"{base}/private", folder=tmp_path)
    with pytest.raises(dropread.DropError, match="inside the web page"):
        dropread.download("blob:https://example.test/1234", folder=tmp_path)
    import base64

    data_url = "data:image/png;base64," + base64.b64encode(pic).decode()
    assert dropread.download(data_url, folder=tmp_path).read_bytes() == pic


def test_to_files_order(server, tmp_path):
    base, pic = server
    real = tmp_path / "x.png"
    real.write_bytes(pic)
    assert dropread.to_files(dropread.Dropped(files=[real]), folder=tmp_path) == ([real], "files")
    files, how = dropread.to_files(dropread.Dropped(blobs=[("a.png", pic)]), folder=tmp_path / "s")
    assert how == "saved" and files[0].read_bytes() == pic
    files, how = dropread.to_files(dropread.Dropped(url=f"{base}/pic", url_is_file=True), folder=tmp_path / "d")
    assert how == "downloaded"  # a picture's own address (from its tag)
    files, how = dropread.to_files(dropread.Dropped(url=f"{base}/pic"), folder=tmp_path / "p")
    assert how == "page" and files[0].suffix == ".url"  # a plain link without a file name: a page
    with pytest.raises(dropread.DropError):
        dropread.to_files(dropread.Dropped(), folder=tmp_path)


# ---------------------------------------------------------------- the circle, end to end (no mouse needed)

def test_dropzone_receives_a_drop():
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from app.ui.dropzone import DROPEFFECT_COPY, DropZone, _Target

    QApplication.instance() or QApplication([])
    zone = DropZone()
    got = []
    zone.dropped.connect(got.append)
    zone.show()  # offscreen tests have no real window handle to register; Windows' calls are made directly
    pic = _png()
    target = _Target(zone)
    obj = data_object({"FileGroupDescriptorW": _descriptor([("dog.png", len(pic))]), "FileContents": pic})
    assert target.DragEnter(obj, 0, (400, 300), DROPEFFECT_COPY) == DROPEFFECT_COPY
    assert target.Drop(obj, 0, (400, 300), DROPEFFECT_COPY) == DROPEFFECT_COPY
    loop = QEventLoop()
    QTimer.singleShot(150, loop.quit)
    loop.exec()
    assert got and got[0].blobs == [("dog.png", pic)] and not zone.isVisible()
    zone.close()


def test_dropzone_says_when_nothing_was_dragged_in():
    """Ctrl+Shift held, then a press on selected text: the browser changes the selection instead of starting a
    drag, so nothing reaches the circle. It goes away and says so; a real drag never triggers that."""
    import time

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from app.ui.dropzone import DROPEFFECT_COPY, DropZone, _Target

    QApplication.instance() or QApplication([])
    for dragged_in, expect in ((False, 1), (True, 0)):
        zone = DropZone()
        missed = []
        zone.missed.connect(lambda: missed.append(1))
        zone.show()
        zone.t0 = time.perf_counter()
        if dragged_in:
            _Target(zone).DragEnter(None, 0, (0, 0), DROPEFFECT_COPY)
        zone._timer.start()  # the mouse button is up in tests: "let go", so it closes after a moment
        for _ in range(40):  # slow machines (CI) take longer; wait until it's gone, up to 4 s
            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec()
            if not zone.isVisible():
                break
        assert not zone.isVisible() and len(missed) == expect
        zone.close()


# ---------------------------------------------------------------- copied text from a web page, then a tap

def _cf_html(fragment: str, source: str = "https://en.example.org/wiki/Prices") -> bytes:
    body = f"<html><body><!--StartFragment-->{fragment}<!--EndFragment--></body></html>"
    return (f"Version:0.9\r\nStartHTML:0000000000\r\nEndHTML:0000000000\r\nStartFragment:0000000000\r\n"
            f"EndFragment:0000000000\r\nSourceURL:{source}\r\n{body}").encode("utf-8")


def test_copied_text_from_a_page_is_a_clip():
    clip = dropread.clip_from_html(_cf_html("<p>Hello <b>there</b></p>"))
    assert clip and clip.clip and clip.source == "https://en.example.org/wiki/Prices" and "Hello" in clip.html
    assert dropread.clip_from_html(_cf_html("<table><tr><td></td></tr></table>")).clip  # a table, even empty
    assert dropread.clip_from_html(_cf_html('<img src="a.png">')) is None  # "Copy image": a picture, not a clip
    assert dropread.clip_from_html(_cf_html("<p>From Word</p>", source="")) is None  # not from a web page


def test_tap_after_copying_text_opens_the_clip_once(tmp_path, monkeypatch):
    import time
    from types import SimpleNamespace

    from app.main import Controller

    monkeypatch.setattr(dropread, "downloads_dir", lambda: tmp_path / "Tapshift")
    monkeypatch.setattr(dropread, "clipboard_clip", lambda: dropread.clip_from_html(_cf_html("<p>Hello</p>")))
    opened = []
    fake = SimpleNamespace(_text_copied=time.monotonic(), _text_used="", _drop_notes=[], _drop_site="",
                           open_picker=lambda files, where: opened.append((files, where)))
    assert Controller._copied_clip(fake) is True
    (path,), where = opened[0]
    assert where == "clip" and path.parent == tmp_path / "Tapshift" and path.suffix == ".html"
    text = path.read_text(encoding="utf-8")
    assert "Hello" in text and "https://en.example.org/wiki/Prices" in text  # with where it came from
    assert Controller._copied_clip(fake) is False  # the same copy again: this tap is for the page itself
    fake._text_used, fake._text_copied = "", time.monotonic() - 600
    assert Controller._copied_clip(fake) is False  # copied long ago: not what this tap is about
