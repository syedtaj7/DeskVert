"""Renders README screenshots into docs/images (dark theme by default).
Usage: python tools/screenshots.py [dark|light]"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["TAPSHIFT_THEME"] = sys.argv[1] if len(sys.argv) > 1 else "dark"

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from app.catalog import describe_selection, offers_for  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.guide import GuideWindow  # noqa: E402
from app.ui.onboarding import TourWindow  # noqa: E402
from app.ui.panels import ProgressPanel  # noqa: E402
from app.ui.popup import Popup  # noqa: E402
from app.ui.settings_ui import SettingsWindow  # noqa: E402

OUT = ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def save(widget, name):
    widget.grab().save(str(OUT / f"{name}.png"))


tour = TourWindow({"autostart": True, "theme": "auto", "cpu": 25, "hotkey": "Ctrl+Shift"},
                  {"word": True, "excel": True, "powerpoint": True})
tour.present()
wait(600)
for i, name, ms in ((0, "welcome", 2600), (1, "how-it-works", 4300), (3, "formats", 2600), (4, "setup", 2000)):
    tour.go(i)
    wait(ms)
    save(tour, name)
tour._done = True
tour.hide()

files = [Path("C:/Pictures/beach.heic")]
offers, _ = offers_for(files, Settings())
pop = Popup(describe_selection(files), "1 HEIC", "", offers)
pop.show()
wait(200)
idx = next(i for i, o in enumerate(pop.wheel.items) if o is not None and o.target.label == "WEBP")
pop.wheel.set_hover(idx)
pop._wheel_hover(idx)
wait(100)
wheel = pop.grab()
pop.hide()

panel = ProgressPanel()
panel.start("WEBP", 1)
panel.set_file("beach.heic", 1, 1)
panel.finish("success", "Saved beach.webp", "Checked against the original: everything matches.", "C:/x/beach.webp")
wait(300)
card = panel.grab()
panel.hide()

sheet = QPixmap(wheel.width() + card.width() + 30, max(wheel.height(), card.height()) + 20)
sheet.fill(QColor(0, 0, 0, 0))
p = QPainter(sheet)
p.drawPixmap(10, 10, wheel)
p.drawPixmap(wheel.width() + 20, sheet.height() - card.height() - 10, card)
p.end()
sheet.save(str(OUT / "wheel-and-progress.png"))

g = GuideWindow()
g.present()
wait(400)
g.nav.select(1)
wait(1000)
save(g, "guide")
g.hide()

s = SettingsWindow(Settings(), True)
s.present(2)
wait(1000)
save(s, "settings")
s.hide()
print("screenshots written to", OUT)
