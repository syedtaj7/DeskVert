"""Damaged or hostile files and pages, and settings that must never hold a password (found in a code review of
1.16.0)."""

from __future__ import annotations

import struct
import time
import zlib
from pathlib import Path

import pytest

from app.errors import ConversionError


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------- Kindle books

def test_kindle_extra_info_with_a_huge_count_and_an_empty_entry_stops_at_once():
    from app.engines.kindle import _exth

    header_len = 0xE8
    rec0 = bytearray(16 + header_len)
    rec0 += b"EXTH" + struct.pack(">II", 12 + 8, 0xFFFFFFFF)  # "4 billion entries"
    rec0 += struct.pack(">II", 503, 0)  # ... the first of which says it's 0 bytes long
    start = time.monotonic()
    out = _exth(bytes(rec0), header_len)
    assert time.monotonic() - start < 1 and sum(len(v) for v in out.values()) <= 1


# ---------------------------------------------------------------- SCC captions

def _scc_word(b1: int, b2: int) -> str:
    odd = lambda b: b | (0x80 if bin(b).count("1") % 2 == 0 else 0)  # noqa: E731 - each byte has odd parity
    return f"{odd(b1):02x}{odd(b2):02x}"


def _scc_text(s: str) -> list[str]:
    s = s + ("\0" if len(s) % 2 else "")
    return [_scc_word(ord(s[i]), ord(s[i + 1]) if s[i + 1] != "\0" else 0) for i in range(0, len(s), 2)]


def _scc(body: list[tuple[str, list[str]]]) -> str:
    lines = ["Scenarist_SCC V1.0", ""]
    for tc, words in body:
        lines += [f"{tc}\t{' '.join(words)}", ""]
    return "\n".join(lines)


def twice(c):
    return [_scc_word(*c), _scc_word(*c)]  # commands are sent twice


RDC, RU2, CR, EDM, PAC15 = (0x14, 0x29), (0x14, 0x25), (0x14, 0x2D), (0x14, 0x2C), (0x14, 0x70)


def test_scc_paint_on_captions_are_kept():
    from app.engines.scc import read_scc

    cues = read_scc(_scc([
        ("00:00:02:00", twice(RDC) + twice(PAC15) + _scc_text("Painted words")),
        ("00:00:05:00", twice(EDM)),
    ]))
    assert [c[2] for c in cues] == ["Painted words"]
    assert 1900 < cues[0][0] < 2400 and 4900 < cues[0][1] < 5300


def test_scc_roll_up_keeps_the_last_line_before_the_screen_clears():
    from app.engines.scc import read_scc

    cues = read_scc(_scc([
        ("00:00:10:00", twice(RU2) + _scc_text("FIRST LINE") + twice(CR)),
        ("00:00:12:00", _scc_text("LAST LINE")),
        ("00:00:15:00", twice(EDM)),
    ]))
    assert any("LAST LINE" in c[2] for c in cues)
    assert 14900 < cues[-1][1] < 15300  # shown until the erase, not dropped


# ---------------------------------------------------------------- fonts

def _woff(tag: bytes, packed: bytes, says_orig: int) -> bytes:
    head = struct.pack(">4s4sIHHIHHIIIII", b"wOFF", b"\x00\x01\x00\x00", 64 + len(packed), 1, 0, says_orig, 1, 0,
                       0, 0, 0, 0, 0)
    return head + struct.pack(">4sIIII", tag, 64, len(packed), says_orig, 0) + packed


def test_woff_table_that_swells_past_what_it_says_is_refused():
    from app.engines.font import _woff_tables

    bomb = zlib.compress(b"\0" * (20 * 1024 * 1024), 9)  # 20 MB of zeros in ~20 KB
    with pytest.raises(ConversionError, match="damaged"):
        _woff_tables(_woff(b"glyf", bomb, says_orig=len(bomb) + 100))


def test_woff_and_woff2_that_claim_an_impossible_size_are_refused():
    from app.engines.font import MAX_FONT_BYTES, _woff_tables, woff2_to_sfnt

    with pytest.raises(ConversionError, match="bigger than any real font"):
        _woff_tables(_woff(b"glyf", zlib.compress(b"x"), says_orig=MAX_FONT_BYTES + 1))
    woff2 = bytearray(48)
    woff2[0:4] = b"wOF2"
    struct.pack_into(">I", woff2, 16, MAX_FONT_BYTES + 1)
    with pytest.raises(ConversionError, match="bigger than any real font"):
        woff2_to_sfnt(bytes(woff2))


def test_a_damaged_font_name_never_fails_the_conversion():
    from app.engines.font import _name

    assert _name({b"name": b"\x00\x00\x00\x05\x00"}, 4) == ""  # says 5 names, holds none


# ---------------------------------------------------------------- web pages

def test_article_never_takes_this_pcs_files_or_scripts():
    from app.engines.webextra import article

    words = "<p>" + "Plenty of real article text goes here, sentence after sentence. " * 40 + "</p>"
    page = (f"<html><head><title>Story</title></head><body><article><h1>Story</h1>{words}"
            '<img src="file:///C:/Users/someone/secret.png"><img src="pics/ok.jpg">'
            '<a href=" JavaScript:alert(1)">bad</a><a href="FILE:///C:/x.txt">local</a>'
            f'<a href="/next">next</a>{words}</article></body></html>')
    body = article(page, "https://news.example.org/story")[1].lower()
    assert "file:" not in body and "javascript:" not in body
    assert "https://news.example.org/pics/ok.jpg" in body and "https://news.example.org/next" in body


def test_odd_picture_sizes_from_a_page_dont_break_anything():
    from app.engines.webextra import _best_from_srcset

    best, _w = _best_from_srcset("a.jpg ..w, b.jpg 800w, c.jpg .5x", "https://x.example/")
    assert best == "https://x.example/b.jpg"


def test_picture_names_windows_keeps_for_devices_are_renamed():
    from app.engines.webextra import _name_for

    used: set[str] = set()
    assert _name_for("https://x.example/nul.jpg", ".jpg", used) == "picture nul.jpg"
    assert _name_for("https://x.example/COM1", ".png", used) == "picture COM1.png"
    assert _name_for("https://x.example/console.png", ".png", used) == "console.png"


# ---------------------------------------------------------------- DWG, history, "always do this"

def test_the_newest_oda_converter_is_used(tmp_path, monkeypatch):
    from app.engines import oda

    for v in ("25.9.0", "25.12.0", "24.10.0"):
        d = tmp_path / "ODA" / f"ODAFileConverter {v}"
        d.mkdir(parents=True)
        (d / "ODAFileConverter.exe").write_bytes(b"MZ")
    monkeypatch.delenv("DESKVERT_ODA", raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", "")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "none"))
    assert "25.12.0" in oda.find_oda()


def test_a_damaged_history_file_is_read_safely(tmp_path, monkeypatch):
    import json

    from app import history

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    history.path().write_text(json.dumps([
        {"time": "yesterday", "outputs": ["a.jpg"]},
        {"time": 1.0, "outputs": [3]},
        {"time": 1.0, "outputs": ["b.jpg"], "sources": "b.heic"},
        {"time": 2.0, "label": "JPG", "outputs": ["c.jpg"], "sources": ["c.heic"], "failed": 0},
    ]), encoding="utf-8")
    assert [e["outputs"] for e in history.load()] == [["c.jpg"]]


def test_history_never_stops_a_conversion_when_its_folder_cant_be_made(monkeypatch):
    from app import history

    def broken():
        raise PermissionError("no")

    monkeypatch.setattr(history, "path", broken)
    history.add("JPG", ["a.heic"], ["a.jpg"])  # nothing raised


def test_password_tools_are_never_offered_as_always(qapp, tmp_path):
    from types import SimpleNamespace

    from app.jobs import Batch
    from app.main import Controller
    from app.settings import Settings
    from app.ui.panels import ProgressPanel

    a = tmp_path / "a.pdf"
    a.write_bytes(b"%PDF-1.4")
    panel = ProgressPanel()
    fake = SimpleNamespace(settings=Settings(), panel=panel, _one_kind=Controller._one_kind)
    action = {"key": "pdf.lock", "target": "pdf.lock", "label": "add password", "options": {"password": "hunter22"},
              "auto": False, "secret": True, "files": [str(a)]}
    ok = [{"ok": True, "output": str(tmp_path / "a (locked).pdf"), "sources": [str(a)]}]
    Controller._offer_always(fake, Batch("add password", [], action=action), ok)
    assert panel.extra_btn.isHidden() or "Always" not in panel.extra_btn.text()


def test_a_saved_rule_with_a_password_is_dropped(tmp_path, monkeypatch):
    import json

    from app.settings import Settings

    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = Settings.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"settings_version": 3, "always": {
        ".pdf": {"key": "pdf.lock", "target": "pdf.lock", "label": "add password", "options": {"password": "x1234"}},
        ".heic": {"key": "image.jpg", "target": "image.jpg", "label": "JPG", "options": {"quality": 90}},
    }}), encoding="utf-8")
    s = Settings.load()
    assert list(s.always) == [".heic"]
    assert "x1234" not in Path(p).read_text(encoding="utf-8")
