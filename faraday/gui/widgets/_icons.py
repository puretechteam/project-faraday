"""
Icon loading helper for the widgets package.

Loads bundled PNG icons from ``assets/icons`` (Feather/Lucide MIT set) at an
appropriate DPI for the current Tk scaling. If an icon file is missing (e.g. the
asset bundle is not yet installed, or running headless), :func:`load_icon`
returns ``None`` and callers must fall back to label text only — it must never
raise.
"""

from __future__ import annotations

import os
from typing import Optional

from tkinter import PhotoImage, _default_root

# assets/icons lives at <project>/assets/icons (four levels up from this file:
# _icons.py -> widgets -> gui -> faraday -> <project>).
_ICONS_DIR = os.path.join(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
    "assets",
    "icons",
)

_CACHE: dict = {}


def _detect_scale() -> int:
    """Return 2 for hi-DPI (tk scaling >= 1.5) else 1."""
    try:
        root = _default_root
        if root is not None:
            s = float(root.tk.call("tk", "scaling"))
            return 2 if s >= 1.5 else 1
    except Exception:
        pass
    return 1


def load_icon(name: str, scale: Optional[int] = None) -> Optional[PhotoImage]:
    """Load a bundled icon ``name`` (without extension) as a ``PhotoImage``.

    Tries ``<name>@2x.png`` then ``<name>.png`` at the detected (or supplied)
    DPI. Returns ``None`` when ``name`` is empty, no file is present, or Tk
    cannot decode it, so callers can fall back to text without crashing.
    """
    if not name:
        return None

    cache_key = (name, scale)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    if scale is None:
        scale = _detect_scale()
    base = os.path.join(_ICONS_DIR, name)
    candidates = (
        [base + "@2x.png", base + ".png"]
        if scale >= 2
        else [base + ".png", base + "@2x.png"]
    )
    path = next((c for c in candidates if os.path.isfile(c)), None)
    if not path:
        _CACHE[cache_key] = None
        return None
    try:
        img = PhotoImage(file=path)
    except Exception:
        _CACHE[cache_key] = None
        return None
    _CACHE[cache_key] = img
    return img
