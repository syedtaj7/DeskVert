"""User settings stored as JSON in %APPDATA%\\FileFormatter\\settings.json."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields

from .paths import config_dir

log = logging.getLogger(__name__)


SUBFOLDER = "Converted"  # the folder used by save_to = "subfolder"
PICKER_SCALE = {"compact": 0.86, "normal": 1.0, "large": 1.14}
QUALITY_LEVELS = {
    "smaller": {"jpeg_quality": 80, "webp_quality": 80, "avif_quality": 70, "heic_quality": 76},
    "high": {"jpeg_quality": 92, "webp_quality": 92, "avif_quality": 88, "heic_quality": 90},  # the defaults
    "best": {"jpeg_quality": 97, "webp_quality": 97, "avif_quality": 95, "heic_quality": 96},
}


@dataclass
class Settings:
    hotkey: str = "Ctrl+Shift"  # tap Ctrl+Shift together; or a combo such as "Ctrl+Shift+Space"
    theme: str = "auto"  # auto (follow Windows) | dark | light
    palette: str = "verdant"  # verdant (green) | signal (orange) | native (your Windows accent color)
    picker_size: str = "normal"  # compact | normal | large (how big the web of choices opens)
    save_to: str = "same"  # same (next to the original) | subfolder (a "Converted" folder beside it) | ask
    auto_update_check: bool = True  # ask GitHub now and then whether a newer Tapshift exists
    last_update_check: float = 0.0  # when it last asked (time.time())
    update_noticed: str = ""  # "<version>@<time>": the last update we told you about, and when
    onboarded: bool = False  # the welcome tour has been shown
    settings_version: int = 3
    jpeg_quality: int = 92
    webp_quality: int = 92
    avif_quality: int = 88
    heic_quality: int = 90
    use_clipboard_fallback: bool = True
    keep_modified_date: bool = True
    max_cpu_percent: int = 25  # hard limit on total CPU used by conversions (5-100)
    max_workers: int = 1  # files converted at the same time; the CPU cap is shared between them
    context_menu: bool = True  # "Convert with Tapshift" in the right-click menu
    drag_convert: bool = True  # hold Ctrl+Shift while dragging something: a drop target appears
    browser_actions: bool = True  # tap Ctrl+Shift on a browser window: the page as PDF, picture or QR code
    auto_jpg_downloads: bool = False  # WEBP and AVIF pictures arriving in Downloads get a JPG copy
    reduce_motion: bool = False  # still pictures instead of animations (Windows' own setting also counts)
    watch_folders: list = field(default_factory=list)  # [{"path": folder, "action": "PDF"}]: new files converted
    quick_recents: bool = True  # recently used actions go on the picker's inner ring
    favourites: list = field(default_factory=list)  # action keys pinned to the inner ring
    recent_actions: list = field(default_factory=list)  # most recent first
    presets: list = field(default_factory=list)  # {id, name, kind, key, options, summary}

    @property
    def picker_scale(self) -> float:
        return PICKER_SCALE.get(self.picker_size, 1.0)

    @property
    def quality_level(self) -> str:
        """The photo quality as one word (Settings > Quality has the exact numbers)."""
        if self.jpeg_quality <= 84:
            return "smaller"
        return "best" if self.jpeg_quality >= 95 else "high"

    def set_quality_level(self, level: str) -> None:
        for key, value in QUALITY_LEVELS.get(level, QUALITY_LEVELS["high"]).items():
            setattr(self, key, value)

    @property
    def workers(self) -> int:
        return max(1, min(4, self.max_workers))

    @property
    def cpu_percent_per_worker(self) -> int:
        return max(5, min(100, self.max_cpu_percent) // self.workers)

    @classmethod
    def path(cls):
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        p = cls.path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("settings_version", 1) < 2:
                    # v1 defaults: Ctrl+Shift+Space hotkey, 2+ parallel workers
                    if data.get("hotkey") == "Ctrl+Shift+Space":
                        data["hotkey"] = "Ctrl+Shift"
                    data["max_workers"] = 1
                    data["settings_version"] = 2
                    migrated = True
                else:
                    migrated = False
                if data.get("settings_version", 1) < 3:
                    data["palette"] = "verdant"  # 1.0.1 redesign: green accent by default
                    data["settings_version"] = 3
                    migrated = True
                names = {f.name for f in fields(cls)}
                for k, v in data.items():
                    if k in names and isinstance(v, type(getattr(s, k))):
                        setattr(s, k, v)
                if migrated or set(names) - set(data):
                    s.save()  # write migrated values and any new settings
            except Exception:
                log.exception("settings.json is unreadable; using defaults")
        else:
            s.save()
        return s

    def save(self) -> None:
        p = self.path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(tmp, p)
