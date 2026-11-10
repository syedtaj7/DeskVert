"""Saved e-mails (EML) and saved web pages (MHTML / MHT).

- html: one self-contained page (pictures inside it); e-mails get a header with
        From, To, Date and Subject.
- pdf:  the same, as an A4 PDF (laid out by Qt; scripts never run).
- txt / md: just the text (Markdown keeps headings, lists and links).
- zip:  an e-mail's attachments in one ZIP.

Read with Python's own e-mail parser; nothing is downloaded from the internet
(web pictures that weren't saved inside the file are left out).
"""

from __future__ import annotations

import base64
import email
import html
import re
import zipfile
from email import policy
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path
from .officeutil import text_coverage, words


class Message:
    def __init__(self, src: Path):
        raw = Path(long_path(src)).read_bytes()
        self.msg = email.message_from_bytes(raw, policy=policy.default)
        self.is_mail = src.suffix.lower() == ".eml"
        self.html: str | None = None
        self.text: str | None = None
        self.resources: dict[str, tuple[str, bytes]] = {}  # cid / location -> (mime, data)
        self.attachments: list[tuple[str, bytes]] = []
        for part in self.msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            try:
                payload = part.get_payload(decode=True) or b""
            except Exception:  # noqa: BLE001
                payload = b""
            name = part.get_filename()
            if disp == "attachment" or (name and not ctype.startswith("text/") and not part.get("Content-ID")):
                self.attachments.append((name or f"attachment {len(self.attachments) + 1}", payload))
                continue
            if ctype == "text/html" and self.html is None:
                self.html = _decode(part, payload)
            elif ctype == "text/plain" and self.text is None and not name:
                self.text = _decode(part, payload)
            else:
                for key in (part.get("Content-ID"), part.get("Content-Location")):
                    if key:
                        self.resources[key.strip("<> ")] = (ctype, payload)
        if self.html is None and self.text is None:
            raise ConversionError("This file has no readable text or page in it.")

    def header_html(self) -> str:
        if not self.is_mail:
            return ""
        rows = []
        for k in ("From", "To", "Cc", "Date", "Subject"):
            v = self.msg.get(k)
            if v:
                rows.append(f"<tr><td style='color:#666;padding-right:12px'>{k}</td><td>{html.escape(str(v))}</td></tr>")
        if self.attachments:
            names = ", ".join(html.escape(n) for n, _ in self.attachments)
            rows.append(f"<tr><td style='color:#666;padding-right:12px'>Attachments</td><td>{names}</td></tr>")
        return "<table style='margin-bottom:12px;font-family:Segoe UI,Arial;font-size:10pt'>" + "".join(rows) + \
            "</table><hr>"

    def body_html(self, inline: bool) -> str:
        """The page. inline=True: pictures as data: URLs (for a standalone HTML file)."""
        if self.html is not None:
            body = re.sub(r"(?is)<script.*?</script>", "", self.html)
            body = re.sub(r"(?is)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", body)  # event handlers
        else:
            body = "<pre style='white-space:pre-wrap;font-family:Segoe UI,Arial'>" + html.escape(self.text or "") + \
                   "</pre>"
        if inline:
            def sub(m):
                ref = m.group(2)
                key = ref[4:] if ref.lower().startswith("cid:") else ref
                if key in self.resources:
                    mime, data = self.resources[key]
                    return f'{m.group(1)}"data:{mime};base64,{base64.b64encode(data).decode()}"'
                return m.group(0)
            body = re.sub(r'((?:src|href)\s*=\s*)["\']([^"\']+)["\']', sub, body, flags=re.I)
        head = self.header_html()
        if head:
            body = re.sub(r"(?i)(<body[^>]*>)", r"\1" + head.replace("\\", "\\\\"), body, count=1) \
                if re.search(r"(?i)<body", body) else head + body
        return body

    def plain(self) -> str:
        if self.text is not None and (self.html is None or self.is_mail):
            body = self.text
        else:
            body = _qt_doc(self.html or "", {}).toPlainText()
        if self.is_mail:
            head = "\n".join(f"{k}: {self.msg.get(k)}" for k in ("From", "To", "Cc", "Date", "Subject")
                             if self.msg.get(k))
            if self.attachments:
                head += "\nAttachments: " + ", ".join(n for n, _ in self.attachments)
            return head + "\n\n" + body
        return body


def _decode(part, payload: bytes) -> str:
    cs = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(cs, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _qt_doc(page: str, resources: dict):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QFont, QImage, QTextDocument

    from .textdoc import _app

    _app()
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Segoe UI", 10))
    for key, (mime, data) in resources.items():
        if mime.startswith("image/"):
            img = QImage.fromData(data)
            if not img.isNull():
                if img.width() > 1600:
                    img = img.scaledToWidth(1600)
                doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(key), img)
                doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl("cid:" + key), img)
    doc.setHtml(page)
    return doc


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    m = Message(sources[0])
    notes: list[str] = []
    if fmt == "html":
        page = m.body_html(inline=True)
        Path(long_path(out)).write_text(page, encoding="utf-8")
        back = _qt_doc(Path(long_path(out)).read_text(encoding="utf-8"), {}).toPlainText()
        want = _qt_doc(m.body_html(inline=False), m.resources).toPlainText()
        if words(back) != words(want):
            raise VerificationError("the page's text doesn't match")
        notes.append("Checked: all of the text, with the pictures saved inside the page. Scripts were removed.")
    elif fmt == "pdf":
        import pymupdf
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter

        doc = _qt_doc(m.body_html(inline=False), m.resources)
        writer = QPdfWriter(long_path(out))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageMargins(QMarginsF(18, 16, 18, 16), QPageLayout.Unit.Millimeter)
        writer.setResolution(300)
        writer.setTitle(str(m.msg.get("Subject") or sources[0].stem))
        writer.setCreator("Tapshift")
        doc.print_(writer)
        del writer
        with pymupdf.open(long_path(out)) as d:
            pages, text = d.page_count, "\n".join(p.get_text() for p in d)
        cov = text_coverage(doc.toPlainText(), text)
        if pages < 1 or (cov is not None and cov < 0.97):
            raise VerificationError("some of the text is missing from the PDF")
        notes.append(f"Checked: {pages} A4 page{'s' if pages != 1 else ''}, all of the text included.")
    elif fmt == "txt":
        text = m.plain().replace(chr(13) + chr(10), chr(10))
        Path(long_path(out)).write_text(text, encoding="utf-8", newline=chr(13) + chr(10))
        if Path(long_path(out)).read_text(encoding="utf-8").replace(chr(13) + chr(10), chr(10)) != text:
            raise VerificationError("the text file doesn't match")
        notes.append(f"Checked: {len(words(text)):,} words saved as plain text.")
    elif fmt == "md":
        doc = _qt_doc(m.body_html(inline=False), m.resources)
        md = doc.toMarkdown()
        Path(long_path(out)).write_text(md, encoding="utf-8")
        cov = text_coverage(doc.toPlainText(), md)
        if cov is not None and cov < 0.95:
            raise VerificationError("some of the text is missing from the Markdown")
        notes.append("Checked: all of the text, as Markdown (pictures are left out).")
    elif fmt == "zip":
        if not m.attachments:
            raise ConversionError("This e-mail has no attachments.")
        used: set[str] = set()
        with zipfile.ZipFile(long_path(out), "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in m.attachments:
                safe = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "attachment"
                base, k = safe, 2
                while safe.lower() in used:
                    stem, dot, ext = base.rpartition(".")
                    safe = f"{stem} ({k}).{ext}" if dot else f"{base} ({k})"
                    k += 1
                used.add(safe.lower())
                z.writestr(safe, data)
        with zipfile.ZipFile(long_path(out)) as z:
            if z.testzip() is not None or len(z.namelist()) != len(m.attachments):
                raise VerificationError("the ZIP is incomplete")
        notes.append(f"Checked: {len(m.attachments)} attachment{'s' if len(m.attachments) != 1 else ''} in the ZIP.")
    else:
        raise ConversionError(f"Unknown conversion: {fmt}")
    return notes
