"""User settings stored as JSON in %APPDATA%\\FileFormatter\\settings.json."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields

from .paths import config_dir

log = logging.getLogger(__name__)


@dataclass
class Settings:
    hotkey: str = "Ctrl+Shift"  # tap Ctrl+Shift together; or a combo such as "Ctrl+Shift+Space"
    theme: str = "auto"  # auto (follow Windows) | dark | light
    palette: str = "verdant"  # verdant (green) | signal (orange) | native (your Windows accent color)
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
