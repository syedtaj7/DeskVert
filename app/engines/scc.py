"""Scenarist SCC closed captions (CEA-608, the TV caption format), read into subtitles.

An SCC file is a list of timecodes, each followed by caption bytes in hex. The bytes are commands for a
caption decoder: load a caption off screen and show it at once (pop-on), let lines roll up, or paint them
on as they arrive. This plays those commands and notes what was on screen from when to when, which is
exactly what a subtitle file stores. Positions and colours aren't kept; italics are.

Times: SCC counts frames at 29.97 a second; ";" timecodes are drop-frame (they match the clock),
":" ones are not (they drift by 3.6 s an hour, as the format defines).
"""

from __future__ import annotations

import re

from ..errors import ConversionError

FPS = 30000 / 1001
LINE_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})([:;.,])(\d{2})\s+((?:[0-9a-fA-F]{4}\s*)+)$")

# the basic character set differs from ASCII in a few places
BASIC = {0x2A: "á", 0x5C: "é", 0x5E: "í", 0x5F: "ó", 0x60: "ú", 0x7B: "ç", 0x7C: "÷", 0x7D: "Ñ", 0x7E: "ñ",
         0x7F: "█"}
SPECIAL = "®°½¿™¢£♪à èâêîôû"  # 0x11 0x30-0x3F
EXTENDED_12 = "ÁÉÓÚÜü‘¡*'—©℠•“”ÀÂÇÈÊËëÎÏïÔÙùÛ«»"  # 0x12 0x20-0x3F
EXTENDED_13 = "ÃãÍÌìÒòÕõ{}\\^_|~ÄäÖöß¥¤│ÅåØø┌┐└┘"  # 0x13 0x20-0x3F


def _frames(h: int, m: int, s: int, f: int, drop: bool) -> int:
    total = ((h * 60 + m) * 60 + s) * 30 + f
    if drop:  # two frame numbers are skipped every minute, except every tenth
        minutes = h * 60 + m
        total -= 2 * (minutes - minutes // 10)
    return total


def _char(b: int) -> str:
    return BASIC.get(b, chr(b)) if 0x20 <= b <= 0x7F else ""


class _Screen:
    """Caption memory: what's being loaded (pop-on) and what's shown, as rows of text."""

    def __init__(self):
        self.mode = "pop"  # pop | roll | paint
        self.rows = 2
        self.loading: dict[int, str] = {}
        self.shown: dict[int, str] = {}
        self.row = 15
        self.italic = False

    def target(self) -> dict[int, str]:
        return self.loading if self.mode == "pop" else self.shown

    def put(self, text: str) -> None:
        mem = self.target()
        mem[self.row] = mem.get(self.row, "") + text

    def back(self) -> None:
        mem = self.target()
        if mem.get(self.row):
            mem[self.row] = mem[self.row][:-1]

    def text(self) -> str:
        return "\n".join(t.strip() for _r, t in sorted(self.shown.items()) if t.strip())


def read_scc(text: str) -> list[tuple[int, int, str]]:
    if not text.lstrip().startswith("Scenarist_SCC"):
        raise ConversionError("This isn't a Scenarist SCC caption file (its first line should say Scenarist_SCC).")
    scr = _Screen()
    cues: list[tuple[int, int, str]] = []
    on_screen = ("", 0)  # (text, since when, in ms)

    def changed(at_ms: int) -> None:
        nonlocal on_screen
        now = scr.text()
        if now == on_screen[0]:
            return
        if on_screen[0] and at_ms > on_screen[1]:
            cues.append((on_screen[1], at_ms, on_screen[0]))
        on_screen = (now, at_ms)

    last_control = None
    last_ms = 0
    for line in text.splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        h, mi, s, sep, f, words = m.groups()
        start = _frames(int(h), int(mi), int(s), int(f), sep in ";,")
        for k, word in enumerate(words.split()):
            ms = round((start + k) / FPS * 1000)
            last_ms = ms
            b1, b2 = int(word[:2], 16) & 0x7F, int(word[2:], 16) & 0x7F
            if b1 == 0 and b2 == 0:
                last_control = None
                continue
            if 0x10 <= b1 <= 0x1F:  # a command (sent twice for safety: the copy is skipped)
                code = (b1, b2)
                if code == last_control:
                    last_control = None
                    continue
                last_control = code
                ch = b1 & 0x17  # caption channel 1 and 2 use the same commands
                if ch == 0x14 and b2 == 0x20:  # resume caption loading: pop-on
                    scr.mode = "pop"
                elif ch == 0x14 and b2 in (0x25, 0x26, 0x27):  # roll-up, 2 to 4 rows
                    scr.mode, scr.rows = "roll", b2 - 0x23
                elif ch == 0x14 and b2 == 0x29:  # resume direct captioning: paint-on
                    scr.mode = "paint"
                elif ch == 0x14 and b2 == 0x2C:  # erase what's shown
                    scr.shown = {}
                    changed(ms)
                elif ch == 0x14 and b2 == 0x2E:  # erase what's being loaded
                    scr.loading = {}
                elif ch == 0x14 and b2 == 0x2F:  # end of caption: show what was loaded
                    scr.shown, scr.loading = scr.loading, scr.shown
                    changed(ms)
                elif ch == 0x14 and b2 == 0x2D:  # carriage return: roll the lines up
                    if scr.mode == "roll":
                        changed(ms)
                        rows = sorted(scr.shown)
                        scr.shown = {r - 1: scr.shown[r] for r in rows[-(scr.rows - 1):]} if scr.rows > 1 else {}
                        scr.shown[scr.row] = ""
                elif ch == 0x14 and b2 == 0x21:  # backspace
                    scr.back()
                elif ch == 0x11 and 0x30 <= b2 <= 0x3F:  # special character
                    scr.put(SPECIAL[b2 - 0x30])
                elif ch in (0x12, 0x13) and 0x20 <= b2 <= 0x3F:  # extended character: replaces the one before
                    scr.back()
                    scr.put((EXTENDED_12 if ch == 0x12 else EXTENDED_13)[b2 - 0x20])
                elif ch == 0x11 and 0x20 <= b2 <= 0x2F:  # mid-row style change: shown as a space
                    if scr.target().get(scr.row, "")[-1:] not in ("", " "):
                        scr.put(" ")
                elif 0x40 <= b2 <= 0x7F:  # preamble: which row the next text goes on
                    rows = [11, 1, 3, 12, 14, 5, 7, 9]
                    base = rows[b1 & 0x07] if (b1 & 0x07) < len(rows) else 15
                    row = base + (1 if b2 & 0x20 else 0)
                    if scr.mode == "roll":
                        row = scr.row  # roll-up text always goes on the bottom row
                    scr.row = row
                    if scr.target().get(row):
                        scr.put(" ")
                continue
            last_control = None
            scr.put(_char(b1) + _char(b2))  # roll-up and paint-on lines count once complete (carriage return)
    changed(last_ms)
    if on_screen[0]:  # a caption still showing when the file ends: 4 s more
        cues.append((on_screen[1], max(last_ms, on_screen[1]) + 4000, on_screen[0]))
    cues = [(a, b, t) for a, b, t in cues if t.strip() and b > a]
    if not cues:
        raise ConversionError("No captions were found in this SCC file.")
    return cues
