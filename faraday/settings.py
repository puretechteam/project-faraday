"""
User preferences, stored as ``settings.json`` in the app data folder.

Unknown keys in the file are kept on save so a newer Faraday's settings
survive a round trip through an older one.
"""

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict

from . import themes
from .paths import app_data_dir
from .vault.atomic import atomic_write_bytes

THEME_MODES = tuple(themes.THEME_IDS)


@dataclass
class AppSettings:
    auto_lock_minutes: int = 5          # 0 = never
    clipboard_seconds: int = 30         # 0 = never clear
    reveal_seconds: int = 20            # how long a revealed secret stays visible
    pin_grace_seconds: int = 60         # 0 = ask every time
    theme_mode: str = "system"          # a faraday.themes id
    accent: str = ""                    # "" = the theme's own accent
    theme_colors: Dict[str, str] = field(default_factory=dict)  # per-colour overrides from 3.0
    font_scale: float = 1.0
    minimize_to_tray: bool = False
    lock_on_minimize: bool = False
    lock_on_session_lock: bool = True
    hide_from_capture: bool = False
    backup_keep_recent: int = 10
    backup_keep_daily: int = 14
    themes_restored: bool = False       # the 3.0 theme has been carried over
    _unknown: Dict[str, Any] = field(default_factory=dict, repr=False)

    def normalized(self) -> "AppSettings":
        def clamp(value, low, high, default):
            try:
                return max(low, min(high, type(default)(value)))
            except (TypeError, ValueError):
                return default
        d = AppSettings()
        self.auto_lock_minutes = clamp(self.auto_lock_minutes, 0, 240, d.auto_lock_minutes)
        self.clipboard_seconds = clamp(self.clipboard_seconds, 0, 600, d.clipboard_seconds)
        self.reveal_seconds = clamp(self.reveal_seconds, 5, 600, d.reveal_seconds)
        self.pin_grace_seconds = clamp(self.pin_grace_seconds, 0, 3600, d.pin_grace_seconds)
        self.font_scale = clamp(self.font_scale, 0.8, 1.6, d.font_scale)
        self.backup_keep_recent = clamp(self.backup_keep_recent, 1, 100, d.backup_keep_recent)
        self.backup_keep_daily = clamp(self.backup_keep_daily, 0, 365, d.backup_keep_daily)
        if self.theme_mode not in THEME_MODES:
            self.theme_mode = d.theme_mode
        if not (self.accent == "" or (isinstance(self.accent, str) and len(self.accent) == 7
                                      and self.accent.startswith("#"))):
            self.accent = d.accent
        if not isinstance(self.theme_colors, dict):
            self.theme_colors = {}
        return self


def settings_path():
    return app_data_dir() / "settings.json"


def load_settings() -> AppSettings:
    path = settings_path()
    raw: Dict[str, Any] = {}
    exists = path.exists()
    if exists:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    migrate = not raw.get("themes_restored")
    if migrate:
        legacy = _legacy_theme()
        if legacy:
            raw.update(legacy)
        raw["themes_restored"] = True
    known = {f.name for f in fields(AppSettings) if not f.name.startswith("_")}
    settings = AppSettings(**{k: v for k, v in raw.items() if k in known})
    settings._unknown = {k: v for k, v in raw.items() if k not in known}
    settings.normalized()
    if migrate and exists:
        try:
            save_settings(settings)
        except OSError:
            pass
    return settings


def save_settings(settings: AppSettings) -> None:
    settings.normalized()
    data = dict(settings._unknown)
    data.update({k: v for k, v in asdict(settings).items() if not k.startswith("_")})
    atomic_write_bytes(str(settings_path()), json.dumps(data, indent=2).encode("utf-8"))


def _legacy_theme() -> Dict[str, Any]:
    """Theme, colours and text size from the 3.0 ``gui_theme.json`` (left in place)."""
    try:
        legacy = json.loads((app_data_dir() / "gui_theme.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(legacy, dict) or not legacy.get("preset"):
        return {}
    theme_id, overrides = themes.from_legacy(str(legacy.get("preset")).lower(), legacy.get("colors") or {})
    out: Dict[str, Any] = {"theme_mode": theme_id, "accent": "", "theme_colors": overrides}
    try:
        out["font_scale"] = float(legacy.get("font_scale", 100)) / 100
    except (TypeError, ValueError):
        pass
    return out
