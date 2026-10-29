"""
Colour themes (toolkit-free, so settings can validate and migrate them).

Each theme gives the base colours; the Qt layer derives hover, soft accent and
status colours from them. ``system`` follows Windows light/dark using the
Faraday themes. The classic themes are the 3.0 presets, colour for colour.
"""

from typing import Dict, List, Tuple

# id: (display name, colours)
THEMES: Dict[str, Tuple[str, Dict[str, str]]] = {
    "dark": ("Faraday dark", {
        "bg": "#0E1014", "surface": "#15181E", "surface_alt": "#1C2028", "hover": "#232833",
        "border": "#2A303B", "text": "#E8EBF1", "muted": "#9AA3B2", "accent": "#4F7CFF", "danger": "#F26D6D"}),
    "light": ("Faraday light", {
        "bg": "#F4F5F8", "surface": "#FFFFFF", "surface_alt": "#EEF0F4", "hover": "#E6E9EF",
        "border": "#DADFE7", "text": "#14171C", "muted": "#5B6474", "accent": "#4F7CFF", "danger": "#D93F3F"}),
    "classic-dark": ("Classic dark", {
        "bg": "#1e1e1e", "surface": "#252526", "border": "#3c3c3c", "text": "#d4d4d4",
        "muted": "#9d9d9d", "accent": "#3b82f6", "danger": "#f87171"}),
    "twilight": ("Twilight", {
        "bg": "#171a21", "surface": "#1b2838", "border": "#2a475e", "text": "#c7d5e0",
        "muted": "#8f98a0", "accent": "#66c0f4", "danger": "#ff6b6b"}),
    "graphite": ("Graphite", {
        "bg": "#2a2d32", "surface": "#34383e", "border": "#4a5058", "text": "#e8eaed",
        "muted": "#9aa0a8", "accent": "#7dd3fc", "danger": "#f87171"}),
    "poly": ("Poly", {
        "bg": "#080a12", "surface": "#0f1422", "border": "#2a3f62", "text": "#e6edf7",
        "muted": "#6b82a8", "accent": "#1f8fff", "danger": "#ff5c8a"}),
    "forest": ("Forest", {
        "bg": "#141c16", "surface": "#1c281f", "border": "#2d4a32", "text": "#dce8de",
        "muted": "#7a9a80", "accent": "#4ade80", "danger": "#f87171"}),
    "newvegas": ("New Vegas", {
        "bg": "#0a100c", "surface": "#101a14", "border": "#1f4d32", "text": "#5dff9a",
        "muted": "#3a8f5c", "accent": "#8cffb4", "danger": "#ff7a45"}),
    "spiral": ("Spiral", {
        "bg": "#000000", "surface": "#0a150a", "border": "#1e4a24", "text": "#e6ffe6",
        "muted": "#6b9c73", "accent": "#9fd12a", "danger": "#ff5c4a"}),
    "sunset": ("Sunset", {
        "bg": "#1c1418", "surface": "#261c22", "border": "#4a3040", "text": "#f3e8ef",
        "muted": "#b8a0b0", "accent": "#fb923c", "danger": "#f87171"}),
    "contrast": ("High contrast", {
        "bg": "#000000", "surface": "#0a0a0a", "border": "#ffffff", "text": "#ffffff",
        "muted": "#e5e5e5", "accent": "#ffff00", "danger": "#ff4444"}),
    "classic-light": ("Classic light", {
        "bg": "#f3f4f6", "surface": "#ffffff", "border": "#d1d5db", "text": "#111827",
        "muted": "#4b5563", "accent": "#2563eb", "danger": "#dc2626"}),
    "paper": ("Paper", {
        "bg": "#f2efe8", "surface": "#faf8f4", "border": "#d4cec3", "text": "#2c2824",
        "muted": "#6b6560", "accent": "#8b6914", "danger": "#b45309"}),
}

SYSTEM = "system"
THEME_IDS: List[str] = [SYSTEM, *THEMES]
COLOR_KEYS = ("bg", "surface", "border", "text", "muted", "accent", "danger")

# 3.0 preset ids (gui_theme.json) -> theme ids here
LEGACY_IDS = {"dark": "classic-dark", "light": "classic-light"}


def theme_name(theme_id: str) -> str:
    if theme_id == SYSTEM:
        return "Match Windows"
    return THEMES.get(theme_id, (theme_id.title(), {}))[0]


def colors(theme_id: str, overrides: Dict[str, str] = None) -> Dict[str, str]:
    """Base colours for a concrete theme id, with optional per-key overrides."""
    base = dict(THEMES.get(theme_id, THEMES["dark"])[1])
    for key, value in (overrides or {}).items():
        if key in COLOR_KEYS and isinstance(value, str) and len(value) == 7 and value.startswith("#"):
            base[key] = value
    return base


def is_dark(theme_id: str) -> bool:
    bg = THEMES.get(theme_id, THEMES["dark"])[1]["bg"].lstrip("#")
    r, g, b = (int(bg[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5


def from_legacy(preset: str, legacy_colors: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Map a 3.0 preset and its saved colours to (theme id, colour overrides)."""
    theme_id = LEGACY_IDS.get(preset, preset)
    if theme_id not in THEMES:
        return "dark", {}
    renamed = {("surface" if k == "bg_elev" else k): v for k, v in (legacy_colors or {}).items()}
    base = THEMES[theme_id][1]
    overrides = {k: v for k, v in renamed.items()
                 if k in COLOR_KEYS and isinstance(v, str) and v.lower() != base.get(k, "").lower()}
    return theme_id, overrides
