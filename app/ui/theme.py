"""Tapshift's visual system: one neutral base, ONE accent, no gradients, no glows.

Rules (keep them consistent everywhere):
- Color: neutrals for surfaces and text, a single accent for "the thing to act
  on" (selected slice, primary button, progress, toggles). Status colors
  (warning / error / success) only for real status.
- Shape: windows and cards 12 px, buttons and inputs 8 px, toggles and
  segmented controls fully rounded. Nothing else.
- Depth: flat surfaces separated by 1 px hairlines; one soft shadow under
  floating windows only.
- Type: Segoe UI Variable (Windows' own), hierarchy from weight and color.

Palettes: "verdant" (green, the default), "signal" (warm orange), "native"
(your Windows accent color). Light/dark follows Windows unless set in settings.
"""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

FONT = "Segoe UI"


def _windows_prefers_light() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "AppsUseLightTheme")[0])
    except OSError:
        return False


def _windows_accent() -> QColor:
    """The accent color chosen in Windows Settings > Personalization > Colors."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as k:
            abgr = int(winreg.QueryValueEx(k, "AccentColor")[0]) & 0xFFFFFFFF
        return QColor(abgr & 0xFF, (abgr >> 8) & 0xFF, (abgr >> 16) & 0xFF)
    except OSError:
        return QColor(0, 120, 212)


def _settings_value(name: str, default: str) -> str:
    try:
        from ..settings import Settings

        return getattr(Settings.load(), name, default) or default
    except Exception:
        return default


def _mode(choice: str | None = None) -> str:
    forced = os.environ.get("TAPSHIFT_THEME")
    if forced in ("dark", "light"):
        return forced
    choice = choice or _settings_value("theme", "auto")
    if choice in ("dark", "light"):
        return choice
    return "light" if _windows_prefers_light() else "dark"


def _luminance(c: QColor) -> float:
    def ch(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def contrast(a: QColor, b: QColor) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def rgba(c: QColor) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"


def _compute(mode: str, palette: str) -> dict:
    """Every color and stylesheet for one look (light or dark, one palette)."""
    DARK = mode == "dark"
    PALETTE = palette

    # ---------------------------------------------------------------- neutrals
    if DARK:
        BG = QColor(18, 18, 20)            # window background
        SURFACE = QColor(28, 28, 32)       # cards, rows, inputs
        SURFACE2 = QColor(38, 38, 43)      # wheel slices, chips
        LINE = QColor(255, 255, 255, 20)   # hairlines
        TEXT = QColor(240, 240, 238)
        DIM = QColor(150, 150, 158)
        HOVER = QColor(255, 255, 255, 12)
        TRACK = QColor(48, 48, 54)
        SHADOW = QColor(0, 0, 0, 140)
    else:
        BG = QColor(250, 250, 249)
        SURFACE = QColor(255, 255, 255)
        SURFACE2 = QColor(241, 241, 239)
        LINE = QColor(24, 24, 27, 22)
        TEXT = QColor(24, 24, 27)
        DIM = QColor(104, 104, 112)
        HOVER = QColor(24, 24, 27, 10)
        TRACK = QColor(228, 228, 231)
        SHADOW = QColor(24, 24, 27, 46)

    # ---------------------------------------------------------------- accent
    if PALETTE == "native":
        ACCENT = _windows_accent()
        if DARK and _luminance(ACCENT) < 0.18:
            ACCENT = ACCENT.lighter(150)  # Windows itself uses a lighter accent shade on dark
    elif PALETTE == "verdant":
        ACCENT = QColor(52, 190, 132) if DARK else QColor(22, 128, 86)
    else:  # "signal"
        ACCENT = QColor(240, 122, 72) if DARK else QColor(201, 82, 32)

    ON_ACCENT = QColor(18, 18, 20) if contrast(ACCENT, QColor(18, 18, 20)) >= contrast(ACCENT, QColor(255, 255, 255)) \
        else QColor(255, 255, 255)
    ACCENT_HOVER = ACCENT.lighter(112) if DARK else ACCENT.darker(110)
    ACCENT_SOFT = QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 34 if DARK else 26)

    # Status colors: only for real status, never decoration.
    WARN = QColor(222, 164, 54) if DARK else QColor(161, 98, 7)
    ERROR = QColor(236, 92, 84) if DARK else QColor(200, 40, 40)
    SUCCESS = QColor(70, 192, 126) if DARK else QColor(21, 128, 61)
    if PALETTE == "verdant":
        SUCCESS = ACCENT  # one green, not two

    # Compatibility names used across the UI code (all resolve to the one accent).
    ACCENT_A = ACCENT_B = ACCENT
    SLICE = SURFACE2
    SLICE_EDGE = BG
    CENTER = BG
    BORDER = LINE

    RADIUS_CARD = 12
    RADIUS_CONTROL = 8




    CARD_QSS = f"""
    QFrame#card {{
        background: {rgba(BG)};
        border: 1px solid {rgba(LINE)};
        border-radius: {RADIUS_CARD}px;
    }}
    QLabel {{ color: {rgba(TEXT)}; font-family: '{FONT}'; }}
    QLabel#title {{ font-size: 13px; font-weight: 600; }}
    QLabel#big {{ font-size: 15px; font-weight: 600; }}
    QLabel#sub, QLabel#hint {{ color: {rgba(DIM)}; font-size: 11px; }}
    QLabel#warn {{ color: {rgba(WARN)}; font-size: 11px; }}
    QLabel#error {{ color: {rgba(ERROR)}; font-size: 12px; }}
    QLineEdit {{
        background: {rgba(SURFACE)}; color: {rgba(TEXT)};
        border: 1px solid {rgba(LINE)}; border-radius: {RADIUS_CONTROL}px;
        padding: 7px 10px; font: 13px '{FONT}'; selection-background-color: {rgba(ACCENT)};
        selection-color: {rgba(ON_ACCENT)};
    }}
    QLineEdit:focus {{ border: 1px solid {rgba(ACCENT)}; }}
    QListWidget {{ background: transparent; border: none; outline: none; }}
    QPushButton {{
        background: {rgba(SURFACE)}; color: {rgba(TEXT)}; border: 1px solid {rgba(LINE)};
        border-radius: {RADIUS_CONTROL}px; padding: 6px 14px; font: 600 12px '{FONT}';
    }}
    QPushButton:hover {{ background: {rgba(SURFACE2)}; }}
    QPushButton#primary {{ background: {rgba(ACCENT)}; color: {rgba(ON_ACCENT)}; border: none; }}
    QPushButton#primary:hover {{ background: {rgba(ACCENT_HOVER)}; }}
    QPushButton#flat {{ background: transparent; border: none; color: {rgba(DIM)}; padding: 4px 8px; }}
    QPushButton#flat:hover {{ color: {rgba(TEXT)}; }}
    QCheckBox, QComboBox {{ color: {rgba(TEXT)}; font: 12px '{FONT}'; }}
    QComboBox {{ background: {rgba(SURFACE)}; border: 1px solid {rgba(LINE)}; border-radius: {RADIUS_CONTROL}px;
                 padding: 5px 10px; }}
    QComboBox QAbstractItemView {{ background: {rgba(SURFACE)}; color: {rgba(TEXT)};
                                   selection-background-color: {rgba(ACCENT)}; selection-color: {rgba(ON_ACCENT)}; }}
    QSlider::groove:horizontal {{ height: 4px; background: {rgba(TRACK)}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {rgba(ACCENT)}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {rgba(TEXT)}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {rgba(LINE)}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """

    MENU_QSS = f"""
    QMenu {{ background: {rgba(SURFACE)}; color: {rgba(TEXT)}; border: 1px solid {rgba(LINE)};
             border-radius: {RADIUS_CONTROL}px; padding: 5px; font: 12px '{FONT}'; }}
    QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {rgba(HOVER if DARK else SURFACE2)}; }}
    QMenu::item:disabled {{ color: {rgba(DIM)}; }}
    QMenu::indicator {{ width: 14px; height: 14px; }}
    QMenu::separator {{ height: 1px; background: {rgba(LINE)}; margin: 4px 8px; }}
    """
    return {k: v for k, v in locals().items() if k.isupper()}


def refresh(theme_choice: str | None = None, palette: str | None = None) -> None:
    """(Re)compute the look. Called at import and when the look changes in Settings,
    so new choices apply right away; everything reads colors as ``theme.NAME`` when it paints."""
    mode = _mode(theme_choice)
    pal = palette or os.environ.get("TAPSHIFT_PALETTE") or _settings_value("palette", "verdant")
    globals().update(_compute(mode, pal), MODE=mode)


refresh()


def paint_logo(p: QPainter, c: QPointF, size: float, progress: float = 1.0, spin: float = 0.0,
               busy: bool = False, color: QColor | None = None) -> None:
    """The Tapshift mark: five ring segments around a dot, in the accent color.
    ``progress`` 0..1 draws the segments in (for animations), ``spin`` rotates (degrees)."""
    col = color or ACCENT
    r = size * 0.40
    pen = QPen(col, max(2.0, size * 0.16))
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
        p.drawArc(rect, int((90 + spin + i * span + gap / 2) * 16), int((span - gap) * local * 16))
    if progress >= 0.999:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(SUCCESS if busy else col)
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
