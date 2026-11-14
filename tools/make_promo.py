"""Makes the 20-second launch video (1920x1080, 30 fps, MP4) from the app's own pictures: a title, the
Explorer demo (select a file, tap Ctrl + Shift, pick a format), dragging from a browser, and an end card.

    python tools/capped.py 25 .venv/Scripts/python.exe tools/make_promo.py

Output: website/assets/media/deskvert-demo.mp4 (+ deskvert-demo.jpg, a still for posts and the page)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

W, H, FPS = 1920, 1080, 30
INTRO, DEMO, DRAG, OUTRO = 2.2, 11.0, 5.0, 1.8   # seconds; 20 in all
OUT = ROOT / "website" / "assets" / "media" / "deskvert-demo.mp4"


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts"))
    from types import SimpleNamespace

    from PIL import Image
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from make_site_media import Mp4Writer, faststart

    app = QApplication.instance() or QApplication([])
    from app.ui import theme
    theme.refresh("dark", "verdant")
    import app.ui.demo as demo_mod
    import app.ui.showcase as sc
    from app.ui.fx import ease_in_out, ease_out, phase

    def font(px: float, weight=QFont.Weight.Bold) -> QFont:
        f = QFont("Segoe UI")
        f.setPixelSize(int(px))
        f.setWeight(weight)
        return f

    def say(p: QPainter, r: QRectF, s: str, px: float, color: QColor, alpha: float = 1.0, rise: float = 0.0,
            weight=QFont.Weight.Bold, align=Qt.AlignmentFlag.AlignCenter) -> None:
        if alpha <= 0:
            return
        p.save()
        p.setOpacity(alpha)
        p.setPen(color)
        p.setFont(font(px, weight))
        p.drawText(r.translated(0, rise), align, s)
        p.restore()

    def wordmark(p: QPainter, cx: float, y: float, size: float, alpha: float, grow: float = 1.0) -> None:
        """The mark and Desk|vert, centred on cx."""
        p.save()
        p.setOpacity(alpha)
        f = font(size * 0.62, QFont.Weight.DemiBold)
        p.setFont(f)
        from PySide6.QtGui import QFontMetricsF
        fm = QFontMetricsF(f)
        w1, w2 = fm.horizontalAdvance("Desk"), fm.horizontalAdvance("vert")
        total = size + size * 0.3 + w1 + w2
        x = cx - total / 2
        theme.paint_logo(p, QPointF(x + size / 2, y), size, progress=grow)
        tx = x + size * 1.3
        r = QRectF(tx, y - size, w1 + w2 + 4, size * 2)
        p.setPen(theme.TEXT)
        p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Desk")
        p.setPen(theme.ACCENT)
        p.drawText(r.translated(w1, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "vert")
        p.restore()

    def glow(p: QPainter) -> None:
        from PySide6.QtGui import QRadialGradient
        g = QRadialGradient(QPointF(W * 0.5, H * 0.62), W * 0.55)
        c = QColor(theme.ACCENT)
        c.setAlphaF(0.10)
        g.setColorAt(0, c)
        c2 = QColor(theme.ACCENT)
        c2.setAlphaF(0.0)
        g.setColorAt(1, c2)
        p.fillRect(QRectF(0, 0, W, H), g)

    # the Explorer demo, drawn by the app's own scene (scaled up, not stretched)
    dw, dh = 1818, 1000
    demo = demo_mod.DemoScene(width=dw, height=dh, steps=False)
    demo.resize(dw, dh)
    demo.setStyleSheet(f"background: {theme.BG.name()};")
    demo.show()
    app.processEvents()
    card = SimpleNamespace(cycle=["JPG", "PNG", "WEBP", "AVIF"], src="HEIC")
    drag = sc.STORIES["web_drag"]

    def frame(i: int) -> QImage:
        t = i / FPS
        img = QImage(W, H, QImage.Format.Format_ARGB32)
        img.fill(theme.BG)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        glow(p)
        if t < INTRO:  # ----------------------------------------------------------- title
            out = 1 - ease_in_out(phase(t, INTRO - 0.35, INTRO))
            wordmark(p, W / 2, H * 0.36, 92, ease_out(phase(t, 0.0, 0.5)) * out, grow=ease_out(phase(t, 0.0, 0.8)))
            k = ease_out(phase(t, 0.45, 1.05))
            say(p, QRectF(0, H * 0.46, W, 140), "Convert any file with one tap.", 92, theme.TEXT, k * out,
                rise=(1 - k) * 30)
            k2 = ease_out(phase(t, 0.85, 1.4))
            say(p, QRectF(0, H * 0.62, W, 60), "Free for Windows  ·  nothing is uploaded", 38, theme.DIM,
                k2 * out * 0.8, weight=QFont.Weight.Normal)
        elif t < INTRO + DEMO:  # -------------------------------------------------- select, Ctrl + Shift, pick
            td = t - INTRO
            demo._t0 = time.perf_counter() - td
            shot = demo.grab().toImage()
            crop = shot.copy(int(120 * dw / 1600), 0, int(1360 * dw / 1600), int(792 * dh / 880))
            x = (W - crop.width()) / 2
            y = (H - crop.height()) / 2 + 20
            p.drawImage(QPointF(x, y), crop)
            k = ease_out(phase(td, 0.2, 0.7)) * (1 - ease_in_out(phase(td, DEMO - 0.5, DEMO)))
            say(p, QRectF(0, 22, W, 70), "Select a file  ·  tap Ctrl + Shift  ·  pick a format", 44, theme.TEXT, k)
        elif t < INTRO + DEMO + DRAG:  # ------------------------------------------- straight from the browser
            ts = t - INTRO - DEMO
            fade = ease_out(phase(ts, 0.0, 0.35)) * (1 - ease_in_out(phase(ts, DRAG - 0.4, DRAG)))
            say(p, QRectF(0, 40, W, 80), "Or drag anything straight from your browser", 52, theme.TEXT, fade)
            sw, sh = 1600, 800
            p.save()
            p.translate((W - sw) / 2, 170)
            p.scale(sw / 300, sh / 150)
            p.setOpacity(fade)
            drag(p, ts, 0, card)
            p.restore()
        else:  # ------------------------------------------------------------------ end card
            te = t - INTRO - DEMO - DRAG
            k = ease_out(phase(te, 0.0, 0.5))
            wordmark(p, W / 2, H * 0.34, 84, k)
            say(p, QRectF(0, H * 0.44, W, 90), "197 kinds of files. Free and open source.", 60, theme.TEXT,
                ease_out(phase(te, 0.15, 0.65)), rise=(1 - k) * 20)
            say(p, QRectF(0, H * 0.58, W, 70), "deskvert-website.vercel.app", 46, theme.ACCENT,
                ease_out(phase(te, 0.3, 0.8)), weight=QFont.Weight.DemiBold)
        p.end()
        return img

    if os.environ.get("PROMO_FRAMES"):  # check a few moments as pictures instead: PROMO_FRAMES=1.4,9.6 <folder>
        folder = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
        for s in os.environ["PROMO_FRAMES"].split(","):
            frame(int(float(s) * FPS)).save(str(folder / f"promo-{s}.png"))
        demo.close()
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.unlink(missing_ok=True)
    n = int((INTRO + DEMO + DRAG + OUTRO) * FPS)
    writer = Mp4Writer(OUT, W, H, FPS, 3200)
    t0 = time.perf_counter()
    still = None
    for i in range(n):
        img = frame(i).convertToFormat(QImage.Format.Format_ARGB32)
        writer.write(bytes(img.constBits())[: W * H * 4])
        if i == int((INTRO + 4.2) * FPS):  # the picker open, WEBP chosen
            q = img.convertToFormat(QImage.Format.Format_RGB888)
            still = Image.frombuffer("RGB", (W, H), bytes(q.constBits()), "raw", "RGB", q.bytesPerLine(), 1)
        if i % 60 == 0:
            print(f"frame {i}/{n}", flush=True)
    writer.close()
    faststart(OUT)
    if still is not None:
        still.save(OUT.with_suffix(".jpg"), quality=86, optimize=True, progressive=True)
    demo.close()
    print(f"done: {OUT.stat().st_size // 1024} KB, {time.perf_counter() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
