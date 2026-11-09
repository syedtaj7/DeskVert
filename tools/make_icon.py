"""Draws the Tapshift logo into assets/tapshift.ico (16-256 px) for the .exe and installer."""

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap  # noqa: E402

app = QGuiApplication([])
from app.ui import theme  # noqa: E402

frames = []
for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    theme.paint_logo(p, QPointF(size / 2, size / 2), size * 1.08)
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    frames.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))

out = ROOT / "assets" / "tapshift.ico"
out.parent.mkdir(exist_ok=True)
frames[-1].save(out, format="ICO", sizes=[f.size for f in frames], append_images=frames[:-1])
frames[-1].save(ROOT / "assets" / "tapshift.png")
print("wrote", out)
