"""More from a web page link (.url): every picture on it, or just the article as a clean PDF.

Both read the page as a browser shows it: the Edge (or Chrome) already on this PC opens it in a
private, empty profile and hands back the finished page (so pictures that pages add with scripts
are found too). Nothing of yours is used, and pages behind a sign-in come out signed-out.

- pictures: every picture on the page at the biggest size the page offers, in a new folder.
  Icons, spacers and tiny pictures are left out. Each one is opened to check it's a real picture.
- reader: the article itself (headline, text, its pictures and tables) without menus, ads, cookie
  banners or comments, laid out as a calm A4 PDF with a line saying where it came from.
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path
from .webpage import read_url, to_pdf

MAX_PICTURES = 150
MAX_PICTURE_BYTES = 30 * 1024 * 1024
MAX_TOTAL = 400 * 1024 * 1024
MIN_SIDE = 120  # smaller than this on both sides: an icon or a spacer, not a picture you want
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Deskvert"
PICTURE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp", ".heic", ".tif", ".tiff")
NOISE = re.compile(r"(^|[\s_-])(ads?|advert\w*|banner|cookie\w*|consent|promo\w*|related|share|sharing|social|"
                   r"comments?|newsletter|subscribe|sidebar|popup|modal|breadcrumbs?|recommend\w*|sponsor\w*|"
                   r"outbrain|taboola|paywall|signup|login)([\s_-]|$)", re.I)


# ---------------------------------------------------------------- reading the page

def dump_dom(url: str, workdir: Path, timeout: int = 90) -> str:
    """The page's HTML after the browser has run it (what you'd see), in a private, empty profile."""
    from .webpage import run_browser

    r = run_browser(["--dump-dom", url], lambda res: b"<" in (res.stdout or b""), workdir, timeout)
    return r.stdout.decode("utf-8", errors="replace")


def _best_from_srcset(srcset: str, base: str) -> tuple[str, float]:
    best, best_w = "", 0.0
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        w = 1.0
        if len(bits) > 1:
            m = re.match(r"([\d.]+)([wx])", bits[1])
            if m:
                w = float(m.group(1)) * (1 if m.group(2) == "w" else 1000)
        if w >= best_w:
            best, best_w = urllib.parse.urljoin(base, html.unescape(bits[0])), w
    return best, best_w


def picture_addresses(page: str, base: str) -> list[str]:
    """Every picture the page shows or links to, biggest version first, each once (in page order)."""
    import lxml.html

    root = lxml.html.document_fromstring(page)
    b = root.find(".//base")
    if b is not None and b.get("href"):
        base = urllib.parse.urljoin(base, b.get("href"))
    found: list[str] = []

    def add(u: str):
        u = (u or "").strip()
        if not u or u.startswith(("data:", "blob:", "javascript:")):
            return
        u = urllib.parse.urljoin(base, html.unescape(u))
        svg = urllib.parse.urlsplit(u).path.lower().endswith(".svg")  # logos and icons, drawn
        if u.startswith(("http://", "https://")) and not svg and u not in found:
            found.append(u)

    for meta in root.xpath("//meta[@property='og:image' or @name='twitter:image' or @property='og:image:url']"):
        add(meta.get("content"))
    for el in root.xpath("//img | //picture/source"):
        options = []
        for attr in ("srcset", "data-srcset", "data-lazy-srcset"):
            if el.get(attr):
                options.append(_best_from_srcset(el.get(attr), base))
        best = max(options, key=lambda o: o[1])[0] if options else ""
        add(best or el.get("data-src") or el.get("data-original") or el.get("data-lazy-src") or el.get("src"))
    for a in root.xpath("//a[@href]"):  # galleries link the thumbnail to the full-size picture
        path = urllib.parse.urlsplit(a.get("href")).path.lower()
        if path.endswith(PICTURE_EXTS):
            add(a.get("href"))
    return found


# ---------------------------------------------------------------- all pictures

def _fetch(url: str, referer: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": referer, "Accept": "image/*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(MAX_PICTURE_BYTES + 1)
    if len(data) > MAX_PICTURE_BYTES:
        raise ValueError("too big")
    return data


def _name_for(url: str, ext: str, used: set[str]) -> str:
    stem = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).stem or "picture"
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", stem).strip(" .")[:80] or "picture"
    name, k = f"{stem}{ext}", 2
    while name.lower() in used:
        name, k = f"{stem} ({k}){ext}", k + 1
    used.add(name.lower())
    return name


def save_pictures(page: str, url: str, folder: Path) -> list[str]:
    import io

    from PIL import Image

    from ..dropread import sniff
    from .image import _ensure_plugins

    _ensure_plugins()
    addresses = picture_addresses(page, url)
    if not addresses:
        raise ConversionError("No pictures were found on this page.")
    folder.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    saved = small = failed = 0
    total = 0
    for addr in addresses[:MAX_PICTURES * 2]:
        if saved >= MAX_PICTURES or total > MAX_TOTAL:
            break
        try:
            data = _fetch(addr, url)
            ext = sniff(data)
            if ext not in PICTURE_EXTS and ext != ".jpg":
                failed += 1
                continue
            with Image.open(io.BytesIO(data)) as im:
                w, h = im.size
                im.load()
        except Exception:  # noqa: BLE001 - one broken picture never stops the rest
            failed += 1
            continue
        if w < MIN_SIDE and h < MIN_SIDE:
            small += 1
            continue
        (folder / _name_for(addr, ext, used)).write_bytes(data)
        saved += 1
        total += len(data)
    if not saved:
        raise ConversionError("This page has no pictures bigger than an icon (or they couldn't be downloaded).")
    notes = [f"Checked: {saved} picture{'s' if saved != 1 else ''}, each opened and at the biggest size the page "
             "offers."]
    if small:
        notes.append(f"Left out {small} icon{'s' if small != 1 else ''} and tiny picture{'s' if small != 1 else ''}.")
    if failed:
        notes.append(f"{failed} couldn't be downloaded or weren't pictures.")
    if saved >= MAX_PICTURES:
        notes.append(f"Stopped at {MAX_PICTURES} pictures.")
    return notes


# ---------------------------------------------------------------- reader: the article only

KEEP = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "pre", "code", "figure",
        "figcaption", "img", "table", "thead", "tbody", "tr", "td", "th", "a", "strong", "em", "b", "i", "br",
        "sup", "sub", "dl", "dt", "dd", "hr", "picture", "span", "div", "section", "article", "main", "caption"}
DROP = {"script", "style", "noscript", "iframe", "form", "nav", "header", "footer", "aside", "svg", "button",
        "input", "select", "textarea", "template", "canvas", "video", "audio", "object", "embed", "dialog"}


def _text_len(el) -> int:
    return len(" ".join(el.text_content().split()))


def article(page: str, url: str) -> tuple[str, str]:
    """(title, clean HTML of the article's body) from a whole page."""
    import lxml.html

    root = lxml.html.document_fromstring(page)
    title = ""
    for xp in ("//meta[@property='og:title']/@content", "//title/text()", "//h1"):
        got = root.xpath(xp)
        if got:
            title = " ".join((got[0] if isinstance(got[0], str) else got[0].text_content()).split())
            if title:
                break
    for el in list(root.iter()):
        if not isinstance(el.tag, str) or el.getparent() is None:
            continue
        tag = el.tag.lower()
        role = (el.get("role") or "").lower()
        marks = f"{el.get('class') or ''} {el.get('id') or ''}"
        hidden = el.get("hidden") is not None or el.get("aria-hidden") == "true" or \
            re.search(r"display\s*:\s*none", el.get("style") or "", re.I)
        if tag in DROP or role in ("navigation", "banner", "contentinfo", "complementary", "dialog", "search") \
                or hidden or (tag not in ("body", "html", "article", "main") and NOISE.search(marks)
                              and _text_len(el) < 4000):
            el.drop_tree()
    # the part of the page with the most paragraph text is the article
    scores: dict = {}
    for p in root.iter("p"):
        n = _text_len(p)
        if n < 40:
            continue
        parent = p.getparent()
        if parent is not None:
            scores[parent] = scores.get(parent, 0) + n
            grand = parent.getparent()
            if grand is not None:
                scores[grand] = scores.get(grand, 0) + n / 2
    candidates = root.xpath("//article") + root.xpath("//main")
    best = max(candidates, key=_text_len) if candidates else None
    if best is None or _text_len(best) < 400:
        best = max(scores, key=scores.get) if scores else root.find("body")
    if best is None or _text_len(best) < 80:
        raise ConversionError("Deskvert couldn't find an article on this page. Try “Page as PDF” instead.")
    # tidy what's left: only reading tags, pictures at their biggest, links absolute
    for el in list(best.iter()):
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        if tag not in KEEP:
            el.drop_tag()
            continue
        if tag == "img":
            options = [_best_from_srcset(el.get(a), url) for a in ("srcset", "data-srcset") if el.get(a)]
            src = (max(options, key=lambda o: o[1])[0] if options else "") or el.get("data-src") or el.get("src")
            if not src or src.startswith("data:"):
                el.drop_tree()
                continue
            alt = el.get("alt") or ""
            el.attrib.clear()
            el.set("src", urllib.parse.urljoin(url, src))
            el.set("alt", alt)
            continue
        href = el.get("href") if tag == "a" else None
        el.attrib.clear()
        if href and not href.startswith("javascript:"):
            el.set("href", urllib.parse.urljoin(url, href))
    body = lxml.html.tostring(best, encoding="unicode", method="html")
    if title and title.lower() not in body[:2000].lower():
        body = f"<h1>{html.escape(title)}</h1>\n" + body
    return title or urllib.parse.urlsplit(url).netloc, body


READER_CSS = ("body{font-family:'Segoe UI',Arial,sans-serif;font-size:16px;line-height:1.62;color:#1d1d22;"
              "max-width:700px;margin:28px auto;padding:0 12px}h1{font-size:30px;line-height:1.2;margin:0 0 18px}"
              "h2{font-size:22px;margin:28px 0 8px}h3{font-size:18px}img{max-width:100%;height:auto;"
              "border-radius:6px;margin:10px 0}figure{margin:16px 0}figcaption{color:#666;font-size:13px}"
              "blockquote{border-left:3px solid #ccc;margin:16px 0;padding:2px 14px;color:#444}"
              "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}a{color:#2d5bd2}"
              "pre{white-space:pre-wrap;background:#f4f4f6;padding:10px;border-radius:6px}"
              ".source{color:#777;font-size:12px;margin-top:30px;border-top:1px solid #ddd;padding-top:8px}")


def reader_pdf(page: str, url: str, out: Path) -> list[str]:
    import pymupdf

    title, body = article(page, url)
    clean = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><base href="{html.escape(url)}">'
             f"<title>{html.escape(title)}</title><style>{READER_CSS}</style></head><body>\n{body}\n"
             f'<p class="source">From <a href="{html.escape(url)}">{html.escape(url)}</a></p></body></html>')
    page_file = out.with_name("article.html")
    page_file.write_text(clean, encoding="utf-8")
    notes: list[str] = []
    to_pdf(page_file.as_uri(), out, notes)
    import lxml.html

    want = " ".join(lxml.html.fragment_fromstring(body, create_parent="div").text_content().split())
    with pymupdf.open(long_path(out)) as d:
        got = " ".join(" ".join(p.get_text() for p in d).split())
        pages = d.page_count
    words = [w for w in re.findall(r"\w{4,}", want)[:400]]
    if words:
        have = set(re.findall(r"\w{4,}", got))
        if sum(w in have for w in words) / len(words) < 0.9:
            raise VerificationError("some of the article's text is missing from the PDF")
    return [f"Checked: the article on {pages} page{'s' if pages != 1 else ''}, without menus, ads or banners; "
            "text stays text."]


# ---------------------------------------------------------------- entry point

def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    url = read_url(sources[0])
    if not url.lower().startswith(("http://", "https://")):
        raise ConversionError("Only web pages (http and https addresses) can be read.")
    page = dump_dom(url, out.parent)
    note = "Opened in a private, signed-out browser window: pages that need a sign-in show as signed-out."
    if fmt == "pictures":
        return save_pictures(page, url, Path(long_path(out))) + [note]
    if fmt == "reader":
        return reader_pdf(page, url, out) + [note]
    raise ConversionError(f"Unknown page conversion: {fmt}")
