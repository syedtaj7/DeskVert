"""Builds the website's generated parts from the app itself, so the site always matches what Deskvert does:

- website/formats.json        every file type and what it turns into (the format finder reads it)
- website/convert/<a>-to-<b>.html   one page per popular conversion (found by people searching for it),
                                    written from the app's own captions and warnings for that conversion
- website/convert/index.html  every conversion page, grouped
- website/changelog.html      What's new, from CHANGELOG.md
- website/sitemap.xml         every page
- the counts on the home page ("N kinds of files. M ways out.")

    python tools/make_site_pages.py        (run again after adding conversions or a release)
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SITE = ROOT / "website"
BASE = "https://deskvert-website.vercel.app"
GENERIC = {"ZIP", "7Z", "TAR.GZ", "Checksum"}  # offered for every file: not listed per type

# (file type, the picker's label, page name, how people say the two formats)
PAIRS = [
    (".heic", "JPG", "heic-to-jpg", "HEIC", "JPG"), (".heic", "PNG", "heic-to-png", "HEIC", "PNG"),
    (".heic", "PDF", "heic-to-pdf", "HEIC", "PDF"), (".webp", "JPG", "webp-to-jpg", "WEBP", "JPG"),
    (".webp", "PNG", "webp-to-png", "WEBP", "PNG"), (".png", "JPG", "png-to-jpg", "PNG", "JPG"),
    (".jpg", "PNG", "jpg-to-png", "JPG", "PNG"), (".jpg", "PDF", "jpg-to-pdf", "JPG", "PDF"),
    (".png", "PDF", "png-to-pdf", "PNG", "PDF"), (".jpg", "WEBP", "jpg-to-webp", "JPG", "WEBP"),
    (".png", "WEBP", "png-to-webp", "PNG", "WEBP"), (".avif", "JPG", "avif-to-jpg", "AVIF", "JPG"),
    (".png", "ICO", "png-to-ico", "PNG", "ICO"), (".svg", "PNG", "svg-to-png", "SVG", "PNG"),
    (".png", "SVG", "png-to-svg", "PNG", "SVG"), (".jpg", "SVG", "jpg-to-svg", "JPG", "SVG"),
    (".cr2", "JPG", "cr2-to-jpg", "CR2", "JPG"), (".nef", "JPG", "nef-to-jpg", "NEF", "JPG"),
    (".dng", "JPG", "dng-to-jpg", "DNG", "JPG"), (".tiff", "PDF", "tiff-to-pdf", "TIFF", "PDF"),
    (".pdf", "DOCX", "pdf-to-word", "PDF", "Word"), (".pdf", "JPG", "pdf-to-jpg", "PDF", "JPG"),
    (".pdf", "PNG", "pdf-to-png", "PDF", "PNG"), (".pdf", "TXT", "pdf-to-text", "PDF", "text"),
    (".pdf", "Tables", "pdf-to-excel", "PDF", "Excel"), (".pdf", "Compress", "compress-pdf", "PDF", "a smaller PDF"),
    (".docx", "PDF", "word-to-pdf", "Word", "PDF"), (".doc", "PDF", "doc-to-pdf", "DOC", "PDF"),
    (".xlsx", "PDF", "excel-to-pdf", "Excel", "PDF"), (".pptx", "PDF", "powerpoint-to-pdf", "PowerPoint", "PDF"),
    (".xlsx", "CSV", "excel-to-csv", "Excel", "CSV"), (".csv", "XLSX", "csv-to-excel", "CSV", "Excel"),
    (".json", "CSV", "json-to-csv", "JSON", "CSV"), (".csv", "JSON", "csv-to-json", "CSV", "JSON"),
    (".md", "PDF", "markdown-to-pdf", "Markdown", "PDF"), (".md", "DOCX", "markdown-to-word", "Markdown", "Word"),
    (".epub", "PDF", "epub-to-pdf", "EPUB", "PDF"), (".mp4", "MP3", "mp4-to-mp3", "MP4", "MP3"),
    (".mp4", "GIF", "mp4-to-gif", "MP4", "GIF"), (".mov", "MP3", "mov-to-mp3", "MOV", "MP3"),
    (".m4a", "MP3", "m4a-to-mp3", "M4A", "MP3"), (".wav", "MP3", "wav-to-mp3", "WAV", "MP3"),
    (".flac", "MP3", "flac-to-mp3", "FLAC", "MP3"), (".msg", "PDF", "msg-to-pdf", "Outlook MSG", "PDF"),
    (".eml", "PDF", "eml-to-pdf", "EML", "PDF"), (".kml", "GPX", "kml-to-gpx", "KML", "GPX"),
    (".gpx", "KML", "gpx-to-kml", "GPX", "KML"), (".shp", "KML", "shapefile-to-kml", "Shapefile", "KML"),
    (".shp", "GeoJSON", "shapefile-to-geojson", "Shapefile", "GeoJSON"), (".srt", "WebVTT", "srt-to-vtt", "SRT", "VTT"),
    (".ttf", "WOFF", "ttf-to-woff", "TTF", "WOFF"), (".ttf", "WOFF2", "ttf-to-woff2", "TTF", "WOFF2"),
    (".woff2", "TTF / OTF", "woff2-to-ttf", "WOFF2", "TTF"), (".scc", "SRT", "scc-to-srt", "SCC", "SRT"),
    (".azw3", "EPUB", "azw3-to-epub", "AZW3", "EPUB"), (".azw3", "PDF", "azw3-to-pdf", "AZW3", "PDF"),
    (".mov", "GIF", "mov-to-gif", "MOV", "GIF"),
]

ABOUT = {  # one plain line about each format named on a page
    "HEIC": "the photo format iPhones save, which many Windows apps and websites can't open",
    "JPG": "the picture format that opens everywhere", "PNG": "a lossless picture format that keeps transparency",
    "WEBP": "the compact picture format many websites serve", "AVIF": "a newer, very compact picture format",
    "PDF": "the document format that looks the same everywhere", "ICO": "the icon format Windows and websites use",
    "SVG": "drawings made of shapes that stay sharp at any size", "TIFF": "a high-quality format for scans and print",
    "CR2": "Canon's camera RAW format", "NEF": "Nikon's camera RAW format", "DNG": "Adobe's open camera RAW format",
    "Word": "Microsoft Word's editable DOCX documents", "DOC": "Word's older document format",
    "Excel": "Microsoft Excel workbooks", "PowerPoint": "Microsoft PowerPoint presentations",
    "CSV": "plain tables most apps can read", "JSON": "structured data used by apps and websites",
    "Markdown": "plain text with simple formatting", "EPUB": "the common e-book format", "MP4": "the usual video format",
    "MOV": "the video format iPhones and Macs record", "MP3": "the sound format every player plays",
    "GIF": "short looping pictures for chats and documents", "M4A": "the sound format of iPhone voice memos and "
    "iTunes", "WAV": "uncompressed sound", "FLAC": "lossless compressed sound",
    "Outlook MSG": "e-mails saved from Outlook", "EML": "e-mails saved from most mail apps",
    "KML": "Google Earth's map format", "GPX": "GPS tracks and waypoints", "GeoJSON": "map data for the web",
    "Shapefile": "the classic GIS map format (.shp with its .dbf and .prj)", "SRT": "the common subtitle format",
    "VTT": "the subtitle format web video players use", "TTF": "a desktop font", "WOFF": "a font made for websites",
    "WOFF2": "the smallest font format for websites", "SCC": "TV-style closed captions (Scenarist)",
    "AZW3": "the Kindle book format (books without DRM)",
    "text": "plain text you can paste anywhere", "a smaller PDF": "the same PDF in a smaller file",
}


def input_exts() -> list[str]:
    """Every extension named anywhere in the app's code; the picker then says which it really opens."""
    exts: set[str] = set()
    for py in (ROOT / "app").rglob("*.py"):
        exts |= set(re.findall(r"""["'](\.[a-z0-9]{1,8}(?:\.[a-z0-9]{1,4})?)["']""",
                               py.read_text(encoding="utf-8", errors="ignore")))
    return sorted(exts)


def gather() -> dict:
    """{".heic": {"formats": [labels], "tools": [labels], "offers": {label: (caption, warnings)}}}"""
    from app.catalog import offers_for
    from app.settings import Settings

    folder = Path(tempfile.mkdtemp())
    out = {}
    for ext in input_exts():
        p = folder / ("sample" + ext)
        p.write_bytes(b"")
        try:
            offers, _ = offers_for([p], Settings())
        except Exception:  # noqa: BLE001 - a type the catalog can't judge from an empty file: left out
            continue
        every = {o.target.key for o in offers}
        offers = [o for o in offers if o.target.label not in GENERIC]
        if not offers:
            continue
        out.setdefault("_keys", set()).update(every)
        formats, tools, info = [], [], {}
        for o in offers:
            t = o.target
            is_format = not t.suffix and not t.folder and not t.combine and t.ext not in ("*", "")
            (formats if is_format else tools).append(t.label)
            info[t.label] = (o.caption, list(o.warnings), t.key)
        out[ext] = {"formats": list(dict.fromkeys(formats)), "tools": list(dict.fromkeys(tools)), "offers": info}
    return out


# ---------------------------------------------------------------- page parts

HEAD = """<!doctype html>
<html lang="en" data-theme="auto">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <link rel="canonical" href="{url}">
  <meta name="theme-color" content="#121214" media="(prefers-color-scheme: dark)">
  <meta name="theme-color" content="#fafaf9" media="(prefers-color-scheme: light)">
  <link rel="icon" href="{up}assets/favicon.ico" sizes="any">
  <link rel="icon" href="{up}assets/logo.png" type="image/png">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Deskvert">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{base}/assets/og-image.png">
  <meta name="twitter:card" content="summary_large_image">
  {jsonld}
  <link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css">
  <link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/bold/style.css">
  <link rel="stylesheet" href="{up}styles.css">
  <link rel="stylesheet" href="{up}pages.css?v=1">
  <script>try {{ const t = localStorage.getItem("deskvert-theme"); if (t) document.documentElement.dataset.theme = t; }} catch (e) {{}}</script>
</head>
<body class="sub-page">
  <header class="nav">
    <a class="brand" href="{up}" aria-label="Deskvert home"><img src="{up}assets/logo.png" alt="" width="30" height="30"><span>Desk<b>vert</b></span></a>
    <nav class="nav-links" aria-label="Pages">
      <a href="{up}#how">How it works</a>
      <a href="/convert">All conversions</a>
      <a href="/changelog">What's new</a>
    </nav>
    <div class="nav-end">
      <button class="icon-btn" id="theme-toggle" type="button" aria-label="Switch light or dark"><i class="ph ph-moon-stars" aria-hidden="true"></i></button>
      <a class="btn btn-primary btn-small" href="https://github.com/syedtaj7/DeskVert/releases/latest" aria-label="Download for Windows"><i class="ph-bold ph-windows-logo" aria-hidden="true"></i><span>Download for Windows</span></a>
    </div>
  </header>
  <main id="main">
"""

FOOT = """  </main>
  <footer class="foot">
    <a class="brand" href="{up}"><img src="{up}assets/logo.png" alt="" width="26" height="26"><span>Desk<b>vert</b></span></a>
    <nav aria-label="Project links">
      <a href="/convert">All conversions</a>
      <a href="/changelog">What's new</a>
      <a href="https://github.com/syedtaj7/DeskVert">GitHub</a>
      <a href="https://github.com/sponsors/syedtaj7">Support</a>
      <a href="https://github.com/syedtaj7/DeskVert/blob/main/PRIVACY.md">Privacy</a>
      <a href="https://github.com/syedtaj7/DeskVert/blob/main/LICENSE">License (AGPL-3.0)</a>
    </nav>
  </footer>
  <script>
    (function () {{
      var root = document.documentElement, btn = document.getElementById("theme-toggle");
      var dark = function () {{ return root.dataset.theme === "dark" || (root.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches); }};
      var icon = function () {{ btn.querySelector("i").className = dark() ? "ph ph-sun" : "ph ph-moon-stars"; }};
      icon();
      btn.addEventListener("click", function () {{
        root.dataset.theme = dark() ? "light" : "dark";
        try {{ localStorage.setItem("deskvert-theme", root.dataset.theme); }} catch (e) {{}}
        icon();
      }});
    }})();
  </script>
</body>
</html>
"""

DOWNLOAD = ('<div class="cta-row"><a class="btn btn-primary btn-big" href="https://github.com/syedtaj7/DeskVert/releases/'
            'latest"><i class="ph-bold ph-windows-logo" aria-hidden="true"></i><span>Download for Windows</span></a>'
            '<a class="btn btn-ghost btn-big" href="{up}#how"><i class="ph ph-play-circle" aria-hidden="true"></i>'
            '<span>See how it works</span></a></div>')


def e(s: str) -> str:
    return html.escape(s, quote=True)


def faq_ld(qas: list[tuple[str, str]]) -> str:
    return json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qas]})


def pair_page(src_ext: str, label: str, slug: str, a: str, b: str, data: dict, pages: dict) -> str:
    caption, warnings, key = data[src_ext]["offers"][label]
    up = "/"
    url = f"{BASE}/convert/{slug}"
    office = key.startswith("doc.") and src_ext != ".pdf"
    title = f"Convert {a} to {b} on Windows: free and offline | Deskvert"
    if label == "Compress":
        title = "Compress a PDF on Windows: free and offline | Deskvert"
    desc = (f"Convert {a} to {b} on Windows in one tap: select the files, press Ctrl + Shift, pick {label}. "
            "Free, open source and offline: nothing is uploaded.")
    h1 = f"Compress PDFs on Windows" if label == "Compress" else f"Convert {a} to {b} on Windows"
    about_a, about_b = ABOUT.get(a, ""), ABOUT.get(b, "")
    intro = (f"<b>{e(a)}</b> is {e(about_a)}. " if about_a else "") + (
        f"<b>{e(b)}</b> is {e(about_b)}. " if about_b and b != a else "")
    if office:
        intro += "Deskvert has your own Microsoft Office do it (or the free LibreOffice), then checks the result."
    else:
        intro += "Deskvert does it right on your PC, then opens the result again and checks it before saving."
    steps = [
        ("Select", f"Select one or more {e(a)} files in File Explorer or on the Desktop."),
        ("Tap Ctrl + Shift", "Tap the two keys together. A small picker opens at your pointer."),
        (f"Pick {e(label)}", f"The new file is saved next to the original{', ' + e(caption) if caption else ''}. "
                             "The original isn't changed."),
    ]
    steps_html = "".join(f'<li><span class="n">{i}</span><div><h3>{t}</h3><p>{d}</p></div></li>'
                         for i, (t, d) in enumerate(steps, 1))
    notes = "".join(f"<li>{e(w)}</li>" for w in warnings if "Microsoft Office" not in w)
    also = [x for x in data[src_ext]["formats"] if x != label][:14]
    also_html = "".join(
        (f'<a class="chip" href="/convert/{pages[(src_ext, x)]}">{e(x)}</a>' if (src_ext, x) in pages else
         f'<span class="chip">{e(x)}</span>') for x in also)
    tools = data[src_ext]["tools"][:12]
    tools_html = "".join(f'<span class="chip tool">{e(x)}</span>' for x in tools)
    related = [(p[2], p[3], p[4]) for p in PAIRS if p[2] != slug and (p[3] == a or p[4] == b)][:8]
    related_html = "".join(f'<li><a href="/convert/{s}">{e(x)} to {e(y)}</a></li>' for s, x, y in related)
    qas = [
        (f"Is converting {a} to {b} with Deskvert free?", "Yes. Deskvert is free and open source (AGPL-3.0), with "
         "no ads, no account and no limits."),
        ("Are my files uploaded?", "No. Everything is converted on your own PC; nothing is sent anywhere."),
        ("Can I convert many files at once?", f"Yes. Select all the {a} files and tap Ctrl + Shift once."),
    ]
    faq_html = "".join(f"<details><summary>{e(q)}</summary><p>{e(ans)}</p></details>" for q, ans in qas)
    body = f"""
    <section class="page-hero">
      <p class="eyebrow">{e(a)} → {e(b)}</p>
      <h1>{e(h1)}</h1>
      <p class="lead">Select, tap <kbd>Ctrl</kbd> + <kbd>Shift</kbd>, pick <b>{e(label)}</b>. Free, offline, and nothing is uploaded.</p>
      {DOWNLOAD.format(up=up)}
    </section>
    <section class="page-body">
      <p class="intro">{intro}</p>
      <h2>How to convert {e(a)} to {e(b)}</h2>
      <ol class="steps-list">{steps_html}</ol>
      {f'<h2>Good to know</h2><ul class="notes">{notes}</ul>' if notes else ''}
      <h2>{e(a)} files can also become</h2>
      <div class="chips">{also_html}</div>
      {f'<h3 class="tools-title">And these tools work on them</h3><div class="chips">{tools_html}</div>' if tools else ''}
      <h2>Questions</h2>
      <div class="faq-list">{faq_html}</div>
      {f'<h2>Related conversions</h2><ul class="related">{related_html}</ul>' if related else ''}
      <p class="back"><a href="/convert">All conversions</a> · <a href="{up}">Deskvert home</a></p>
    </section>
"""
    ld = f'<script type="application/ld+json">{faq_ld(qas)}</script>'
    return HEAD.format(title=e(title), desc=e(desc), url=url, up=up, base=BASE, jsonld=ld) + body + FOOT.format(up=up)


def index_page(made: list[tuple[str, str, str]], data: dict, kinds: int, ways: int) -> str:
    up = "/"
    groups: dict[str, list] = {}
    for slug, a, b in made:
        groups.setdefault(a, []).append((slug, b))
    cards = "".join(
        f'<div class="group"><h3>{e(a)}</h3><ul>' + "".join(f'<li><a href="/convert/{s}">{e(a)} to {e(b)}</a></li>'
                                                         for s, b in items) + "</ul></div>"
        for a, items in groups.items())
    every = "".join(f'<span class="chip">{e(x.lstrip(".").upper())}</span>' for x in sorted(data))
    body = f"""
    <section class="page-hero">
      <p class="eyebrow">Conversions</p>
      <h1>Every way Deskvert converts</h1>
      <p class="lead">{kinds} kinds of files, {ways} ways out. These are the most asked-for; the picker shows
      everything a file can become.</p>
      {DOWNLOAD.format(up=up)}
    </section>
    <section class="page-body">
      <div class="groups">{cards}</div>
      <h2>All {kinds} file types it opens</h2>
      <div class="chips">{every}</div>
    </section>
"""
    return HEAD.format(title="All conversions: convert any file on Windows, free | Deskvert",
                       desc=f"{kinds} kinds of files in {ws(ways)} ways, offline and free: pictures, PDFs, Office "
                            "documents, video, sound, e-mails, maps and more.", url=f"{BASE}/convert", up=up,
                       base=BASE, jsonld="") + body + FOOT.format(up=up)


def ws(n: int) -> str:
    return f"{n}"


# ---------------------------------------------------------------- What's new (CHANGELOG.md)

def md_inline(text: str) -> str:
    t = e(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"(?<![\"=>])(https?://[^\s<]+[^\s<.,)])", r'<a href="\1">\1</a>', t)
    return t


def changelog_page(limit: int = 12) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = re.split(r"(?m)^## ", text)[1:]
    shown = [v for v in versions if not v.lower().startswith("unreleased")][:limit]
    parts = []
    for v in shown:
        lines = v.splitlines()
        parts.append(f'<article class="release"><h2>Version {e(lines[0].strip())}</h2>')
        para, in_list = [], False
        items: list[str] = []

        def flush_list():
            nonlocal items, in_list
            if items:
                parts.append("<ul>" + "".join(f"<li>{md_inline(i)}</li>" for i in items) + "</ul>")
            items, in_list = [], False

        for ln in lines[1:]:
            if ln.startswith("### "):
                flush_list()
                parts.append(f"<h3>{md_inline(ln[4:].strip())}</h3>")
            elif ln.startswith("- "):
                items.append(ln[2:].strip())
                in_list = True
            elif ln.startswith("  ") and in_list and items:
                items[-1] += " " + ln.strip()
            elif ln.strip():
                flush_list()
                parts.append(f"<p>{md_inline(ln.strip())}</p>")
            else:
                flush_list()
        flush_list()
        parts.append("</article>")
    up = "/"
    body = f"""
    <section class="page-hero">
      <p class="eyebrow">What's new</p>
      <h1>What's new in Deskvert</h1>
      <p class="lead">Every release, newest first. Deskvert updates itself, and each update is checked before it's
      installed. Older versions are on <a href="https://github.com/syedtaj7/DeskVert/blob/main/CHANGELOG.md">GitHub</a>.</p>
      {DOWNLOAD.format(up=up)}
    </section>
    <section class="page-body changelog">{''.join(parts)}</section>
"""
    return HEAD.format(title="What's new in Deskvert: release notes", desc="Every Deskvert release, newest first: new "
                       "conversions, browser features and fixes.", url=f"{BASE}/changelog", up=up, base=BASE,
                       jsonld="") + body + FOOT.format(up=up)


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    data = gather()
    keys = data.pop("_keys")
    kinds = len(data)
    ways = len(keys)  # every distinct conversion and tool, the archive ones included

    conv = SITE / "convert"
    conv.mkdir(exist_ok=True)
    for old in conv.glob("*.html"):
        old.unlink()
    pages = {(p[0], p[1]): p[2] for p in PAIRS if p[0] in data and p[1] in data[p[0]]["offers"]}
    made = []
    for src_ext, label, slug, a, b in PAIRS:
        if (src_ext, label) not in pages:
            print(f"skipped {slug}: {label} isn't offered for {src_ext}")
            continue
        (conv / f"{slug}.html").write_text(pair_page(src_ext, label, slug, a, b, data, pages), encoding="utf-8")
        made.append((slug, a, b))
    (conv / "index.html").write_text(index_page(made, data, kinds, ways), encoding="utf-8")
    links: dict[str, dict] = {}
    for src_ext, label, slug, _a, _b in PAIRS:
        if (src_ext, label) in pages:
            links.setdefault(src_ext.lstrip("."), {})[label] = slug
    (SITE / "formats.json").write_text(json.dumps(
        {ext.lstrip("."): {"to": d["formats"], "tools": d["tools"], "pages": links.get(ext.lstrip("."), {})}
         for ext, d in data.items()}, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (SITE / "changelog.html").write_text(changelog_page(), encoding="utf-8")

    urls = [f"{BASE}/", f"{BASE}/convert", f"{BASE}/changelog"] + [f"{BASE}/convert/{s}" for s, _a, _b in made]
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")

    # the counts on the home page and in its description
    index = SITE / "index.html"
    page = index.read_text(encoding="utf-8")
    page = re.sub(r'data-to="\d+">\d+</span> kinds', f'data-to="{kinds}">{kinds}</span> kinds', page)
    page = re.sub(r'data-to="\d+">\d+</span> ways', f'data-to="{ways}">{ways}</span> ways', page)
    page = re.sub(r"\d+ kinds of files in \d+ ways", f"{kinds} kinds of files in {ways} ways", page)
    page = re.sub(r"the same for \d+ kinds of files", f"the same for {kinds} kinds of files", page)
    index.write_text(page, encoding="utf-8", newline="\n")
    print(f"{kinds} kinds of files, {ways} ways out; {len(made)} conversion pages")


if __name__ == "__main__":
    main()
