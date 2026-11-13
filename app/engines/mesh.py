"""3D models: STL, OBJ, PLY, 3MF and GLB / glTF into each other, and a PNG preview.

The model's shape (its points and triangles) is converted; colors, textures and
materials are not, and the notes say so when the source had them. Faces with
more than three corners are split into triangles. glTF scenes are flattened
with their transforms applied. Units are kept as numbers (3MF says millimeters).

The new file is read back: the same triangles, at the same positions.
"""

from __future__ import annotations

import base64
import json
import re
import struct
import zipfile
from pathlib import Path

import numpy as np

from ..errors import ConversionError, VerificationError
from ..paths import long_path

EXTS = {".stl": "stl", ".obj": "obj", ".ply": "ply", ".3mf": "3mf", ".glb": "glb", ".gltf": "gltf"}
MAX_PREVIEW_TRIANGLES = 300_000


class Mesh:
    def __init__(self, v: np.ndarray, f: np.ndarray, extras: bool = False):
        self.v = np.asarray(v, dtype=np.float64).reshape(-1, 3)
        self.f = np.asarray(f, dtype=np.int64).reshape(-1, 3)
        self.extras = extras  # the source had colors / textures / materials
        self.zup = True  # STL, PLY and 3MF point Z up; glTF and most OBJ files point Y up
        if len(self.f) == 0:
            raise ConversionError("This model has no triangles.")
        if self.f.min() < 0 or self.f.max() >= len(self.v):
            raise ConversionError("This model is damaged (a face points to a missing corner).")

    def tris(self) -> np.ndarray:
        return self.v[self.f]


def _fan(poly: list[int]) -> list[list[int]]:
    return [[poly[0], poly[i], poly[i + 1]] for i in range(1, len(poly) - 1)]


# ---------------------------------------------------------------- readers

def read_stl(data: bytes) -> Mesh:
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + 50 * n == len(data):
            rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
                                count=n, offset=84)
            tris = rec["v"].astype(np.float64)
            return _dedupe(tris)
    text = data.decode("latin-1")
    nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
    if not nums or len(nums) % 3:
        raise ConversionError("This STL file couldn't be read.")
    tris = np.array(nums, dtype=np.float64).reshape(-1, 3, 3)
    return _dedupe(tris)


def _dedupe(tris: np.ndarray) -> Mesh:
    pts = tris.reshape(-1, 3)
    uniq, inv = np.unique(pts, axis=0, return_inverse=True)
    return Mesh(uniq, inv.reshape(-1, 3))


def read_obj(text: str) -> Mesh:
    vs, faces, extras = [], [], False
    for line in text.splitlines():
        if line.startswith("v "):
            parts = line.split()
            vs.append([float(parts[1]), float(parts[2]), float(parts[3])])
            if len(parts) > 4:
                extras = True  # vertex colors
        elif line.startswith("f "):
            idx = []
            for tok in line.split()[1:]:
                i = int(tok.split("/")[0])
                idx.append(i - 1 if i > 0 else len(vs) + i)
            faces += _fan(idx)
        elif line.startswith(("usemtl", "mtllib", "vt ")):
            extras = True
    if not faces:
        raise ConversionError("This OBJ file has no faces.")
    return Mesh(np.array(vs), np.array(faces), extras)


PLY_TYPES = {"char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1", "short": "i2", "int16": "i2",
             "ushort": "u2", "uint16": "u2", "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4",
             "float": "f4", "float32": "f4", "double": "f8", "float64": "f8"}


def read_ply(data: bytes) -> Mesh:
    end = data.find(b"end_header")
    if not data.startswith(b"ply") or end < 0:
        raise ConversionError("This isn't a PLY file.")
    body_start = data.index(b"\n", end) + 1
    header = data[:end].decode("latin-1").splitlines()
    fmt = "ascii"
    elements: list[dict] = []
    for line in header:
        p = line.split()
        if not p:
            continue
        if p[0] == "format":
            fmt = p[1]
        elif p[0] == "element":
            elements.append({"name": p[1], "count": int(p[2]), "props": []})
        elif p[0] == "property" and elements:
            elements[-1]["props"].append(p[1:])
    extras = any(pr[-1] in ("red", "green", "blue", "s", "t", "u", "v") for e in elements for pr in e["props"])
    verts = faces = None
    if fmt == "ascii":
        rows = data[body_start:].decode("latin-1").split("\n")
        k = 0
        for e in elements:
            block = rows[k:k + e["count"]]
            k += e["count"]
            if e["name"] == "vertex":
                names = [pr[-1] for pr in e["props"]]
                ix = [names.index(c) for c in ("x", "y", "z")]
                verts = np.array([[float(r.split()[i]) for i in ix] for r in block])
            elif e["name"] == "face":
                faces = [tri for r in block for tri in _fan([int(x) for x in r.split()[1:]][:int(r.split()[0])])]
        if verts is None or faces is None:
            raise ConversionError("This PLY file has no vertices or faces.")
        return Mesh(verts, np.array(faces), extras)
    order = "<" if fmt == "binary_little_endian" else ">"
    pos = body_start
    for e in elements:
        if e["name"] == "face" or any(pr[0] == "list" for pr in e["props"]):
            if e["name"] != "face":
                raise ConversionError("This PLY file has a layout Deskvert doesn't read.")
            lst = next(pr for pr in e["props"] if pr[0] == "list")
            ct, it = order + PLY_TYPES[lst[1]], order + PLY_TYPES[lst[2]]
            if len(e["props"]) == 1:  # try the common case: every face a triangle
                dt = np.dtype([("n", ct), ("i", it, 3)])
                arr = np.frombuffer(data, dtype=dt, count=e["count"], offset=pos)
                if (arr["n"] == 3).all():
                    faces = arr["i"].astype(np.int64)
                    pos += dt.itemsize * e["count"]
                    continue
            out = []
            cs, isz = np.dtype(ct).itemsize, np.dtype(it).itemsize
            for _ in range(e["count"]):
                n = int(np.frombuffer(data, dtype=ct, count=1, offset=pos)[0])
                pos += cs
                idx = np.frombuffer(data, dtype=it, count=n, offset=pos).tolist()
                pos += isz * n
                out += _fan(idx)
            faces = np.array(out)
        else:
            dt = np.dtype([(pr[-1], order + PLY_TYPES[pr[0]]) for pr in e["props"]])
            arr = np.frombuffer(data, dtype=dt, count=e["count"], offset=pos)
            pos += dt.itemsize * e["count"]
            if e["name"] == "vertex":
                verts = np.stack([arr["x"], arr["y"], arr["z"]], axis=1).astype(np.float64)
    if verts is None or faces is None:
        raise ConversionError("This PLY file has no vertices or faces.")
    return Mesh(verts, faces, extras)


def read_3mf(path: Path) -> Mesh:
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(long_path(path)) as z:
        name = next((n for n in z.namelist() if n.lower().endswith(".model")), None)
        if name is None:
            raise ConversionError("This 3MF file has no model inside.")
        root = ET.fromstring(z.read(name))
    local = lambda el: el.tag.rsplit("}", 1)[-1]  # noqa: E731
    objects = {}
    extras = False
    for obj in root.iter():
        if local(obj) != "object":
            continue
        for mesh in obj:
            if local(mesh) != "mesh":
                continue
            vs = [[float(x.get("x")), float(x.get("y")), float(x.get("z"))] for x in mesh.iter() if local(x) == "vertex"]
            fs = []
            for t in mesh.iter():
                if local(t) == "triangle":
                    fs.append([int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))])
                    extras = extras or "pid" in t.attrib
            objects[obj.get("id")] = (np.array(vs), np.array(fs))
    allv, allf = [], []
    items = [it for it in root.iter() if local(it) == "item"] or [None]
    for it in items:
        oid = it.get("objectid") if it is not None else next(iter(objects), None)
        if oid not in objects:
            continue
        v, f = objects[oid]
        if it is not None and it.get("transform"):
            m = [float(x) for x in it.get("transform").split()]
            mat = np.array(m).reshape(4, 3)
            v = v @ mat[:3] + mat[3]
        allf.append(f + sum(len(x) for x in allv))
        allv.append(v)
    if not allv:
        raise ConversionError("This 3MF file has no meshes.")
    return Mesh(np.concatenate(allv), np.concatenate(allf), extras)


def _gltf_buffers(gltf: dict, bin_chunk: bytes | None, folder: Path) -> list[bytes]:
    out = []
    for i, b in enumerate(gltf.get("buffers", [])):
        uri = b.get("uri")
        if uri is None:
            if bin_chunk is None:
                raise ConversionError("This model's data is missing.")
            out.append(bin_chunk)
        elif uri.startswith("data:"):
            out.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            p = (folder / uri).resolve()
            if folder.resolve() not in p.parents:
                raise ConversionError("This model refers to a file outside its folder.")
            out.append(Path(long_path(p)).read_bytes())
    return out


COMP = {5120: "i1", 5121: "u1", 5122: "i2", 5123: "u2", 5125: "u4", 5126: "f4"}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _accessor(gltf, buffers, idx) -> np.ndarray:
    acc = gltf["accessors"][idx]
    bv = gltf["bufferViews"][acc["bufferView"]]
    dt = np.dtype("<" + COMP[acc["componentType"]])
    n = NCOMP[acc["type"]]
    buf = buffers[bv["buffer"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    if stride and stride != dt.itemsize * n:
        rows = [np.frombuffer(buf, dtype=dt, count=n, offset=start + i * stride) for i in range(acc["count"])]
        return np.array(rows)
    return np.frombuffer(buf, dtype=dt, count=acc["count"] * n, offset=start).reshape(acc["count"], n)


def _node_matrix(node) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.array(node.get("translation", [0, 0, 0]), dtype=np.float64)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    s = np.diag(node.get("scale", [1, 1, 1]))
    m = np.eye(4)
    m[:3, :3] = r @ s
    m[:3, 3] = t
    return m


def read_gltf(path: Path) -> Mesh:
    data = Path(long_path(path)).read_bytes()
    bin_chunk = None
    if data[:4] == b"glTF":
        pos, js = 12, None
        while pos < len(data):
            ln, kind = struct.unpack("<II", data[pos:pos + 8])
            chunk = data[pos + 8:pos + 8 + ln]
            if kind == 0x4E4F534A:
                js = json.loads(chunk.decode("utf-8"))
            elif kind == 0x004E4942:
                bin_chunk = chunk
            pos += 8 + ln
        gltf = js
    else:
        gltf = json.loads(data.decode("utf-8-sig"))
    used = set(gltf.get("extensionsUsed", []))
    if used & {"KHR_draco_mesh_compression", "EXT_meshopt_compression"}:
        raise ConversionError("This model is compressed (Draco or meshopt), which Deskvert can't unpack.")
    buffers = _gltf_buffers(gltf, bin_chunk, path.parent)
    extras = bool(gltf.get("materials") or gltf.get("textures"))
    allv, allf = [], []

    def visit(ni, parent):
        node = gltf["nodes"][ni]
        m = parent @ _node_matrix(node)
        if "mesh" in node:
            for prim in gltf["meshes"][node["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4:
                    continue
                v = _accessor(gltf, buffers, prim["attributes"]["POSITION"]).astype(np.float64)
                v = (np.c_[v, np.ones(len(v))] @ m.T)[:, :3]
                f = (_accessor(gltf, buffers, prim["indices"]).reshape(-1).astype(np.int64) if "indices" in prim
                     else np.arange(len(v)))
                allf.append(f.reshape(-1, 3) + sum(len(x) for x in allv))
                allv.append(v)
        for c in node.get("children", []):
            visit(c, m)

    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)] if gltf.get("scenes") else {"nodes": list(
        range(len(gltf.get("nodes", []))))}
    for ni in scene.get("nodes", []):
        visit(ni, np.eye(4))
    if not allv:
        raise ConversionError("This model has no triangle meshes.")
    return Mesh(np.concatenate(allv), np.concatenate(allf), extras)


def read(path: Path) -> Mesh:
    kind = EXTS.get(path.suffix.lower())
    try:
        if kind == "stl":
            return read_stl(Path(long_path(path)).read_bytes())
        if kind == "obj":
            m = read_obj(Path(long_path(path)).read_text(encoding="utf-8", errors="replace"))
            m.zup = False
            return m
        if kind == "ply":
            return read_ply(Path(long_path(path)).read_bytes())
        if kind == "3mf":
            return read_3mf(path)
        if kind in ("glb", "gltf"):
            m = read_gltf(path)
            m.zup = False
            return m
    except ConversionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"This 3D model couldn't be read ({e}).") from e
    raise ConversionError("Unknown 3D model format.")


# ---------------------------------------------------------------- writers

def write_stl(m: Mesh, out: Path) -> None:
    t = m.tris().astype(np.float32)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    rec = np.zeros(len(t), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    rec["n"], rec["v"] = n, t
    with open(long_path(out), "wb") as fh:
        fh.write(b"Deskvert STL".ljust(80, b" ") + struct.pack("<I", len(t)) + rec.tobytes())


def write_obj(m: Mesh, out: Path) -> None:
    lines = ["# made with Deskvert"]
    lines += [f"v {x!r} {y!r} {z!r}" for x, y, z in m.v.tolist()]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in m.f.tolist()]
    Path(long_path(out)).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_ply(m: Mesh, out: Path) -> None:
    head = (f"ply\nformat binary_little_endian 1.0\ncomment made with Deskvert\nelement vertex {len(m.v)}\n"
            "property double x\nproperty double y\nproperty double z\n"
            f"element face {len(m.f)}\nproperty list uchar int vertex_indices\nend_header\n").encode("ascii")
    faces = np.zeros(len(m.f), dtype=np.dtype([("n", "u1"), ("i", "<i4", 3)]))
    faces["n"], faces["i"] = 3, m.f
    with open(long_path(out), "wb") as fh:
        fh.write(head + m.v.astype("<f8").tobytes() + faces.tobytes())


def write_3mf(m: Mesh, out: Path) -> None:
    verts = "".join(f'<vertex x="{x!r}" y="{y!r}" z="{z!r}"/>' for x, y, z in m.v.tolist())
    tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.f.tolist())
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources><object id="1" '
             f'type="model"><mesh><vertices>{verts}</vertices><triangles>{tris}</triangles></mesh></object>'
             '</resources><build><item objectid="1"/></build></model>')
    types = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
             'content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
             'relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing'
             '-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.'
            'com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(long_path(out), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)


def write_glb(m: Mesh, out: Path) -> None:
    pos = m.v.astype("<f4")
    idx = m.f.astype("<u4").reshape(-1)
    pb, ib = pos.tobytes(), idx.tobytes()
    gltf = {
        "asset": {"version": "2.0", "generator": "Deskvert"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "buffers": [{"byteLength": len(pb) + len(ib)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pb), "target": 34962},
                        {"buffer": 0, "byteOffset": len(pb), "byteLength": len(ib), "target": 34963}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
                       "min": pos.min(axis=0).tolist(), "max": pos.max(axis=0).tolist()},
                      {"bufferView": 1, "componentType": 5125, "count": len(idx), "type": "SCALAR"}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    binary = pb + ib
    binary += b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    with open(long_path(out), "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js +
                 struct.pack("<II", len(binary), 0x004E4942) + binary)


def preview(m: Mesh, out: Path, notes: list[str]) -> None:
    """A shaded picture of the model, seen from the front, a little from above and the side."""
    from PIL import Image, ImageDraw

    t = m.tris()
    if len(t) > MAX_PREVIEW_TRIANGLES:
        step = int(np.ceil(len(t) / MAX_PREVIEW_TRIANGLES))
        t = t[::step]
        notes.append(f"Big model: every {step}th triangle is drawn in the preview.")
    c = (t.reshape(-1, 3).max(0) + t.reshape(-1, 3).min(0)) / 2
    t = t - c
    a, b = np.radians(-35), np.radians(25)
    ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
    # models are usually Z-up (STL, 3MF): turn so Z points up on screen
    zup = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]]) if m.zup else np.eye(3)
    p = t @ zup.T @ ry.T @ rx.T
    W, H, pad = 1200, 900, 40
    xy = p[..., :2]
    span = max(np.ptp(xy[..., 0]), np.ptp(xy[..., 1])) or 1.0
    s = min(W - 2 * pad, H - 2 * pad) / span
    sx = xy[..., 0] * s + W / 2
    sy = -xy[..., 1] * s + H / 2
    nrm = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    light = np.abs(nrm @ np.array([0.3, 0.5, 0.8]) / np.where(ln > 0, ln, 1) / np.linalg.norm([0.3, 0.5, 0.8]))
    order = np.argsort(p[..., 2].mean(axis=1))  # far first
    img = Image.new("RGB", (W, H), (245, 246, 248))
    d = ImageDraw.Draw(img)
    for i in order.tolist():
        g = int(70 + 165 * light[i])
        d.polygon([(sx[i, 0], sy[i, 0]), (sx[i, 1], sy[i, 1]), (sx[i, 2], sy[i, 2])], fill=(g // 2 + 20, g, g // 2 + 60))
    img.save(long_path(out), "PNG")


WRITERS = {"stl": write_stl, "obj": write_obj, "ply": write_ply, "3mf": write_3mf, "glb": write_glb}


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    m = read(sources[0])
    notes: list[str] = []
    if fmt == "png":
        preview(m, out, notes)
        from PIL import Image

        with Image.open(long_path(out)) as im:
            if im.size != (1200, 900):
                raise VerificationError("the preview picture is broken")
        notes.insert(0, f"Checked: a preview of {len(m.f):,} triangles.")
        return notes
    if fmt not in WRITERS:
        raise ConversionError(f"Unknown 3D format: {fmt}")
    WRITERS[fmt](m, out)
    back = read(out)
    a, b = m.tris(), back.tris()
    size = float(np.ptp(m.v, axis=0).max()) or 1.0
    tol = size * (2e-6 if fmt in ("stl", "glb") else 1e-9) + 1e-9  # STL and GLB store 32-bit numbers
    if a.shape != b.shape or not np.allclose(a, b, rtol=0, atol=tol):
        raise VerificationError("the triangles changed")
    notes.append(f"Checked: {len(m.f):,} triangles, {len(m.v):,} corners, same shape.")
    if m.extras:
        notes.append("Colors, textures and materials aren't converted; only the shape is.")
    return notes
