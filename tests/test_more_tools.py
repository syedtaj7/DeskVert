"""Video stills, audio trimming and signing a PDF (all light: nothing is re-encoded but the trimmed sound)."""

from __future__ import annotations

import math
import struct
import uuid
import wave
from pathlib import Path

import pytest
from PIL import Image

from app.catalog import offers_for
from app.jobs import build_jobs
from app.settings import Settings
from app.worker import run_job


def run(files, label, options=None, ok=True):
    offers, _ = offers_for(files, Settings())
    offer = next((o for o in offers if o.target.label == label), None)
    assert offer is not None, [o.target.label for o in offers]
    opts = {o.key: o.default for o in offer.options}
    opts.update(options or {})
    job = build_jobs(offer, opts, Settings())[0]
    job["id"] = uuid.uuid4().hex[:12]
    res = run_job(job)
    if ok:
        assert res["ok"], res.get("error")
        res["path"] = Path(res["output"])
    return res


def make_avi(path: Path, w=160, h=120, n=30, fps=10) -> Path:
    """An uncompressed AVI: frame i has a red top half of strength 8*i, a blue bottom half."""
    row = w * 3
    pad = (4 - row % 4) % 4
    size = (row + pad) * h
    frames = []
    for i in range(n):
        top = bytes((0, 0, min(255, i * 8))) * w + b"\0" * pad
        bottom = bytes((200, 40, 0)) * w + b"\0" * pad
        frames.append(bottom * (h // 2) + top * (h - h // 2))  # DIB rows go bottom-up

    def chunk(tag, data):
        return tag + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")

    def lst(tag, data):
        return chunk(b"LIST", tag + data)

    avih = struct.pack("<IIIIIIIIIIIIII", 1000000 // fps, size * fps, 0, 0x10, n, 0, 1, size, w, h, 0, 0, 0, 0)
    strh = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"vids", b"DIB ", 0, 0, 0, 0, 1, fps, 0, n, size, 0xFFFFFFFF, 0,
                       0, 0, w, h)
    strf = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, size, 0, 0, 0, 0)
    hdrl = lst(b"hdrl", chunk(b"avih", avih) + lst(b"strl", chunk(b"strh", strh) + chunk(b"strf", strf)))
    movi = lst(b"movi", b"".join(chunk(b"00db", f) for f in frames))
    idx, off = b"", 4
    for f in frames:
        idx += struct.pack("<4sIII", b"00db", 0x10, off, len(f))
        off += 8 + len(f) + (len(f) % 2)
    body = b"AVI " + hdrl + movi + chunk(b"idx1", idx)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def test_video_still_at_the_moment_you_pick(tmp_path):
    video = make_avi(tmp_path / "Lake.avi")
    still = run([video], "Picture", {"moment": "The middle"})["path"]
    assert still.name == "Lake (frame).jpg"
    with Image.open(still) as im:
        assert im.size == (160, 120)
        r, g, b = im.convert("RGB").getpixel((80, 10))  # the top: frame 15's red is 120
        assert 105 <= r <= 135 and g < 30 and b < 30
        r, g, b = im.convert("RGB").getpixel((80, 110))  # the bottom stays blue: right way up
        assert b > 170 and r < 30


def test_video_frames_sheet(tmp_path):
    sheet = run([make_avi(tmp_path / "Lake.avi")], "Frames sheet")["path"]
    with Image.open(sheet) as im:
        assert im.width > 3 * 160 and im.height > 3 * 120


def test_video_to_gif(tmp_path):
    video = make_avi(tmp_path / "Lake.avi", n=40)  # 4 seconds at 10 pictures a second
    gif = run([video], "GIF", {"start": "0:01", "length": "3 seconds", "size": "Small (320 px wide)"})["path"]
    assert gif.name == "Lake.gif"
    with Image.open(gif) as im:
        assert im.size == (160, 120)  # never bigger than the video itself
        assert im.info.get("loop") == 0
        total = 0
        for i in range(im.n_frames):
            im.seek(i)
            total += im.info["duration"]
        assert 2500 <= total <= 3100  # three seconds
        im.seek(0)
        first = im.convert("RGB").getpixel((80, 10))[0]
        im.seek(im.n_frames - 1)
        last = im.convert("RGB").getpixel((80, 10))[0]
    assert 70 <= first <= 95 and last > first + 150  # from 1 s (red 80) on, getting redder: right moments
    res = run([video], "GIF", {"start": "0:09"}, ok=False)
    assert not res["ok"] and "earlier start" in res["error"]


def test_trim_keeps_only_the_part_you_pick(tmp_path):
    src = tmp_path / "Talk.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 330 * i / 22050)))
                               for i in range(22050 * 6)))
    out = run([src], "Trim", {"start": "0:01", "end": "0:04"})["path"]
    assert out.name == "Talk (trimmed).wav"
    with wave.open(str(out), "rb") as w:
        assert abs(w.getnframes() / w.getframerate() - 3.0) < 0.3
    bad = run([src], "Trim", {"start": "0:05", "end": "0:02"}, ok=False)
    assert not bad["ok"] and "before the end" in bad["error"]


def test_time_typing_is_checked():
    from app.engines.media import parse_time

    assert parse_time("1:15") == 75 and parse_time("90") == 90 and parse_time("1:00:02.5") == 3602.5
    with pytest.raises(ValueError):
        parse_time("soon")


def test_sign_a_pdf(tmp_path):
    import pymupdf

    src = tmp_path / "Lease.pdf"
    d = pymupdf.open()
    for i in range(3):
        d.new_page().insert_text((72, 100), f"Lease agreement page {i + 1}")
    d.save(src)
    d.close()
    out = run([src], "Sign", {"name": "Asha Rao", "pages": "Last page"})["path"]
    assert out.name == "Lease (signed).pdf"
    with pymupdf.open(out) as d:
        texts = [p.get_text() for p in d]
    assert "Signed by Asha Rao" in texts[2] and "Signed by" not in texts[0]
    assert all(f"Lease agreement page {i + 1}" in texts[i] for i in range(3))
    pic = tmp_path / "sig.png"
    Image.new("RGBA", (300, 100), (0, 0, 0, 0)).save(pic)
    out2 = run([src], "Sign", {"name": "Asha Rao", "pages": "Every page", "picture": str(pic)})["path"]
    with pymupdf.open(out2) as d:
        assert all("Signed by Asha Rao" in p.get_text() and p.get_images() for p in d)


def test_rename_makes_tidy_copies_and_keeps_originals(tmp_path):
    import os
    import time as _t

    files = []
    for i, name in enumerate(["IMG_10.jpg", "IMG_2.jpg", "IMG_1.jpg"]):
        p = tmp_path / name
        Image.new("RGB", (20, 20), (i * 60, 0, 0)).save(p)
        stamp = _t.mktime((2026, 11, 1 + i, 9, 0, 0, 0, 0, -1))
        os.utime(p, (stamp, stamp))
        files.append(p)
    res = run(files, "Rename", {"pattern": "Trip {n}", "order": "Name"})
    folder = res["path"]
    assert sorted(f.name for f in folder.iterdir()) == ["Trip 01.jpg", "Trip 02.jpg", "Trip 03.jpg"]
    assert (folder / "Trip 01.jpg").read_bytes() == (tmp_path / "IMG_1.jpg").read_bytes()  # 1, 2, 10 in order
    assert (folder / "Trip 03.jpg").read_bytes() == (tmp_path / "IMG_10.jpg").read_bytes()
    assert all(p.exists() for p in files)  # originals untouched

    from app.engines.rename import plan

    by_date = [n for _, n in plan(files, "{date} {n}", "Date taken")]
    assert by_date == ["2026-11-01 01.jpg", "2026-11-02 02.jpg", "2026-11-03 03.jpg"]


def test_watch_folder_converts_new_files_once(tmp_path):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.watch import FolderWatcher

    folder = tmp_path / "Inbox"
    folder.mkdir()
    old = folder / "old.png"
    Image.new("RGB", (20, 20), "red").save(old)
    import os

    os.utime(old, (0, 1_000_000))  # there long before the watch started
    w = FolderWatcher(Settings())
    got = []
    w.convert.connect(lambda offer, opts, dest: got.append((offer, dest)))
    w.set_rules([{"path": str(folder), "action": "PDF"}, {"path": str(tmp_path / "missing"), "action": "PDF"}])
    new = folder / "new.png"
    Image.new("RGB", (20, 20), "blue").save(new)
    (folder / "half.crdownload").write_bytes(b"still downloading")
    w.scan()  # first look: sizes noted
    assert got == []
    w.scan()  # unchanged: finished arriving
    assert len(got) == 1 and got[0][0].sources == [new] and got[0][0].target.label == "PDF"
    assert got[0][1] == str(folder / "Converted")
    w.scan()
    assert len(got) == 1  # once only


# ---------------------------------------------------------------- a video's sound can end before its picture (#29)

def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _mp4(path: Path, video_s: float, sound_s: float, edit_s: float | None = None, v1: bool = False) -> Path:
    """Just the boxes that say how long each track is (enough for the length check)."""
    def mdhd(scale, seconds):
        if v1:
            return _box(b"mdhd", b"\x01\0\0\0" + b"\0" * 16 + struct.pack(">IQ", scale, round(seconds * scale)) + b"\0" * 4)
        return _box(b"mdhd", b"\0" * 4 + b"\0" * 8 + struct.pack(">II", scale, round(seconds * scale)) + b"\0" * 4)

    def hdlr(kind):
        return _box(b"hdlr", b"\0" * 8 + kind + b"\0" * 12 + b"\0")

    def trak(kind, scale, seconds, edit=None):
        edts = b""
        if edit is not None:
            edts = _box(b"edts", _box(b"elst", b"\0" * 4 + struct.pack(">IIiI", 1, round(edit * 1000), 0, 0x10000)))
        return _box(b"trak", edts + _box(b"mdia", mdhd(scale, seconds) + hdlr(kind)))

    mvhd = _box(b"mvhd", b"\0" * 4 + b"\0" * 8 + struct.pack(">II", 1000, round(video_s * 1000)) + b"\0" * 80)
    moov = _box(b"moov", mvhd + trak(b"vide", 30000, video_s) + trak(b"soun", 48000, sound_s, edit_s))
    path.write_bytes(_box(b"ftyp", b"isom\0\0\0\0isom") + _box(b"mdat", b"\0" * 64) + moov)
    return path


def test_sound_track_length_is_read_from_the_file(tmp_path):
    from app.engines.media import sound_track_seconds

    assert abs(sound_track_seconds(_mp4(tmp_path / "a.mp4", 22.4, 20.6)) - 20.6) < 0.01
    assert abs(sound_track_seconds(_mp4(tmp_path / "b.mov", 22.4, 20.6, v1=True)) - 20.6) < 0.01
    assert abs(sound_track_seconds(_mp4(tmp_path / "c.mp4", 22.4, 20.6, edit_s=20.0)) - 20.0) < 0.01  # edited
    (tmp_path / "d.mp4").write_bytes(b"not a video")
    assert sound_track_seconds(tmp_path / "d.mp4") is None
    assert sound_track_seconds(tmp_path / "e.mkv") is None  # not an MP4-family file


@pytest.mark.parametrize("name, sound, made, ok", [
    ("clip.mp4", 20.6, 20.6, True),    # the issue: sound ends before the picture, all of it is kept
    ("clip.mp4", 22.4, 20.6, False),   # the file says 22.4 s of sound: 20.6 s came out, so something was lost
    ("clip.mkv", None, 20.6, True),    # no length in the file: shorter than the picture is fine...
    ("clip.mkv", None, 23.5, False),   # ...longer never is
])
def test_sound_from_a_video_with_shorter_sound(tmp_path, monkeypatch, name, sound, made, ok):
    from app.engines import media
    from app.errors import VerificationError

    src = _mp4(tmp_path / name, 22.4, sound) if sound else tmp_path / name
    if not src.exists():
        src.write_bytes(b"\0" * 64)

    async def duration(path, video):
        return 22.4 if Path(path).name == name else made

    async def transcode(s, out, fmt, quality, trim=None):
        Path(out).write_bytes(b"\0" * 128)

    monkeypatch.setattr(media, "_duration", duration)
    monkeypatch.setattr(media, "_transcode", transcode)
    out = tmp_path / "clip.mp3"
    if ok:
        notes = media.convert([src], out, "mp3", {})
        assert any("shorter than its picture" in n for n in notes)
    else:
        with pytest.raises(VerificationError):
            media.convert([src], out, "mp3", {})


@pytest.mark.parametrize("kind", ["white noise", "silence"])
@pytest.mark.parametrize("fmt", ["mp3", "m4a"])
def test_any_sound_converts_even_static_or_silence(tmp_path, kind, fmt):
    """Deskvert doesn't judge what the sound is: static, noise or silence is converted like music."""
    import random

    src = tmp_path / f"{kind}.wav"
    rnd = random.Random(7)
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        n = 22050 * 3
        if kind == "silence":
            w.writeframes(b"\0\0" * n)
        else:
            w.writeframes(b"".join(struct.pack("<h", rnd.randint(-20000, 20000)) for _ in range(n)))
    res = run([src], fmt.upper())
    assert res["path"].suffix == f".{fmt}" and res["path"].stat().st_size > 1000
    assert "0:03" in res["notes"][0]
