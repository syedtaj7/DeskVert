"""Esri Shapefiles (.shp with its .dbf, .shx, .prj and .cpg beside it), read without extra libraries.

Points, lines and areas come out as GeoJSON-style features with the details from the .dbf table, so the
map engine writes them as KML, GeoJSON, GPX, KMZ, CSV or Excel like any other map file.

Coordinates must end up as longitude / latitude. A .prj that says the map is already in degrees (WGS 84,
NAD 83, ETRS 89: within a metre or so of each other) is used as it is; Web Mercator (web maps) and UTM zones
are turned into degrees with the standard formulas. Other projections are refused with a plain message rather
than guessed.
"""

from __future__ import annotations

import datetime
import math
import re
import struct
from pathlib import Path

from ..errors import ConversionError
from ..paths import long_path

POINT, POLYLINE, POLYGON, MULTIPOINT = 1, 3, 5, 8
KINDS = {1: POINT, 11: POINT, 21: POINT, 3: POLYLINE, 13: POLYLINE, 23: POLYLINE,
         5: POLYGON, 15: POLYGON, 25: POLYGON, 8: MULTIPOINT, 18: MULTIPOINT, 28: MULTIPOINT}


def _sibling(src: Path, ext: str) -> Path | None:
    for cand in (src.with_suffix(ext), src.with_suffix(ext.upper())):
        if Path(long_path(cand)).exists():
            return cand
    return None


# ---------------------------------------------------------------- projections

A_WGS84, F_WGS84 = 6378137.0, 1 / 298.257223563


def _web_mercator(x: float, y: float) -> tuple[float, float]:
    lon = math.degrees(x / A_WGS84)
    lat = math.degrees(2 * math.atan(math.exp(y / A_WGS84)) - math.pi / 2)
    return lon, lat


def _utm(zone: int, south: bool):
    """A function from UTM easting / northing (metres, WGS 84) to (longitude, latitude)."""
    a, f, k0 = A_WGS84, F_WGS84, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)

    def inv(x: float, y: float) -> tuple[float, float]:
        x -= 500000.0
        if south:
            y -= 10000000.0
        m = y / k0
        mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
        p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32)
              * math.sin(4 * mu) + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
        n1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
        t1 = math.tan(p1) ** 2
        c1 = ep2 * math.cos(p1) ** 2
        r1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
        d = x / (n1 * k0)
        lat = p1 - (n1 * math.tan(p1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                              + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2)
                                              * d ** 6 / 720)
        lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2)
                      * d ** 5 / 120) / math.cos(p1)
        return math.degrees(lon), math.degrees(lat)

    return inv


def projection(src: Path):
    """(to degrees: a function, or None when already in degrees, a note)."""
    prj = _sibling(src, ".prj")
    if prj is None:
        return None, "No .prj file came with it: the coordinates are taken as longitude / latitude."
    wkt = Path(long_path(prj)).read_text(encoding="utf-8", errors="ignore")
    if not wkt.strip().upper().startswith("PROJCS"):
        return None, ""
    name = wkt.upper()
    if "MERCATOR_AUXILIARY_SPHERE" in name or "PSEUDO" in name and "MERCATOR" in name or "WEB_MERCATOR" in name \
            or "POPULAR_VISUALISATION" in name:
        return _web_mercator, "Turned from Web Mercator into longitude / latitude."
    m = re.search(r"UTM[_ ]ZONE[_ ](\d{1,2})([NS])?", name)
    if m and ("WGS" in name or "NAD" in name or "ETRS" in name):
        zone = int(m.group(1))
        south = m.group(2) == "S" or "SOUTH" in name.split("UTM", 1)[1][:30]
        return _utm(zone, south), f"Turned from UTM zone {zone}{'S' if south else 'N'} into longitude / latitude."
    title = re.search(r'PROJCS\["([^"]+)"', wkt)
    raise ConversionError(f"This map uses the “{title.group(1) if title else 'unknown'}” projection, which Deskvert "
                          "can't turn into longitude / latitude yet (it does degrees, Web Mercator and UTM).")


# ---------------------------------------------------------------- the .dbf table


def read_dbf(path: Path, encoding: str) -> list[dict]:
    data = Path(long_path(path)).read_bytes()
    if len(data) < 32:
        return []
    count, header_len, record_len = struct.unpack("<IHH", data[4:12])
    fields, pos = [], 32
    while pos + 32 <= header_len and data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\0", 1)[0].decode("latin-1").strip()
        fields.append((name, chr(data[pos + 11]), data[pos + 16], data[pos + 17]))
        pos += 32
    rows = []
    for i in range(count):
        start = header_len + i * record_len
        rec = data[start:start + record_len]
        if len(rec) < record_len:
            break
        if rec[:1] == b"*":  # deleted
            rows.append(None)
            continue
        row, off = {}, 1
        for name, kind, length, decimals in fields:
            raw = rec[off:off + length]
            off += length
            text = raw.decode(encoding, errors="replace").strip()
            if kind in "NF":
                try:
                    num = float(text) if text and text.strip("*") else None
                    row[name] = int(num) if num is not None and decimals == 0 and num.is_integer() else num
                except ValueError:
                    row[name] = text or None
            elif kind == "D" and len(text) == 8 and text.isdigit():
                try:
                    row[name] = datetime.date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
                except ValueError:
                    row[name] = text
            elif kind == "L":
                row[name] = True if text[:1] in "YyTt" else False if text[:1] in "NnFf" else None
            else:
                row[name] = text
        rows.append(row)
    return rows


# ---------------------------------------------------------------- the .shp shapes


def _ring_area(ring: list[list[float]]) -> float:
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def _inside(pt, ring) -> bool:
    x, y, inside = pt[0], pt[1], False
    for i in range(len(ring) - 1):
        (x1, y1), (x2, y2) = ring[i][:2], ring[i + 1][:2]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-300) + x1:
            inside = not inside
    return inside


def _polygon(rings: list[list[list[float]]]) -> dict:
    """Shapefile rings (outer edges clockwise, holes counter-clockwise) -> a GeoJSON (Multi)Polygon."""
    polys: list[list] = []
    holes = []
    for r in rings:
        if len(r) < 4:
            continue
        (polys.append([r]) if _ring_area(r) <= 0 else holes.append(r))  # clockwise: negative area
    if not polys:  # wound the other way round: take them all as outer edges
        polys, holes = [[r] for r in holes], []
    for h in holes:
        home = next((p for p in polys if _inside(h[0], p[0])), polys[-1])
        home.append(h)
    for p in polys:  # GeoJSON winds outer edges counter-clockwise, holes clockwise
        p[0] = p[0][::-1]
        for k in range(1, len(p)):
            p[k] = p[k][::-1]
    return {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else \
        {"type": "MultiPolygon", "coordinates": polys}


def read_shp(src: Path) -> tuple[list[dict], list[str]]:
    """(features, notes)."""
    data = Path(long_path(src)).read_bytes()
    if len(data) < 100 or struct.unpack(">i", data[:4])[0] != 9994:
        raise ConversionError("This isn't a Shapefile (.shp) or it's damaged.")
    to_deg, note = projection(src)
    notes = [note] if note else []
    cpg = _sibling(src, ".cpg")
    encoding = "utf-8"
    if cpg is not None:
        enc = Path(long_path(cpg)).read_text(encoding="ascii", errors="ignore").strip().lower()
        encoding = {"utf8": "utf-8", "utf-8": "utf-8", "1252": "cp1252", "ansi 1252": "cp1252"}.get(enc, enc or "utf-8")
        try:
            "".encode(encoding)
        except LookupError:
            encoding = "utf-8"
    dbf = _sibling(src, ".dbf")
    rows = read_dbf(dbf, encoding) if dbf is not None else []
    if dbf is None:
        notes.append("No .dbf file came with it, so the places have no names or details.")

    def pt(x: float, y: float) -> list[float]:
        lon, lat = to_deg(x, y) if to_deg else (x, y)
        if not (-180.0001 <= lon <= 180.0001 and -90.0001 <= lat <= 90.0001):
            raise ConversionError("The coordinates aren't longitude / latitude, and no .prj file says which "
                                  "projection they're in. Keep the .prj file next to the .shp.")
        return [round(lon, 9), round(lat, 9)]

    feats: list[dict] = []
    pos, index = 100, 0
    while pos + 8 <= len(data):
        _num, words = struct.unpack(">ii", data[pos:pos + 8])
        content = data[pos + 8:pos + 8 + words * 2]
        pos += 8 + words * 2
        row = rows[index] if index < len(rows) else {}
        index += 1
        if len(content) < 4 or row is None:
            continue
        kind = KINDS.get(struct.unpack("<i", content[:4])[0])
        geom = None
        if kind == POINT and len(content) >= 20:
            geom = {"type": "Point", "coordinates": pt(*struct.unpack("<2d", content[4:20]))}
        elif kind == MULTIPOINT:
            n = struct.unpack("<i", content[36:40])[0]
            xy = struct.unpack(f"<{2 * n}d", content[40:40 + 16 * n])
            geom = {"type": "MultiPoint", "coordinates": [pt(xy[i], xy[i + 1]) for i in range(0, 2 * n, 2)]}
        elif kind in (POLYLINE, POLYGON):
            nparts, npts = struct.unpack("<2i", content[36:44])
            parts = list(struct.unpack(f"<{nparts}i", content[44:44 + 4 * nparts])) + [npts]
            base = 44 + 4 * nparts
            xy = struct.unpack(f"<{2 * npts}d", content[base:base + 16 * npts])
            pts = [pt(xy[i], xy[i + 1]) for i in range(0, 2 * npts, 2)]
            pieces = [pts[parts[k]:parts[k + 1]] for k in range(nparts) if parts[k + 1] > parts[k]]
            if kind == POLYLINE:
                geom = {"type": "LineString", "coordinates": pieces[0]} if len(pieces) == 1 else \
                    {"type": "MultiLineString", "coordinates": pieces}
            else:
                geom = _polygon(pieces)
        if geom is not None:
            feats.append({"type": "Feature", "geometry": geom, "properties": dict(row)})
    if not feats:
        raise ConversionError("No places, lines or areas were found in this Shapefile.")
    return feats, notes
