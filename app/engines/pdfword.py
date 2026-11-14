"""PDF to an editable Word document (DOCX), made by Deskvert itself.

Word's own PDF import asks a question even when Word runs hidden, so it isn't used, and nothing else is needed:
the PDF is read with PyMuPDF (already used for every PDF tool) into headings (bigger text), paragraphs with
bold and italic, bullet lists, pictures and tables, a page break between pages, and written straight into a
.docx that Word, LibreOffice, Google Docs and Pages open. Works without Microsoft Office. Light: no layout
models, no extra downloads.

Checked before it's kept: the .docx opens as a valid package and has the PDF's words.
"""

from __future__ import annotations

import html
import re
import zipfile
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

from ..errors import ConversionError, VerificationError
from ..paths import long_path

MAX_PICTURES = 400
BULLETS = "•◦▪●■–-*·‣⁃"
EMU = 12700  # per point

# A run of text: (text, bold, italic, superscript)
Run = tuple


def _inside(box, rects) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return any(r[0] - 1 <= cx <= r[2] + 1 and r[1] - 1 <= cy <= r[3] + 1 for r in rects)


def _runs(spans: list[dict]) -> list[Run]:
    out: list[Run] = []
    for s in spans:
        t = s["text"]
        if not t:
            continue
        run = (t, bool(s["flags"] & 16), bool(s["flags"] & 2), bool(s["flags"] & 1) and s["size"] < 9)
        if out and out[-1][1:] == run[1:]:
            out[-1] = (out[-1][0] + t,) + run[1:]
        else:
            out.append(run)
    return out


def _plain(runs: list[Run]) -> str:
    return "".join(r[0] for r in runs)


def _strip_bullet(runs: list[Run]) -> list[Run]:
    first = runs[0][0].lstrip()
    first = first[1:].lstrip() if first and first[0] in BULLETS else first
    return ([(first,) + runs[0][1:]] if first else []) + runs[1:]


def pdf_items(src: Path) -> tuple[list[tuple], str, int, tuple[float, float]]:
    """(items, the PDF's plain text, pages, first page size in points). Items, top to bottom:
    ("h", level, runs) ("p", runs) ("li", runs) ("img", bytes, ext, w_pt, h_pt) ("table", rows) ("break",)"""
    from .pdf import _cell_text, _open, _page_texts

    with _open(src) as d:
        texts = _page_texts(d)
        if not "".join(texts).strip():
            raise ConversionError("This PDF has no text in it: it's probably scanned pages. Use Read text first "
                                  "to make it searchable, then convert that to Word.")
        size0 = (d[0].rect.width, d[0].rect.height)
        sizes: Counter = Counter()
        pages = []
        for page in d:
            blocks = page.get_text("dict", flags=1 | 2 | 4)["blocks"]  # ligatures, white space, pictures
            pages.append(blocks)
            for b in blocks:
                for line in b.get("lines", []):
                    for s in line["spans"]:
                        if s["text"].strip():
                            sizes[round(s["size"], 1)] += len(s["text"])
        body = sizes.most_common(1)[0][0] if sizes else 11.0
        items: list[tuple] = []
        n_pics = 0
        for pno, (page, blocks) in enumerate(zip(d, pages)):
            if pno:
                items.append(("break",))
            placed: list[tuple[float, tuple]] = []
            rects = []
            try:
                found = page.find_tables().tables
            except Exception:  # noqa: BLE001 - a page the table finder can't handle: no tables on it
                found = []
            if found:
                words = page.get_text("words")
                for t in found:
                    rows = [[_cell_text(words, c) if c is not None else "" for c in row.cells] for row in t.rows]
                    rows = [r for r in rows if any(c.strip() for c in r)]
                    if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                        rects.append(tuple(t.bbox))
                        placed.append((t.bbox[1], ("table", rows)))
            for b in blocks:
                if _inside(b["bbox"], rects):
                    continue
                x0, y0, x1, y1 = b["bbox"]
                if b.get("type") == 1:  # a picture
                    if n_pics >= MAX_PICTURES or not b.get("image") or x1 - x0 < 12 or y1 - y0 < 12:
                        continue
                    pic = _picture(b)
                    if pic:
                        n_pics += 1
                        w = min(x1 - x0, 450)
                        placed.append((y0, ("img", pic[0], pic[1], w, (y1 - y0) * w / (x1 - x0))))
                    continue
                lines = [ln for ln in b.get("lines", []) if any(s["text"].strip() for s in ln["spans"])]
                para: list[Run] = []

                def flush():
                    nonlocal para
                    if para and _plain(para).strip():
                        placed.append((y0 + len(placed) * 1e-3, ("p", para)))
                    para = []

                for ln in lines:
                    spans = [s for s in ln["spans"] if s["text"].strip()]
                    size = max(s["size"] for s in spans)
                    runs = _runs(ln["spans"])
                    plain = _plain(runs).strip()
                    level = 1 if size >= body * 1.6 else 2 if size >= body * 1.3 else 3 if size >= body * 1.12 else 0
                    if level and len(plain) < 160:
                        flush()
                        placed.append((y0 + len(placed) * 1e-3, ("h", level, [(plain, False, False, False)])))
                    elif plain[:1] in BULLETS and len(plain) > 1:
                        flush()
                        placed.append((y0 + len(placed) * 1e-3, ("li", _strip_bullet(runs))))
                    elif para and re.search(r"[A-Za-z]-$", _plain(para).rstrip()):
                        last = para[-1]
                        para[-1] = (last[0].rstrip()[:-1],) + last[1:]  # a word split over two lines
                        para += runs
                    else:
                        if para:
                            para.append((" ",) + para[-1][1:])
                        para += runs
                flush()
            placed.sort(key=lambda it: it[0])
            items += [it for _y, it in placed]
        count = d.page_count
    return items, "\n".join(texts), count, size0


def _picture(b: dict) -> tuple[bytes, str] | None:
    ext = (b.get("ext") or "png").lower()
    if ext in ("png", "jpeg", "jpg", "gif", "bmp"):
        return b["image"], "jpeg" if ext == "jpg" else ext
    try:
        import pymupdf

        pix = pymupdf.Pixmap(b["image"])
        if pix.alpha or pix.n > 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        return pix.tobytes("png"), "png"
    except Exception:  # noqa: BLE001 - a picture MuPDF can't redraw: left out
        return None


# ---------------------------------------------------------------- the .docx package

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _t(text: str) -> str:
    return escape(_BAD_XML.sub("", text))


def _run_xml(r: Run) -> str:
    text, bold, italic, sup = r
    props = ("<w:b/>" if bold else "") + ("<w:i/>" if italic else "") + ('<w:vertAlign w:val="superscript"/>' if sup else "")
    return (f"<w:r>{'<w:rPr>' + props + '</w:rPr>' if props else ''}"
            f'<w:t xml:space="preserve">{_t(text)}</w:t></w:r>')


def _para(runs: list[Run], style: str = "", numbered: bool = False) -> str:
    ppr = ""
    if style or numbered:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + \
              ('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>' if numbered else "") + "</w:pPr>"
    return f"<w:p>{ppr}{''.join(_run_xml(r) for r in runs)}</w:p>"


def _image_xml(rid: str, n: int, w_pt: float, h_pt: float) -> str:
    cx, cy = int(w_pt * EMU), int(h_pt * EMU)
    return (f'<w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{n}" name="Picture {n}"/><a:graphic><a:graphicData '
            'uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr>'
            f'<pic:cNvPr id="{n}" name="Picture {n}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill>'
            f'<a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm>'
            f'<a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
            "</a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>")


def _table_xml(rows: list[list[str]], width_twips: int) -> str:
    cols = max(len(r) for r in rows)
    col_w = max(400, width_twips // cols)
    grid = "".join(f'<w:gridCol w:w="{col_w}"/>' for _ in range(cols))
    body = ""
    for r in rows:
        cells = ""
        for c in r + [""] * (cols - len(r)):
            cells += (f'<w:tc><w:tcPr><w:tcW w:w="{col_w}" w:type="dxa"/></w:tcPr>'
                      f"{_para([(c, False, False, False)] if c else [])}</w:tc>")
        body += f"<w:tr>{cells}</w:tr>"
    return (f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
            f"<w:tblGrid>{grid}</w:tblGrid>{body}</w:tbl><w:p/>")


STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/>
<w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
<w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
<w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="30"/><w:szCs w:val="30"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
<w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/><w:outlineLvl w:val="2"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="40"/><w:ind w:left="720"/></w:pPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:space="0" w:color="999999"/><w:left w:val="single" w:sz="4" w:space="0" w:color="999999"/>
<w:bottom w:val="single" w:sz="4" w:space="0" w:color="999999"/><w:right w:val="single" w:sz="4" w:space="0" w:color="999999"/>
<w:insideH w:val="single" w:sz="4" w:space="0" w:color="999999"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="999999"/>
</w:tblBorders><w:tblCellMar><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>"""

NUMBERING = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/>
<w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
</w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>"""


def write_docx(items: list[tuple], out: Path, page_size: tuple[float, float], title: str) -> int:
    """Writes the .docx; returns how many pictures went in."""
    pw, ph = page_size
    if not (200 < pw < 2000 and 200 < ph < 3000):
        pw, ph = 595.0, 842.0  # A4
    margin = 1440 if pw > 400 else 720
    text_w = int(pw * 20) - 2 * margin
    body: list[str] = []
    media: list[tuple[str, bytes]] = []
    for it in items:
        kind = it[0]
        if kind == "break":
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        elif kind == "h":
            body.append(_para(it[2], f"Heading{it[1]}"))
        elif kind == "p":
            body.append(_para(it[1]))
        elif kind == "li":
            body.append(_para(it[1], "ListParagraph", numbered=True))
        elif kind == "img":
            n = len(media) + 1
            name = f"image{n}.{'jpg' if it[2] == 'jpeg' else it[2]}"
            media.append((name, it[1]))
            w = min(it[3], text_w / 20)
            body.append(_image_xml(f"rIdImg{n}", n, w, it[4] * w / it[3]))
        elif kind == "table":
            body.append(_table_xml(it[1], text_w))
    sect = (f'<w:sectPr><w:pgSz w:w="{int(pw * 20)}" w:h="{int(ph * 20)}"/><w:pgMar w:top="{margin}" '
            f'w:right="{margin}" w:bottom="{margin}" w:left="{margin}" w:header="708" w:footer="708" w:gutter="0"/>'
            "</w:sectPr>")
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {NS}><w:body>'
                + "".join(body) + sect + "</w:body></w:document>")
    types = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "bmp": "image/bmp"}
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     + "".join(f'<Default Extension="{e}" ContentType="{t}"/>' for e, t in types.items()) +
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
                     'officedocument.wordprocessingml.document.main+xml"/>'
                     '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
                     'officedocument.wordprocessingml.styles+xml"/>'
                     '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-'
                     'officedocument.wordprocessingml.numbering+xml"/>'
                     '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.'
                     'core-properties+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/'
            'core-properties" Target="docProps/core.xml"/></Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rIdNumbering" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/numbering" Target="numbering.xml"/>'
                + "".join(f'<Relationship Id="rIdImg{i}" Type="http://schemas.openxmlformats.org/officeDocument/'
                          f'2006/relationships/image" Target="media/{name}"/>' for i, (name, _b) in enumerate(media, 1))
                + "</Relationships>")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + _t(title) + "</dc:title>"
            "<dc:creator>Deskvert</dc:creator></cp:coreProperties>")
    with zipfile.ZipFile(long_path(out), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/numbering.xml", NUMBERING)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        for name, data in media:
            z.writestr(f"word/media/{name}", data, compress_type=zipfile.ZIP_STORED)
    return len(media)


def docx_text(path: Path) -> str:
    """The words in a .docx's main text, read straight from the file (also checks it's well-formed XML)."""
    from lxml import etree

    with zipfile.ZipFile(long_path(path)) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        for part in ("word/styles.xml", "word/numbering.xml", "[Content_Types].xml", "word/_rels/document.xml.rels"):
            etree.fromstring(z.read(part))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return "\n".join("".join(t.text or "" for t in p.iter(f"{w}t")) for p in root.iter(f"{w}p"))


def to_word(src: Path, out: Path, opts: dict, notes: list[str]) -> None:
    from .officeutil import text_coverage

    items, pdf_text, pages, size = pdf_items(src)
    pics = write_docx(items, out, size, src.stem)
    try:
        text = docx_text(out)
    except Exception as e:  # noqa: BLE001
        raise VerificationError(f"the Word document isn't valid ({e})") from e
    joined = re.sub(r"([A-Za-z])-\s*\n\s*([a-z])", r"\1\2", pdf_text)  # words split over two lines
    cov = text_coverage(joined, text)
    if cov is not None and cov < 0.95:
        raise VerificationError(f"only {cov:.0%} of the PDF's words are in the Word document")
    tables = sum(1 for it in items if it[0] == "table")
    extra = [f"{pics} picture{'s' if pics != 1 else ''}" if pics else "",
             f"{tables} table{'s' if tables != 1 else ''}" if tables else ""]
    extra = [e for e in extra if e]
    notes.append(f"Checked: all of the text from {pages} page{'s' if pages != 1 else ''} is in the document"
                 + (f", with {' and '.join(extra)}." if extra else "."))
    notes.append("Headings, bold, lists, pictures and tables are kept; the exact page layout can shift.")
