"""
Faraday 3.0.0 design system.

A single source of truth for the visual language, built ON TOP of the merged
color palette produced by :mod:`faraday.gui.ui_theme`. It owns the spacing
scale, radii, typography roles, and the semantic tokens (surface, hover,
shadow, on_accent) derived from the active theme.

The existing theme system in :mod:`faraday.gui.ui_theme` remains the owner of
the raw palette; this module only consumes it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import ui_theme


# ---------------------------------------------------------------------------
# Spacing scale (8px-grid friendly). Use exclusively across the GUI.
# ---------------------------------------------------------------------------
SPACING: Dict[str, int] = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
    "xxl": 24,
}


# ---------------------------------------------------------------------------
# Corner radii.
# ---------------------------------------------------------------------------
RADIUS: Dict[str, int] = {
    "sm": 6,
    "md": 10,
    "lg": 14,
}


# ---------------------------------------------------------------------------
# Typography.
# ---------------------------------------------------------------------------
# System font stacks ordered by preference across platforms. Tk picks the first
# family that is actually installed, falling back to the last entry.
_SYSTEM_UI: List[str] = [
    "Segoe UI",        # Windows
    ".SF NS Text",     # macOS
    "Cantarell",       # Linux (GNOME)
    "DejaVu Sans",     # Linux (generic)
    "Helvetica",
    "TkDefaultFont",
]
_MONO: List[str] = [
    "Consolas",        # Windows
    "Menlo",           # macOS
    "DejaVu Sans Mono",  # Linux
    "Courier New",
    "TkFixedFont",
]

# Named typography roles. ``size`` is the base (unscaled) point size; ``weight``
# maps to Tk's limited weight set (semibold collapses to bold). ``mono`` selects
# the monospace stack used for secrets.
TYPOGRAPHY: Dict[str, Dict[str, Any]] = {
    "display": {"size": 20, "weight": "bold", "mono": False},
    "title": {"size": 15, "weight": "semibold", "mono": False},
    "body": {"size": 13, "weight": "normal", "mono": False},
    "caption": {"size": 11, "weight": "normal", "mono": False},
    "mono": {"size": 13, "weight": "normal", "mono": True},
}

_FAMILY_CACHE: Dict[int, str] = {}


def _resolve_family(stack: List[str]) -> str:
    """Return the first installed family from ``stack`` (cached)."""
    key = id(stack)
    cached = _FAMILY_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        available = set(tkfont.families())
    except Exception:
        available = set()
    chosen = stack[-1]
    for candidate in stack:
        if candidate in available:
            chosen = candidate
            break
    _FAMILY_CACHE[key] = chosen
    return chosen


def font(base: Any, scale: Optional[int] = None) -> Tuple[Any, ...]:
    """Return a Tk font tuple for ``base``, scaled by the active ``font_scale``.

    ``base`` may be a numeric base point size (scaled by ``font_scale``) or a
    named typography role (``"display"``, ``"title"``, ``"body"``,
    ``"caption"``, ``"mono"``). ``scale`` defaults to the active theme
    ``font_scale`` (range 90–130) exposed by
    :func:`faraday.gui.ui_theme.get_active_font_scale`.
    """
    if isinstance(base, str):
        return font_role(base, scale)
    if scale is None:
        try:
            scale = ui_theme.get_active_font_scale()
        except Exception:
            scale = 100
    scaled = max(1, round(float(base) * float(scale) / 100.0))
    return (_resolve_family(_SYSTEM_UI), scaled)


def font_role(role: str, scale: Optional[int] = None) -> Tuple[Any, ...]:
    """Return a Tk font tuple for a named typography role (e.g. ``"title"``)."""
    spec = TYPOGRAPHY[role]
    family = _resolve_family(_MONO if spec.get("mono") else _SYSTEM_UI)
    if scale is None:
        try:
            scale = ui_theme.get_active_font_scale()
        except Exception:
            scale = 100
    size = max(1, round(spec["size"] * float(scale) / 100.0))
    weight = spec.get("weight", "normal")
    if weight in ("semibold", "medium"):
        weight = "bold"
    return (family, size, weight)


# ---------------------------------------------------------------------------
# Color helpers.
# ---------------------------------------------------------------------------
def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(c))) for c in rgb))


def _srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    r, g, b = (c / 255.0 for c in _hex_to_rgb(hex_color))
    return 0.2126 * _srgb_to_lin(r) + 0.7152 * _srgb_to_lin(g) + 0.0722 * _srgb_to_lin(b)


def _contrast_ratio(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _lighten(hex_color: str, amount: float) -> str:
    """Blend ``hex_color`` toward white by ``amount`` (0..1)."""
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount))


def _darken(hex_color: str, amount: float) -> str:
    """Blend ``hex_color`` toward black by ``amount`` (0..1)."""
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((r * (1 - amount), g * (1 - amount), b * (1 - amount)))


def contrast_text_on_accent(hex_color: str) -> str:
    """Return readable black/white text for use on an ``accent`` background."""
    return "#000000" if _contrast_ratio(hex_color, "#000000") >= _contrast_ratio(hex_color, "#ffffff") else "#ffffff"


# ---------------------------------------------------------------------------
# Semantic tokens.
# ---------------------------------------------------------------------------
class Tokens:
    """Resolved design tokens derived from a merged theme palette.

    Exposes every raw merged color plus the derived semantic tokens:
    ``surface``, ``hover``, ``shadow`` (faked — Tkinter has no native shadows),
    and ``on_accent``.
    """

    def __init__(self, merged: Dict[str, str]) -> None:
        self.raw: Dict[str, str] = dict(merged)
        self.bg: str = merged["bg"]
        self.bg_elev: str = merged["bg_elev"]
        self.border: str = merged["border"]
        self.text: str = merged["text"]
        self.muted: str = merged["muted"]
        self.accent: str = merged["accent"]
        self.danger: str = merged["danger"]

        lum = _relative_luminance(self.bg_elev)
        self.surface: str = self.bg_elev
        self.hover: str = _lighten(self.bg_elev, 0.07) if lum < 0.5 else _darken(self.bg_elev, 0.05)
        self.shadow: str = _lighten(self.bg_elev, 0.04) if lum < 0.5 else _darken(self.bg_elev, 0.06)
        self.on_accent: str = contrast_text_on_accent(self.accent)

    def to_dict(self) -> Dict[str, str]:
        """Return all raw colors plus the derived semantic tokens as a dict."""
        out: Dict[str, str] = dict(self.raw)
        out.update(
            surface=self.surface,
            hover=self.hover,
            shadow=self.shadow,
            on_accent=self.on_accent,
        )
        return out

    def __getitem__(self, key: str) -> str:
        return getattr(self, key)


def build_tokens(merged: Dict[str, str]) -> Dict[str, str]:
    """Build semantic design tokens from a merged theme color dict and return
    them as a plain ``dict``.

    Contains every raw merged color plus the derived semantic tokens:
    ``surface`` (``merged['bg_elev']``), ``hover`` (a derived shade),
    ``shadow`` (a 1px-lighter ``bg_elev`` stand-in for shadows — Tkinter has no
    native shadows), and ``on_accent`` (``contrast_text_on_accent(accent)``).
    """
    return Tokens(merged).to_dict()


# ---------------------------------------------------------------------------
# Convenience access to the active palette.
# ---------------------------------------------------------------------------
def get_active_merged() -> Dict[str, str]:
    """Return the current merged theme palette from the saved config."""
    return ui_theme.get_active_merged()
