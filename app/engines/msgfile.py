"""Outlook .msg e-mails, read without Outlook: turned into a standard e-mail (EML) that the mail
engine already knows how to save as PDF, a web page, text, Markdown, or its attachments as a ZIP.

A .msg is a Microsoft "compound file" (a little file system inside one file). This reads it
directly, read-only: the subject, sender, recipients, date, the HTML or plain-text body, pictures
shown in the body, and attachments. Nothing is run and nothing is downloaded.
"""

from __future__ import annotations

import datetime
import email.policy
import mimetypes
import re
import struct
from email.message import EmailMessage
from email.utils import format_datetime, formataddr
from pathlib import Path

from ..errors import ConversionError
from ..paths import long_path

MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
FREE, END, FATSECT, DIFSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFC
NOSTREAM = 0xFFFFFFFF


class CompoundFile:
    """A read-only reader for Microsoft compound files (the container of .msg, .doc, .xls...)."""

    def __init__(self, data: bytes):
        if len(data) < 512 or data[:8] != MAGIC:
            raise ConversionError("This isn't an Outlook message (.msg) Deskvert can read.")
        self.data = data
        self.ss = 1 << struct.unpack_from("<H", data, 0x1E)[0]
        self.mss = 1 << struct.unpack_from("<H", data, 0x20)[0]
        n_fat, first_dir = struct.unpack_from("<II", data, 0x2C)
        self.cutoff, first_minifat, n_minifat, first_difat, n_difat = struct.unpack_from("<IIIII", data, 0x38)
        difat = list(struct.unpack_from("<109I", data, 0x4C))
        sec, guard = first_difat, 0
        while sec not in (END, FREE) and guard < n_difat + 1:
            vals = struct.unpack_from(f"<{self.ss // 4}I", self._sector(sec))
            difat += vals[:-1]
            sec, guard = vals[-1], guard + 1
        self.fat: list[int] = []
        for s in difat[:n_fat]:
            if s in (FREE, END):
                continue
            self.fat += struct.unpack_from(f"<{self.ss // 4}I", self._sector(s))
        dirs = self._chain_bytes(first_dir)
        self.entries = []
        for i in range(len(dirs) // 128):
            e = dirs[i * 128:(i + 1) * 128]
            nlen = struct.unpack_from("<H", e, 64)[0]
            name = e[:max(0, nlen - 2)].decode("utf-16-le", errors="replace")
            kind = e[66]
            left, right, child = struct.unpack_from("<III", e, 68)
            start = struct.unpack_from("<I", e, 116)[0]
            size = struct.unpack_from("<Q", e, 120)[0]
            if self.ss == 512:
                size &= 0xFFFFFFFF
            self.entries.append({"name": name, "kind": kind, "left": left, "right": right, "child": child,
                                 "start": start, "size": size})
        if not self.entries or self.entries[0]["kind"] != 5:
            raise ConversionError("This .msg file is damaged.")
        root = self.entries[0]
        self.ministream = self._chain_bytes(root["start"])[:root["size"]] if root["start"] != END else b""
        self.minifat = []
        if n_minifat:
            raw = self._chain_bytes(first_minifat)
            self.minifat = list(struct.unpack_from(f"<{len(raw) // 4}I", raw))

    def _sector(self, n: int) -> bytes:
        off = (n + 1) * self.ss
        if off + self.ss > len(self.data):
            return self.data[off:].ljust(self.ss, b"\0")
        return self.data[off:off + self.ss]

    def _chain_bytes(self, start: int) -> bytes:
        out, sec, seen = [], start, set()
        while sec not in (END, FREE, FATSECT, DIFSECT) and sec < len(self.fat) and sec not in seen:
            seen.add(sec)
            out.append(self._sector(sec))
            sec = self.fat[sec]
        return b"".join(out)

    def _mini_bytes(self, start: int, size: int) -> bytes:
        out, sec, seen = [], start, set()
        while sec not in (END, FREE) and sec < len(self.minifat) and sec not in seen and len(out) * self.mss < size:
            seen.add(sec)
            out.append(self.ministream[sec * self.mss:(sec + 1) * self.mss])
            sec = self.minifat[sec]
        return b"".join(out)[:size]

    def children(self, index: int) -> dict[str, int]:
        """{name: entry index} of a storage's direct children."""
        out: dict[str, int] = {}
        stack, seen = [self.entries[index]["child"]], set()
        while stack:
            i = stack.pop()
            if i == NOSTREAM or i in seen or i >= len(self.entries):
                continue
            seen.add(i)
            e = self.entries[i]
            out[e["name"]] = i
            stack += [e["left"], e["right"]]
        return out

    def read(self, index: int) -> bytes:
        e = self.entries[index]
        if e["size"] < self.cutoff:
            return self._mini_bytes(e["start"], e["size"])
        return self._chain_bytes(e["start"])[:e["size"]]


# ---------------------------------------------------------------- MAPI properties

SUBJECT, SENDER_NAME, SENDER_EMAIL, SENDER_SMTP = 0x0037, 0x0C1A, 0x0C1F, 0x5D01
DISPLAY_TO, DISPLAY_CC, BODY, HTML, HEADERS, CPID = 0x0E04, 0x0E03, 0x1000, 0x1013, 0x007D, 0x3FDE
ATT_DATA, ATT_LONG_NAME, ATT_NAME, ATT_MIME, ATT_CID = 0x3701, 0x3707, 0x3704, 0x370E, 0x3712
RECIP_NAME, RECIP_SMTP, RECIP_EMAIL, RECIP_TYPE = 0x3001, 0x39FE, 0x3003, 0x0C15
SUBMIT_TIME, DELIVERY_TIME = 0x0039, 0x0E06


class Props:
    """The properties stored in one storage of a .msg (strings and binaries as streams, the rest fixed)."""

    def __init__(self, cf: CompoundFile, index: int, top: bool, codepage: str = "cp1252"):
        self.cf, self.kids, self.codepage = cf, cf.children(index), codepage
        self.fixed: dict[int, bytes] = {}
        p = self.kids.get("__properties_version1.0")
        if p is not None:
            raw = cf.read(p)
            off = 32 if top else 8
            for k in range(off, len(raw) - 15, 16):
                tag = struct.unpack_from("<I", raw, k)[0]
                self.fixed[tag >> 16] = raw[k + 8:k + 16]

    def raw(self, prop: int) -> bytes | None:
        for kind in ("001F", "001E", "0102"):
            i = self.kids.get(f"__substg1.0_{prop:04X}{kind}")
            if i is not None:
                return self.cf.read(i)
        return None

    def text(self, prop: int) -> str:
        i = self.kids.get(f"__substg1.0_{prop:04X}001F")
        if i is not None:
            return self.cf.read(i).decode("utf-16-le", errors="replace").rstrip("\0")
        i = self.kids.get(f"__substg1.0_{prop:04X}001E")
        if i is not None:
            return self.cf.read(i).decode(self.codepage, errors="replace").rstrip("\0")
        return ""

    def number(self, prop: int) -> int | None:
        v = self.fixed.get(prop)
        return struct.unpack_from("<I", v)[0] if v else None

    def time(self, prop: int) -> datetime.datetime | None:
        v = self.fixed.get(prop)
        if not v:
            return None
        ft = struct.unpack_from("<Q", v)[0]
        if not ft:
            return None
        return datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(microseconds=ft // 10)


def _codepage(cpid: int | None) -> str:
    return {65001: "utf-8", 1252: "cp1252", 28591: "latin-1", 20127: "ascii", 1250: "cp1250", 1251: "cp1251",
            932: "cp932", 936: "gbk", 949: "cp949", 950: "cp950"}.get(cpid or 0, "cp1252")


def to_eml(src: Path) -> bytes:
    """The .msg as a standard e-mail (bytes), for the mail engine."""
    cf = CompoundFile(Path(long_path(src)).read_bytes())
    top = Props(cf, 0, top=True)
    top.codepage = _codepage(top.number(CPID))
    msg = EmailMessage(policy=email.policy.default)
    msg["Subject"] = top.text(SUBJECT) or src.stem
    sender = top.text(SENDER_SMTP) or top.text(SENDER_EMAIL)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", sender or ""):
        sender = ""
    name = top.text(SENDER_NAME)
    if name or sender:
        msg["From"] = formataddr((name, sender)) if sender else name
    to, cc = [], []
    for key, idx in cf.children(0).items():
        if key.startswith("__recip_version1.0_"):
            r = Props(cf, idx, top=False, codepage=top.codepage)
            addr = r.text(RECIP_SMTP) or r.text(RECIP_EMAIL)
            addr = addr if re.fullmatch(r"[^@\s]+@[^@\s]+", addr or "") else ""
            who = formataddr((r.text(RECIP_NAME), addr)) if addr else r.text(RECIP_NAME)
            (cc if r.number(RECIP_TYPE) == 2 else to).append(who)
    if to or top.text(DISPLAY_TO):
        msg["To"] = ", ".join(to) or top.text(DISPLAY_TO)
    if cc or top.text(DISPLAY_CC):
        msg["Cc"] = ", ".join(cc) or top.text(DISPLAY_CC)
    when = top.time(SUBMIT_TIME) or top.time(DELIVERY_TIME)
    if when is None:
        m = re.search(r"^Date:\s*(.+)$", top.text(HEADERS), re.M | re.I)
        if m:
            msg["Date"] = m.group(1).strip()
    else:
        msg["Date"] = format_datetime(when)
    body = top.text(BODY)
    html_raw = top.raw(HTML)
    html_text = ""
    if html_raw:
        if f"__substg1.0_{HTML:04X}001F" in top.kids:
            html_text = html_raw.decode("utf-16-le", errors="replace").rstrip("\0")
        else:
            m = re.search(rb"charset=[\"']?([\w-]+)", html_raw[:2000], re.I)
            enc = m.group(1).decode() if m else top.codepage
            try:
                html_text = html_raw.decode(enc, errors="replace")
            except LookupError:
                html_text = html_raw.decode(top.codepage, errors="replace")
    if not body and not html_text:
        raise ConversionError("This e-mail has no text in it that Deskvert can read (it may hold only a "
                              "rich-text body, which isn't supported).")
    msg.set_content(body or re.sub(r"<[^>]+>", " ", html_text))
    if html_text:
        msg.add_alternative(html_text, subtype="html")
    html_part = msg.get_payload()[-1] if html_text else None
    for key, idx in sorted(cf.children(0).items()):
        if not key.startswith("__attach_version1.0_"):
            continue
        a = Props(cf, idx, top=False, codepage=top.codepage)
        data = a.raw(ATT_DATA)
        if data is None:
            continue  # an embedded message or object: not a plain file
        fname = a.text(ATT_LONG_NAME) or a.text(ATT_NAME) or f"attachment {idx}"
        mime = a.text(ATT_MIME) or mimetypes.guess_type(fname)[0] or "application/octet-stream"
        maintype, _, subtype = mime.partition("/")
        cid = a.text(ATT_CID)
        if cid and html_part is not None and cid in html_text:
            html_part.add_related(data, maintype, subtype or "octet-stream", cid=f"<{cid}>", filename=fname,
                                  disposition="inline")  # shown in the body, not a separate attachment
        else:
            msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=fname)
    return msg.as_bytes()
