"""A still picture from a video, the light way: Windows' own decoder (Media Foundation).

Only the frames needed are decoded (a jump to the nearest key frame, then forward to the moment
you picked); nothing is re-encoded, so it's quick even on a slow laptop.

- frame: one moment as a JPG (the first frame, a tenth in, the middle, three quarters in).
- sheet: nine moments in a 3 x 3 grid with their times, like a contact sheet.
- gif: a few seconds as a small looping GIF (10 pictures a second), for chats and documents.

The picture is opened again and must have the video's size (or the sheet's).
"""

from __future__ import annotations

import ctypes
import uuid
from ctypes import POINTER, byref, c_int64, c_uint32, c_uint64, c_ulong, c_ushort, c_void_p, wintypes
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

MOMENTS = {"A tenth in": 0.1, "The middle": 0.5, "First frame": 0.0, "Three quarters in": 0.75}


class GUID(ctypes.Structure):
    _fields_ = [("d1", c_ulong), ("d2", c_ushort), ("d3", c_ushort), ("d4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, s: str) -> "GUID":
        u = uuid.UUID(s)
        g = cls()
        ctypes.memmove(byref(g), u.bytes_le, 16)
        return g


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("val", c_int64),
                ("pad", c_int64)]


MF_VERSION = 0x00020070
MF_SOURCE_READER_ENABLE_VIDEO_PROCESSING = GUID.of("fb394f3d-ccf1-42ee-bbb3-f9b845d5681d")
MF_MT_MAJOR_TYPE = GUID.of("48eba18e-f8c9-4687-bf11-0a74c9f96a8f")
MF_MT_SUBTYPE = GUID.of("f7e34c9a-42e8-4714-b74b-cb29d72c35e5")
MF_MT_FRAME_SIZE = GUID.of("1652c33d-d6b2-4012-b834-72030849a37d")
MF_MT_DEFAULT_STRIDE = GUID.of("644b4e48-1e02-4516-b0eb-c01ca9d49ac6")
MF_PD_DURATION = GUID.of("6c990d33-bb8e-477a-8598-0d5d96fcd88a")
MFMediaType_Video = GUID.of("73646976-0000-0010-8000-00aa00389b71")
MFVideoFormat_RGB32 = GUID.of("00000016-0000-0010-8000-00aa00389b71")
GUID_NULL = GUID()
FIRST_VIDEO = 0xFFFFFFFC
ALL_STREAMS = 0xFFFFFFFE
MEDIA_SOURCE = 0xFFFFFFFF
END_OF_STREAM = 0x2
VT_I8, VT_UI8 = 20, 21

HRESULT = ctypes.c_long


def _call(obj: c_void_p, index: int, *args, types=()):
    """Call method number `index` of a COM object (its vtable), raising on failure."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    fn = ctypes.WINFUNCTYPE(HRESULT, c_void_p, *types)(vtbl[index])
    hr = fn(obj, *args)
    if hr < 0:
        raise OSError(hr & 0xFFFFFFFF, f"Media Foundation error 0x{hr & 0xFFFFFFFF:08X}")
    return hr


def _release(obj: c_void_p) -> None:
    if obj:
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])(obj)


# IMFAttributes: GetUINT32 7, GetUINT64 8, SetUINT32 21, SetGUID 24
# IMFSourceReader: SetStreamSelection 4, GetCurrentMediaType 6, SetCurrentMediaType 7,
#                  SetCurrentPosition 8, ReadSample 9, GetPresentationAttribute 12
# IMFSample: ConvertToContiguousBuffer 41;  IMFMediaBuffer: Lock 3, Unlock 4


class Reader:
    """Frames of one video, as RGB pictures, through Media Foundation's source reader."""

    def __init__(self, path: Path):
        self.mfplat = ctypes.WinDLL("mfplat")
        self.mfread = ctypes.WinDLL("mfreadwrite")
        ctypes.windll.ole32.CoInitializeEx(None, 0)
        if self.mfplat.MFStartup(MF_VERSION, 0) < 0:
            raise ConversionError("Windows' video decoder isn't available on this PC.")
        self.reader = c_void_p()
        attrs = c_void_p()
        try:
            self.mfplat.MFCreateAttributes(byref(attrs), 1)
            _call(attrs, 21, byref(MF_SOURCE_READER_ENABLE_VIDEO_PROCESSING), c_uint32(1),
                  types=(c_void_p, c_uint32))
            self.mfread.MFCreateSourceReaderFromURL.argtypes = [wintypes.LPCWSTR, c_void_p, POINTER(c_void_p)]
            hr = self.mfread.MFCreateSourceReaderFromURL(str(path), attrs, byref(self.reader))
            if hr < 0 or not self.reader:
                raise ConversionError("Windows can't open this video (its format may need an extension from the "
                                      "Microsoft Store, like “HEVC Video Extensions” or “Web Media Extensions”).")
        finally:
            _release(attrs)
        _call(self.reader, 4, c_uint32(ALL_STREAMS), c_uint32(0), types=(c_uint32, c_uint32))
        _call(self.reader, 4, c_uint32(FIRST_VIDEO), c_uint32(1), types=(c_uint32, c_uint32))
        mt = c_void_p()
        self.mfplat.MFCreateMediaType(byref(mt))
        try:
            _call(mt, 24, byref(MF_MT_MAJOR_TYPE), byref(MFMediaType_Video), types=(c_void_p, c_void_p))
            _call(mt, 24, byref(MF_MT_SUBTYPE), byref(MFVideoFormat_RGB32), types=(c_void_p, c_void_p))
            try:
                _call(self.reader, 7, c_uint32(FIRST_VIDEO), None, mt, types=(c_uint32, c_void_p, c_void_p))
            except OSError as e:
                raise ConversionError("This file has no picture Windows can decode (it may be sound only, or "
                                      "need a video extension from the Microsoft Store).") from e
        finally:
            _release(mt)
        cur = c_void_p()
        _call(self.reader, 6, c_uint32(FIRST_VIDEO), byref(cur), types=(c_uint32, POINTER(c_void_p)))
        try:
            size = c_uint64()
            _call(cur, 8, byref(MF_MT_FRAME_SIZE), byref(size), types=(c_void_p, POINTER(c_uint64)))
            self.width, self.height = size.value >> 32, size.value & 0xFFFFFFFF
            stride = c_uint32()
            try:
                _call(cur, 7, byref(MF_MT_DEFAULT_STRIDE), byref(stride), types=(c_void_p, POINTER(c_uint32)))
                self.stride = ctypes.c_int32(stride.value).value
            except OSError:
                self.stride = self.width * 4
        finally:
            _release(cur)
        pv = PROPVARIANT()
        try:
            _call(self.reader, 12, c_uint32(MEDIA_SOURCE), byref(MF_PD_DURATION), byref(pv),
                  types=(c_uint32, c_void_p, c_void_p))
            self.duration = pv.val / 1e7 if pv.vt in (VT_UI8, VT_I8) else 0.0
        except OSError:
            self.duration = 0.0

    def frame(self, seconds: float):
        """The picture shown at `seconds` (a PIL image)."""
        from PIL import Image

        target = int(max(0.0, seconds) * 1e7)
        pv = PROPVARIANT()
        pv.vt, pv.val = VT_I8, target
        _call(self.reader, 8, byref(GUID_NULL), byref(pv), types=(c_void_p, c_void_p))
        last = None
        for _ in range(900):  # from the key frame before it, forward to the moment (never a long walk)
            index, flags, stamp, sample = c_uint32(), c_uint32(), c_int64(), c_void_p()
            _call(self.reader, 9, c_uint32(FIRST_VIDEO), c_uint32(0), byref(index), byref(flags), byref(stamp),
                  byref(sample), types=(c_uint32, c_uint32, c_void_p, c_void_p, c_void_p, c_void_p))
            if sample:
                if last:
                    _release(last)
                last = sample
                if stamp.value + 400000 >= target:  # within 40 ms of the moment
                    break
            if flags.value & END_OF_STREAM:
                break
        if not last:
            raise ConversionError("No picture could be read at that moment of the video.")
        try:
            return self._picture(last)
        finally:
            _release(last)

    def _picture(self, sample):
        """A decoded sample as a PIL image (the sample itself is released by the caller)."""
        from PIL import Image

        buf = c_void_p()
        _call(sample, 41, byref(buf), types=(POINTER(c_void_p),))
        try:
            ptr, maxlen, curlen = c_void_p(), c_uint32(), c_uint32()
            _call(buf, 3, byref(ptr), byref(maxlen), byref(curlen), types=(c_void_p, c_void_p, c_void_p))
            try:
                raw = ctypes.string_at(ptr, curlen.value)
            finally:
                _call(buf, 4)
        finally:
            _release(buf)
        stride = abs(self.stride) or self.width * 4
        if len(raw) < stride * self.height:
            raise ConversionError("Windows returned an incomplete picture for this video.")
        img = Image.frombuffer("RGB", (self.width, self.height), raw, "raw", "BGRX", stride, -1 if self.stride < 0 else 1)
        return img.copy()

    def frames(self, start: float, seconds: float, fps: float):
        """(time, picture) every 1/fps seconds from `start` for `seconds`, read in order: one jump to the key
        frame before `start`, then forward. Only this stretch of the video is decoded."""
        pv = PROPVARIANT()
        pv.vt, pv.val = VT_I8, int(max(0.0, start) * 1e7)
        _call(self.reader, 8, byref(GUID_NULL), byref(pv), types=(c_void_p, c_void_p))
        step, want, end = 1.0 / fps, max(0.0, start), start + seconds
        for _ in range(int((seconds + 30) * 120)):  # never an endless walk, even for odd files
            index, flags, stamp, sample = c_uint32(), c_uint32(), c_int64(), c_void_p()
            _call(self.reader, 9, c_uint32(FIRST_VIDEO), c_uint32(0), byref(index), byref(flags), byref(stamp),
                  byref(sample), types=(c_uint32, c_uint32, c_void_p, c_void_p, c_void_p, c_void_p))
            if sample:
                t = stamp.value / 1e7
                try:
                    if t >= end:
                        break
                    if t + 0.02 >= want:
                        yield t, self._picture(sample)
                        while want <= t + 0.02:
                            want += step
                finally:
                    _release(sample)
            if flags.value & END_OF_STREAM:
                break

    def close(self):
        _release(self.reader)
        self.reader = c_void_p()
        self.mfplat.MFShutdown()


def _stamp(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _sheet(reader: Reader):
    from PIL import Image, ImageDraw, ImageFont

    n, cols = 9, 3
    cell_w = min(480, reader.width)
    cell_h = max(1, round(cell_w * reader.height / reader.width))
    gap, pad = 8, 12
    sheet = Image.new("RGB", (cols * cell_w + (cols - 1) * gap + 2 * pad, 3 * cell_h + 2 * gap + 2 * pad),
                      (24, 24, 28))
    try:
        font = ImageFont.truetype("segoeuib.ttf", max(12, cell_w // 22))
    except OSError:
        font = ImageFont.load_default()
    span = reader.duration or 0.0
    for i in range(n):
        at = span * (i + 0.5) / n if span else 0.0
        frame = reader.frame(at).resize((cell_w, cell_h))
        x = pad + (i % cols) * (cell_w + gap)
        y = pad + (i // cols) * (cell_h + gap)
        sheet.paste(frame, (x, y))
        d = ImageDraw.Draw(sheet)
        label = _stamp(at)
        box = d.textbbox((0, 0), label, font=font)
        w, h = box[2] - box[0] + 12, box[3] - box[1] + 8
        d.rounded_rectangle((x + 8, y + cell_h - h - 8, x + 8 + w, y + cell_h - 8), 5, fill=(0, 0, 0))
        d.text((x + 14, y + cell_h - h - 8 + 3 - box[1]), label, fill=(255, 255, 255), font=font)
    return sheet


GIF_FPS = 10
GIF_LENGTHS = {"3 seconds": 3.0, "5 seconds": 5.0, "10 seconds": 10.0}
GIF_SIZES = {"Small (320 px wide)": 320, "Medium (480 px wide)": 480, "Large (640 px wide)": 640}


def _gif(reader: Reader, out: Path, opts: dict) -> list[str]:
    """A short looping GIF of a stretch of the video: 10 pictures a second, made smaller first."""
    from PIL import Image

    from .media import parse_time

    try:
        start = parse_time(str(opts.get("start") or "0:00"))
    except ValueError as e:
        raise ConversionError(str(e)) from e
    length = GIF_LENGTHS.get(str(opts.get("length", "5 seconds")), 5.0)
    width = min(GIF_SIZES.get(str(opts.get("size", "Medium (480 px wide)")), 480), reader.width)
    if reader.duration and start >= reader.duration - 0.05:
        raise ConversionError(f"The video is only {_stamp(reader.duration)} long: pick an earlier start.")
    if reader.duration:
        length = min(length, reader.duration - start)
    height = max(2, round(width * reader.height / reader.width))
    pictures = []
    for _t, frame in reader.frames(start, length, GIF_FPS):
        pictures.append(frame.resize((width, height), Image.LANCZOS))
        if len(pictures) >= max(1, round(length * GIF_FPS)):
            break
    if not pictures:
        raise ConversionError("No pictures could be read from that part of the video.")
    # one shared palette from a few moments keeps the colours steady from picture to picture
    picks = pictures[:: max(1, len(pictures) // 4)][:4]
    probe = Image.new("RGB", (width, height * len(picks)))
    for i, pic in enumerate(picks):
        probe.paste(pic, (0, i * height))
    palette = probe.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    frames = [p.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG) for p in pictures]
    frames[0].save(long_path(out), "GIF", save_all=True, append_images=frames[1:], duration=int(1000 / GIF_FPS),
                   loop=0, optimize=False, disposal=1)
    with Image.open(long_path(out)) as back:  # identical pictures in a row are stored once, shown longer
        total = 0
        for i in range(getattr(back, "n_frames", 1)):
            back.seek(i)
            total += back.info.get("duration", 0)
        if back.size != (width, height) or abs(total - len(frames) * 1000 / GIF_FPS) > 1000 / GIF_FPS:
            raise VerificationError("the GIF came out with the wrong size or length")
    size_kb = Path(long_path(out)).stat().st_size // 1024
    secs = len(frames) / GIF_FPS
    return [f"Checked: {secs:.1f} seconds from {_stamp(start)}, {len(frames)} pictures, {width}×{height} px, "
            f"{size_kb:,} KB. It loops, with no sound (GIFs have none).",
            "Only this part of the video was decoded; the video itself wasn't touched."]


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    from PIL import Image

    src = Path(long_path(sources[0]))
    reader = Reader(src)
    try:
        if fmt == "frame":
            moment = str(opts.get("moment", "A tenth in"))
            at = reader.duration * MOMENTS.get(moment, 0.1)
            img = reader.frame(at)
            note = f"The picture at {_stamp(at)}, {reader.width}×{reader.height} px (the video's own size)."
            want = (reader.width, reader.height)
        elif fmt == "sheet":
            img = _sheet(reader)
            note = f"Nine moments across {_stamp(reader.duration)}, each with its time."
            want = img.size
        elif fmt == "gif":
            return _gif(reader, out, opts)
        else:
            raise ConversionError(f"Unknown video picture: {fmt}")
    finally:
        reader.close()
    if img.convert("L").getextrema()[1] < 8 and fmt == "frame":
        note += " This moment is black; try another one."
    img.save(long_path(out), "JPEG", quality=92, optimize=True)
    with Image.open(long_path(out)) as back:
        back.load()
        if back.size != want:
            raise VerificationError("the picture came out the wrong size")
    return [f"Checked: {note}", "Only the frames needed were decoded; the video wasn't re-encoded."]
