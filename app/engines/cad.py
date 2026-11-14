"""CAD drawings: DXF -> SVG, PDF or PNG, without AutoCAD.

Draws lines, polylines (with arcs), circles, arcs, ellipses, splines (through
their control points), points, solids, text and blocks (inserted with their
position, scale and rotation, including dimension blocks). Hatch fills, images
and 3D solids aren't drawn; the notes count anything left out.

The SVG is the drawing; the PDF (vector) and PNG are made from it by MuPDF.
DWG files (AutoCAD's closed format) are read through the free ODA File Converter when it's installed.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

ACI = {1: "#d32f2f", 2: "#b8860b", 3: "#2e7d32", 4: "#00838f", 5: "#1565c0", 6: "#8e24aa"}
DRAWN = {"LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE", "POINT", "TEXT", "MTEXT", "SOLID",
         "3DFACE", "TRACE", "INSERT", "DIMENSION"}


def _pairs(text: str):
    lines = text.splitlines()
    for i in range(0, len(lines) - 1, 2):
        try:
            yield int(lines[i].strip()), lines[i + 1].rstrip("\r")
        except ValueError:
            raise ConversionError("This DXF file is damaged.") from None


def parse(text: str) -> tuple[list[dict], dict[str, list[dict]], dict[str, int]]:
    """(entities, blocks, layer colors)."""
    entities: list[dict] = []
    blocks: dict[str, list[dict]] = {}
    layers: dict[str, int] = {}
    section = None
    cur: dict | None = None
    block_name = None
    in_layer_table = False
    layer: dict | None = None
    target = entities

    def flush():
        nonlocal cur
        if cur is not None:
            target.append(cur)
        cur = None

    for code, val in _pairs(text):
        v = val.strip()
        if code == 0:
            flush()
            if layer is not None and layer.get("name"):
                layers[layer["name"]] = abs(int(layer.get("color", 7)))
            layer = None
            if v == "SECTION":
                section = "?"
                continue
            if v == "ENDSEC":
                section = None
                continue
            if section == "TABLES":
                if v == "LAYER":
                    in_layer_table = True
                    layer = {}
                continue
            if section == "BLOCKS":
                if v == "BLOCK":
                    block_name = ""
                    target = []
                    continue
                if v == "ENDBLK":
                    if block_name is not None:
                        blocks[block_name] = target
                    block_name, target = None, entities
                    continue
            if section in ("ENTITIES", "BLOCKS"):
                cur = {"type": v, "codes": []}
            continue
        if section == "?" and code == 2:
            section = v
            continue
        if section == "TABLES" and in_layer_table and layer is not None:
            if code == 2:
                layer["name"] = v
            elif code == 62:
                layer["color"] = v
            continue
        if section == "BLOCKS" and cur is None and block_name == "" and code == 2:
            block_name = v
            continue
        if cur is not None:
            cur["codes"].append((code, v))
    flush()
    return entities, blocks, layers


def _get(e, code, default=None, cast=float):
    for c, v in e["codes"]:
        if c == code:
            try:
                return cast(v)
            except ValueError:
                return default
    return default


def _all(e, code, cast=float):
    return [cast(v) for c, v in e["codes"] if c == code]


class Drawing:
    def __init__(self, blocks, layers):
        self.blocks, self.layers = blocks, layers
        self.items: list[str] = []
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.skipped: dict[str, int] = {}
        self.count = 0

    def color(self, e, inherited="#111111") -> str:
        c = _get(e, 62, None, int)
        if c == 0:
            return inherited  # BYBLOCK
        if c is None or c == 256:  # BYLAYER
            c = self.layers.get(_get(e, 8, "0", str), 7)
        return ACI.get(c, "#111111")

    def _pt(self, m, x, y):
        a, b, c, d, e, f = m
        px, py = a * x + c * y + e, b * x + d * y + f
        self.xs.append(px)
        self.ys.append(py)
        return px, py

    def _path(self, pts, closed, col, width=1.0):
        if len(pts) < 2:
            return
        d = "M" + " L".join(f"{x:.4f},{y:.4f}" for x, y in pts) + (" Z" if closed else "")
        self.items.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{width}" '
                          'vector-effect="non-scaling-stroke"/>')
        self.count += 1

    def _arc_pts(self, m, cx, cy, r, a0, a1, rx=None, ry=None, rot=0.0):
        rx = r if rx is None else rx
        ry = r if ry is None else ry
        while a1 < a0:
            a1 += 2 * math.pi
        n = max(8, int((a1 - a0) / (2 * math.pi) * 96))
        cr, sr = math.cos(rot), math.sin(rot)
        out = []
        for i in range(n + 1):
            t = a0 + (a1 - a0) * i / n
            x, y = rx * math.cos(t), ry * math.sin(t)
            out.append(self._pt(m, cx + x * cr - y * sr, cy + x * sr + y * cr))
        return out

    def entity(self, e, m, inherited="#111111", depth=0):
        t = e["type"]
        col = self.color(e, inherited)
        if t == "LINE":
            self._path([self._pt(m, _get(e, 10, 0), _get(e, 20, 0)), self._pt(m, _get(e, 11, 0), _get(e, 21, 0))],
                       False, col)
        elif t in ("LWPOLYLINE",):
            xs, ys = _all(e, 10), _all(e, 20)
            bulges = {}
            k = -1
            for c, v in e["codes"]:
                if c == 10:
                    k += 1
                elif c == 42 and k >= 0:
                    bulges[k] = float(v)
            closed = bool(int(_get(e, 70, 0) or 0) & 1)
            self._path(self._poly(m, list(zip(xs, ys)), bulges, closed), closed, col)
        elif t == "CIRCLE":
            self._path(self._arc_pts(m, _get(e, 10, 0), _get(e, 20, 0), _get(e, 40, 0), 0, 2 * math.pi), True, col)
        elif t == "ARC":
            self._path(self._arc_pts(m, _get(e, 10, 0), _get(e, 20, 0), _get(e, 40, 0),
                                     math.radians(_get(e, 50, 0)), math.radians(_get(e, 51, 360))), False, col)
        elif t == "ELLIPSE":
            mx, my = _get(e, 11, 1), _get(e, 21, 0)
            rx = math.hypot(mx, my)
            self._path(self._arc_pts(m, _get(e, 10, 0), _get(e, 20, 0), 0, _get(e, 41, 0), _get(e, 42, 2 * math.pi),
                                     rx, rx * _get(e, 40, 1), math.atan2(my, mx)), False, col)
        elif t == "SPLINE":
            xs, ys = _all(e, 11), _all(e, 21)
            if len(xs) < 2:
                xs, ys = _all(e, 10), _all(e, 20)
            self._path([self._pt(m, x, y) for x, y in zip(xs, ys)], bool(int(_get(e, 70, 0) or 0) & 1), col)
        elif t == "POINT":
            x, y = self._pt(m, _get(e, 10, 0), _get(e, 20, 0))
            self.items.append(f'<circle cx="{x:.4f}" cy="{y:.4f}" r="0.5" fill="{col}"/>')
            self.count += 1
        elif t in ("SOLID", "3DFACE", "TRACE"):
            pts = [(_get(e, 10 + i, None), _get(e, 20 + i, None)) for i in range(4)]
            pts = [p for p in pts if p[0] is not None]
            if t == "SOLID" and len(pts) == 4:
                pts = [pts[0], pts[1], pts[3], pts[2]]
            self._path([self._pt(m, x, y) for x, y in pts], True, col)
        elif t in ("TEXT", "MTEXT"):
            text = _get(e, 1, "", str)
            if t == "MTEXT":
                text = "".join(_all(e, 3, str)) + text
                text = re.sub(r"\\[A-Za-z][^;\\]*;", "", text).replace("\\P", " ").replace("{", "").replace("}", "")
            if not text.strip():
                return
            h = _get(e, 40, 1.0) or 1.0
            x, y = self._pt(m, _get(e, 10, 0), _get(e, 20, 0))
            rot = _get(e, 50, 0)
            if t == "MTEXT" and _get(e, 11, None) is not None:
                rot = math.degrees(math.atan2(_get(e, 21, 0), _get(e, 11, 1)))
            scale = math.hypot(m[0], m[1])
            rot += math.degrees(math.atan2(m[1], m[0]))
            esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self.items.append(f'<text transform="translate({x:.4f},{y:.4f}) rotate({rot:.3f}) scale(1,-1)" '
                              f'font-family="Arial" font-size="{h * scale:.4f}" fill="{col}">{esc}</text>')
            self.xs.append(x + len(text) * h * scale * 0.6)
            self.ys.append(y + h * scale)
            self.count += 1
        elif t in ("INSERT", "DIMENSION"):
            name = _get(e, 2, "", str)
            block = self.blocks.get(name)
            if block is None or depth > 8:
                return
            if t == "DIMENSION":
                bm = (1, 0, 0, 1, 0, 0)
            else:
                sx, sy = _get(e, 41, 1) or 1, _get(e, 42, 1) or 1
                r = math.radians(_get(e, 50, 0))
                tx, ty = _get(e, 10, 0), _get(e, 20, 0)
                bm = (sx * math.cos(r), sx * math.sin(r), -sy * math.sin(r), sy * math.cos(r), tx, ty)
            a, b, c, d, ee, f = m
            A, B, C, D, E, F = bm
            mm = (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + ee, b * E + d * F + f)
            for sub in block:
                self.entity(sub, mm, col, depth + 1)
        elif t == "POLYLINE":
            return  # drawn with its VERTEX entities in draw()
        else:
            self.skipped[t] = self.skipped.get(t, 0) + 1

    def _poly(self, m, pts, bulges, closed):
        out = []
        n = len(pts)
        for i in range(n if closed else n - 1):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
            bl = bulges.get(i, 0.0)
            if not out:
                out.append(self._pt(m, x1, y1))
            if abs(bl) < 1e-9:
                out.append(self._pt(m, x2, y2))
                continue
            ang = 4 * math.atan(bl)
            chord = math.hypot(x2 - x1, y2 - y1)
            r = chord / (2 * math.sin(ang / 2))
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            h = r * math.cos(ang / 2)
            nx, ny = -(y2 - y1) / chord, (x2 - x1) / chord
            cx, cy = mx + nx * h, my + ny * h
            a0 = math.atan2(y1 - cy, x1 - cx)
            steps = max(4, int(abs(ang) / (2 * math.pi) * 96))
            for k in range(1, steps + 1):
                t = a0 + ang * k / steps
                out.append(self._pt(m, cx + abs(r) * math.cos(t), cy + abs(r) * math.sin(t)))
        if n == 1:
            out.append(self._pt(m, *pts[0]))
        return out

    def draw(self, entities):
        ident = (1, 0, 0, 1, 0, 0)
        i = 0
        while i < len(entities):
            e = entities[i]
            if e["type"] == "POLYLINE":
                verts = []
                bulges = {}
                j = i + 1
                while j < len(entities) and entities[j]["type"] == "VERTEX":
                    v = entities[j]
                    bl = _get(v, 42, 0.0)
                    if bl:
                        bulges[len(verts)] = bl
                    verts.append((_get(v, 10, 0), _get(v, 20, 0)))
                    j += 1
                closed = bool(int(_get(e, 70, 0) or 0) & 1)
                self._path(self._poly(ident, verts, bulges, closed), closed, self.color(e))
                i = j + (1 if j < len(entities) and entities[j]["type"] == "SEQEND" else 0)
                continue
            if e["type"] not in ("VERTEX", "SEQEND", "ATTRIB", "ATTDEF", "VIEWPORT"):
                self.entity(e, ident)
            i += 1


def to_svg(src: Path) -> tuple[str, int, dict[str, int]]:
    raw = Path(long_path(src)).read_bytes()
    if src.suffix.lower() == ".dwg" or raw.startswith(b"AC10"):
        raise ConversionError("DWG is AutoCAD's closed format. Save it as DXF in a CAD program first.")
    if raw.startswith(b"AutoCAD Binary DXF"):
        raise ConversionError("This is a binary DXF; save it as an ASCII (text) DXF in a CAD program first.")
    text = raw.decode("utf-8", errors="replace") if b"$DWGCODEPAGE" not in raw[:4000] or b"UTF" in raw[:4000] \
        else raw.decode("cp1252", errors="replace")
    entities, blocks, layers = parse(text)
    dr = Drawing(blocks, layers)
    dr.draw(entities)
    if not dr.count:
        raise ConversionError("Nothing in this drawing could be drawn (it may be 3D only).")
    x0, x1, y0, y1 = min(dr.xs), max(dr.xs), min(dr.ys), max(dr.ys)
    w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    pad = max(w, h) * 0.03
    vb = f"{x0 - pad:.4f} {-(y1 + pad):.4f} {w + 2 * pad:.4f} {h + 2 * pad:.4f}"
    k = 1000 / max(w + 2 * pad, h + 2 * pad)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{(w + 2 * pad) * k:.1f}" '
           f'height="{(h + 2 * pad) * k:.1f}">\n<rect x="{x0 - pad:.4f}" y="{-(y1 + pad):.4f}" '
           f'width="{w + 2 * pad:.4f}" height="{h + 2 * pad:.4f}" fill="white"/>\n<g transform="scale(1,-1)">\n'
           + "\n".join(dr.items) + "\n</g>\n</svg>\n")
    return svg, dr.count, dr.skipped


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    import pymupdf

    src = sources[0]
    via = []
    if src.suffix.lower() == ".dwg":  # AutoCAD's own format: read through the free ODA File Converter
        from .oda import dwg_to_dxf

        src = dwg_to_dxf(src, out.parent)
        via = ["Read through the free ODA File Converter."]
        if fmt == "dxf":
            import shutil

            shutil.copyfile(src, long_path(out))
            _entities, _blocks, _skipped = parse(Path(long_path(out)).read_text(encoding="utf-8", errors="replace"))
            if not _entities:
                raise VerificationError("the DXF has nothing drawn in it")
            return [f"Checked: {len(_entities):,} drawing items in the DXF (AutoCAD 2018 DXF)."] + via
    svg, count, skipped = to_svg(src)
    notes = [f"Checked: {count:,} drawing items."] + via
    if skipped:
        notes.append("Not drawn: " + ", ".join(f"{n} {t.lower()}" for t, n in sorted(skipped.items())) + ".")
    if fmt == "svg":
        Path(long_path(out)).write_text(svg, encoding="utf-8")
        import xml.etree.ElementTree as ET

        root = ET.fromstring(Path(long_path(out)).read_bytes())
        drawn = sum(1 for el in root.iter() if el.tag.rsplit("}", 1)[-1] in ("path", "circle", "text"))
        if drawn != count:
            raise VerificationError("the drawing lost items")
        return notes
    with pymupdf.open("svg", svg.encode("utf-8")) as doc:
        if fmt == "pdf":
            pdf = pymupdf.open("pdf", doc.convert_to_pdf())
            pdf.set_metadata({"title": sources[0].stem, "creator": "Deskvert"})
            pdf.save(long_path(out), garbage=3, deflate=True)
            pdf.close()
            with pymupdf.open(long_path(out)) as d:
                if d.page_count != 1:
                    raise VerificationError("the PDF is broken")
        elif fmt == "png":
            page = doc[0]
            zoom = 2400 / max(page.rect.width, page.rect.height)
            page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).save(long_path(out))
            from PIL import Image

            with Image.open(long_path(out)) as im:
                if max(im.size) < 2000:
                    raise VerificationError("the picture is broken")
        else:
            raise ConversionError(f"Unknown drawing format: {fmt}")
    return notes
