"""What the picker shows: the offers for a selection, arranged as a web.

Top-level nodes circle the selection. Related choices are grouped into a branch
(for example Split: in half / every N pages / by ranges / every page) whose
children fan out when you point at it, so new tools can keep joining without
the picker growing. Mixed selections get one branch per type of file plus
"All files" actions. Favourites, recently used actions and your own presets
fill the inner ring.

Light on purpose: this runs in the tray app on every shortcut press.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Offer, kind_of, offers_for
from .settings import Settings

# Branches per kind of file: (label, caption, target keys in order). A branch with only one
# available choice is shown as that choice instead.
BRANCHES = {
    "pdf": [
        ("Split", "into parts", ["pdf.splithalf", "pdf.splitevery", "pdf.splitranges", "pdf.split"]),
        ("Pages", "order and layout", ["pdf.pages", "pdf.reorder", "pdf.reverse", "pdf.rotate", "pdf.numbers",
                                       "pdf.nup"]),
        ("Protect", "password and more", ["pdf.lock", "pdf.unlock", "pdf.watermark", "pdf.flatten", "pdf.clean"]),
        ("Convert", "to other files", ["pdf.png", "pdf.jpg", "pdf.txt", "pdf.md", "pdf.html", "ebook.epub",
                                       "pdf.longimg", "pdf.tiff", "ebook.cbz", "pdf.pictures", "pdf.gray"]),
        ("Text", "read scans", ["ocr.txt", "ocr.pdf"]),
    ],
    "image": [
        ("Edit", "turn, resize, clean", ["imgedit.rotr", "imgedit.rotl", "imgedit.rot180", "imgedit.flip",
                                         "imgedit.resize", "imgedit.gray", "imgedit.clean", "imgedit.dpi",
                                         "imgedit.stitch", "imgedit.anim"]),
        ("More formats", "every image format", ["image.heic", "image.avif", "image.ico", "image.tiff", "image.gif",
                                                "image.bmp", "image.jp2", "image.icns", "image.tga", "image.qoi",
                                                "image.dds", "image.pcx", "image.ppm", "image.sgi", "image.xbm",
                                                "vector.pdf", "vector.svgz", "vector.svg"]),
        ("Text", "read the text", ["ocr.txt", "ocr.pdf"]),
    ],
    "data": [("JSON tools", "tidy or minify", ["data.tidy", "data.minify", "data.jsonl"]),
             ("Map", "from coordinates", ["geo.kml", "geo.geojson", "geo.gpx", "geo.kmz"]),
             ("More formats", "TOML, XML, TSV", ["data.toml", "data.xml", "data.tsv"])],
    "subtitle": [("More formats", "every subtitle format", ["subtitle.ass", "subtitle.sami", "subtitle.ttml",
                                                           "subtitle.lrc", "subtitle.microdvd"])],
    "model": [("More formats", "every 3D format", ["mesh.3mf", "mesh.ply"])],
    "document": [("Data", "without Excel", ["data.sheets", "data.json", "data.yaml", "data.xml"])],
    "map": [("Data", "tables", ["geo.csv", "geo.xlsx"])],
    "audio": [("Lossless", "WAV, FLAC", ["media.wav", "media.flac"])],
    "video": [("Sound", "MP3, M4A, WAV...", ["media.mp3", "media.m4a", "media.wav", "media.flac", "media.wma"])],
}
KIND_WORDS = {"image": ("picture", "pictures"), "document": ("document", "documents"), "data": ("data file", "data files"),
              "markdown": ("Markdown file", "Markdown files"), "archive": ("archive", "archives"),
              "subtitle": ("subtitle file", "subtitle files"), "ebook": ("e-book", "e-books"),
              "font": ("font", "fonts"), "model": ("3D model", "3D models"), "drawing": ("drawing", "drawings"),
              "mail": ("e-mail or page", "e-mails or pages"), "map": ("map file", "map files"),
              "vector": ("drawing", "drawings"), "audio": ("sound file", "sound files"),
              "video": ("video", "videos")}
# Every kind of file: the ways to pack them.
PACK = ("Pack", "ZIP, 7Z, TAR.GZ", ["archive.zip", "archive.7z", "archive.targz"])
REPACK = ("Repack", "ZIP, 7Z, TAR.GZ", ["archive.tozip", "archive.to7z", "archive.totargz"])
FAN_MAX = 8  # choices in one fan; bigger groups open fans of their own (a web, never a list)
# Big branches, split into named fans of their own: (kind, branch) -> [(label, caption, keys)].
SUBGROUPS = {
    ("image", "More formats"): [
        ("Everyday", "HEIC, AVIF, ICO...", ["image.heic", "image.avif", "image.ico", "image.tiff", "image.gif",
                                            "image.bmp"]),
        ("Pro", "JPEG 2000, ICNS...", ["image.jp2", "image.icns", "image.tga", "image.qoi", "image.dds"]),
        ("Classic", "PCX, PPM, SGI, XBM", ["image.pcx", "image.ppm", "image.sgi", "image.xbm"]),
        ("Vector", "SVG as PDF", ["vector.pdf", "vector.svgz", "vector.svg"]),
    ],
    ("image", "Edit"): [
        ("Turn", "rotate, mirror", ["imgedit.rotr", "imgedit.rotl", "imgedit.rot180", "imgedit.flip"]),
        ("Fix", "size, color, info", ["imgedit.resize", "imgedit.gray", "imgedit.clean", "imgedit.dpi"]),
        ("Combine", "several in one", ["imgedit.stitch", "imgedit.anim"]),
    ],
    ("pdf", "Convert"): [
        ("As images", "PNG, JPG, TIFF...", ["pdf.png", "pdf.jpg", "pdf.longimg", "pdf.tiff", "pdf.pictures"]),
        ("As text", "TXT, Markdown, HTML", ["pdf.txt", "pdf.md", "pdf.html"]),
        ("As e-book", "EPUB, comic", ["ebook.epub", "ebook.cbz"]),
    ],
}


def _nest(kids: list, kind: str = "", branch: str = "") -> list:
    """Keep every fan readable: named sub-fans where defined, otherwise extra fans of up to FAN_MAX."""
    if len(kids) <= FAN_MAX:
        return kids
    by_key = {k.key: k for k in kids}
    named = SUBGROUPS.get((kind, branch))
    out, used = [], set()
    if named:
        for label, caption, keys in named:
            sub = [by_key[k] for k in keys if k in by_key and k not in used]
            used.update(n.key for n in sub)
            if len(sub) == 1:
                out.append(sub[0])
            elif sub:
                out.append(Node(label, caption, children=_nest(sub), key=f"branch:{branch}/{label}"))
        rest = [k for k in kids if k.key not in used]
        out += rest
        if len(out) <= FAN_MAX:
            return out
        kids = out
    # generic: the first choices stay, the rest open a further fan ("More"), as deep as needed
    head, tail = kids[:FAN_MAX - 1], kids[FAN_MAX - 1:]
    return head + [Node("More", f"{len(tail)} more", children=_nest(tail), key=f"branch:{branch}/more")]
QUICK_MAX = 6
# Mixed selections: the most useful actions per type (the rest are under "More…").
MIXED_PICKS = {
    "pdf": ["pdf.compress", "pdf.merge", "pdf.lock", "pdf.splithalf", "pdf.pages", "pdf.gray", "pdf.png", "ocr.txt"],
    "image": ["compress.image", "image.jpg", "image.png", "image.webp", "image.pdf_combined", "imgedit.resize",
              "ocr.txt"],
}


@dataclass
class Node:
    label: str
    caption: str = ""
    offer: Offer | None = None
    children: list[Node] = field(default_factory=list)
    preset: dict | None = None  # options chosen in advance (a saved preset): nothing to ask
    key: str = ""  # remembered for favourites and recents: the target key, or "preset:<id>"
    tool: bool = True
    blurb: str = ""  # overrides the usual one-line description (presets)

    @property
    def branch(self) -> bool:
        return bool(self.children)

    def leaves(self):
        if self.children:
            for c in self.children:
                yield from c.leaves()
        elif self.offer is not None:
            yield self


def _is_tool(o: Offer) -> bool:
    t = o.target
    return t.engine in ("compress", "archive", "ocr") or bool(t.suffix) or t.ask or t.combine or t.key.startswith(
        "pdf.split")


def _leaf(o: Offer) -> Node:
    return Node(o.target.label, o.caption, offer=o, key=o.target.key, tool=_is_tool(o))


def _arrange(offers: list[Offer], kind: str) -> list[Node]:
    """Offers -> top-level nodes, grouping related ones into branches."""
    by_key = {o.target.key: o for o in offers}
    branch_of: dict[str, tuple[str, str]] = {}
    groups = list(BRANCHES.get(kind, [])) + [PACK, REPACK]
    for label, caption, keys in groups:
        for k in keys:
            branch_of.setdefault(k, (label, caption))
    nodes: list[Node] = []
    built: dict[str, Node] = {}
    for o in offers:
        b = branch_of.get(o.target.key)
        if b is None:
            nodes.append(_leaf(o))
            continue
        if b[0] not in built:
            keys = next(k for lbl, _c, k in groups if lbl == b[0])
            kids = [_leaf(by_key[k]) for k in keys if k in by_key]
            kids = _nest(kids, kind, b[0])
            node = kids[0] if len(kids) == 1 else Node(b[0], b[1], children=kids, key=f"branch:{b[0]}")
            built[b[0]] = node
            nodes.append(node)
    return nodes


def _menu_kind(files: list[Path]) -> str:
    k = kind_of(files[0])
    if k == "document" and all(p.suffix.lower() == ".pdf" for p in files):
        return "pdf"
    return k or ""


def _groups(paths: list[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for p in paths:
        k = kind_of(p)
        if k == "document" and p.suffix.lower() == ".pdf":
            k = "pdf"
        if k:
            groups.setdefault(k, []).append(p)
    return groups


def build_menu(paths: list[Path], s: Settings) -> tuple[list[Node], list[Node], list[Path]]:
    """(top-level nodes, quick nodes for the inner ring, files nothing applies to)."""
    groups = _groups(paths)
    unsupported = [p for p in paths if not any(p in g for g in groups.values())]
    if len(groups) <= 1:
        offers, left_out = offers_for(paths, s)
        kind = _menu_kind([p for p in paths if p not in left_out] or paths) if offers else ""
        nodes = _arrange(offers, kind)
        quick = _quick(nodes, s, kind)
        on_inner = {q.key for q in quick}
        nodes = [n for n in nodes if n.branch or n.key not in on_inner]  # no duplicates on the outer ring
        return nodes, quick, left_out
    # Mixed selection: one branch per type of file, plus actions for all of them.
    nodes: list[Node] = []
    for kind, files in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        offers, _ = offers_for(files, s)
        offers = [o for o in offers if o.target.key not in ("archive.zip", "archive.7z", "archive.targz")]
        if not offers:
            continue
        picks = MIXED_PICKS.get(kind)
        chosen = ([o for k in picks for o in offers if o.target.key == k] if picks else offers)[:FAN_MAX - 1]
        leaves = [_leaf(o) for o in chosen]
        rest = [_leaf(o) for o in offers if o not in chosen]
        if rest:  # everything else for these files, one fan further out (no list, no search)
            leaves.append(Node("All", f"{len(rest)} more", children=_nest(rest), key=f"branch:{kind}/all"))
        one, many = KIND_WORDS.get("document" if kind == "pdf" else kind, ("file", "files"))
        if kind == "pdf":
            one, many = "PDF", "PDFs"
        label = f"{len(files)} {one if len(files) == 1 else many}"
        nodes.append(Node(label, "for these only", children=leaves, key=f"group:{kind}"))
    from . import toolbox

    combinable = [p for p in paths if p in groups.get("pdf", []) or p in groups.get("image", [])]
    if len(combinable) >= 2 and "pdf" in groups and "image" in groups:
        o = Offer(toolbox.MIXED_PDF, "into 1 PDF", ["Pictures and PDFs in one PDF, in the order selected."])
        o.sources = combinable
        n = _leaf(o)
        n.label = "Combine"
        nodes.append(n)
    z = toolbox.zip_offer(list(paths))
    nodes.append(_leaf(z))
    return nodes, _quick(nodes, s, "mixed"), unsupported


def _quick(nodes: list[Node], s: Settings, kind: str) -> list[Node]:
    """Your presets, favourites and recent actions that apply here (inner ring)."""
    leaves = {n.key: n for top in nodes for n in top.leaves()}
    quick: list[Node] = []
    for p in getattr(s, "presets", []) or []:
        base = leaves.get(p.get("key", ""))
        if base is not None and base.offer is not None:
            quick.append(Node(p.get("name", "Preset"), p.get("summary", ""), offer=base.offer,
                              preset=dict(p.get("options", {})), key=f"preset:{p.get('id', '')}", tool=True,
                              blurb=p.get("summary", "")))
    want = list(getattr(s, "favourites", []) or [])
    if getattr(s, "quick_recents", True):
        want += list(getattr(s, "recent_actions", []) or [])
    for key in want:
        if len(quick) >= QUICK_MAX:
            break
        n = leaves.get(key)
        if n is not None and all(q.key != key for q in quick):
            quick.append(n)
    # Don't keep a single top-level node that's only a duplicate of the inner ring.
    return quick[:QUICK_MAX]


def remember(s: Settings, key: str) -> None:
    """Note an action as recently used (most recent first)."""
    if not key or key.startswith(("branch:", "group:")):
        return
    rec = [k for k in (getattr(s, "recent_actions", []) or []) if k != key]
    s.recent_actions = [key] + rec[:7]


# ------------------------------------------------------------- customizing

# Actions you can pin to the inner ring from Settings (shown only when they apply).
FAVOURITE_CHOICES = [
    ("compress.image", "Pictures: Compress"), ("image.jpg", "Pictures: to JPG"), ("image.png", "Pictures: to PNG"),
    ("image.webp", "Pictures: to WEBP"), ("image.pdf_combined", "Pictures: into 1 PDF"),
    ("ocr.txt", "Read the text (pictures or scans)"), ("pdf.compress", "PDF: Compress"),
    ("pdf.merge", "PDFs: into 1 PDF"), ("pdf.lock", "PDF: Lock"), ("pdf.unlock", "PDF: Unlock"),
    ("pdf.splithalf", "PDF: Split in half"), ("pdf.pages", "PDF: Keep or remove pages"),
    ("pdf.rotate", "PDF: Rotate"), ("pdf.numbers", "PDF: Page numbers"), ("pdf.watermark", "PDF: Watermark"),
    ("pdf.gray", "PDF: Grayscale"), ("pdf.png", "PDF: pages to PNG"), ("pdf.nup", "PDF: pages per sheet"),
    ("imgedit.rotr", "Pictures: turn right"), ("imgedit.resize", "Pictures: resize"),
    ("imgedit.clean", "Pictures: remove location & camera info"), ("doc.pdf", "Documents: to PDF"),
    ("archive.zip", "Any files: ZIP"), ("media.mp3", "Sound: to MP3"), ("media.m4a", "Sound: to M4A"),
]
FAVOURITE_NAMES = dict(FAVOURITE_CHOICES)

# Preset kinds: (id, label in Settings).
PRESET_KINDS = [("image_size", "Picture under a size"), ("image_exact", "Picture, exact size"),
                ("pdf_size", "PDF under a size")]
STARTER_PRESETS = [
    ("WhatsApp photo", "image_size", {"kb": 300, "fmt": "JPG"}),
    ("College PDF", "pdf_size", {"kb": 300}),
    ("Exam photo", "image_exact", {"kb": 50, "w": 200, "h": 230}),
]


def make_preset(name: str, kind: str, kb: int, w: int = 0, h: int = 0, fmt: str = "JPG") -> dict:
    """A saved preset: one action with its options chosen in advance.
    Raises ValueError with a short, friendly message when something is off."""
    import uuid

    name = " ".join(name.split())[:28]
    if not name:
        raise ValueError("Give the preset a name.")
    suffix = f" ({name})"
    if kind == "image_size":
        if not 5 <= kb <= 20_000:
            raise ValueError("Size limit: 5 to 20000 KB.")
        fmt = fmt if fmt in ("JPG", "WEBP") else "JPG"
        key, opts, summary = "compress.image", {"mode": "size", "target_kb": kb, "format": fmt,
                                                "name_suffix": suffix}, f"{fmt} under {kb} KB"
    elif kind == "image_exact":
        if not (16 <= w <= 8000 and 16 <= h <= 8000):
            raise ValueError("Width and height: 16 to 8000 px.")
        if not 5 <= kb <= 20_000:
            raise ValueError("Size limit: 5 to 20000 KB.")
        key, opts = "compress.image", {"format": "JPG", "mode": "preset", "preset": "custom", "w": w, "h": h,
                                       "max_kb": kb, "name_suffix": suffix}
        summary = f"{w}×{h} px, under {kb} KB"
    elif kind == "pdf_size":
        if not 20 <= kb <= 50_000:
            raise ValueError("Size limit for a PDF: 20 to 50000 KB.")
        key, opts, summary = "pdf.compress", {"level": "Custom", "limit_kb": kb, "name_suffix": suffix}, \
            f"PDF under {kb} KB"
    else:
        raise ValueError("Unknown kind of preset.")
    return {"id": uuid.uuid4().hex[:8], "name": name, "kind": kind, "key": key, "options": opts,
            "summary": summary}
