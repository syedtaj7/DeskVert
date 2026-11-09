"""Subtitles: SRT <-> WebVTT.

- vtt: SRT -> WebVTT (for web players and HTML5 video)
- srt: WebVTT -> SRT (for TVs, VLC and most video editors)

Timings are kept to the millisecond. Italic, bold and underline survive;
WebVTT-only styling (voice names, classes, positions) isn't part of SRT and is
dropped. The new file is read back and every cue is compared with the source.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

TIME = r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})"
CUE_RE = re.compile(rf"^\s*{TIME}\s*-->\s*{TIME}(.*)$")
KEEP_TAGS = re.compile(r"</?(?:i|b|u)>", re.I)
ANY_TAG = re.compile(r"<[^>]+>")


def _ms(h, m, s, f) -> int:
    return ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int((f + "00")[:3])


def _read(src: Path) -> str:
    raw = Path(long_path(src)).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse(text: str) -> list[tuple[int, int, str]]:
    """[(start ms, end ms, text)] from SRT or WebVTT."""
    cues = []
    blocks = re.split(r"\r?\n\s*\r?\n", text.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = block.split("\n")
        k = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if k is None:
            continue  # WEBVTT header, NOTE, STYLE, REGION or a stray number
        m = CUE_RE.match(lines[k])
        if not m:
            continue
        g = m.groups()
        start, end = _ms(*g[0:4]), _ms(*g[4:8])
        body = "\n".join(line.rstrip() for line in lines[k + 1:]).strip("\n")
        cues.append((start, end, body))
    if not cues:
        raise ConversionError("No subtitles were found in this file.")
    return cues


def _plain(text: str) -> str:
    """The text with the tags both formats share; others removed."""
    keep = KEEP_TAGS.sub(lambda m: m.group(0).lower(), text)
    return ANY_TAG.sub(lambda m: m.group(0) if KEEP_TAGS.fullmatch(m.group(0)) else "", keep)


def _stamp(ms: int, sep: str) -> str:
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues) -> str:
    out = []
    for n, (a, b, t) in enumerate(cues, 1):
        out.append(f"{n}\n{_stamp(a, ',')} --> {_stamp(b, ',')}\n{_plain(t)}\n")
    return "\n".join(out)


def to_vtt(cues) -> str:
    out = ["WEBVTT\n"]
    for a, b, t in cues:
        out.append(f"{_stamp(a, '.')} --> {_stamp(b, '.')}\n{_plain(t)}\n")
    return "\n".join(out)


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    src = sources[0]
    cues = parse(_read(src))
    if fmt == "vtt":
        text = to_vtt(cues)
    elif fmt == "srt":
        text = to_srt(cues)
    else:
        raise ConversionError(f"Unknown subtitle format: {fmt}")
    Path(long_path(out)).write_text(text, encoding="utf-8", newline="\n")
    back = parse(Path(long_path(out)).read_text(encoding="utf-8"))
    want = [(a, b, _plain(t)) for a, b, t in cues]
    if back != want:
        raise VerificationError("the subtitles changed on the way")
    notes = [f"Checked: {len(cues)} subtitles, every timing kept to the millisecond."]
    if any(_plain(t) != t for _a, _b, t in cues):
        notes.append("Styling that the new format doesn't have (like voice names or positions) was left out.")
    return notes
