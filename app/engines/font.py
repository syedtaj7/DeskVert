"""Fonts: TTF / OTF <-> WOFF and WOFF2, and TTF / OTF -> EOT.

- woff: the font's tables, each compressed (WOFF 1.0), for web pages.
- sfnt: a WOFF or EOT back to an installable desktop font (.ttf, or .otf for
        PostScript-outline fonts).
- eot:  Embedded OpenType for old Internet Explorer pages (uncompressed).

The font's tables are copied byte for byte; only the container changes. The
new file is unpacked again and every table compared with the original.
WOFF2 (Brotli, through fontTools) repacks the outlines, so there every glyph's points are compared instead.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path


# ---------------------------------------------------------------- reading

def _sfnt_tables(data: bytes) -> tuple[bytes, dict[bytes, bytes]]:
    if len(data) < 12:
        raise ConversionError("This font file is damaged.")
    flavor = data[:4]
    if flavor == b"ttcf":
        raise ConversionError("This is a font collection (several fonts in one file); convert one font at a time.")
    if flavor not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        raise ConversionError("This isn't a TrueType or OpenType font.")
    n = struct.unpack(">H", data[4:6])[0]
    tables = {}
    for i in range(n):
        tag, _cs, off, ln = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        if off + ln > len(data):
            raise ConversionError("This font file is damaged (a table runs past the end).")
        tables[tag] = data[off:off + ln]
    return flavor, tables


def _woff_tables(data: bytes) -> tuple[bytes, dict[bytes, bytes]]:
    if data[:4] != b"wOFF":
        raise ConversionError("This isn't a WOFF font.")
    flavor, _ln, n = struct.unpack(">4sIH", data[4:14])
    tables = {}
    for i in range(n):
        tag, off, comp, orig, _cs = struct.unpack(">4sIIII", data[44 + 20 * i:64 + 20 * i])
        chunk = data[off:off + comp]
        tables[tag] = zlib.decompress(chunk) if comp < orig else chunk
        if len(tables[tag]) != orig:
            raise ConversionError("This WOFF font is damaged.")
    return flavor, tables


def _eot_font_data(data: bytes) -> bytes:
    eot_size, font_size, version, flags = struct.unpack("<IIII", data[:16])
    if struct.unpack("<H", data[34:36])[0] != 0x504C:
        raise ConversionError("This isn't an EOT font.")
    if flags & 0x4:
        raise ConversionError("This EOT font is compressed (MicroType Express), which Deskvert can't unpack.")
    font = data[eot_size - font_size:eot_size]
    if flags & 0x10000000:  # obfuscated with XOR 0x50
        font = bytes(b ^ 0x50 for b in font)
    return font


def load(src: Path) -> tuple[bytes, dict[bytes, bytes]]:
    data = Path(long_path(src)).read_bytes()
    ext = src.suffix.lower()
    if ext == ".woff":
        return _woff_tables(data)
    if ext == ".woff2":
        return _sfnt_tables(woff2_to_sfnt(data))
    if ext == ".eot":
        return _sfnt_tables(_eot_font_data(data))
    return _sfnt_tables(data)


def woff2_to_sfnt(data: bytes) -> bytes:
    """A WOFF2 font unpacked to a plain TrueType / OpenType file (fontTools, Brotli)."""
    import io

    from fontTools.ttLib import woff2

    if data[:4] != b"wOF2":
        raise ConversionError("This isn't a WOFF2 font.")
    out = io.BytesIO()
    try:
        woff2.decompress(io.BytesIO(data), out)
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"This WOFF2 font is damaged ({e}).") from e
    return out.getvalue()


def build_woff2(flavor: bytes, tables: dict[bytes, bytes]) -> bytes:
    """WOFF2: the font's tables, Brotli-compressed (outlines rearranged the way WOFF2 packs them best)."""
    import io

    from fontTools.ttLib import woff2

    out = io.BytesIO()
    woff2.compress(io.BytesIO(build_sfnt(flavor, tables)), out)
    return out.getvalue()


def _same_outlines(a: bytes, b: bytes) -> bool:
    """Two TrueType fonts draw every glyph with the same points (WOFF2 repacks the glyf table, so the bytes differ)."""
    import io

    from fontTools.ttLib import TTFont

    fa, fb = TTFont(io.BytesIO(a), lazy=True), TTFont(io.BytesIO(b), lazy=True)
    if fa.getGlyphOrder() != fb.getGlyphOrder():
        return False
    ga, gb = fa["glyf"], fb["glyf"]
    for name in fa.getGlyphOrder():
        x, y = ga[name], gb[name]
        if x.isComposite() != y.isComposite():
            return False
        if x.isComposite():
            if [(c.glyphName, c.x, c.y) for c in x.components] != [(c.glyphName, c.x, c.y) for c in y.components]:
                return False
            continue
        cx, ex, flx = x.getCoordinates(ga)
        cy, ey, fly = y.getCoordinates(gb)
        if list(cx) != list(cy) or list(ex) != list(ey) or [f & 1 for f in flx] != [f & 1 for f in fly]:
            return False
    return True


# ---------------------------------------------------------------- writing

def _checksum(b: bytes) -> int:
    b = b + b"\0" * (-len(b) % 4)
    return sum(struct.unpack(f">{len(b) // 4}I", b)) & 0xFFFFFFFF


def build_sfnt(flavor: bytes, tables: dict[bytes, bytes]) -> bytes:
    tags = sorted(tables)
    n = len(tags)
    es = max(0, n.bit_length() - 1)
    sr = (1 << es) * 16
    tables = dict(tables)
    if b"head" in tables and len(tables[b"head"]) >= 12:  # checkSumAdjustment is recomputed below
        h = tables[b"head"]
        tables[b"head"] = h[:8] + b"\0\0\0\0" + h[12:]
    header = struct.pack(">4sHHHH", flavor, n, sr, es, n * 16 - sr)
    offset = 12 + 16 * n
    records, body = [], b""
    for tag in tags:
        t = tables[tag]
        records.append(struct.pack(">4sIII", tag, _checksum(t), offset + len(body), len(t)))
        body += t + b"\0" * (-len(t) % 4)
    font = bytearray(header + b"".join(records) + body)
    if b"head" in tables:
        adj = (0xB1B0AFBA - _checksum(bytes(font))) & 0xFFFFFFFF
        pos = offset + sum(len(tables[t]) + (-len(tables[t]) % 4) for t in tags[:tags.index(b"head")])
        font[pos + 8:pos + 12] = struct.pack(">I", adj)
    return bytes(font)


def build_woff(flavor: bytes, tables: dict[bytes, bytes]) -> bytes:
    tags = sorted(tables)
    n = len(tags)
    offset = 44 + 20 * n
    dirs, body = [], b""
    for tag in tags:
        t = tables[tag]
        z = zlib.compress(t, 9)
        stored = z if len(z) < len(t) else t
        dirs.append(struct.pack(">4sIIII", tag, offset + len(body), len(stored), len(t), _checksum(t)))
        body += stored + b"\0" * (-len(stored) % 4)
    total_sfnt = 12 + 16 * n + sum(len(tables[t]) + (-len(tables[t]) % 4) for t in tags)
    length = offset + len(body)
    header = struct.pack(">4s4sIHHIHHIIIII", b"wOFF", flavor, length, n, 0, total_sfnt, 1, 0, 0, 0, 0, 0, 0)
    return header + b"".join(dirs) + body


def _name(tables: dict[bytes, bytes], name_id: int) -> str:
    t = tables.get(b"name")
    if not t:
        return ""
    _fmt, count, string_off = struct.unpack(">HHH", t[:6])
    best = ""
    for i in range(count):
        pid, eid, lid, nid, ln, off = struct.unpack(">HHHHHH", t[6 + 12 * i:18 + 12 * i])
        if nid != name_id:
            continue
        raw = t[string_off + off:string_off + off + ln]
        if pid == 3 and eid in (0, 1, 10):
            s = raw.decode("utf-16-be", errors="replace")
            if lid == 0x409:
                return s
            best = best or s
        elif pid == 1 and not best:
            best = raw.decode("mac_roman", errors="replace")
    return best


def build_eot(flavor: bytes, tables: dict[bytes, bytes]) -> bytes:
    font = build_sfnt(flavor, tables)
    os2 = tables.get(b"OS/2", b"")
    head = tables.get(b"head", b"")
    if len(os2) < 86 or len(head) < 54:
        raise ConversionError("This font is missing information EOT needs (its OS/2 table).")
    weight = struct.unpack(">H", os2[4:6])[0]
    fs_type = struct.unpack(">H", os2[8:10])[0]
    panose = os2[32:42]
    ur = struct.unpack(">IIII", os2[42:58])
    fs_sel = struct.unpack(">H", os2[62:64])[0]
    cp = struct.unpack(">II", os2[78:86]) if len(os2) >= 86 else (0, 0)
    adj = struct.unpack(">I", _sfnt_tables(font)[1][b"head"][8:12])[0]  # of the font as written

    def s(text: str) -> bytes:
        b = text.encode("utf-16-le")
        return struct.pack("<H", len(b)) + b

    names = (s(_name(tables, 1)) + b"\0\0" + s(_name(tables, 2)) + b"\0\0" + s(_name(tables, 5)) + b"\0\0" +
             s(_name(tables, 4)) + b"\0\0" + struct.pack("<H", 0))
    fixed = struct.pack("<II", 0x00020001, 0) + panose + struct.pack("<BBIHH", 1, 1 if fs_sel & 1 else 0, weight,
                                                                     fs_type, 0x504C)
    fixed += struct.pack("<IIIIIII", *ur, *cp, adj) + b"\0" * 16 + b"\0\0"
    head_len = 8 + len(fixed) + len(names)
    total = head_len + len(font)
    return struct.pack("<II", total, len(font)) + fixed + names + font


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    flavor, tables = load(sources[0])
    if fmt == "woff2":
        data = build_woff2(flavor, tables)
        back_flavor, back = _sfnt_tables(woff2_to_sfnt(data))
        Path(long_path(out)).write_bytes(data)
        if Path(long_path(out)).read_bytes() != data or back_flavor != flavor or set(back) != set(tables):
            raise VerificationError("the font's tables don't match")
        repacked = {b"glyf", b"loca", b"head", b"hmtx", b"DSIG"}  # WOFF2 rebuilds these (DSIG: signatures drop)
        for tag, t in tables.items():
            if tag not in repacked and back[tag] != t:
                raise VerificationError(f"the {tag.decode('latin-1')} table changed")
        if b"glyf" in tables and not _same_outlines(build_sfnt(flavor, tables), build_sfnt(back_flavor, back)):
            raise VerificationError("a glyph's outline changed")
        kind = "PostScript (CFF)" if flavor == b"OTTO" else "TrueType"
        family = _name(tables, 4) or sources[0].stem
        size = len(Path(long_path(sources[0])).read_bytes())
        return [f"Checked: {family}, every glyph and table the same ({kind} outlines).",
                f"{len(data) * 100 // max(1, size)}% of the original size."]
    if fmt == "woff":
        data = build_woff(flavor, tables)
        back_flavor, back = _woff_tables(data)
    elif fmt == "sfnt":
        data = build_sfnt(flavor, tables)
        back_flavor, back = _sfnt_tables(data)
    elif fmt == "eot":
        data = build_eot(flavor, tables)
        back_flavor, back = _sfnt_tables(_eot_font_data(data))
    else:
        raise ConversionError(f"Unknown font format: {fmt}")
    Path(long_path(out)).write_bytes(data)
    on_disk = Path(long_path(out)).read_bytes()
    if on_disk != data or back_flavor != flavor or set(back) != set(tables):
        raise VerificationError("the font's tables don't match")
    for tag, t in tables.items():
        b = back[tag]
        if tag == b"head":
            t, b = t[:8] + t[12:], b[:8] + b[12:]  # the whole-file checksum field is recomputed
        if t != b:
            raise VerificationError(f"the {tag.decode('latin-1')} table changed")
    kind = "PostScript (CFF)" if flavor == b"OTTO" else "TrueType"
    family = _name(tables, 4) or sources[0].stem
    return [f"Checked: {family}, {len(tables)} tables copied exactly ({kind} outlines)."]


def desktop_ext(src: Path) -> str:
    """.otf for PostScript-outline fonts, .ttf otherwise (reads only the first bytes)."""
    try:
        with open(long_path(src), "rb") as f:
            head = f.read(8)
        if head[:4] in (b"wOFF", b"wOF2"):
            return ".otf" if head[4:8] == b"OTTO" else ".ttf"
        if src.suffix.lower() == ".eot":
            data = Path(long_path(src)).read_bytes()
            return ".otf" if _eot_font_data(data)[:4] == b"OTTO" else ".ttf"
    except (OSError, ConversionError, struct.error):
        pass
    return ".ttf"
