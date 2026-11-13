"""Renders README screenshots into docs/images (dark theme by default).
Usage: python tools/screenshots.py [dark|light]"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DESKVERT_THEME"] = sys.argv[1] if len(sys.argv) > 1 else "dark"

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from app.catalog import describe_selection, offers_for  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.guide import GuideWindow  # noqa: E402
from app.ui.onboarding import TourWindow  # noqa: E402
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
pop = Popup(describe_selection(files), "beach.heic", "", offers)
pop.show()
wait(900)  # let the orbit finish opening
idx = next(i for i, o in enumerate(pop.orbit.items) if o is not None and o.target.label == "WEBP")
pop.orbit.set_hover(idx)
wait(700)  # the drift stops and the side card slides in
save(pop, "picker")
pop.hide()

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
