"""Maps and GPS data: GeoJSON, KML, KMZ, GPX and CSV into each other (and Shapefiles into them).

Everything is read into GeoJSON-style features (points, lines and areas with
their names and other details), always in longitude / latitude (WGS 84), and
written out again. The new file is read back: same number of places, same
coordinates (to 7 decimals, about 1 cm).

- GPX has no areas: an area is saved as a track around its edge.
- CSV: points get longitude / latitude columns, lines and areas a WKT column.
  A CSV with longitude / latitude columns (or WKT) can become a map file too.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ..errors import ConversionError, VerificationError
from ..paths import long_path

KML_NS = "http://www.opengis.net/kml/2.2"
GPX_NS = "http://www.topografix.com/GPX/1/1"
LAT_NAMES = ("lat", "latitude", "y", "lat_dd")
LON_NAMES = ("lon", "lng", "long", "longitude", "x", "lon_dd")
EXTS = {".geojson": "geojson", ".kml": "kml", ".kmz": "kmz", ".gpx": "gpx", ".csv": "csv"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _feature(geom, props=None) -> dict:
    return {"type": "Feature", "geometry": geom, "properties": dict(props or {})}


# ---------------------------------------------------------------- readers

def _read_text(src: Path) -> str:
    raw = Path(long_path(src)).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def read_geojson(text: str) -> list[dict]:
    data = json.loads(text)
    t = data.get("type")
    if t == "FeatureCollection":
        return [f for f in data.get("features", []) if f.get("geometry")]
    if t == "Feature":
        return [data] if data.get("geometry") else []
    if t in ("Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon", "GeometryCollection"):
        return [_feature(data)]
    raise ConversionError("This isn't GeoJSON (no features or geometry).")


def _coords(text: str) -> list[list[float]]:
    pts = []
    for tup in (text or "").split():
        parts = tup.split(",")
        if len(parts) >= 2:
            pt = [float(parts[0]), float(parts[1])]
            if len(parts) > 2 and parts[2].strip():
                pt.append(float(parts[2]))
            pts.append(pt)
    return pts


def _kml_geom(el):
    tag = _local(el.tag)
    if tag == "Point":
        c = el.find(f"{{{KML_NS}}}coordinates") if el.find(f"{{{KML_NS}}}coordinates") is not None else \
            next((x for x in el.iter() if _local(x.tag) == "coordinates"), None)
        pts = _coords(c.text if c is not None else "")
        return {"type": "Point", "coordinates": pts[0]} if pts else None
    if tag == "LineString":
        c = next((x for x in el.iter() if _local(x.tag) == "coordinates"), None)
        pts = _coords(c.text if c is not None else "")
        return {"type": "LineString", "coordinates": pts} if len(pts) >= 2 else None
    if tag == "Polygon":
        rings = []
        for b in el:
            if _local(b.tag) in ("outerBoundaryIs", "innerBoundaryIs"):
                c = next((x for x in b.iter() if _local(x.tag) == "coordinates"), None)
                ring = _coords(c.text if c is not None else "")
                if _local(b.tag) == "outerBoundaryIs":
                    rings.insert(0, ring)
                else:
                    rings.append(ring)
        return {"type": "Polygon", "coordinates": rings} if rings else None
    if tag == "MultiGeometry":
        parts = [g for g in (_kml_geom(c) for c in el) if g]
        return {"type": "GeometryCollection", "geometries": parts} if parts else None
    return None


def read_kml(text: str) -> list[dict]:
    root = ET.fromstring(text.encode("utf-8"))
    feats = []
    for pm in root.iter():
        if _local(pm.tag) != "Placemark":
            continue
        props = {}
        geom = None
        for child in pm:
            t = _local(child.tag)
            if t in ("name", "description") and child.text:
                props[t] = child.text.strip()
            elif t == "ExtendedData":
                for d in child.iter():
                    if _local(d.tag) in ("Data", "SimpleData") and d.get("name"):
                        v = next((x.text for x in d if _local(x.tag) == "value"), None) if _local(d.tag) == "Data" \
                            else d.text
                        props[d.get("name")] = v or ""
            elif geom is None:
                geom = _kml_geom(child)
        if geom:
            feats.append(_feature(geom, props))
    return feats


def read_kmz(src: Path) -> list[dict]:
    with zipfile.ZipFile(long_path(src)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not names:
            raise ConversionError("This KMZ has no KML map inside.")
        main = "doc.kml" if "doc.kml" in names else names[0]
        return read_kml(z.read(main).decode("utf-8-sig"))


def read_gpx(text: str) -> list[dict]:
    root = ET.fromstring(text.encode("utf-8"))

    def pt(el):
        p = [float(el.get("lon")), float(el.get("lat"))]
        ele = next((x.text for x in el if _local(x.tag) == "ele"), None)
        if ele:
            p.append(float(ele))
        return p

    def props(el):
        return {_local(x.tag): (x.text or "").strip() for x in el if _local(x.tag) in ("name", "desc", "time", "type")
                and x.text}

    feats = []
    for el in root:
        t = _local(el.tag)
        if t == "wpt":
            feats.append(_feature({"type": "Point", "coordinates": pt(el)}, props(el)))
        elif t == "rte":
            pts = [pt(x) for x in el if _local(x.tag) == "rtept"]
            if len(pts) >= 2:
                feats.append(_feature({"type": "LineString", "coordinates": pts}, props(el)))
        elif t == "trk":
            segs = [[pt(x) for x in seg if _local(x.tag) == "trkpt"] for seg in el if _local(seg.tag) == "trkseg"]
            segs = [s for s in segs if len(s) >= 2]
            if len(segs) == 1:
                feats.append(_feature({"type": "LineString", "coordinates": segs[0]}, props(el)))
            elif segs:
                feats.append(_feature({"type": "MultiLineString", "coordinates": segs}, props(el)))
    return feats


def _wkt(text: str):
    text = text.strip()
    m = re.match(r"(?i)\s*(POINT|LINESTRING|POLYGON)\s*Z?\s*\((.*)\)\s*$", text, re.S)
    if not m:
        return None
    kind, body = m.group(1).upper(), m.group(2)

    def seq(s):
        return [[float(v) for v in p.split()[:3]] for p in s.split(",") if p.strip()]

    if kind == "POINT":
        return {"type": "Point", "coordinates": seq(body)[0]}
    if kind == "LINESTRING":
        return {"type": "LineString", "coordinates": seq(body)}
    rings = re.findall(r"\(([^()]*)\)", body)
    return {"type": "Polygon", "coordinates": [seq(r) for r in rings]}


def csv_columns(header: list[str]) -> tuple[int, int, int] | None:
    """(lon index, lat index, wkt index), -1 where absent; None if no coordinates."""
    low = [h.strip().lower() for h in header]
    lat = next((i for i, h in enumerate(low) if h in LAT_NAMES), -1)
    lon = next((i for i, h in enumerate(low) if h in LON_NAMES), -1)
    wkt = next((i for i, h in enumerate(low) if h in ("wkt", "geometry", "geom", "the_geom")), -1)
    if (lat >= 0 and lon >= 0) or wkt >= 0:
        return lon, lat, wkt
    return None


def read_csv(text: str) -> list[dict]:
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        raise ConversionError("The file is empty.")
    cols = csv_columns(rows[0])
    if cols is None:
        raise ConversionError("This CSV has no longitude / latitude (or WKT) column.")
    lon, lat, wkt = cols
    header = rows[0]
    feats = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        r = r + [""] * (len(header) - len(r))
        props = {h: v for i, (h, v) in enumerate(zip(header, r)) if i not in (lon, lat, wkt)}
        geom = None
        if wkt >= 0 and r[wkt].strip():
            geom = _wkt(r[wkt])
        elif lat >= 0 and lon >= 0 and r[lat].strip() and r[lon].strip():
            try:
                geom = {"type": "Point", "coordinates": [float(r[lon]), float(r[lat])]}
            except ValueError:
                geom = None
        if geom:
            feats.append(_feature(geom, props))
    return feats


def read(src: Path) -> list[dict]:
    kind = EXTS.get(src.suffix.lower())
    try:
        if kind == "kmz":
            feats = read_kmz(src)
        else:
            text = _read_text(src)
            feats = {"geojson": read_geojson, "kml": read_kml, "gpx": read_gpx, "csv": read_csv}[kind](text)
    except ConversionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"This map file couldn't be read ({e}).") from e
    if not feats:
        raise ConversionError("No places, routes or areas were found in this file.")
    return feats


# ---------------------------------------------------------------- writers

def _parts(geom) -> list[dict]:
    """Simple geometries (Multi* and collections split up)."""
    t = geom["type"]
    if t == "GeometryCollection":
        return [p for g in geom["geometries"] for p in _parts(g)]
    if t == "MultiPoint":
        return [{"type": "Point", "coordinates": c} for c in geom["coordinates"]]
    if t == "MultiLineString":
        return [{"type": "LineString", "coordinates": c} for c in geom["coordinates"]]
    if t == "MultiPolygon":
        return [{"type": "Polygon", "coordinates": c} for c in geom["coordinates"]]
    return [geom]


def _fmt(pt) -> str:
    return ",".join(repr(round(float(v), 8)) for v in pt[:3])


def to_geojson(feats) -> str:
    return json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, indent=1) + "\n"


def to_kml(feats, name: str) -> str:
    def esc(s) -> str:
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def geom_xml(g) -> str:
        parts = _parts(g)
        xs = []
        for p in parts:
            if p["type"] == "Point":
                xs.append(f"<Point><coordinates>{_fmt(p['coordinates'])}</coordinates></Point>")
            elif p["type"] == "LineString":
                xs.append("<LineString><coordinates>" + " ".join(_fmt(c) for c in p["coordinates"]) +
                          "</coordinates></LineString>")
            elif p["type"] == "Polygon":
                rings = p["coordinates"]
                inner = "".join("<innerBoundaryIs><LinearRing><coordinates>" + " ".join(_fmt(c) for c in r) +
                                "</coordinates></LinearRing></innerBoundaryIs>" for r in rings[1:])
                xs.append("<Polygon><outerBoundaryIs><LinearRing><coordinates>" + " ".join(_fmt(c) for c in rings[0])
                          + "</coordinates></LinearRing></outerBoundaryIs>" + inner + "</Polygon>")
        return xs[0] if len(xs) == 1 else "<MultiGeometry>" + "".join(xs) + "</MultiGeometry>"

    out = [f'<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="{KML_NS}">\n<Document>\n<name>{esc(name)}</name>']
    for f in feats:
        props = dict(f.get("properties") or {})
        nm = props.pop("name", None)
        desc = props.pop("description", None)
        x = ["<Placemark>"]
        if nm is not None:
            x.append(f"<name>{esc(nm)}</name>")
        if desc is not None:
            x.append(f"<description>{esc(desc)}</description>")
        if props:
            x.append("<ExtendedData>" + "".join(
                f'<Data name="{esc(k)}"><value>{esc("" if v is None else v)}</value></Data>' for k, v in props.items())
                     + "</ExtendedData>")
        x.append(geom_xml(f["geometry"]))
        x.append("</Placemark>")
        out.append("".join(x))
    out.append("</Document>\n</kml>\n")
    return "\n".join(out)


def to_gpx(feats) -> tuple[str, int]:
    def esc(s) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def pt(tag, c) -> str:
        ele = f"<ele>{c[2]}</ele>" if len(c) > 2 else ""
        return f'<{tag} lat="{round(c[1], 8)}" lon="{round(c[0], 8)}">{ele}</{tag}>'

    wpts, trks, areas = [], [], 0
    for f in feats:
        props = f.get("properties") or {}
        meta = "".join(f"<{k}>{esc(props[k])}</{k}>" for k in ("name", "desc") if props.get(k) not in (None, ""))
        if "desc" not in props and props.get("description"):
            meta += f"<desc>{esc(props['description'])}</desc>"
        lines = []
        for p in _parts(f["geometry"]):
            if p["type"] == "Point":
                c = p["coordinates"]
                ele = f"<ele>{c[2]}</ele>" if len(c) > 2 else ""
                wpts.append(f'<wpt lat="{round(c[1], 8)}" lon="{round(c[0], 8)}">{ele}{meta}</wpt>')
            elif p["type"] == "LineString":
                lines.append(p["coordinates"])
            elif p["type"] == "Polygon":
                lines.append(p["coordinates"][0])
                areas += 1
        if lines:
            segs = "".join("<trkseg>" + "".join(pt("trkpt", c) for c in seg) + "</trkseg>" for seg in lines)
            trks.append(f"<trk>{meta}{segs}</trk>")
    text = (f'<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Deskvert" xmlns="{GPX_NS}">\n'
            + "\n".join(wpts + trks) + "\n</gpx>\n")
    return text, areas


def _wkt_of(g) -> str:
    def seq(cs):
        return ", ".join(" ".join(repr(round(float(v), 8)) for v in c[:3]) for c in cs)

    if g["type"] == "Point":
        return f"POINT ({seq([g['coordinates']])})"
    if g["type"] == "LineString":
        return f"LINESTRING ({seq(g['coordinates'])})"
    if g["type"] == "Polygon":
        return "POLYGON (" + ", ".join(f"({seq(r)})" for r in g["coordinates"]) + ")"
    return ""


def table(feats) -> list[list]:
    """One row per place: its details, then longitude / latitude (points) or WKT (lines, areas)."""
    keys: dict[str, None] = {}
    for f in feats:
        for k in (f.get("properties") or {}):
            keys.setdefault(str(k), None)
    header = list(keys) + ["longitude", "latitude", "wkt"]
    rows = [header]
    for f in feats:
        for p in _parts(f["geometry"]):
            props = f.get("properties") or {}
            base = ["" if props.get(k) is None else (props[k] if isinstance(props[k], str) else json.dumps(props[k]))
                    for k in keys]
            if p["type"] == "Point":
                c = p["coordinates"]
                rows.append(base + [repr(round(float(c[0]), 8)), repr(round(float(c[1]), 8)), ""])
            else:
                rows.append(base + ["", "", _wkt_of(p)])
    return rows


# ---------------------------------------------------------------- verify

def _flat(feats) -> list[tuple]:
    out = []
    for f in feats:
        for p in _parts(f["geometry"]):
            cs = p["coordinates"]
            if p["type"] == "Point":
                cs = [cs]
            elif p["type"] == "Polygon":
                cs = [c for ring in cs for c in ring]
            out.append(tuple((round(float(c[0]), 7), round(float(c[1]), 7)) for c in cs))
    return out


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    src = sources[0]
    notes: list[str] = []
    if src.suffix.lower() == ".shp":  # a Shapefile: read with its .dbf / .prj beside it
        from .shapefile import read_shp

        feats, notes = read_shp(src)
    else:
        feats = read(src)
    if fmt == "geojson":
        Path(long_path(out)).write_text(to_geojson(feats), encoding="utf-8")
    elif fmt == "kml":
        Path(long_path(out)).write_text(to_kml(feats, src.stem), encoding="utf-8")
    elif fmt == "kmz":
        with zipfile.ZipFile(long_path(out), "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("doc.kml", to_kml(feats, src.stem))
    elif fmt == "gpx":
        text, areas = to_gpx(feats)
        Path(long_path(out)).write_text(text, encoding="utf-8")
        if areas:
            notes.append(f"GPX has no areas: {areas} area(s) were saved as a track around the edge.")
    elif fmt == "csv":
        buf = io.StringIO(newline="")
        csv.writer(buf, lineterminator="\r\n").writerows(table(feats))
        Path(long_path(out)).write_bytes(buf.getvalue().encode("utf-8-sig"))
    elif fmt == "xlsx":
        from .data import _check_xlsx, _write_xlsx

        expected = _write_xlsx(table(feats), out, notes, src.stem)
        _check_xlsx(out, expected)
    else:
        raise ConversionError(f"Unknown map format: {fmt}")
    if fmt != "xlsx":
        back = read(out)
        want = _flat(feats)
        got = _flat(back)
        if fmt == "gpx":  # points first, then tracks; an area keeps only its outer edge
            outer = [_feature({"type": "LineString", "coordinates": p["coordinates"][0]}) if p["type"] == "Polygon"
                     else _feature(p) for f in feats for p in _parts(f["geometry"])]
            want = sorted(_flat(outer))
            got = sorted(got)
        if got != want:
            raise VerificationError("the places or their coordinates changed")
    n = len(_flat(feats))
    notes.insert(0, f"Checked: {n} place{'s' if n != 1 else ''} (points, lines or areas), coordinates kept.")
    return notes
