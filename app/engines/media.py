"""Audio, the light way: Windows' own converter (Media Foundation), no download.

- mp3 / m4a / wma / wav / flac: music and recordings into each other.
- The same targets on a video take only its sound (the picture is never decoded
  or re-encoded, so it stays light).

Video re-encoding (making videos smaller, 720p, WebM, GIF) isn't offered: it's
the heavy kind of work Deskvert keeps off low-end laptops.

Every result is opened again: its length must match the source's.
"""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".wma", ".ogg", ".opus", ".alac", ".m4b", ".aif", ".aiff",
              ".amr", ".3ga"}
VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".avi", ".wmv", ".3gp", ".3g2", ".webm", ".mts", ".m2ts", ".ts",
              ".mpg", ".mpeg", ".flv"}
QUALITY = {"High (192 kbps)": "HIGH", "Medium (128 kbps)": "MEDIUM", "Small (96 kbps)": "LOW"}


def _plain(p: Path) -> str:
    s = str(p)
    return s[4:] if s.startswith("\\\\?\\") else s


async def _duration(path: Path, video: bool) -> float:
    from winrt.windows.storage import StorageFile

    f = await StorageFile.get_file_from_path_async(_plain(path))
    props = await (f.properties.get_video_properties_async() if video else f.properties.get_music_properties_async())
    return props.duration.total_seconds() if hasattr(props.duration, "total_seconds") else float(props.duration) / 1e7


MP4_FAMILY = {".mp4", ".m4v", ".mov", ".3gp", ".3g2", ".m4a", ".m4b"}


def _boxes(f, start: int, end: int):
    """(type, payload start, payload end) of the MP4 boxes between two offsets (big media data is skipped)."""
    import struct

    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        head = f.read(16)
        if len(head) < 8:
            return
        size, kind = struct.unpack(">I4s", head[:8])
        hdr = 8
        if size == 1 and len(head) >= 16:
            size, hdr = struct.unpack(">Q", head[8:16])[0], 16
        elif size == 0:
            size = end - pos
        if size < hdr:
            return
        yield kind.decode("latin-1"), pos + hdr, min(pos + size, end)
        pos += size


def sound_track_seconds(path: Path) -> float | None:
    """How long a video's sound track is, read from the file itself (MP4 / MOV / 3GP), or None.
    A video's sound can end before its picture does; Windows reports the picture's length."""
    import os
    import struct

    if path.suffix.lower() not in MP4_FAMILY:
        return None
    try:
        with open(long_path(path), "rb") as f:
            size = os.fstat(f.fileno()).st_size
            moov = next(((s, e) for k, s, e in _boxes(f, 0, size) if k == "moov"), None)
            if moov is None:
                return None
            movie_scale = 0
            longest = None
            for kind, s, e in _boxes(f, *moov):
                if kind == "mvhd":
                    f.seek(s)
                    v = f.read(1)[0]
                    f.seek(s + (20 if v == 1 else 12))
                    movie_scale = struct.unpack(">I", f.read(4))[0]
                if kind != "trak":
                    continue
                parts = {k: (ps, pe) for k, ps, pe in _boxes(f, s, e)}
                if "mdia" not in parts:
                    continue
                mdia = {k: (ps, pe) for k, ps, pe in _boxes(f, *parts["mdia"])}
                if "hdlr" not in mdia or "mdhd" not in mdia:
                    continue
                f.seek(mdia["hdlr"][0] + 8)
                if f.read(4) != b"soun":
                    continue
                f.seek(mdia["mdhd"][0])
                v = f.read(1)[0]
                if v == 1:
                    f.seek(mdia["mdhd"][0] + 20)
                    scale, dur = struct.unpack(">IQ", f.read(12))
                else:
                    f.seek(mdia["mdhd"][0] + 12)
                    scale, dur = struct.unpack(">II", f.read(8))
                seconds = dur / scale if scale else 0.0
                if "edts" in parts and movie_scale:  # an edit list says which part of the sound is played
                    elst = next(((ps, pe) for k, ps, pe in _boxes(f, *parts["edts"]) if k == "elst"), None)
                    if elst:
                        f.seek(elst[0])
                        ev = f.read(1)[0]
                        f.read(3)
                        (n,) = struct.unpack(">I", f.read(4))
                        played = 0
                        for _ in range(min(n, 1000)):
                            if ev == 1:
                                seg, media_time = struct.unpack(">Qq", f.read(16))
                            else:
                                seg, media_time = struct.unpack(">Ii", f.read(8))
                            f.read(4)
                            if media_time != -1:  # -1: an empty edit (a pause before the sound starts)
                                played += seg
                        if played:
                            seconds = min(seconds, played / movie_scale)
                longest = max(longest or 0.0, seconds)
            return longest if longest else None
    except (OSError, struct.error, IndexError, ValueError):
        return None


def parse_time(text: str) -> float:
    """"1:23", "83", "1:02:03" or "1:23.5" -> seconds. Raises ValueError with a plain message."""
    t = (text or "").strip().replace(",", ".")
    if not t:
        raise ValueError("Type a time, like 0:30 or 1:15.")
    parts = t.split(":")
    if len(parts) > 3 or not all(p.replace(".", "", 1).isdigit() for p in parts):
        raise ValueError("Type a time like 1:15 (minutes:seconds) or 75 (seconds).")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + float(p)
    return secs


async def _transcode(src: Path, out: Path, fmt: str, quality: str, trim: tuple[float, float] | None = None) -> None:
    from winrt.windows.media.mediaproperties import AudioEncodingQuality, MediaEncodingProfile
    from winrt.windows.media.transcoding import MediaTranscoder, TranscodeFailureReason
    from winrt.windows.storage import CreationCollisionOption, StorageFile, StorageFolder

    q = getattr(AudioEncodingQuality, QUALITY.get(quality, "HIGH"))
    make = {"mp3": MediaEncodingProfile.create_mp3, "m4a": MediaEncodingProfile.create_m4a,
            "wma": MediaEncodingProfile.create_wma, "wav": MediaEncodingProfile.create_wav,
            "flac": MediaEncodingProfile.create_flac}[fmt]
    profile = make(q)
    s = await StorageFile.get_file_from_path_async(_plain(src))
    folder = await StorageFolder.get_folder_from_path_async(_plain(out.parent))
    d = await folder.create_file_async(out.name, CreationCollisionOption.REPLACE_EXISTING)
    t = MediaTranscoder()
    if trim is not None:  # keep start..end (Windows takes the end as a time in the recording, not an amount)
        import datetime

        t.trim_start_time = datetime.timedelta(seconds=trim[0])
        t.trim_stop_time = datetime.timedelta(seconds=trim[1])
    prep = await t.prepare_file_transcode_async(s, d, profile)
    if not prep.can_transcode:
        reason = prep.failure_reason
        if reason == TranscodeFailureReason.CODEC_NOT_FOUND:
            raise ConversionError("Windows can't read this file's sound (its codec isn't installed). Files like "
                                  "OGG or Opus need the free “Web Media Extensions” from the Microsoft Store.")
        if reason == TranscodeFailureReason.INVALID_PROFILE:
            raise ConversionError("Windows can't make this kind of file on this PC.")
        raise ConversionError("Windows couldn't read this file; it may be damaged or have no sound.")
    await prep.transcode_async()


def _flac_seconds(path: Path) -> float:
    with open(long_path(path), "rb") as f:
        head = f.read(42)
    if head[:4] != b"fLaC":
        raise VerificationError("the FLAC file is broken")
    x = int.from_bytes(head[18:26], "big")  # STREAMINFO: sample rate (20 bits) ... total samples (36 bits)
    rate, total = x >> 44, x & ((1 << 36) - 1)
    return total / rate if rate else 0.0


def _trim(src: Path, out: Path, opts: dict) -> list[str]:
    """Keep only a part of a recording (same format when Windows can write it, otherwise M4A)."""
    is_video = src.suffix.lower() in VIDEO_EXTS
    fmt = out.suffix.lower().lstrip(".")
    try:
        start = parse_time(str(opts.get("start") or "0"))
        end_text = str(opts.get("end") or "").strip()
        end = parse_time(end_text) if end_text else None
    except ValueError as e:
        raise ConversionError(str(e)) from e
    try:
        total = asyncio.run(_duration(src, is_video))
    except Exception as e:  # noqa: BLE001
        raise ConversionError("Windows can't tell how long this recording is, so it can't be trimmed.") from e
    end = total if end is None else min(end, total)
    if start >= end:
        raise ConversionError(f"The start ({start:.1f} s) must be before the end ({end:.1f} s); the recording is "
                              f"{total:.1f} s long.")
    try:
        asyncio.run(_transcode(src, out, fmt, str(opts.get("quality", "High (192 kbps)")), (start, end)))
    except ConversionError:
        raise
    except OSError as e:
        raise ConversionError(f"Windows couldn't trim this file ({e}).") from e
    if fmt == "wav":
        with wave.open(_plain(out), "rb") as w:
            after = w.getnframes() / float(w.getframerate())
    elif fmt == "flac":
        after = _flac_seconds(out)
    else:
        after = asyncio.run(_duration(out, False))
    want = end - start
    if after <= 0 or abs(after - want) > max(0.35, want * 0.02):
        raise VerificationError(f"the new file is {after:.1f} s long instead of {want:.1f} s")

    def mmss(s: float) -> str:
        m, sec = divmod(s, 60)
        return f"{int(m)}:{sec:04.1f}"
    return [f"Checked: {mmss(after)} kept, from {mmss(start)} to {mmss(end)}."]


TRIM_FORMATS = {"mp3", "m4a", "wma", "wav", "flac"}


def trim_ext(src: Path) -> str:
    e = src.suffix.lower().lstrip(".")
    return f".{e}" if e in TRIM_FORMATS else ".m4a"


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    src = sources[0]
    ext = src.suffix.lower()
    is_video = ext in VIDEO_EXTS
    if fmt == "trim":
        return _trim(src, out, opts)
    if fmt not in ("mp3", "m4a", "wma", "wav", "flac"):
        raise ConversionError(f"Unknown audio format: {fmt}")
    quality = str(opts.get("quality", "High (192 kbps)"))
    try:
        before = asyncio.run(_duration(src, is_video))
    except Exception:  # noqa: BLE001 - some files don't report a length; the result is still checked
        before = 0.0
    try:
        asyncio.run(_transcode(src, out, fmt, quality))
    except ConversionError:
        raise
    except OSError as e:
        raise ConversionError(f"Windows couldn't convert this file ({e}).") from e
    if not Path(long_path(out)).exists() or Path(long_path(out)).stat().st_size < 64:
        raise VerificationError("the new file is empty")
    if fmt == "wav":
        with wave.open(_plain(out), "rb") as w:
            after = w.getnframes() / float(w.getframerate())
    elif fmt == "flac":
        after = _flac_seconds(out)  # Windows' file properties misreport FLAC lengths; read the header itself
    else:
        after = asyncio.run(_duration(out, False))
    if after <= 0:
        raise VerificationError("the new file has no sound")
    tol = max(0.25, before * 0.01)
    video_len = before if is_video else 0.0
    shorter_sound = None
    if is_video and before > 0 and after < before - tol:
        # A video's sound can end before its picture: compare with the sound track itself when the file says how
        # long it is; otherwise sound shorter than the picture is fine, but never longer.
        track = sound_track_seconds(src)
        if track is not None:
            before, tol = track, max(0.25, track * 0.01)
        else:
            shorter_sound = before
            before = 0.0
    if before > 0 and abs(after - before) > tol:
        raise VerificationError(f"the new file is {after:.1f} s long, the original {before:.1f} s")
    if shorter_sound is not None and after > shorter_sound + tol:
        raise VerificationError(f"the new file is {after:.1f} s long, longer than the video ({shorter_sound:.1f} s)")
    mins, secs = divmod(int(round(after)), 60)
    notes = [f"Checked: {mins}:{secs:02d} of sound{', taken from the video' if is_video else ''}."]
    if video_len and after < video_len - max(0.25, video_len * 0.01):
        notes.append(f"The video's sound is shorter than its picture ({after:.1f} s of sound, "
                     f"{video_len:.1f} s of video); all of the sound is here.")
    lossy_src = ext in (".mp3", ".m4a", ".aac", ".wma", ".ogg", ".opus", ".amr", ".3ga") or is_video
    if fmt in ("wav", "flac") and lossy_src:
        notes.append("Lossless formats keep the sound exactly as it is now; they can't bring back quality the "
                     "original had already lost.")
    if fmt in ("mp3", "m4a", "wma"):
        notes.append(f"Quality: {quality}.")
    return notes
