"""Makes the 20-second video (1920x1080, 30 fps, MP4) from the app's own pictures, in four parts:

1. the problem: a file nothing will open
2. Deskvert at work in File Explorer (select, tap Ctrl + Shift, pick a format)
3. checked before you see it: what's compared, line by line
4. an end card

    python tools/capped.py 25 .venv/Scripts/python.exe tools/make_promo.py
    PROMO_FRAMES=1.5,8,15,19 python tools/make_promo.py <folder>     (stills of those moments, to look at)

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
PROBLEM, DEMO, CHECKS, OUTRO = 3.0, 10.0, 4.5, 2.5   # seconds; 20 in all
DEMO_FROM = 0.6  # where the Explorer demo starts (its own fade-in is skipped)
OUT = ROOT / "website" / "assets" / "media" / "deskvert-demo.mp4"
CHECK_LINES = [("beach.heic  →  beach.webp", "same size, same picture"),
               ("report.pdf  →  report.docx", "every word is there"),
               ("talk.mp4  →  talk.mp3", "as long as the sound track"),
               ("budget.xlsx  →  budget.csv", "every cell compared")]


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts"))

    from PIL import Image
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen
    from PySide6.QtWidgets import QApplication

    from make_site_media import Mp4Writer, faststart

    app = QApplication.instance() or QApplication([])
    from app.ui import theme
    theme.refresh("light", "verdant")  # a light look of its own
    import app.ui.demo as demo_mod
    from app.ui.fx import ease_in_out, ease_out, phase

    def font(px: float, weight=QFont.Weight.Bold, mono: bool = False) -> QFont:
        f = QFont("Cascadia Mono" if mono else "Segoe UI")
        f.setPixelSize(int(px))
        f.setWeight(weight)
        return f

    def say(p: QPainter, r: QRectF, s: str, px: float, color: QColor, alpha: float = 1.0, rise: float = 0.0,
            weight=QFont.Weight.Bold, align=Qt.AlignmentFlag.AlignCenter, mono: bool = False) -> None:
        if alpha <= 0:
            return
        p.save()
        p.setOpacity(alpha)
        p.setPen(color)
        p.setFont(font(px, weight, mono))
        p.drawText(r.translated(0, rise), align, s)
        p.restore()

    def card(p: QPainter, r: QRectF, alpha: float = 1.0) -> None:
        p.save()
        p.setOpacity(alpha)
        p.setPen(QPen(theme.LINE, 1.5))
        p.setBrush(theme.SURFACE)
        p.drawRoundedRect(r, 22, 22)
        p.restore()

    def wordmark(p: QPainter, cx: float, y: float, size: float, alpha: float) -> None:
        p.save()
        p.setOpacity(alpha)
        f = font(size * 0.62, QFont.Weight.DemiBold)
        p.setFont(f)
        fm = QFontMetricsF(f)
        w1, w2 = fm.horizontalAdvance("Desk"), fm.horizontalAdvance("vert")
        x = cx - (size * 1.3 + w1 + w2) / 2
        theme.paint_logo(p, QPointF(x + size / 2, y), size)
        r = QRectF(x + size * 1.3, y - size, w1 + w2 + 4, size * 2)
        p.setPen(theme.TEXT)
        p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Desk")
        p.setPen(theme.ACCENT)
        p.drawText(r.translated(w1, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "vert")
        p.restore()

    def tick(p: QPainter, c: QPointF, r: float, k: float, ok: bool = True) -> None:
        if k <= 0:
            return
        p.save()
        p.translate(c)
        p.scale(k, k)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.ACCENT if ok else QColor("#d4553f"))
        p.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))
        pen = QPen(QColor("white"), r * 0.28)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        path = QPainterPath(QPointF(-r * 0.42, 0.02 * r))
        path.lineTo(QPointF(-r * 0.1, r * 0.34))
        path.lineTo(QPointF(r * 0.46, -r * 0.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.restore()

    def file_icon(p: QPainter, r: QRectF, label: str, color: QColor) -> None:
        fold = r.width() * 0.28
        path = QPainterPath(r.topLeft())
        path.lineTo(r.right() - fold, r.top())
        path.lineTo(r.right(), r.top() + fold)
        path.lineTo(r.bottomRight())
        path.lineTo(r.bottomLeft())
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(path)
        say(p, QRectF(r.left(), r.bottom() - r.height() * 0.42, r.width(), r.height() * 0.3), label,
            r.width() * 0.2, QColor("white"))

    dw, dh = 1818, 1000
    demo = demo_mod.DemoScene(width=dw, height=dh, steps=False)
    demo.resize(dw, dh)
    demo.setStyleSheet(f"background: {theme.BG.name()};")
    demo.show()
    app.processEvents()

    def frame(i: int) -> QImage:
        t = i / FPS
        img = QImage(W, H, QImage.Format.Format_ARGB32)
        img.fill(theme.BG)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if t < PROBLEM:  # --------------------------------------------------------- a file nothing will open
            out = 1 - ease_in_out(phase(t, PROBLEM - 0.35, PROBLEM))
            k = ease_out(phase(t, 0.0, 0.6))
            say(p, QRectF(0, 170, W, 120), "Got a file nothing will open?", 84, theme.TEXT, k * out, rise=(1 - k) * 24)
            k2 = ease_out(phase(t, 0.5, 1.1))
            box = QRectF(W / 2 - 430, 380 + (1 - k2) * 30, 860, 300)
            card(p, box, k2 * out)
            p.save()
            p.setOpacity(k2 * out)
            file_icon(p, QRectF(box.left() + 70, box.top() + 70, 130, 160), "HEIC", QColor("#3b82f6"))
            say(p, QRectF(box.left() + 250, box.top() + 80, 560, 60), "beach.heic", 46, theme.TEXT,
                align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            say(p, QRectF(box.left() + 250, box.top() + 145, 560, 50), "This app can't open this file.", 34,
                QColor("#d4553f"), weight=QFont.Weight.DemiBold,
                align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            say(p, QRectF(box.left() + 250, box.top() + 200, 560, 44), "Upload it to a website?  No thanks.", 30,
                theme.DIM, weight=QFont.Weight.Normal, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                alpha=ease_out(phase(t, 1.3, 1.8)))
            p.restore()
        elif t < PROBLEM + DEMO:  # ----------------------------------------------- Deskvert at work
            td = t - PROBLEM
            demo._t0 = time.perf_counter() - (td + DEMO_FROM)
            shot = demo.grab().toImage()
            crop = shot.copy(int(120 * dw / 1600), 0, int(1360 * dw / 1600), int(792 * dh / 880))
            k = ease_out(phase(td, 0.0, 0.4)) * (1 - ease_in_out(phase(td, DEMO - 0.4, DEMO)))
            p.save()
            p.setOpacity(k)
            p.drawImage(QPointF((W - crop.width()) / 2, (H - crop.height()) / 2 + 30), crop)
            p.restore()
            first = ease_out(phase(td, 0.2, 0.7)) * (1 - ease_in_out(phase(td, 2.6, 3.0)))
            second = ease_out(phase(td, 3.0, 3.5)) * (1 - ease_in_out(phase(td, DEMO - 0.5, DEMO - 0.1)))
            say(p, QRectF(0, 26, W, 70), "Tap Ctrl + Shift on it.", 50, theme.TEXT, first)
            say(p, QRectF(0, 26, W, 70), "Pick what you need. It's saved beside it.", 50, theme.TEXT, second)
        elif t < PROBLEM + DEMO + CHECKS:  # -------------------------------------- checked before you see it
            tc = t - PROBLEM - DEMO
            out = 1 - ease_in_out(phase(tc, CHECKS - 0.35, CHECKS))
            k = ease_out(phase(tc, 0.0, 0.5))
            say(p, QRectF(0, 130, W, 110), "Checked before you see it.", 78, theme.TEXT, k * out, rise=(1 - k) * 20)
            box = QRectF(W / 2 - 620, 300, 1240, 470)
            card(p, box, k * out)
            for n, (pair, what) in enumerate(CHECK_LINES):
                kk = ease_out(phase(tc, 0.5 + n * 0.55, 0.9 + n * 0.55)) * out
                y = box.top() + 50 + n * 100
                say(p, QRectF(box.left() + 60, y, 640, 70), pair, 32, theme.TEXT, kk, mono=True,
                    weight=QFont.Weight.DemiBold, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                say(p, QRectF(box.left() + 700, y, 420, 70), what, 30, theme.DIM, kk, weight=QFont.Weight.Normal,
                    align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                p.save()
                p.setOpacity(out)
                tick(p, QPointF(box.right() - 70, y + 35), 22, ease_out(phase(tc, 0.75 + n * 0.55, 1.05 + n * 0.55)))
                p.restore()
            say(p, QRectF(0, 820, W, 60), "If anything doesn't match, nothing is saved.", 34, theme.DIM,
                ease_out(phase(tc, 2.9, 3.4)) * out, weight=QFont.Weight.Normal)
        else:  # ------------------------------------------------------------------ end card
            te = t - PROBLEM - DEMO - CHECKS
            k = ease_out(phase(te, 0.0, 0.5))
            wordmark(p, W / 2, H * 0.33, 84, k)
            say(p, QRectF(0, H * 0.43, W, 110), "Tap, don't drag.", 88, theme.TEXT, ease_out(phase(te, 0.15, 0.65)),
                rise=(1 - k) * 20)
            say(p, QRectF(0, H * 0.58, W, 60), "Free for Windows  ·  nothing is uploaded", 38, theme.DIM,
                ease_out(phase(te, 0.3, 0.8)), weight=QFont.Weight.Normal)
            say(p, QRectF(0, H * 0.67, W, 60), "deskvert-website.vercel.app", 42, theme.ACCENT,
                ease_out(phase(te, 0.45, 0.95)), weight=QFont.Weight.DemiBold)
        p.end()
        return img

    if os.environ.get("PROMO_FRAMES"):  # look at a few moments as pictures instead: PROMO_FRAMES=1.5,8 <folder>
        folder = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
        for s in os.environ["PROMO_FRAMES"].split(","):
            frame(int(float(s) * FPS)).save(str(folder / f"promo-{s}.png"))
        demo.close()
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.unlink(missing_ok=True)
    n = int((PROBLEM + DEMO + CHECKS + OUTRO) * FPS)
    writer = Mp4Writer(OUT, W, H, FPS, 3200)
    t0 = time.perf_counter()
    still = None
    for i in range(n):
        img = frame(i).convertToFormat(QImage.Format.Format_ARGB32)
        writer.write(bytes(img.constBits())[: W * H * 4])
        if i == int((PROBLEM + 3.4) * FPS):  # the picker open, a format chosen
            q = img.convertToFormat(QImage.Format.Format_RGB888)
            still = Image.frombuffer("RGB", (W, H), bytes(q.constBits()), "raw", "RGB", q.bytesPerLine(), 1)
        if i % 120 == 0:
            print(f"frame {i}/{n}", flush=True)
    writer.close()
    faststart(OUT)
    if still is not None:
        still.save(OUT.with_suffix(".jpg"), quality=86, optimize=True, progressive=True)
    demo.close()
    print(f"done: {OUT.stat().st_size // 1024} KB, {time.perf_counter() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
