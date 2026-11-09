"""Colors and the app icon (drawn in code, so there are no image files to ship).

Two palettes, picked to match Windows' light/dark app setting (or forced with
"theme": "dark" / "light" in settings.json):
- Dark: graphite surfaces with a cyan-to-blue accent.
- Light: white surfaces with a sky-to-blue accent.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QConicalGradient, QIcon, QPainter, QPen, QPixmap

FONT = "Segoe UI"


def _windows_prefers_light() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "AppsUseLightTheme")[0])
    except OSError:
        return False


def _mode() -> str:
    import os

    forced = os.environ.get("TAPSHIFT_THEME")
    if forced in ("dark", "light"):
        return forced
    try:
        from ..settings import Settings

        choice = Settings.load().theme
    except Exception:
        choice = "auto"
    if choice in ("dark", "light"):
        return choice
    return "light" if _windows_prefers_light() else "dark"


MODE = _mode()
DARK = MODE == "dark"

if DARK:
    BG = QColor(21, 23, 28, 250)
    SURFACE = QColor(31, 35, 43)
    SLICE = QColor(31, 35, 43)
    SLICE_EDGE = QColor(21, 23, 28)
    CENTER = QColor(15, 17, 21)
    TEXT = QColor(243, 244, 246)
    DIM = QColor(154, 163, 178)
    HOVER = QColor(255, 255, 255, 16)
    LINE = QColor(255, 255, 255, 22)
    ACCENT_A = QColor(34, 211, 238)   # cyan
    ACCENT_B = QColor(59, 130, 246)   # blue
    WARN = QColor(251, 191, 36)
    ERROR = QColor(248, 113, 113)
    SUCCESS = QColor(52, 211, 153)
    TRACK = QColor(42, 47, 57)
else:
    BG = QColor(255, 255, 255, 252)
    SURFACE = QColor(241, 244, 248)
    SLICE = QColor(241, 244, 248)
    SLICE_EDGE = QColor(255, 255, 255)
    CENTER = QColor(255, 255, 255)
    TEXT = QColor(15, 23, 42)
    DIM = QColor(100, 116, 139)
    HOVER = QColor(15, 23, 42, 12)
    LINE = QColor(15, 23, 42, 26)
    ACCENT_A = QColor(14, 165, 233)   # sky
    ACCENT_B = QColor(37, 99, 235)    # blue
    WARN = QColor(180, 83, 9)
    ERROR = QColor(220, 38, 38)
    SUCCESS = QColor(5, 150, 105)
    TRACK = QColor(226, 232, 240)

ON_ACCENT = QColor(255, 255, 255)
BORDER = LINE


def rgba(c: QColor) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"


CARD_QSS = f"""
QFrame#card {{
    background: {rgba(BG)};
    border: 1px solid {rgba(LINE)};
    border-radius: 18px;
}}
QLabel {{ color: {rgba(TEXT)}; font-family: '{FONT}'; }}
QLabel#title {{ font-size: 13px; font-weight: 600; }}
QLabel#big {{ font-size: 15px; font-weight: 600; }}
QLabel#sub, QLabel#hint {{ color: {rgba(DIM)}; font-size: 11px; }}
QLabel#warn {{ color: {rgba(WARN)}; font-size: 11px; }}
QLabel#error {{ color: {rgba(ERROR)}; font-size: 12px; }}
QLineEdit {{
    background: {rgba(SURFACE)}; color: {rgba(TEXT)};
    border: 1px solid {rgba(LINE)}; border-radius: 9px;
    padding: 7px 10px; font: 13px '{FONT}'; selection-background-color: {rgba(ACCENT_B)};
}}
QLineEdit:focus {{ border: 1px solid {rgba(ACCENT_A)}; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QPushButton {{
    background: {rgba(SURFACE)}; color: {rgba(TEXT)}; border: 1px solid {rgba(LINE)};
    border-radius: 9px; padding: 6px 14px; font: 600 12px '{FONT}';
}}
QPushButton:hover {{ border: 1px solid {rgba(ACCENT_A)}; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {rgba(ACCENT_A)}, stop:1 {rgba(ACCENT_B)});
    color: white; border: none;
}}
QPushButton#flat {{ background: transparent; border: none; color: {rgba(DIM)}; padding: 4px 8px; }}
QPushButton#flat:hover {{ color: {rgba(TEXT)}; }}
QCheckBox, QComboBox {{ color: {rgba(TEXT)}; font: 12px '{FONT}'; }}
QComboBox {{ background: {rgba(SURFACE)}; border: 1px solid {rgba(LINE)}; border-radius: 8px; padding: 5px 10px; }}
QComboBox QAbstractItemView {{ background: {rgba(SURFACE)}; color: {rgba(TEXT)}; selection-background-color: {rgba(ACCENT_B)}; }}
QSlider::groove:horizontal {{ height: 4px; background: {rgba(TRACK)}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {rgba(ACCENT_A)}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {rgba(ACCENT_B)}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {rgba(LINE)}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

MENU_QSS = f"""
QMenu {{ background: {rgba(QColor(BG.red(), BG.green(), BG.blue()))}; color: {rgba(TEXT)}; border: 1px solid {rgba(LINE)};
         border-radius: 10px; padding: 6px; font: 12px '{FONT}'; }}
QMenu::item {{ padding: 7px 26px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {rgba(ACCENT_B)}; color: white; }}
QMenu::item:disabled {{ color: {rgba(DIM)}; }}
QMenu::separator {{ height: 1px; background: {rgba(LINE)}; margin: 5px 8px; }}
"""


def paint_logo(p: QPainter, c: QPointF, size: float, progress: float = 1.0, spin: float = 0.0,
               busy: bool = False) -> None:
    """The Tapshift mark: five ring segments around a dot.
    ``progress`` 0..1 draws the segments in (for animations), ``spin`` rotates (degrees)."""
    r = size * 0.40
    grad = QConicalGradient(c, 90 + spin)
    grad.setColorAt(0.0, QColor(34, 211, 238))
    grad.setColorAt(0.5, QColor(52, 211, 153) if busy else QColor(59, 130, 246))
    grad.setColorAt(1.0, QColor(34, 211, 238))
    pen = QPen(grad, max(2.0, size * 0.16))
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    segments, gap = 5, 14
    span = 360 / segments
    for i in range(segments):
        local = max(0.0, min(1.0, progress * segments - i))
        if local <= 0:
            continue
        sweep = (span - gap) * local
        p.drawArc(rect, int((90 + spin + i * span + gap / 2) * 16), int(sweep * 16))
    if progress >= 0.999:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(52, 211, 153) if busy else QColor(34, 211, 238))
        d = size * 0.17
        p.drawEllipse(QRectF(c.x() - d / 2, c.y() - d / 2, d, d))


def app_icon(busy: bool = False) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_logo(p, QPointF(size / 2, size / 2), size, busy=busy)
        p.end()
        icon.addPixmap(pm)
    return icon


def polar(center: QPointF, radius: float, deg_ccw_from_east: float) -> QPointF:
    a = math.radians(deg_ccw_from_east)
    return QPointF(center.x() + radius * math.cos(a), center.y() - radius * math.sin(a))
