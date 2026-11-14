"""Kindle books (AZW3 / KF8, and older AZW / MOBI files), read without Kindle software.

A Kindle book is a Palm database: a header record, then the book's text in compressed records, then its
pictures. This reads the text records (PalmDOC compression), removes the bookkeeping bytes each record
carries, and puts the book back together as one web page with its pictures, which the e-book engine then
turns into a PDF, an EPUB or plain text. For KF8 books the text records hold the book's files one after
another, so the reading order is kept.

Books sold with Amazon's DRM are locked and can't be read; those, and HUFF/CDIC-compressed books, get a plain
message instead.
"""

from __future__ import annotations

import base64
import re
import struct
from pathlib import Path

from ..errors import ConversionError
from ..paths import long_path

NO_COMPRESSION, PALMDOC, HUFF = 1, 2, 17480


def palmdoc_decompress(data: bytes) -> bytes:
    """PalmDOC's small LZ77: literal bytes, short literal runs, back-references and space + letter pairs."""
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        i += 1
        if c == 0 or 0x09 <= c <= 0x7F:
            out.append(c)
        elif c <= 0x08:  # the next c bytes as they are
            out += data[i:i + c]
            i += c
        elif c <= 0xBF:  # copy from earlier: 11 bits back, 3 to 10 bytes
            if i >= n:
                break
            pair = ((c << 8) | data[i]) & 0x3FFF
            i += 1
            dist, length = pair >> 3, (pair & 7) + 3
            if dist == 0 or dist > len(out):
                raise ConversionError("This Kindle book's text is damaged.")
            for _ in range(length):
                out.append(out[-dist])
        else:  # a space, then a letter
            out += b" " + bytes([c ^ 0x80])
    return bytes(out)


def _trailing(record: bytes, flags: int) -> bytes:
    """A text record without the extra bytes Kindle readers use for navigation."""
    def back_int(data: bytes) -> int:
        value, shift = 0, 0
        for byte in reversed(data[-4:]):
            value |= (byte & 0x7F) << shift
            shift += 7
            if byte & 0x80:
                break
        return value

    end = len(record)
    for bit in range(15, 0, -1):
        if flags & (1 << bit) and end > 0:
            end -= min(end, back_int(record[:end]))
    if flags & 1 and end > 0:
        end -= (record[end - 1] & 3) + 1
    return record[:max(0, end)]


def _records(data: bytes) -> list[bytes]:
    if len(data) < 78 or data[60:68] not in (b"BOOKMOBI", b"TEXtREAd"):
        raise ConversionError("This isn't a Kindle book (AZW3, AZW or MOBI).")
    (count,) = struct.unpack(">H", data[76:78])
    offsets = [struct.unpack(">I", data[78 + 8 * i:82 + 8 * i])[0] for i in range(count)]
    offsets.append(len(data))
    return [data[offsets[i]:offsets[i + 1]] for i in range(count)]


def _exth(rec0: bytes, header_len: int) -> dict[int, list[bytes]]:
    start = 16 + header_len
    if rec0[start:start + 4] != b"EXTH":
        return {}
    (n,) = struct.unpack(">I", rec0[start + 8:start + 12])
    pos, out = start + 12, {}
    for _ in range(n):
        if pos + 8 > len(rec0):
            break
        kind, size = struct.unpack(">II", rec0[pos:pos + 8])
        out.setdefault(kind, []).append(rec0[pos + 8:pos + size])
        pos += size
    return out


def _book(records: list[bytes], first: int) -> tuple[str, str, dict]:
    """(text, title, info) of the book whose header is records[first]."""
    rec0 = records[first]
    # PalmDOC header: compression, (unused), text length, text record count, record size, encryption
    compression, _unused, _text_len, text_count, _rec_size, encryption = struct.unpack(">HHIHHH", rec0[:14])
    if encryption:
        raise ConversionError("This Kindle book is locked with Amazon's DRM, so it can't be converted. Books you "
                              "bought on Amazon usually are; your own or free books aren't.")
    if compression == HUFF:
        raise ConversionError("This Kindle book uses a compression Deskvert can't read yet (HUFF/CDIC).")
    if compression not in (NO_COMPRESSION, PALMDOC):
        raise ConversionError("This Kindle book is compressed in a way Deskvert doesn't know.")
    info = {"version": 6, "first_image": None, "encoding": "cp1252", "header_len": 0}
    flags = 0
    title = ""
    if rec0[16:20] == b"MOBI":
        header_len, _mtype, codepage = struct.unpack(">III", rec0[20:32])
        info["header_len"] = header_len
        info["encoding"] = "utf-8" if codepage == 65001 else "cp1252"
        info["version"] = struct.unpack(">I", rec0[36:40])[0]
        first_image = struct.unpack(">I", rec0[108:112])[0] if header_len >= 0x60 else 0xFFFFFFFF
        info["first_image"] = None if first_image == 0xFFFFFFFF else first_image
        if header_len >= 0xE4:
            flags = struct.unpack(">H", rec0[242:244])[0]
        name_off, name_len = struct.unpack(">II", rec0[84:92])
        title = rec0[name_off:name_off + name_len].decode(info["encoding"], errors="replace")
        info["exth"] = _exth(rec0, header_len)
    parts = []
    for rec in records[first + 1:first + 1 + text_count]:
        rec = _trailing(rec, flags)
        parts.append(palmdoc_decompress(rec) if compression == PALMDOC else rec)
    text = b"".join(parts).decode(info["encoding"], errors="replace")
    return text, title, info


def _picture(data: bytes) -> str | None:
    for sig, mime in ((b"\xff\xd8", "image/jpeg"), (b"\x89PNG", "image/png"), (b"GIF8", "image/gif")):
        if data.startswith(sig):
            return mime
    return None


def to_html(src: Path) -> tuple[str, str]:
    """(one web page with the book's text and pictures, the book's title)."""
    data = Path(long_path(src)).read_bytes()
    records = _records(data)
    if not records:
        raise ConversionError("This Kindle book is empty.")
    text, title, info = _book(records, 0)
    exth = info.get("exth", {})
    boundary = exth.get(121)  # a book that holds both an old MOBI copy and the newer KF8 one: read the KF8 one
    if boundary:
        (kf8,) = struct.unpack(">I", boundary[0][:4])
        if 0 < kf8 < len(records) and records[kf8][16:20] == b"MOBI":
            text, title2, kinfo = _book(records, kf8)
            title = title2 or title
            if kinfo.get("first_image") is not None:
                kinfo["first_image"] += kf8
            info = {**info, **{k: v for k, v in kinfo.items() if v is not None}}
    if exth.get(503):
        title = exth[503][0].decode("utf-8", errors="replace") or title
    first = info.get("first_image")

    def picture(n: int) -> str | None:
        if first is None or not 0 <= first + n < len(records):
            return None
        rec = records[first + n]
        mime = _picture(rec)
        return f"data:{mime};base64,{base64.b64encode(rec).decode()}" if mime else None

    def kf8_embed(m):  # kindle:embed:0001?mime=image/jpg (base 32, counted from 1)
        uri = picture(int(m.group(2), 32) - 1)
        return f'{m.group(1)}"{uri}"' if uri else m.group(0)

    def mobi_recindex(m):  # recindex="00001" (counted from 1)
        uri = picture(int(m.group(1)) - 1)
        return f'src="{uri}"' if uri else m.group(0)

    text = re.sub(r'(src=)["\']kindle:embed:([0-9A-Va-v]{4})[^"\']*["\']', kf8_embed, text)
    text = re.sub(r'recindex=["\']?(\d+)["\']?', mobi_recindex, text)
    text = re.sub(r"<mbp:pagebreak\s*/?>", '<div style="page-break-after:always"></div>', text, flags=re.I)
    text = re.sub(r"</?mbp:[^>]*>", "", text, flags=re.I)
    body = re.sub(r"(?is)</?(?:html|head|body)[^>]*>|<title>.*?</title>|<\?xml[^>]*\?>|<!DOCTYPE[^>]*>", "", text)
    body = re.sub(r"(?is)<link[^>]*>|<meta[^>]*>", "", body)
    if not re.sub(r"<[^>]+>|\s", "", body):
        raise ConversionError("No text was found in this Kindle book.")
    import lxml.html
    from lxml import etree

    root = lxml.html.document_fromstring("<html><head><title></title></head><body>" + body + "</body></html>")
    root.find("head/title").text = title or src.stem
    for bad in root.xpath("//script|//style[contains(., '@import')]"):
        bad.getparent().remove(bad)
    root.set("xmlns", "http://www.w3.org/1999/xhtml")
    page = '<?xml version="1.0" encoding="utf-8"?>\n' + etree.tostring(root, method="xml", encoding="unicode")
    return page, title or src.stem
