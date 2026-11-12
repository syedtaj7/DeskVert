"""The windows people see, built and driven without showing them: the result card with the app's
real event timing (events arrive back to back), every tour page, the picker, Settings and the
results list. These catch a window that fails to build or ends up invisible."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _wait(sec: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(sec * 1000), loop.quit)
    loop.exec()


def _shown(panel) -> bool:
    return panel.isVisible() and panel.windowOpacity() > 0.99


def test_result_card_is_visible_whatever_the_timing(qapp):
    from app.ui.panels import ProgressPanel

    p = ProgressPanel()
    # as a conversion really starts: "started" and "this file" in the same instant
    p.start("JPG", 1)
    p.set_file("photo.png", 1, 1)
    _wait(0.6)
    assert _shown(p), "invisible while converting (the 1.9.2 bug)"
    # a conversion that finishes at once
    p.finish("success", "Saved as JPG", "Checked.", "", [], name="photo.jpg")
    _wait(0.6)
    assert _shown(p)
    # a new one while the card is sliding away
    p._dismiss()
    _wait(0.08)
    p.start("PNG", 2)
    p.set_file("b.jpg", 1, 2)
    _wait(0.6)
    assert _shown(p)
    # back to back, with the Details button for a batch
    p.finish("warning", "Converted 1 file, 1 failed", "b.jpg: damaged", "", [], details=True)
    assert p.details_btn.isVisibleTo(p)
    p.start("PDF", 1)
    p.set_file("c.docx", 1, 1)
    _wait(0.6)
    assert _shown(p)
    # it goes away on its own, and the next one still shows
    p.finish("success", "Saved as PDF", "Checked.", "", [], name="c.pdf")
    p._countdown(200)
    _wait(0.9)
    assert not p.isVisible()
    p.start("WEBP", 1)
    p.set_file("d.png", 1, 1)
    _wait(0.6)
    assert _shown(p)
    p.hide()


def test_every_tour_page_builds_and_shows(qapp):
    from app.ui.onboarding import TourWindow

    choices = {"autostart": True, "theme": "light", "cpu": 25, "hotkey": "Ctrl+Shift", "layout_clash": True}
    w = TourWindow(choices, {"word": False, "excel": False, "powerpoint": False})
    w.resize(1120, 780)
    w.present()
    _wait(0.2)
    for i in range(len(w.pages)):
        w.go(i)
        _wait(0.25)
        assert w.pages[i] is not None and w.pages[i].isVisible(), f"page {i}"
    assert w.pages[0].stats.text().startswith("<b>"), "the format counts never arrived"
    w.close()


def test_picker_settings_and_results_build(qapp):
    from app.menu import build_menu
    from app.settings import Settings
    from app.ui.popup import Popup
    from app.ui.results import ResultsWindow, as_text
    from app.ui.settings_ui import SettingsWindow

    s = Settings()
    for name in ("report.pdf", "photo.heic", "song.wav", "data.csv"):
        nodes, quick, offers = build_menu([Path("C:/x") / name], s)
        Popup(name, "1 file", "", offers, nodes=nodes, quick=quick, scale=s.picker_scale).deleteLater()
    sw = SettingsWindow(s, True)
    sw.present(0)
    _wait(0.1)
    sw.close()
    results = [{"sources": ["C:/x/a.png"], "ok": True, "output": "C:/x/a.jpg"},
               {"sources": ["C:/x/b.png"], "ok": False, "error": "The file is damaged."},
               {"sources": ["C:/x/c.png"], "ok": False, "error": "Cancelled.", "cancelled": True}]
    rw = ResultsWindow("To JPG", results)
    rw.present()
    _wait(0.1)
    text = as_text("To JPG", results)
    assert "1 converted, 1 failed, 1 cancelled" in text and "FAILED  b.png: The file is damaged." in text
    rw.close()
