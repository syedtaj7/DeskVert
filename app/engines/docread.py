"""Word (DOCX) and OpenDocument (ODT) files read directly, without Microsoft Office.

Both formats are a zip of XML. The text, headings, lists, tables, bold and italic
are read from it and written as plain text, Markdown or a web page:

- txt:  the words, paragraph by paragraph; tables as tab-separated lines
- md:   headings, lists, tables, bold and italic as Markdown
- html: one self-contained web page

Pictures, page layout, headers and footers aren't carried over (the note says so).
Every result is checked: all the document's words must be in the new file.
"""

from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path
from .officeutil import text_coverage, words

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
TXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TBL = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
FO = "{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}"

Run = tuple[str, bool, bool]  # text, bold, italic


@dataclass
class Block:
    kind: str  # "h" | "p" | "li" | "table"
    runs: list[Run] = field(default_factory=list)
    level: int = 0  # heading level, or list depth
    ordered: bool = False
    rows: list[list[str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(t for t, _b, _i in self.runs)


def _xml(z: zipfile.ZipFile, name: str):
    from lxml import etree

    try:
        raw = z.read(name)
    except KeyError as e:
        raise ConversionError("This document is damaged: part of it is missing.") from e
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)
    return etree.fromstring(raw, parser)


def _merge(runs: list[Run]) -> list[Run]:
    out: list[Run] = []
    for t, b, i in runs:
        if not t:
            continue
        if out and out[-1][1:] == (b, i):
            out[-1] = (out[-1][0] + t, b, i)
        else:
            out.append((t, b, i))
    return out


# ---------------------------------------------------------------- DOCX

def _on(el) -> bool:
    """A Word on/off property (<w:b/>, <w:b w:val="0"/>...)."""
    if el is None:
        return False
    return el.get(W + "val", "true").lower() not in ("0", "false", "off", "none")


def _docx_runs(p) -> list[Run]:
    runs: list[Run] = []
    for el in p.iter(W + "r"):
        if any(a.tag == MC_FALLBACK for a in el.iterancestors()):
            continue  # the same text box again, for older Word versions
        if any(a.tag == W + "txbxContent" for a in el.iterancestors()):
            continue  # text boxes become paragraphs of their own
        rpr = el.find(W + "rPr")
        b = _on(rpr.find(W + "b")) if rpr is not None else False
        i = _on(rpr.find(W + "i")) if rpr is not None else False
        for c in el:
            if c.tag == W + "t":
                runs.append((c.text or "", b, i))
            elif c.tag == W + "tab":
                runs.append(("\t", b, i))
            elif c.tag in (W + "br", W + "cr"):
                runs.append(("\n", b, i))
            elif c.tag == W + "noBreakHyphen":
                runs.append(("-", b, i))
    return _merge(runs)


def _docx_styles(z: zipfile.ZipFile) -> dict[str, int]:
    """Style id -> heading level (from the style's outline level or its name)."""
    levels: dict[str, int] = {}
    if "word/styles.xml" not in z.namelist():
        return levels
    for st in _xml(z, "word/styles.xml").iter(W + "style"):
        sid = st.get(W + "styleId", "")
        name = (st.find(W + "name").get(W + "val", "") if st.find(W + "name") is not None else "").lower()
        ol = st.find(f"{W}pPr/{W}outlineLvl")
        if ol is not None and ol.get(W + "val", "").isdigit() and int(ol.get(W + "val")) < 6:
            levels[sid] = int(ol.get(W + "val")) + 1
        elif m := re.fullmatch(r"heading (\d)", name):
            levels[sid] = min(6, int(m.group(1)))
        elif name == "title":
            levels[sid] = 1
    return levels


def _docx_ordered(z: zipfile.ZipFile) -> set[tuple[str, str]]:
    """(numId, level) pairs that are numbered lists (the rest are bullets)."""
    if "word/numbering.xml" not in z.namelist():
        return set()
    root = _xml(z, "word/numbering.xml")
    abstract: dict[str, dict[str, str]] = {}
    for a in root.iter(W + "abstractNum"):
        abstract[a.get(W + "abstractNumId", "")] = {
            lvl.get(W + "ilvl", "0"): (lvl.find(W + "numFmt").get(W + "val", "") if lvl.find(W + "numFmt")
                                       is not None else "") for lvl in a.iter(W + "lvl")}
    out = set()
    for n in root.iter(W + "num"):
        ref = n.find(W + "abstractNumId")
        fmts = abstract.get(ref.get(W + "val", "") if ref is not None else "", {})
        for lvl, fmt in fmts.items():
            if fmt and fmt not in ("bullet", "none"):
                out.add((n.get(W + "numId", ""), lvl))
    return out


def _docx_paragraph(p, heads: dict[str, int], ordered: set) -> Block:
    runs = _docx_runs(p)
    ppr = p.find(W + "pPr")
    if ppr is not None:
        st = ppr.find(W + "pStyle")
        level = heads.get(st.get(W + "val", "")) if st is not None else None
        ol = ppr.find(W + "outlineLvl")
        if level is None and ol is not None and ol.get(W + "val", "").isdigit() and int(ol.get(W + "val")) < 6:
            level = int(ol.get(W + "val")) + 1
        if level:
            return Block("h", runs, level)
        num = ppr.find(W + "numPr")
        if num is not None and num.find(W + "numId") is not None:
            nid = num.find(W + "numId").get(W + "val", "")
            ilvl = num.find(W + "ilvl").get(W + "val", "0") if num.find(W + "ilvl") is not None else "0"
            if nid != "0":
                return Block("li", runs, int(ilvl) if ilvl.isdigit() else 0, ordered=(nid, ilvl) in ordered)
    return Block("p", runs)


def _cell_text(paragraphs) -> str:
    return " ".join(" ".join("".join(t for t, _b, _i in r).split()) for r in paragraphs).strip()


def read_docx(src: Path) -> tuple[list[Block], str]:
    """(blocks, every word in the document) for a .docx/.docm/.dotx."""
    try:
        z = zipfile.ZipFile(long_path(src))
    except zipfile.BadZipFile as e:
        raise ConversionError("This isn't a Word document Tapshift can read (it may be an old .doc, or "
                              "damaged).") from e
    with z:
        if "word/document.xml" not in z.namelist():
            raise ConversionError("This isn't a Word document Tapshift can read.")
        root = _xml(z, "word/document.xml")
        heads, ordered = _docx_styles(z), _docx_ordered(z)
    body = root.find(W + "body")
    if body is None:
        raise ConversionError("This Word document has no body.")
    blocks: list[Block] = []

    def walk(container):
        for el in container:
            if el.tag == W + "p":
                blocks.append(_docx_paragraph(el, heads, ordered))
                for box in el.iter(W + "txbxContent"):  # text boxes, as their own paragraphs
                    if not any(a.tag == MC_FALLBACK for a in box.iterancestors()):
                        walk(box)
            elif el.tag == W + "tbl":
                rows = []
                for tr in el.iter(W + "tr"):
                    if tr.getparent() is not el:
                        continue  # rows of a nested table go into their cell's text
                    rows.append([_cell_text([_docx_runs(p) for p in tc.iter(W + "p")])
                                 for tc in tr if tc.tag == W + "tc"])
                blocks.append(Block("table", rows=rows))
            elif el.tag == W + "sdt":  # content controls (forms, tables of contents)
                content = el.find(W + "sdtContent")
                if content is not None:
                    walk(content)

    walk(body)
    every = " ".join(t.text or "" for t in root.iter(W + "t")
                     if not any(a.tag == MC_FALLBACK for a in t.iterancestors()))
    return blocks, every


# ---------------------------------------------------------------- ODT

def _odt_bold_italic(root) -> dict[str, tuple[bool, bool]]:
    found: dict[str, tuple[bool, bool]] = {}
    for st in root.iter(STYLE + "style"):
        tp = st.find(STYLE + "text-properties")
        if tp is not None:
            found[st.get(STYLE + "name", "")] = (tp.get(FO + "font-weight", "") == "bold",
                                                 tp.get(FO + "font-style", "") == "italic")
    return found


def _odt_runs(el, styles, b=False, i=False) -> list[Run]:
    runs: list[Run] = []
    if el.text:
        runs.append((el.text, b, i))
    for c in el:
        tag = c.tag
        if tag == TXT + "span":
            cb, ci = styles.get(c.get(TXT + "style-name", ""), (False, False))
            runs += _odt_runs(c, styles, b or cb, i or ci)
        elif tag == TXT + "s":
            runs.append((" " * int(c.get(TXT + "c", "1") or 1), b, i))
        elif tag == TXT + "tab":
            runs.append(("\t", b, i))
        elif tag == TXT + "line-break":
            runs.append(("\n", b, i))
        elif tag in (TXT + "a",):
            runs += _odt_runs(c, styles, b, i)
        elif tag in (TXT + "note", TXT + "bookmark", TXT + "bookmark-start", TXT + "bookmark-end"):
            pass
        else:
            runs += _odt_runs(c, styles, b, i)
        if c.tail:
            runs.append((c.tail, b, i))
    return runs


def read_odt(src: Path) -> tuple[list[Block], str]:
    try:
        z = zipfile.ZipFile(long_path(src))
    except zipfile.BadZipFile as e:
        raise ConversionError("This OpenDocument file is damaged.") from e
    with z:
        root = _xml(z, "content.xml")
        styles = _odt_bold_italic(root)
        if "styles.xml" in z.namelist():
            styles = {**_odt_bold_italic(_xml(z, "styles.xml")), **styles}
    text_body = root.find(f"{OFFICE}body/{OFFICE}text")
    if text_body is None:
        raise ConversionError("This OpenDocument file has no text (is it a spreadsheet or a presentation?).")
    blocks: list[Block] = []

    def walk(container, depth=-1, ordered=False):
        for el in container:
            if el.tag == TXT + "h":
                lvl = int(el.get(TXT + "outline-level", "1") or 1)
                blocks.append(Block("h", _merge(_odt_runs(el, styles)), min(6, max(1, lvl))))
            elif el.tag == TXT + "p":
                kind = "li" if depth >= 0 else "p"
                blocks.append(Block(kind, _merge(_odt_runs(el, styles)), max(0, depth), ordered=ordered))
            elif el.tag == TXT + "list":
                numbered = "num" in (el.get(TXT + "style-name", "") or "").lower()
                for item in el:
                    walk(item, depth + 1, numbered)
            elif el.tag == TBL + "table":
                rows = []
                for tr in el.iter(TBL + "table-row"):
                    rows.append([_cell_text([_odt_runs(p, styles) for p in tc.iter(TXT + "p")])
                                 for tc in tr if tc.tag == TBL + "table-cell"])
                blocks.append(Block("table", rows=rows))
            elif el.tag in (TXT + "section", TXT + "list-item", TXT + "list-header"):
                walk(el, depth, ordered)

    walk(text_body)
    every = " ".join(text_body.itertext())
    return blocks, every


# ---------------------------------------------------------------- writers

def _plain(blocks: list[Block]) -> str:
    out = []
    for b in blocks:
        if b.kind == "table":
            out += ["\t".join(c for c in row) for row in b.rows]
        elif b.kind == "li":
            out.append("  " * b.level + ("- " if not b.ordered else "1. ") + b.text)
        else:
            out.append(b.text)
    return "\n".join(out).strip() + "\n"


_MD_ESC = re.compile(r"([\\`*_\[\]#|<>])")


def _md_inline(runs: list[Run]) -> str:
    parts = []
    for t, b, i in runs:
        lead, core, trail = re.match(r"^(\s*)(.*?)(\s*)$", t, re.S).groups()
        core = _MD_ESC.sub(r"\\\1", core).replace("\n", "  \n")
        if core and (b or i):
            mark = "***" if b and i else ("**" if b else "*")
            core = f"{mark}{core}{mark}"
        parts.append(lead + core + trail)
    return "".join(parts)


def _markdown(blocks: list[Block]) -> str:
    out: list[str] = []
    counters: dict[int, int] = {}
    prev = ""
    for b in blocks:
        if b.kind != "li":
            counters.clear()
        if b.kind == "h":
            text = _md_inline([(t, False, False) for t, _b, _i in b.runs]).strip()
            if text:
                out += ["", "#" * b.level + " " + text, ""]
        elif b.kind == "li":
            n = counters[b.level] = counters.get(b.level, 0) + 1
            for deeper in [k for k in counters if k > b.level]:
                counters.pop(deeper)
            if prev != "li":
                out.append("")
            out.append("    " * b.level + (f"{n}. " if b.ordered else "- ") + _md_inline(b.runs).strip())
        elif b.kind == "table" and b.rows:
            width = max(len(r) for r in b.rows)
            rows = [[_MD_ESC.sub(r"\\\1", c) for c in r] + [""] * (width - len(r)) for r in b.rows]
            out += ["", "| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
            out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
            out.append("")
        else:
            text = _md_inline(b.runs).strip()
            out += [text, ""] if text else []
        prev = b.kind
    md = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"


def _html_inline(runs: list[Run]) -> str:
    parts = []
    for t, b, i in runs:
        s = html.escape(t).replace("\n", "<br>").replace("\t", "&emsp;")
        if i:
            s = f"<em>{s}</em>"
        if b:
            s = f"<strong>{s}</strong>"
        parts.append(s)
    return "".join(parts)


def _html(blocks: list[Block], title: str) -> str:
    from .textdoc import PAGE_CSS

    body: list[str] = []
    stack: list[tuple[int, str]] = []  # open lists: (depth, tag)

    def close_to(depth: int):
        while stack and stack[-1][0] >= depth:
            body.append(f"</{stack.pop()[1]}>")

    for b in blocks:
        if b.kind == "li":
            tag = "ol" if b.ordered else "ul"
            close_to(b.level + 1)
            if not stack or stack[-1][0] < b.level:
                body.append(f"<{tag}>")
                stack.append((b.level, tag))
            body.append(f"<li>{_html_inline(b.runs)}</li>")
            continue
        close_to(0)
        if b.kind == "h":
            body.append(f"<h{b.level}>{_html_inline(b.runs)}</h{b.level}>")
        elif b.kind == "table":
            rows = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in b.rows)
            body.append(f"<table>{rows}</table>")
        elif b.text.strip():
            body.append(f"<p>{_html_inline(b.runs)}</p>")
    close_to(0)
    return (f"<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title>"
            f"<style>{PAGE_CSS}</style></head><body>\n" + "\n".join(body) + "\n</body></html>\n")


def _html_text(page: str) -> str:
    import lxml.html

    root = lxml.html.fromstring(page.encode("utf-8"))
    for junk in root.xpath("//style|//title"):
        junk.drop_tree()
    return " ".join(root.itertext())  # separately: neighbouring cells and items mustn't run together


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    src = sources[0]
    blocks, every = read_odt(src) if src.suffix.lower() == ".odt" else read_docx(src)
    if not words(every):
        raise ConversionError("This document has no text to convert.")
    if fmt == "txt":
        text, check = _plain(blocks), None
    elif fmt == "md":
        text, check = _markdown(blocks), None
    elif fmt == "html":
        text = _html(blocks, src.stem)
        check = _html_text
    else:
        raise ConversionError(f"Unknown document conversion: {fmt}")
    Path(long_path(out)).write_text(text, encoding="utf-8", newline="\n")
    written = Path(long_path(out)).read_text(encoding="utf-8")
    got = check(written) if check else written
    cov = text_coverage(every, got)
    if cov is not None and cov < 0.99:
        raise VerificationError(f"only {cov:.0%} of the document's words made it into the new file")
    if cov is None and words(every) and not set(words(every)) <= set(words(got)):
        raise VerificationError("some of the document's words are missing")
    heads = sum(b.kind == "h" for b in blocks)
    tables = sum(b.kind == "table" for b in blocks)
    what = [f"{len(words(every)):,} words"]
    if heads and fmt != "txt":
        what.append(f"{heads} heading{'s' if heads != 1 else ''}")
    if tables:
        what.append(f"{tables} table{'s' if tables != 1 else ''}")
    return [f"Checked: {', '.join(what)}, all included. Made without Microsoft Office.",
            "Pictures, page layout, headers and footers aren't included."]
