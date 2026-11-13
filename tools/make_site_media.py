"""Makes the website's animations: the app's own gallery stories (and the tour's Explorer demo), rendered
frame by frame with Qt and encoded as MP4 (H.264) with Windows' own encoder (Media Foundation), plus a
still JPG of each to show at once while the video loads (and for people who prefer less motion).

    python tools/make_site_media.py                 # everything
    python tools/make_site_media.py web_drag demo   # just these

Videos are played by the graphics chip, start while still downloading, and are a fraction of the size of
animated images at a smoother 30 frames a second. Output: website/assets/media/<name>-<dark|light>.mp4/.jpg
"""

from __future__ import annotations

import ctypes
import io
import os
import sys
import time
import uuid
from ctypes import POINTER, byref, c_int64, c_uint32, c_uint64, c_ulong, c_ushort, c_void_p, wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "website" / "assets" / "media"

STORIES = ["web_drag", "web_table", "web_clip", "web_page", "web_qr", "web_cloud", "web_copied", "web_reader",
           "web_pictures", "pdf_compress", "img_convert", "ocr", "pdf_merge", "pdf_protect", "audio", "video_frame",
           "audio_trim", "pdf_sign", "msg", "rename", "watch", "office_pdf", "libre", "zip"]
BIG = {"web_drag"}  # shown large on the page: rendered larger
FPS = 30
LOOP = 5.0


# ---------------------------------------------------------------- H.264 through Media Foundation's sink writer

class GUID(ctypes.Structure):
    _fields_ = [("d1", c_ulong), ("d2", c_ushort), ("d3", c_ushort), ("d4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, s: str) -> "GUID":
        g = cls()
        ctypes.memmove(byref(g), uuid.UUID(s).bytes_le, 16)
        return g


MT_MAJOR = GUID.of("48eba18e-f8c9-4687-bf11-0a74c9f96a8f")
MT_SUBTYPE = GUID.of("f7e34c9a-42e8-4714-b74b-cb29d72c35e5")
MT_BITRATE = GUID.of("20332624-fb0d-4d9e-bd0d-cbf6786c102e")
MT_INTERLACE = GUID.of("e2724bb8-e676-4806-b4b2-a8d6efb44ccd")
MT_FRAME_SIZE = GUID.of("1652c33d-d6b2-4012-b834-72030849a37d")
MT_FRAME_RATE = GUID.of("c459a2e8-3d2c-4e44-b132-fee5156c7bb0")
MT_PIXEL_ASPECT = GUID.of("c6376a1e-8d0a-4027-be45-6d9a0ad39bb6")
MT_STRIDE = GUID.of("644b4e48-1e02-4516-b0eb-c01ca9d49ac6")
MT_PROFILE = GUID.of("ad76a80b-2d5c-4e0b-b375-64e520137036")
VIDEO = GUID.of("73646976-0000-0010-8000-00aa00389b71")
H264 = GUID.of("34363248-0000-0010-8000-00aa00389b71")
RGB32 = GUID.of("00000016-0000-0010-8000-00aa00389b71")
HRESULT = ctypes.c_long


def _call(obj, index, *args, types=()):
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    hr = ctypes.WINFUNCTYPE(HRESULT, c_void_p, *types)(vtbl[index])(obj, *args)
    if hr < 0:
        raise OSError(f"Media Foundation error 0x{hr & 0xFFFFFFFF:08X} (method {index})")
    return hr


def _release(obj):
    if obj:
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])(obj)


def _set_u32(a, key, v):
    _call(a, 21, byref(key), c_uint32(v), types=(c_void_p, c_uint32))


def _set_u64(a, key, hi, lo):
    _call(a, 22, byref(key), c_uint64((hi << 32) | lo), types=(c_void_p, c_uint64))


def _set_guid(a, key, g):
    _call(a, 24, byref(key), byref(g), types=(c_void_p, c_void_p))


class Mp4Writer:
    """Frames (RGBA bytes, top row first) in, an H.264 MP4 out."""

    def __init__(self, path: Path, w: int, h: int, fps: int, kbps: int):
        self.w, self.h, self.fps = w, h, fps
        self.plat = ctypes.WinDLL("mfplat")
        rw = ctypes.WinDLL("mfreadwrite")
        ctypes.windll.ole32.CoInitializeEx(None, 0)
        self.plat.MFStartup(0x00020070, 0)
        attrs = c_void_p()
        self.plat.MFCreateAttributes(byref(attrs), 1)
        self.sink = c_void_p()
        # A read-write file: putting the index first means the writer reads the file back when it finishes.
        self.stream_file = c_void_p()
        self.plat.MFCreateFile.argtypes = [c_uint32, c_uint32, c_uint32, wintypes.LPCWSTR, POINTER(c_void_p)]
        hr = self.plat.MFCreateFile(3, 4, 0, str(path), byref(self.stream_file))  # READWRITE, DELETE_IF_EXIST
        if hr < 0:
            raise OSError(f"can't create {path} (0x{hr & 0xFFFFFFFF:08X})")
        rw.MFCreateSinkWriterFromURL.argtypes = [wintypes.LPCWSTR, c_void_p, c_void_p, POINTER(c_void_p)]
        hr = rw.MFCreateSinkWriterFromURL(str(path), self.stream_file, attrs, byref(self.sink))
        _release(attrs)
        if hr < 0:
            raise OSError(f"can't create {path} (0x{hr & 0xFFFFFFFF:08X})")
        out = c_void_p()
        self.plat.MFCreateMediaType(byref(out))
        _set_guid(out, MT_MAJOR, VIDEO)
        _set_guid(out, MT_SUBTYPE, H264)
        _set_u32(out, MT_BITRATE, kbps * 1000)
        _set_u32(out, MT_INTERLACE, 2)  # progressive
        _set_u32(out, MT_PROFILE, 100)  # High
        _set_u64(out, MT_FRAME_SIZE, w, h)
        _set_u64(out, MT_FRAME_RATE, fps, 1)
        _set_u64(out, MT_PIXEL_ASPECT, 1, 1)
        self.stream = c_uint32()
        _call(self.sink, 3, out, byref(self.stream), types=(c_void_p, POINTER(c_uint32)))  # AddStream
        _release(out)
        inp = c_void_p()
        self.plat.MFCreateMediaType(byref(inp))
        _set_guid(inp, MT_MAJOR, VIDEO)
        _set_guid(inp, MT_SUBTYPE, RGB32)
        _set_u32(inp, MT_INTERLACE, 2)
        _set_u32(inp, MT_STRIDE, w * 4)  # positive: the top row comes first
        _set_u64(inp, MT_FRAME_SIZE, w, h)
        _set_u64(inp, MT_FRAME_RATE, fps, 1)
        _set_u64(inp, MT_PIXEL_ASPECT, 1, 1)
        _call(self.sink, 4, self.stream, inp, None, types=(c_uint32, c_void_p, c_void_p))  # SetInputMediaType
        _release(inp)
        _call(self.sink, 5)  # BeginWriting
        self.n = 0

    def write(self, bgra: bytes) -> None:
        size = self.w * self.h * 4
        buf = c_void_p()
        self.plat.MFCreateMemoryBuffer(c_uint32(size), byref(buf))
        ptr = c_void_p()
        _call(buf, 3, byref(ptr), None, None, types=(c_void_p, c_void_p, c_void_p))
        ctypes.memmove(ptr, bgra, size)
        _call(buf, 4)
        _call(buf, 6, c_uint32(size), types=(c_uint32,))
        sample = c_void_p()
        self.plat.MFCreateSample(byref(sample))
        _call(sample, 42, buf, types=(c_void_p,))
        dur = int(10_000_000 / self.fps)
        _call(sample, 36, c_int64(self.n * dur), types=(c_int64,))
        _call(sample, 38, c_int64(dur), types=(c_int64,))
        _call(self.sink, 6, self.stream, sample, types=(c_uint32, c_void_p))  # WriteSample
        _release(sample)
        _release(buf)
        self.n += 1

    def close(self) -> None:
        _call(self.sink, 11)  # Finalize
        _release(self.sink)
        _release(self.stream_file)  # the writer has closed it already
        self.plat.MFShutdown()


def faststart(path: Path) -> None:
    """Move the MP4's index (moov) in front of the media data, so browsers can play while it downloads.
    (Windows' own "index first" option made unplayable files here, so this is done afterwards.)"""
    import struct

    data = path.read_bytes()
    boxes, i = [], 0
    while i < len(data):
        size, kind = struct.unpack(">I4s", data[i:i + 8])
        head = 8
        if size == 1:
            size, head = struct.unpack(">Q", data[i + 8:i + 16])[0], 16
        elif size == 0:
            size = len(data) - i
        boxes.append((kind, data[i:i + size]))
        i += size
    kinds = [k for k, _ in boxes]
    if b"moov" not in kinds or b"mdat" not in kinds or kinds.index(b"moov") < kinds.index(b"mdat"):
        return
    moov = bytearray(dict(boxes)[b"moov"])
    shift = len(moov)

    def patch(buf: bytearray, start: int, end: int) -> None:
        j = start
        while j < end:
            size, kind = struct.unpack(">I4s", buf[j:j + 8])
            if kind in (b"trak", b"mdia", b"minf", b"stbl", b"moov"):
                patch(buf, j + 8, j + size)
            elif kind == b"stco":
                n = struct.unpack(">I", buf[j + 12:j + 16])[0]
                for k in range(n):
                    o = j + 16 + 4 * k
                    buf[o:o + 4] = struct.pack(">I", struct.unpack(">I", buf[o:o + 4])[0] + shift)
            elif kind == b"co64":
                n = struct.unpack(">I", buf[j + 12:j + 16])[0]
                for k in range(n):
                    o = j + 16 + 8 * k
                    buf[o:o + 8] = struct.pack(">Q", struct.unpack(">Q", buf[o:o + 8])[0] + shift)
            j += size

    patch(moov, 8, len(moov))
    out = [b for k, b in boxes if k == b"ftyp"] + [bytes(moov)] + [b for k, b in boxes if k not in (b"ftyp", b"moov")]
    path.write_bytes(b"".join(out))


# ---------------------------------------------------------------- frames from the app's own drawings

def main(names: list[str]) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts"))
    from types import SimpleNamespace

    from PIL import Image
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from app.ui import theme

    OUT.mkdir(parents=True, exist_ok=True)
    card = SimpleNamespace(cycle=["JPG", "PNG", "WEBP", "AVIF"], src="HEIC")
    for mode in ("dark", "light"):
        theme.refresh(mode, "verdant")
        import importlib

        import app.ui.demo as demo_mod
        import app.ui.showcase as sc

        importlib.reload(sc)
        importlib.reload(demo_mod)
        from app.ui.fx import ease_in_out, ease_out, phase

        for name in names:
            t0 = time.perf_counter()
            if name == "demo":
                W, H, n = 1360, 792, int(demo_mod.LOOP * FPS)
                d = demo_mod.DemoScene(width=1600, height=880, steps=False)
                d.resize(1600, 880)
                d.setStyleSheet(f"background: {theme.BG.name()};")
                d.show()
                app.processEvents()

                def frame(i):
                    d._t0 = time.perf_counter() - i / FPS
                    img = d.grab().toImage()
                    bg = QImage(img.size(), QImage.Format.Format_ARGB32)
                    bg.fill(theme.BG)
                    p = QPainter(bg)
                    p.drawImage(0, 0, img)
                    p.end()
                    return bg.copy(120, 0, W, H)
                kbps = 380
            else:
                W, H = (1280, 640) if name in BIG else (800, 400)
                n = int(LOOP * FPS)
                fn = sc.STORIES[name]
                kbps = 420 if name in BIG else 220

                def frame(i, fn=fn, W=W, H=H):
                    t = i / FPS
                    img = QImage(W, H, QImage.Format.Format_ARGB32)
                    img.fill(theme.BG)
                    p = QPainter(img)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    p.scale(W / 300, H / 150)
                    p.setOpacity(ease_out(phase(t, 0.0, 0.3)) * (1 - ease_in_out(phase(t, LOOP - 0.45, LOOP))))
                    fn(p, t, 0, card)
                    p.end()
                    return img
            path = OUT / f"{name}-{mode}.mp4"
            path.unlink(missing_ok=True)
            writer = Mp4Writer(path, W, H, FPS, kbps)
            still = None
            for i in range(n):
                img = frame(i).convertToFormat(QImage.Format.Format_ARGB32)  # BGRA in memory
                writer.write(bytes(img.constBits())[: W * H * 4])
                if i == int(n * 0.78):  # the story's result: shown while loading, and with less motion
                    q = img.convertToFormat(QImage.Format.Format_RGB888)
                    still = Image.frombuffer("RGB", (W, H), bytes(q.constBits()), "raw", "RGB", q.bytesPerLine(), 1)
            writer.close()
            faststart(path)
            if still is not None:
                small = still.resize((W // 2, H // 2), Image.LANCZOS)
                small.save(OUT / f"{name}-{mode}.jpg", quality=82, optimize=True, progressive=True)
            if name == "demo":
                d.close()
            print(f"{name} {mode}: {path.stat().st_size // 1024} KB video, "
                  f"{(OUT / f'{name}-{mode}.jpg').stat().st_size // 1024} KB still, {time.perf_counter() - t0:.1f}s",
                  flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or STORIES + ["demo"])
