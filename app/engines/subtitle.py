"""Subtitles: SRT, WebVTT, ASS/SSA, SAMI, LRC, TTML and MicroDVD, into each other (and SCC captions into them).

Every format is read into the same list of cues (start, end, text) and written
out again; the new file is read back and compared cue by cue. Italic, bold and
underline survive where the format has them; styling a format can't hold
(positions, colors, karaoke) is left out and the notes say so.

MicroDVD counts video frames instead of time: 23.976 frames per second is used
unless the file says otherwise in its first line ({1}{1}25).
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

TIME = r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})"
CUE_RE = re.compile(rf"^\s*{TIME}\s*-->\s*{TIME}(.*)$")
KEEP_TAGS = re.compile(r"</?(?:i|b|u)>", re.I)
ANY_TAG = re.compile(r"<[^>]+>")
FPS = 23.976
EXTS = {".srt": "srt", ".vtt": "vtt", ".ass": "ass", ".ssa": "ass", ".smi": "sami", ".sami": "sami", ".lrc": "lrc",
        ".ttml": "ttml", ".dfxp": "ttml", ".sub": "microdvd", ".scc": "scc"}
OUT_EXT = {"srt": ".srt", "vtt": ".vtt", "ass": ".ass", "sami": ".smi", "lrc": ".lrc", "ttml": ".ttml",
           "microdvd": ".sub"}

Cue = tuple[int, int, str]


def _ms(h, m, s, f) -> int:
    return ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int((f + "00")[:3])


def _read(src: Path) -> str:
    raw = Path(long_path(src)).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp949", "cp1252"):  # cp949: Korean SAMI/SRT files
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def plain(text: str) -> str:
    """The text with the tags every format shares (i, b, u); others removed."""
    keep = KEEP_TAGS.sub(lambda m: m.group(0).lower(), text)
    return ANY_TAG.sub(lambda m: m.group(0) if KEEP_TAGS.fullmatch(m.group(0)) else "", keep).strip()


def _words_only(text: str) -> str:
    return ANY_TAG.sub("", text).strip()


# ---------------------------------------------------------------- readers

def read_srt_vtt(text: str) -> list[Cue]:
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip()):
        lines = block.split("\n")
        k = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if k is None:
            continue
        m = CUE_RE.match(lines[k])
        if not m:
            continue
        g = m.groups()
        cues.append((_ms(*g[0:4]), _ms(*g[4:8]), "\n".join(x.rstrip() for x in lines[k + 1:]).strip("\n")))
    return cues


def _ass_time(t: str) -> int:
    h, m, s = t.strip().split(":")
    sec, _, cs = s.partition(".")
    return ((int(h) * 60 + int(m)) * 60 + int(sec)) * 1000 + int((cs + "00")[:2]) * 10


def read_ass(text: str) -> list[Cue]:
    cues, fields = [], None
    section = ""
    for line in text.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if s.startswith("["):
            section = s.lower()
            continue
        if section != "[events]":
            continue
        if s.lower().startswith("format:"):
            fields = [f.strip().lower() for f in s[7:].split(",")]
        elif s.lower().startswith("dialogue:") and fields:
            parts = s[9:].split(",", len(fields) - 1)
            row = dict(zip(fields, (p.strip() for p in parts)))
            body = row.get("text", "")
            body = re.sub(r"\{\\i1\}", "<i>", body)
            body = re.sub(r"\{\\i0?\}", "</i>", body)
            body = re.sub(r"\{\\b1\}", "<b>", body)
            body = re.sub(r"\{\\b0?\}", "</b>", body)
            body = re.sub(r"\{\\u1\}", "<u>", body)
            body = re.sub(r"\{\\u0?\}", "</u>", body)
            body = re.sub(r"\{[^}]*\}", "", body)
            body = body.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
            cues.append((_ass_time(row["start"]), _ass_time(row["end"]), body))
    cues.sort(key=lambda c: c[0])
    return cues


def read_sami(text: str) -> list[Cue]:
    syncs = [(int(m.group(1)), m.end()) for m in re.finditer(r"<sync[^>]*start\s*=\s*\"?(\d+)", text, re.I)]
    raw = []
    for i, (start, pos) in enumerate(syncs):
        end_pos = syncs[i + 1][1] if i + 1 < len(syncs) else len(text)
        chunk = text[pos:end_pos]
        chunk = re.sub(r"<sync.*", "", chunk, flags=re.I | re.S)
        chunk = chunk.split(">", 1)[1] if ">" in chunk else ""  # the rest of the <SYNC ...> tag
        chunk = re.sub(r"<br\s*/?>", "\n", chunk, flags=re.I)
        chunk = re.sub(r"</?(?:p|body|sami|font|span)[^>]*>", "", chunk, flags=re.I)
        body = html.unescape(chunk).replace("\xa0", " ").strip()
        raw.append((start, body))
    cues = []
    for i, (start, body) in enumerate(raw):
        if not body:
            continue
        end = raw[i + 1][0] if i + 1 < len(raw) else start + 3000
        cues.append((start, end, "\n".join(x.strip() for x in body.split("\n") if x.strip())))
    return cues


def read_lrc(text: str) -> list[Cue]:
    stamps = []
    offset = 0
    for line in text.replace("\r\n", "\n").split("\n"):
        mo = re.match(r"\[offset:\s*([+-]?\d+)\]", line.strip(), re.I)
        if mo:
            offset = int(mo.group(1))
        tags = re.findall(r"\[(\d+):(\d{2})(?:[.:](\d{1,3}))?\]", line)
        words = re.sub(r"\[[^\]]*\]", "", line).strip()
        for m, s, f in tags:
            stamps.append((int(m) * 60000 + int(s) * 1000 + int(((f or "0") + "00")[:3]) - offset, words))
    stamps.sort()
    cues = []
    for i, (start, words) in enumerate(stamps):
        if not words:
            continue
        end = stamps[i + 1][0] if i + 1 < len(stamps) else start + 4000
        cues.append((max(0, start), max(start + 1, end), words))
    return cues


def _ttml_time(t: str, fps: float) -> int:
    t = t.strip()
    m = re.fullmatch(r"(\d+):(\d{2}):(\d{2})(?:[.](\d+))?", t)
    if m:
        h, mi, s, f = m.groups()
        return ((int(h) * 60 + int(mi)) * 60 + int(s)) * 1000 + int(((f or "0") + "00")[:3])
    m = re.fullmatch(r"(\d+):(\d{2}):(\d{2}):(\d+)", t)
    if m:
        h, mi, s, fr = m.groups()
        return ((int(h) * 60 + int(mi)) * 60 + int(s)) * 1000 + round(int(fr) * 1000 / fps)
    m = re.fullmatch(r"([\d.]+)(h|m|s|ms|f|t)", t)
    if m:
        v, unit = float(m.group(1)), m.group(2)
        return round({"h": v * 3_600_000, "m": v * 60_000, "s": v * 1000, "ms": v, "f": v * 1000 / fps,
                      "t": v / 10_000}[unit])
    raise ConversionError(f"Unknown TTML time: {t}")


def read_ttml(text: str) -> list[Cue]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(text.encode("utf-8"))
    fps = FPS
    for k, v in root.attrib.items():
        if k.endswith("frameRate"):
            fps = float(v)
    cues = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] != "p" or "begin" not in el.attrib:
            continue
        start = _ttml_time(el.attrib["begin"], fps)
        if "end" in el.attrib:
            end = _ttml_time(el.attrib["end"], fps)
        else:
            end = start + _ttml_time(el.attrib.get("dur", "3s"), fps)

        def walk(node) -> str:
            tag = node.tag.rsplit("}", 1)[-1]
            out = node.text or ""
            for child in node:
                ct = child.tag.rsplit("}", 1)[-1]
                if ct == "br":
                    out += "\n"
                else:
                    inner = walk(child)
                    style = " ".join(f"{k}={v}" for k, v in child.attrib.items())
                    if "italic" in style:
                        inner = f"<i>{inner}</i>"
                    if "bold" in style:
                        inner = f"<b>{inner}</b>"
                    if "underline" in style:
                        inner = f"<u>{inner}</u>"
                    out += inner
                out += child.tail or ""
            _ = tag
            return out

        body = "\n".join(x.strip() for x in walk(el).split("\n"))
        cues.append((start, end, body.strip()))
    return cues


def read_microdvd(text: str) -> list[Cue]:
    lines = [x for x in text.replace("\r\n", "\n").split("\n") if x.strip()]
    if not lines or not re.match(r"\{\d+\}\{\d*\}", lines[0]):
        raise ConversionError("This .sub file isn't MicroDVD text (it may be a VobSub picture subtitle, which "
                              "can't be read as text).")
    fps = FPS
    first = re.match(r"\{1\}\{1\}([\d.]+)", lines[0])
    if first:
        fps = float(first.group(1))
        lines = lines[1:]
    cues = []
    for line in lines:
        m = re.match(r"\{(\d+)\}\{(\d*)\}(.*)", line)
        if not m:
            continue
        a, b, body = int(m.group(1)), m.group(2), m.group(3)
        end = int(b) if b else a + round(fps * 3)
        italic = body.lower().startswith("{y:i}")
        body = re.sub(r"\{[^}]*\}", "", body).replace("|", "\n")
        if italic:
            body = f"<i>{body}</i>"
        cues.append((round(a * 1000 / fps), round(end * 1000 / fps), body))
    return cues


def read_scc(text: str) -> list[Cue]:
    from .scc import read_scc as scc

    return scc(text)


READERS = {"scc": read_scc, "srt": read_srt_vtt, "vtt": read_srt_vtt, "ass": read_ass, "sami": read_sami, "lrc": read_lrc,
           "ttml": read_ttml, "microdvd": read_microdvd}


def parse(text: str, kind: str = "srt") -> list[Cue]:
    try:
        cues = READERS[kind](text)
    except ConversionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"This subtitle file couldn't be read ({e}).") from e
    if not cues:
        raise ConversionError("No subtitles were found in this file.")
    return cues


# ---------------------------------------------------------------- writers

def _stamp(ms: int, sep: str) -> str:
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues) -> str:
    return "\n".join(f"{n}\n{_stamp(a, ',')} --> {_stamp(b, ',')}\n{plain(t)}\n" for n, (a, b, t) in enumerate(cues, 1))


def to_vtt(cues) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{_stamp(a, '.')} --> {_stamp(b, '.')}\n{plain(t)}\n" for a, b, t in cues)


def _ass_stamp(ms: int) -> str:
    cs = round(ms / 10)
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def to_ass(cues) -> str:
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,64,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,1,2,40,40,"
            "50,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    rows = []
    for a, b, t in cues:
        body = plain(t)
        for tag, code in (("i", "i"), ("b", "b"), ("u", "u")):
            body = body.replace(f"<{tag}>", f"{{\\{code}1}}").replace(f"</{tag}>", f"{{\\{code}0}}")
        rows.append(f"Dialogue: 0,{_ass_stamp(a)},{_ass_stamp(b)},Default,,0,0,0,,{body.replace(chr(10), chr(92) + 'N')}")
    return head + "\n".join(rows) + "\n"


def to_sami(cues) -> str:
    out = ["<SAMI>\n<HEAD>\n<TITLE>Subtitles</TITLE>\n<STYLE TYPE=\"text/css\">\n<!--\n"
           "P { font-family: Arial; text-align: center; }\n.ENCC { Name: English; lang: en-US; }\n-->\n</STYLE>\n"
           "</HEAD>\n<BODY>"]
    for a, b, t in cues:
        body = "<br>".join(html.escape(line, quote=False).replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
                           .replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>").replace("&lt;u&gt;", "<u>")
                           .replace("&lt;/u&gt;", "</u>") for line in plain(t).split("\n"))
        out.append(f"<SYNC Start={a}><P Class=ENCC>{body}")
        out.append(f"<SYNC Start={b}><P Class=ENCC>&nbsp;")
    out.append("</BODY>\n</SAMI>\n")
    return "\n".join(out)


def to_lrc(cues) -> str:
    out = []
    for a, b, t in cues:
        m, rest = divmod(a, 60000)
        out.append(f"[{m:02d}:{rest // 1000:02d}.{(rest % 1000) // 10:02d}]{_words_only(t).replace(chr(10), ' ')}")
        m, rest = divmod(b, 60000)
        out.append(f"[{m:02d}:{rest // 1000:02d}.{(rest % 1000) // 10:02d}]")
    return "\n".join(out) + "\n"


def to_ttml(cues) -> str:
    def body(t: str) -> str:
        s = html.escape(plain(t), quote=False)
        s = s.replace("&lt;i&gt;", '<span tts:fontStyle="italic">').replace("&lt;/i&gt;", "</span>")
        s = s.replace("&lt;b&gt;", '<span tts:fontWeight="bold">').replace("&lt;/b&gt;", "</span>")
        s = s.replace("&lt;u&gt;", '<span tts:textDecoration="underline">').replace("&lt;/u&gt;", "</span>")
        return s.replace("\n", "<br/>")

    rows = "\n".join(f'      <p begin="{_stamp(a, ".")}" end="{_stamp(b, ".")}">{body(t)}</p>' for a, b, t in cues)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<tt xmlns="http://www.w3.org/ns/ttml" '
            'xmlns:tts="http://www.w3.org/ns/ttml#styling" xml:lang="en">\n  <body>\n    <div>\n'
            f"{rows}\n    </div>\n  </body>\n</tt>\n")


def to_microdvd(cues) -> str:
    out = [f"{{1}}{{1}}{FPS}"]
    for a, b, t in cues:
        body = plain(t)
        italic = body.startswith("<i>") and body.endswith("</i>") and body.count("<i>") == 1
        body = _words_only(body).replace("\n", "|")
        out.append(f"{{{round(a * FPS / 1000)}}}{{{round(b * FPS / 1000)}}}{'{y:i}' if italic else ''}{body}")
    return "\n".join(out) + "\n"


WRITERS = {"srt": to_srt, "vtt": to_vtt, "ass": to_ass, "sami": to_sami, "lrc": to_lrc, "ttml": to_ttml,
           "microdvd": to_microdvd}


# ---------------------------------------------------------------- convert + verify

def _expected(cues: list[Cue], fmt: str) -> list[Cue]:
    """What the target format can hold of each cue."""
    if fmt in ("lrc",):
        return [(a, b, _words_only(t).replace("\n", " ")) for a, b, t in cues]
    if fmt == "microdvd":
        return [(a, b, _words_only(t)) for a, b, t in cues]
    return [(a, b, plain(t)) for a, b, t in cues]


def _close(a: list[Cue], b: list[Cue], tol_ms: int, words: bool) -> bool:
    if len(a) != len(b):
        return False
    for (s1, e1, t1), (s2, e2, t2) in zip(a, b):
        if abs(s1 - s2) > tol_ms or abs(e1 - e2) > tol_ms:
            return False
        x, y = (_words_only(t1), _words_only(t2)) if words else (t1, t2)
        if " ".join(x.split()) != " ".join(y.split()):
            return False
    return True


def parse_shift(text: str) -> int:
    """'+2.5', '-1', '1,5 s' -> milliseconds. Raises ValueError with a message for the user."""
    t = (text or "").strip().lower().replace(",", ".").replace("s", "").replace(" ", "")
    m = re.fullmatch(r"([+-]?)(\d{1,5}(?:\.\d{1,3})?)", t)
    if not m:
        raise ValueError("Type seconds, like +2.5 (later) or -1 (earlier).")
    ms = round(float(m.group(2)) * 1000)
    if ms == 0:
        raise ValueError("Type a shift other than 0.")
    return -ms if m.group(1) == "-" else ms


def shift(src: Path, out: Path, kind: str, opts: dict) -> list[str]:
    try:
        delta = parse_shift(str(opts.get("seconds", "")))
    except ValueError as e:
        raise ConversionError(str(e)) from e
    cues = parse(_read(src), kind)
    moved = [(max(0, a + delta), max(0, b + delta), t) for a, b, t in cues]
    clipped = sum(1 for a, _b, _t in cues if a + delta < 0)
    Path(long_path(out)).write_text(WRITERS[kind](moved), encoding="utf-8", newline="\n")
    back = parse(Path(long_path(out)).read_text(encoding="utf-8"), kind)
    tol = {"ass": 10, "lrc": 10, "microdvd": 1000 / FPS + 1}.get(kind, 0)
    if not _close(back, _expected(moved, kind), int(tol), words=kind in ("lrc", "microdvd", "sami", "ttml")):
        raise VerificationError("the subtitles changed on the way")
    secs = f"{abs(delta) / 1000:g} second{'s' if abs(delta) != 1000 else ''}"
    notes = [f"Checked: {len(cues)} subtitles, every one {secs} {'later' if delta > 0 else 'earlier'}. Same format."]
    if clipped:
        notes.append(f"{clipped} subtitle{'s' if clipped != 1 else ''} would have started before 0:00, so "
                     f"{'they start' if clipped != 1 else 'it starts'} at 0:00.")
    return notes


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    src = sources[0]
    kind = EXTS.get(src.suffix.lower())
    if kind is not None and fmt == "shift":
        return shift(src, out, kind, opts)
    if kind is None or fmt not in WRITERS:
        raise ConversionError("Unknown subtitle format.")
    cues = parse(_read(src), kind)
    text = WRITERS[fmt](cues)
    Path(long_path(out)).write_text(text, encoding="utf-8", newline="\n")
    back = parse(Path(long_path(out)).read_text(encoding="utf-8"), fmt)
    want = _expected(cues, fmt)
    # timing precision: ASS keeps hundredths, LRC hundredths, MicroDVD whole frames
    tol = {"ass": 10, "lrc": 10, "microdvd": 1000 / FPS + 1}.get(fmt, 0)
    if not _close(back, want, int(tol), words=fmt in ("lrc", "microdvd", "sami", "ttml")):
        raise VerificationError("the subtitles changed on the way")
    precise = {"ass": "to the hundredth of a second", "lrc": "to the hundredth of a second",
               "microdvd": f"to the frame ({FPS} fps)"}.get(fmt, "to the millisecond")
    notes = [f"Checked: {len(cues)} subtitles, every timing kept {precise}."]
    if any(plain(t) != t.strip() for _a, _b, t in cues) or fmt in ("lrc", "microdvd"):
        notes.append("Styling the new format doesn't have (like positions or colors) was left out.")
    return notes
