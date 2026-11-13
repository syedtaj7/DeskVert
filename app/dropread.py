"""What was dropped on Deskvert, and turning it into files on disk.

A drag from another app arrives as a Windows data object (IDataObject) holding the
same thing in several forms. They're tried best first:

1. real files (CF_HDROP): File Explorer, the desktop. Used where they are.
2. virtual files (FileGroupDescriptorW + FileContents): what browsers give for a
   dragged picture (its own bytes, with its real name), Outlook for attachments,
   zip folders for their contents...
3. picture data (PNG, DIB): apps that hand over just the pixels.
4. a web address (http/https, or a data: URL): downloaded, as a last resort.

Everything but real files is saved in Downloads\\Deskvert under a name that doesn't
exist yet, so nothing is ever overwritten. Nothing here runs or opens what was dropped.
"""

from __future__ import annotations

import base64
import html
import logging
import os
import re
import struct
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

CF_HDROP, CF_DIB, CF_DIBV5, CF_UNICODETEXT = 15, 8, 17, 13
TYMED_HGLOBAL, TYMED_ISTREAM = 1, 4
DVASPECT_CONTENT = 1
FD_FILESIZE = 0x40
FILEDESCRIPTORW_SIZE = 592
MAX_DOWNLOAD = 500 * 1024 * 1024  # bigger than any picture; generous for a sound or video file
MAX_VIRTUAL = 1024 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Deskvert"


VIDEO_SITES = {"youtube.com": "YouTube", "youtu.be": "YouTube", "youtube-nocookie.com": "YouTube",
               "vimeo.com": "Vimeo", "instagram.com": "Instagram", "tiktok.com": "TikTok", "facebook.com": "Facebook",
               "fb.watch": "Facebook", "x.com": "X", "twitter.com": "X", "dailymotion.com": "Dailymotion",
               "twitch.tv": "Twitch", "netflix.com": "Netflix", "primevideo.com": "Prime Video",
               "hotstar.com": "Hotstar"}


class DropError(Exception):
    """A message for the user."""


@dataclass
class Dropped:
    files: list[Path] = field(default_factory=list)  # real files, used where they are
    blobs: list[tuple[str, bytes]] = field(default_factory=list)  # (name, bytes) to save
    url: str = ""  # to download when nothing better came
    link: str = ""  # the link that was dragged along (e.g. the video page a thumbnail belongs to)
    html: str = ""  # the dragged part of a web page (selected text, a table...), as HTML
    source: str = ""  # the page it came from
    title: str = ""  # a link's text, when it has one
    clip: bool = False  # selected text or a table: saved as a web clip
    url_is_file: bool = False  # the address is a picture's own (from its tag), not a page
    notes: list[str] = field(default_factory=list)  # said in the picker (e.g. "the biggest version")

    @property
    def from_video_site(self) -> str:
        """The video site's name when the drag came from one (only its thumbnail picture comes along)."""
        host = urllib.parse.urlsplit(self.link or self.url).netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        for domain, name in VIDEO_SITES.items():
            if host == domain or host.endswith("." + domain):
                return name
        return ""

    @property
    def empty(self) -> bool:
        return not (self.files or self.blobs or self.url or self.clip)


# ---------------------------------------------------------------- reading the data object

def _cf(name: str) -> int:
    import win32clipboard

    return win32clipboard.RegisterClipboardFormat(name)


def _formats(data_object) -> set[int]:
    found = set()
    try:
        enum = data_object.EnumFormatEtc(1)  # DATADIR_GET
        while True:
            items = enum.Next(16)
            if not items:
                break
            found.update(f[0] for f in items)
    except Exception:  # noqa: BLE001 - some sources can't list their formats: just try the ones we want
        pass
    return found


def _format_name(cf: int) -> str:
    builtin = {CF_HDROP: "files", CF_DIB: "DIB", CF_DIBV5: "DIBV5", CF_UNICODETEXT: "text", 1: "TEXT", 7: "OEMTEXT",
               16: "LOCALE", 2: "BITMAP"}
    if cf in builtin:
        return builtin[cf]
    try:
        import win32clipboard

        return win32clipboard.GetClipboardFormatName(cf)
    except Exception:  # noqa: BLE001
        return str(cf)


def _get(data_object, cf: int, index: int = -1, tymed: int = TYMED_HGLOBAL) -> bytes | None:
    try:
        medium = data_object.GetData((cf, None, DVASPECT_CONTENT, index, tymed))
    except Exception:  # noqa: BLE001
        return None
    data = medium.data
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if data is not None and hasattr(data, "Read"):  # an IStream (large virtual files, Outlook)
        chunks, total = [], 0
        while True:
            chunk = data.Read(1 << 20)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_VIRTUAL:
                raise DropError("That's more than 1 GB; save it to a folder first, then convert it there.")
            chunks.append(chunk)
        return b"".join(chunks)
    return None


def parse_hdrop(raw: bytes) -> list[Path]:
    """DROPFILES: a header, then the file names (UTF-16 when fWide), each ending in a 0."""
    if len(raw) < 20:
        return []
    offset, wide = struct.unpack_from("<I", raw, 0)[0], struct.unpack_from("<I", raw, 16)[0]
    body = raw[offset:]
    text = body.decode("utf-16-le", errors="ignore") if wide else body.decode("mbcs", errors="ignore")
    return [Path(n) for n in text.split("\0") if n]


def parse_descriptors(raw: bytes) -> list[tuple[str, int | None, bool]]:
    """FILEGROUPDESCRIPTORW -> [(file name, size if given, is a folder)]."""
    if len(raw) < 4:
        return []
    count = struct.unpack_from("<I", raw, 0)[0]
    out = []
    for i in range(count):
        base = 4 + i * FILEDESCRIPTORW_SIZE
        if base + FILEDESCRIPTORW_SIZE > len(raw):
            break
        flags = struct.unpack_from("<I", raw, base)[0]
        attrs = struct.unpack_from("<I", raw, base + 36)[0]
        high, low = struct.unpack_from("<II", raw, base + 64)
        name = raw[base + 72: base + 72 + 520].decode("utf-16-le", errors="ignore").split("\0", 1)[0]
        out.append((name, (high << 32 | low) if flags & FD_FILESIZE else None, bool(attrs & 0x10)))
    return out


def _dib_to_png(raw: bytes) -> bytes | None:
    """A DIB (a BMP without its file header) -> PNG bytes."""
    import io

    from PIL import Image

    if len(raw) < 40:
        return None
    header_size = struct.unpack_from("<I", raw, 0)[0]
    bits = struct.unpack_from("<H", raw, 14)[0]
    colors = struct.unpack_from("<I", raw, 32)[0] if header_size >= 36 else 0
    compression = struct.unpack_from("<I", raw, 16)[0]
    masks = 12 if compression == 3 and header_size == 40 else 0
    palette = (colors or (1 << bits if bits <= 8 else 0)) * 4
    bmp = b"BM" + struct.pack("<IHHI", 14 + len(raw), 0, 0, 14 + header_size + masks + palette) + raw
    try:
        im = Image.open(io.BytesIO(bmp))
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


_IMG_SRC = re.compile(r"<img[^>]+src\s*=\s*[\"']([^\"']+)[\"']", re.I)


def read(data_object) -> Dropped:
    """Everything useful in a dropped data object (called during the drop: the data is only there then)."""
    got = Dropped()
    have = _formats(data_object)
    log.info("drop: the source offers %s", ", ".join(sorted(_format_name(cf) for cf in have)) or "no list")
    link_cf = _cf("UniformResourceLocatorW")
    if not have or link_cf in have:  # the dragged link, kept for the record (never fetched for itself)
        raw = _get(data_object, link_cf)
        if raw:
            got.link = raw.decode("utf-16-le", errors="ignore").split("\0", 1)[0].strip()

    def has(cf):  # some sources don't list formats: when the list is empty, just try
        return not have or cf in have

    html_cf = _cf("HTML Format")
    if has(html_cf):
        raw = _get(data_object, html_cf)
        if raw:
            got.html, got.source = cf_html(raw)

    if has(CF_HDROP):
        raw = _get(data_object, CF_HDROP)
        if raw:
            got.files = [p for p in parse_hdrop(raw) if p.exists()]
            if got.files:
                return got
    fgd, contents = _cf("FileGroupDescriptorW"), _cf("FileContents")
    if has(fgd):
        raw = _get(data_object, fgd)
        for i, (name, size, folder) in enumerate(parse_descriptors(raw or b"")):
            if folder:
                continue
            data = _get(data_object, contents, i, TYMED_HGLOBAL | TYMED_ISTREAM)
            if data is None and i == 0:
                data = _get(data_object, contents, -1, TYMED_HGLOBAL | TYMED_ISTREAM)
            if data is not None:
                if size is not None and len(data) > size:
                    data = data[:size]  # memory handed over in whole pages: trim to the real size
                got.blobs.append((Path(name.replace("\\", "/")).name or "dropped file", data))
        if got.blobs:
            return got
    png = _cf("PNG")
    if has(png):
        raw = _get(data_object, png)
        if raw and raw.startswith(b"\x89PNG"):
            end = raw.find(b"IEND")
            if end > 0:
                raw = raw[:end + 8]  # memory comes in whole pages: cut after the end marker and its checksum
            got.blobs.append(("picture.png", raw))
            return got
    for cf in (CF_DIBV5, CF_DIB):
        if has(cf):
            raw = _get(data_object, cf)
            converted = _dib_to_png(raw) if raw else None
            if converted:
                got.blobs.append(("picture.png", converted))
                return got
    for name in ("UniformResourceLocatorW", "text/x-moz-url"):  # a dragged link
        cf = _cf(name)
        if has(cf):
            raw = _get(data_object, cf)
            if raw:
                parts = raw.decode("utf-16-le", errors="ignore").split("\0", 1)[0].split("\n")
                got.url = parts[0].strip()
                if len(parts) > 1:
                    got.title = parts[1].strip()
                if got.url:
                    if not got.title:
                        got.title = link_text(got.html)
                    return got
    if got.html:
        if visible_text(got.html) or "<table" in got.html.lower():  # selected text or a table: a web clip
            got.clip = True
            return got
        m = _IMG_SRC.search(got.html)  # just a picture's tag: its address
        if m:
            got.url = urllib.parse.urljoin(got.source, html.unescape(m.group(1)))
            got.url_is_file = True
            return got
    if has(CF_UNICODETEXT):
        raw = _get(data_object, CF_UNICODETEXT)
        text = raw.decode("utf-16-le", errors="ignore").split("\0", 1)[0].strip() if raw else ""
        if re.match(r"(https?|data):", text, re.I) and "\n" not in text:
            got.url = text
    return got


def cf_html(raw: bytes) -> tuple[str, str]:
    """Windows' "HTML Format": a small header (with the page's address), then the HTML.
    Returns (the dragged fragment, the page address)."""
    text = raw.decode("utf-8", errors="ignore").rstrip("\0")
    source = ""
    m = re.search(r"^SourceURL:(\S+)", text, re.M)
    if m:
        source = m.group(1).strip()
    start, end = text.find("<!--StartFragment-->"), text.find("<!--EndFragment-->")
    if start >= 0 and end > start:
        return text[start + len("<!--StartFragment-->"):end], source
    m = re.search(r"<html", text, re.I)
    return (text[m.start():] if m else text), source


def visible_text(fragment: str) -> str:
    import lxml.html

    try:
        return " ".join(lxml.html.fragment_fromstring(fragment, create_parent="div").text_content().split())
    except Exception:  # noqa: BLE001
        return ""


def link_text(fragment: str) -> str:
    m = re.search(r"<a\b[^>]*>(.*?)</a>", fragment or "", re.I | re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(m.group(1))).split())[:100] if m else ""


PAGE_EXTS = {"", ".html", ".htm", ".php", ".asp", ".aspx", ".jsp", ".cfm", ".shtml", ".xhtml"}


def is_file_link(url: str) -> bool:
    """A link straight to a file Deskvert converts (a picture, a PDF, a video...), not to a page."""
    from .catalog import kind_of

    path = urllib.parse.urlsplit(url).path
    ext = os.path.splitext(path)[1].lower()
    return ext not in PAGE_EXTS and kind_of(Path("x" + ext)) is not None


def cloud_link(url: str) -> str | None:
    """A Google Drive, Docs, Dropbox or OneDrive share link -> the address of the file itself."""
    parts = urllib.parse.urlsplit(url)
    host = parts.netloc.lower()
    q = urllib.parse.parse_qs(parts.query)
    if host in ("drive.google.com", "drive.usercontent.google.com"):
        m = re.search(r"/file/d/([\w-]+)", parts.path)
        fid = m.group(1) if m else (q.get("id") or [""])[0]
        if fid:
            return f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
    if host == "docs.google.com":
        m = re.search(r"/(document|spreadsheets|presentation)/d/([\w-]+)", parts.path)
        if m:
            kind, fid = m.groups()
            fmt = {"document": "export?format=docx", "spreadsheets": "export?format=xlsx",
                   "presentation": "export/pptx"}[kind]
            return f"https://docs.google.com/{kind}/d/{fid}/{fmt}"
    if host.endswith("dropbox.com") and "/s" in parts.path:
        q["dl"] = ["1"]
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                        urllib.parse.urlencode({k: v[0] for k, v in q.items()}), ""))
    if host in ("1drv.ms", "onedrive.live.com"):
        token = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        return f"https://api.onedrive.com/v1.0/shares/u!{token}/root/content"
    if host.endswith(".sharepoint.com") and ("/:" in parts.path or "/personal/" in parts.path):
        q["download"] = ["1"]
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                        urllib.parse.urlencode({k: v[0] for k, v in q.items()}), ""))
    return None


def biggest_picture(fragment: str, source: str) -> tuple[str, int]:
    """The largest version of a dragged picture the page itself lists (srcset): (address, width)."""
    best, best_w = "", 0
    for m in re.finditer(r"srcset\s*=\s*[\"']([^\"']+)[\"']", fragment or "", re.I):
        for item in html.unescape(m.group(1)).split(","):
            bits = item.strip().split()
            if not bits:
                continue
            w = 0
            if len(bits) > 1 and bits[1].endswith("w") and bits[1][:-1].isdigit():
                w = int(bits[1][:-1])
            elif len(bits) > 1 and bits[1].endswith("x"):
                try:
                    w = int(float(bits[1][:-1]) * 1000)  # 2x: relative; compared with the picture's own width
                except ValueError:
                    w = 0
            if w > best_w:
                best, best_w = urllib.parse.urljoin(source, bits[0]), w
    return best, best_w


def clipboard_picture() -> bytes | None:
    """A copied picture (a screenshot, a browser's "Copy image"...), as PNG bytes."""
    import win32clipboard

    try:
        win32clipboard.OpenClipboard()
    except Exception:  # noqa: BLE001
        return None
    try:
        png = win32clipboard.RegisterClipboardFormat("PNG")
        if win32clipboard.IsClipboardFormatAvailable(png):
            data = win32clipboard.GetClipboardData(png)
            if data and data.startswith(b"\x89PNG"):
                return data
        for cf in (CF_DIBV5, CF_DIB):
            if win32clipboard.IsClipboardFormatAvailable(cf):
                raw = win32clipboard.GetClipboardData(cf)
                return _dib_to_png(raw) if raw else None
    except Exception:  # noqa: BLE001
        log.exception("couldn't read the copied picture")
    finally:
        win32clipboard.CloseClipboard()
    return None


def clipboard_clip() -> Dropped | None:
    """Text or a table copied from a web page (Ctrl + C in a browser), as a web clip; None for anything else.
    Browsers put the page's address in the "HTML Format" header, so only copies from a page count."""
    import win32clipboard

    try:
        win32clipboard.OpenClipboard()
    except Exception:  # noqa: BLE001
        return None
    try:
        cf = win32clipboard.RegisterClipboardFormat("HTML Format")
        if not win32clipboard.IsClipboardFormatAvailable(cf):
            return None
        raw = win32clipboard.GetClipboardData(cf)
    except Exception:  # noqa: BLE001
        log.exception("couldn't read the copied text")
        return None
    finally:
        win32clipboard.CloseClipboard()
    return clip_from_html(raw if isinstance(raw, bytes) else str(raw).encode("utf-8"))


def clip_from_html(raw: bytes) -> Dropped | None:
    fragment, source = cf_html(raw)
    if not source.lower().startswith(("http://", "https://")):
        return None
    if not (visible_text(fragment) or "<table" in fragment.lower()):
        return None  # e.g. "Copy image": the picture itself is handled as a copied picture
    return Dropped(html=fragment, source=source, clip=True)


# ---------------------------------------------------------------- saving

def downloads_dir() -> Path:
    """Downloads\\Deskvert (the user's own Downloads folder, wherever it is)."""
    base = None
    try:
        from win32com.shell import shell

        base = Path(shell.SHGetKnownFolderPath("{374DE290-123F-4565-9164-39C4925E467B}", 0, None))
    except Exception:  # noqa: BLE001
        pass
    folder = (base or Path.home() / "Downloads") / "Deskvert"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


SIGNATURES = [(b"\xff\xd8\xff", ".jpg"), (b"\x89PNG", ".png"), (b"GIF8", ".gif"), (b"%PDF", ".pdf"),
              (b"BM", ".bmp"), (b"PK\x03\x04", ".zip"), (b"ID3", ".mp3"), (b"fLaC", ".flac"), (b"OggS", ".ogg"),
              (b"II*\x00", ".tif"), (b"MM\x00*", ".tif"), (b"\x1aE\xdf\xa3", ".webm")]


def sniff(data: bytes) -> str:
    """The real type of some bytes, from their first bytes ('' when unknown)."""
    if data[:4] == b"RIFF" and data[8:12] in (b"WEBP", b"WAVE", b"AVI "):
        return {b"WEBP": ".webp", b"WAVE": ".wav", b"AVI ": ".avi"}[data[8:12]]
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return ".avif"
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis"):
            return ".heic"
        if brand in (b"M4A ", b"M4B "):
            return ".m4a"
        if brand.startswith(b"qt"):
            return ".mov"
        return ".mp4"
    if data[:5].lower() == b"<?xml" and b"<svg" in data[:2048].lower() or data[:4].lower() == b"<svg":
        return ".svg"
    for sig, ext in SIGNATURES:
        if data.startswith(sig) and not (ext == ".bmp" and len(data) < 26):
            return ext
    if len(data) > 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0:
        return ".mp3"
    return ""


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def clean_name(name: str, data: bytes) -> str:
    """A safe file name with the extension the content really has."""
    name = urllib.parse.unquote(name or "").strip().strip(".")
    name = _BAD.sub("_", name)[:120] or "dropped file"
    stem, ext = os.path.splitext(name)
    real = sniff(data)
    same = {".jpg": {".jpg", ".jpeg", ".jpe", ".jfif"}, ".tif": {".tif", ".tiff"}, ".heic": {".heic", ".heif"},
            ".mp4": {".mp4", ".m4v"}}
    if real and ext.lower() not in same.get(real, {real}):
        ext = real  # e.g. a ".jpg" link that really sends WEBP: named for what it is
    if stem.lower() in ("", "image", "download", "picture", "dropped file"):  # no real name: add when
        stem = f"{stem or 'picture'} {time.strftime('%Y-%m-%d %H.%M.%S')}"
    return (stem or "dropped") + ext


def save(name: str, data: bytes, folder: Path | None = None) -> Path:
    """Write bytes under a name that doesn't exist yet (never overwrites)."""
    from .safe_write import candidate_names

    folder = folder or downloads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    clean = clean_name(name, data)
    stem, ext = os.path.splitext(clean)
    for candidate in candidate_names(stem, ext):
        target = folder / candidate
        try:
            with open(target, "xb") as f:  # "x": fails if the name was taken a moment ago
                f.write(data)
            return target
        except FileExistsError:
            continue
    raise DropError("Couldn't find a free file name in Downloads\\Deskvert.")


def filename_from(disposition: str) -> str:
    """The file name a server gives in Content-Disposition (cloud services always do)."""
    m = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", disposition)
    if m:
        return urllib.parse.unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"([^"]+)"', disposition) or re.search(r"filename\s*=\s*([^;]+)", disposition)
    return m.group(1).strip() if m else ""


def download(url: str, progress=None, folder: Path | None = None) -> Path:
    """Fetch a dragged web address (only what the user dragged; nothing else is sent)."""
    url = (url or "").strip()
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme == "data":
        head, _, body = url.partition(",")
        try:
            data = base64.b64decode(body) if ";base64" in head.lower() else urllib.parse.unquote_to_bytes(body)
        except Exception as e:  # noqa: BLE001
            raise DropError("That picture's data is damaged.") from e
        return save("picture", data, folder)
    if scheme in ("blob", "about", "javascript", "file"):
        raise DropError("That only exists inside the web page, so it can't be fetched. In the browser, right-click "
                        "it and choose Save, then convert the saved file.")
    if scheme not in ("http", "https"):
        raise DropError("Nothing Deskvert can use came with that drop.")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            kind = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            total = int(r.headers.get("Content-Length") or 0)
            if total > MAX_DOWNLOAD:
                raise DropError(f"That file is {total // (1024 * 1024)} MB, more than Deskvert fetches "
                                "(500 MB). Download it in the browser first.")
            chunks, got = [], 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                got += len(chunk)
                if got > MAX_DOWNLOAD:
                    raise DropError("That file is more than 500 MB. Download it in the browser first.")
                chunks.append(chunk)
                if progress and total:
                    progress(got / total)
            data = b"".join(chunks)
            final_url = r.geturl()
            disposition = r.headers.get("Content-Disposition") or ""
    except DropError:
        raise
    except urllib.error.HTTPError as e:
        raise DropError(f"The website refused (error {e.code}). Some sites only allow their own pages to load "
                        "their pictures: save it in the browser (right-click, Save image as), then convert it.") from e
    except Exception as e:  # noqa: BLE001
        raise DropError("Couldn't fetch it. Check the internet connection, or save it in the browser first.") from e
    if kind.startswith("text/html") or (not sniff(data) and data.lstrip()[:15].lower().startswith((b"<!doctype", b"<html"))):
        if cloud_link(url) or "googleusercontent" in url or "onedrive" in url or "dropbox" in url:
            raise DropError("That file isn't shared with \u201canyone with the link\u201d, so only the browser can open "
                            "it. Download it there, then convert it.")
        raise DropError("That's a link to a web page, not to a picture or a file. Open the page and drag the picture "
                        "itself.")
    if not data:
        raise DropError("The website sent an empty file.")
    name = filename_from(disposition) or os.path.basename(urllib.parse.unquote(urllib.parse.urlsplit(final_url).path))
    name = name or "download"
    if not os.path.splitext(name)[1]:
        guess = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
                 "image/avif": ".avif", "image/svg+xml": ".svg", "application/pdf": ".pdf", "video/mp4": ".mp4",
                 "audio/mpeg": ".mp3"}.get(kind, "")
        name += guess
    log.info("drop: fetched %s (%s, %d bytes)", urllib.parse.urlsplit(final_url).netloc, kind or "?", len(data))
    return save(name, data, folder)


def _page_shortcut(url: str, title: str, folder: Path | None) -> Path:
    """A web page link, kept as a .url shortcut: the picker then offers the page as PDF, a picture, a QR code."""
    from .engines.webpage import write_url

    name = title or urllib.parse.urlsplit(url).netloc or "web page"
    folder = folder or downloads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    from .safe_write import candidate_names

    stem = _BAD.sub("_", name)[:100].strip(". ") or "web page"
    for candidate in candidate_names(stem, ".url"):
        target = folder / candidate
        if not target.exists():
            write_url(target, url)
            return target
    raise DropError("Couldn't find a free file name in Downloads\\Deskvert.")


def _clip_file(dropped: Dropped, folder: Path | None) -> Path:
    """Selected text or a table, as a small web page with a line saying where it came from."""
    host = urllib.parse.urlsplit(dropped.source).netloc.removeprefix("www.") or "a web page"
    what = "Table" if "<table" in dropped.html.lower() else "Clip"
    title = f"{what} from {host}"
    source = (f'<p style="color:#666;font-size:12px;margin-top:24px">From <a href="{html.escape(dropped.source)}">'
              f'{html.escape(dropped.source)}</a>, {time.strftime("%Y-%m-%d %H:%M")}</p>') if dropped.source else ""
    page = (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<meta name="generator" content="Deskvert web clip">'
            + (f'<base href="{html.escape(dropped.source)}">' if dropped.source else "") +
            f'<title>{html.escape(title)}</title>'
            '<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:860px;margin:32px auto;line-height:1.5}'
            "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}</style></head><body>\n"
            f"{dropped.html}\n{source}\n</body></html>\n")
    return save(f"{title} {time.strftime('%Y-%m-%d %H.%M')}.html", page.encode("utf-8"), folder)


def save_clip(dropped: Dropped, folder: Path | None = None) -> Path:
    return _clip_file(dropped, folder)


def _bigger(dropped: Dropped, name: str, data: bytes) -> tuple[str, bytes]:
    """If the page lists a clearly bigger version of a dragged picture, take that one instead."""
    import io

    from PIL import Image

    url, w = biggest_picture(dropped.html, dropped.source)
    if not url or not w:
        return name, data
    try:
        with Image.open(io.BytesIO(data)) as im:
            have = im.size[0]
    except Exception:  # noqa: BLE001 - not a picture: keep it as it is
        return name, data
    if w < 1000 and w < have * 1.25:  # "w" sizes: only when clearly bigger ("x" sizes are always tried)
        return name, data
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": dropped.source or url})
        with urllib.request.urlopen(req, timeout=15) as r:
            big = r.read(MAX_DOWNLOAD)
        with Image.open(io.BytesIO(big)) as im:
            im.load()
            size = im.size
    except Exception:  # noqa: BLE001 - the bigger one isn't reachable: the dragged one is fine
        return name, data
    if size[0] <= have:
        return name, data
    dropped.notes.append(f"The biggest version the page offers: {size[0]}×{size[1]} px (it showed {have} px wide).")
    return name, big


def to_files(dropped: Dropped, progress=None, folder: Path | None = None) -> tuple[list[Path], str]:
    """(files to convert, where they came from: "files" | "saved" | "downloaded" | "page" | "clip").
    Runs off the UI thread (it may fetch from the web)."""
    if dropped.files:
        return dropped.files, "files"
    site = dropped.from_video_site
    if dropped.blobs:
        if len(dropped.blobs) == 1 and dropped.blobs[0][0].lower().endswith(".url"):  # a dragged link
            url = _url_in(dropped.blobs[0][1]) or dropped.url or dropped.link
            title = os.path.splitext(dropped.blobs[0][0])[0]
            if url:
                return _link(url, title, dropped, progress, folder)
        out = []
        for name, data in dropped.blobs:
            if dropped.html and not site and sniff(data) in (".jpg", ".png", ".webp", ".avif", ".gif"):
                name, data = _bigger(dropped, name, data)
            out.append(save(name, data, folder))
        return out, "saved"
    if dropped.clip:
        return [_clip_file(dropped, folder)], "clip"
    if dropped.url:
        return _link(dropped.url, dropped.title, dropped, progress, folder)
    raise DropError("Nothing Deskvert can use came with that drop. Try dragging the picture itself, or a file.")


def _url_in(shortcut: bytes) -> str:
    m = re.search(rb"URL=([^\r\n]+)", shortcut)
    return m.group(1).decode("utf-8", errors="ignore").strip() if m else ""


def _link(url: str, title: str, dropped: Dropped, progress, folder) -> tuple[list[Path], str]:
    """A dragged link: a file is fetched; a cloud share link fetches its file; a page becomes a shortcut."""
    if url.lower().startswith("data:"):
        return [download(url, progress, folder)], "downloaded"
    direct = cloud_link(url)
    if direct:
        dropped.notes.append("From a shared link: the file itself.")
        return [download(direct, progress, folder)], "downloaded"
    if dropped.url_is_file or is_file_link(url):
        return [download(url, progress, folder)], "downloaded"
    if not url.lower().startswith(("http://", "https://")):
        return [download(url, progress, folder)], "downloaded"  # says clearly why it can't be used
    return [_page_shortcut(url, title, folder)], "page"
