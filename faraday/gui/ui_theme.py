"""
UI theme presets and ttk styling aligned with the courier/FTP frontend theme.js (same hex values and preset order).
Stored locally as JSON (not in the vault). Tkinter cannot match a web app pixel-perfect; clam theme is used for broad color coverage.
"""

from __future__ import annotations

import json
import os
import re
import ctypes
import weakref
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, colorchooser, messagebox
from typing import Any, Dict, List, Optional, Tuple

from .icon_helper import set_window_icon

# Registry of custom (canvas/drawn) widgets that recolor via ``apply_theme``.
# Weak references avoid keeping destroyed widgets alive.
_THEMED_WIDGETS: "weakref.WeakSet[tk.Misc]" = weakref.WeakSet()


def register_themed(widget: tk.Misc) -> None:
    """Register a custom widget so it receives live theme updates.

    The widget must implement ``apply_theme(merged)`` where ``merged`` is the
    merged palette dict.
    """
    _THEMED_WIDGETS.add(widget)


def unregister_themed(widget: tk.Misc) -> None:
    """Remove a custom widget from the live theme registry."""
    try:
        _THEMED_WIDGETS.discard(widget)
    except TypeError:
        pass


def apply_theme_to_custom(merged: Dict[str, str]) -> None:
    """Push the merged palette to every registered custom widget.

    Widgets expose ``apply_theme(merged)``; destroyed or misbehaving widgets
    are silently skipped (and unregistered when their Tk object is gone).
    """
    for widget in list(_THEMED_WIDGETS):
        try:
            apply = getattr(widget, "apply_theme", None)
            if apply is None:
                continue
            apply(merged)
        except (tk.TclError, ReferenceError):
            unregister_themed(widget)
        except Exception:
            # A custom widget must not break global theme application.
            pass


def get_active_merged() -> Dict[str, str]:
    """Return the current merged theme palette from the saved config.

    Thin wrapper that does not require a Tk root, suitable for building design
    tokens at (re)theme time.
    """
    cfg = load_theme_config()
    _, merged, _, _ = config_to_merged(cfg)
    return merged


def get_active_font_scale() -> int:
    """Return the current ``font_scale`` (90–130) from the saved config."""
    cfg = load_theme_config()
    _, _, font_scale, _ = config_to_merged(cfg)
    return font_scale

# Mirrors frontend/theme.js — keep keys in sync when porting presets.
COLOR_KEYS: List[Tuple[str, str]] = [
    ("bg", "Background"),
    ("bg_elev", "Surfaces"),
    ("border", "Borders"),
    ("text", "Text"),
    ("muted", "Muted text"),
    ("accent", "Accent"),
    ("danger", "Danger"),
]

THEME_PRESETS: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#1e1e1e",
        "bg_elev": "#252526",
        "border": "#3c3c3c",
        "text": "#d4d4d4",
        "muted": "#9d9d9d",
        "accent": "#3b82f6",
        "danger": "#f87171",
    },
    "twilight": {
        "bg": "#171a21",
        "bg_elev": "#1b2838",
        "border": "#2a475e",
        "text": "#c7d5e0",
        "muted": "#8f98a0",
        "accent": "#66c0f4",
        "danger": "#ff6b6b",
    },
    "light": {
        "bg": "#f3f4f6",
        "bg_elev": "#ffffff",
        "border": "#d1d5db",
        "text": "#111827",
        "muted": "#4b5563",
        "accent": "#2563eb",
        "danger": "#dc2626",
    },
    "contrast": {
        "bg": "#000000",
        "bg_elev": "#0a0a0a",
        "border": "#ffffff",
        "text": "#ffffff",
        "muted": "#e5e5e5",
        "accent": "#ffff00",
        "danger": "#ff4444",
    },
    "forest": {
        "bg": "#141c16",
        "bg_elev": "#1c281f",
        "border": "#2d4a32",
        "text": "#dce8de",
        "muted": "#7a9a80",
        "accent": "#4ade80",
        "danger": "#f87171",
    },
    "newvegas": {
        "bg": "#0a100c",
        "bg_elev": "#101a14",
        "border": "#1f4d32",
        "text": "#5dff9a",
        "muted": "#3a8f5c",
        "accent": "#8cffb4",
        "danger": "#ff7a45",
    },
    # Original Xbox (2001) dashboard: black field, dark green blades, Xbox lime highlights.
    "spiral": {
        "bg": "#000000",
        "bg_elev": "#0a150a",
        "border": "#1e4a24",
        "text": "#e6ffe6",
        "muted": "#6b9c73",
        "accent": "#9fd12a",
        "danger": "#ff5c4a",
    },
    "poly": {
        "bg": "#080a12",
        "bg_elev": "#0f1422",
        "border": "#2a3f62",
        "text": "#e6edf7",
        "muted": "#6b82a8",
        "accent": "#1f8fff",
        "danger": "#ff5c8a",
    },
    "sunset": {
        "bg": "#1c1418",
        "bg_elev": "#261c22",
        "border": "#4a3040",
        "text": "#f3e8ef",
        "muted": "#b8a0b0",
        "accent": "#fb923c",
        "danger": "#f87171",
    },
    "paper": {
        "bg": "#f2efe8",
        "bg_elev": "#faf8f4",
        "border": "#d4cec3",
        "text": "#2c2824",
        "muted": "#6b6560",
        "accent": "#8b6914",
        "danger": "#b45309",
    },
    "graphite": {
        "bg": "#2a2d32",
        "bg_elev": "#34383e",
        "border": "#4a5058",
        "text": "#e8eaed",
        "muted": "#9aa0a8",
        "accent": "#7dd3fc",
        "danger": "#f87171",
    },
}

PRESET_LABELS: List[Tuple[str, str]] = [
    ("dark", "Dark"),
    ("twilight", "Twilight"),
    ("graphite", "Graphite"),
    ("forest", "Forest"),
    ("newvegas", "New Vegas"),
    ("spiral", "Spiral"),
    ("poly", "Poly"),
    ("sunset", "Sunset"),
    ("light", "Light"),
    ("paper", "Paper"),
    ("contrast", "High contrast"),
]

_SCALING_BASELINE: Optional[float] = None

# Palette used by the previous ``apply_theme_to_root`` call. Kept so a theme
# switch can tell "this widget still wears the old theme" apart from "this
# widget was deliberately painted another color".
_LAST_APPLIED_PALETTE: Optional[Dict[str, str]] = None

_THEME_CONFIG_FILENAME = "gui_theme.json"


def _app_data_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "FaradayVault")
    os.makedirs(d, exist_ok=True)
    return d


def theme_config_path() -> str:
    return os.path.join(_app_data_dir(), _THEME_CONFIG_FILENAME)


def normalize_preset_id(p: Optional[str]) -> str:
    if p == "cursor_dark" or not p:
        return "dark"
    if p == "steam":
        return "twilight"
    if p == "polygon":
        return "poly"
    if p in THEME_PRESETS:
        return p
    return "dark"


def merge_theme(preset_id: str, saved_colors: Optional[Dict[str, str]]) -> Dict[str, str]:
    base = dict(THEME_PRESETS.get(preset_id) or THEME_PRESETS["dark"])
    if saved_colors and isinstance(saved_colors, dict):
        hex6 = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for k in list(base.keys()):
            v = saved_colors.get(k)
            if v and hex6.match(v):
                base[k] = v
    return base


def _srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex6: str) -> float:
    h = hex6.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.2126 * _srgb_to_lin(r) + 0.7152 * _srgb_to_lin(g) + 0.0722 * _srgb_to_lin(b)


def _contrast_ratio(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def contrast_text_on_accent(accent_hex: str) -> str:
    return "#000000" if _contrast_ratio(accent_hex, "#000000") >= _contrast_ratio(accent_hex, "#ffffff") else "#ffffff"


def load_theme_config() -> Dict[str, Any]:
    path = theme_config_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_theme_config(data: Dict[str, Any]) -> None:
    with open(theme_config_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def config_to_merged(cfg: Dict[str, Any]) -> Tuple[str, Dict[str, str], int, bool]:
    preset = normalize_preset_id(cfg.get("preset"))
    merged = merge_theme(preset, cfg.get("colors"))
    try:
        font_scale = int(cfg.get("font_scale", 100))
    except (TypeError, ValueError):
        font_scale = 100
    font_scale = max(90, min(130, font_scale))
    reduced_motion = bool(cfg.get("reduced_motion", False))
    return preset, merged, font_scale, reduced_motion


def theme_toplevel_window(win: tk.Misc, merged: Dict[str, str]) -> None:
    """Set Toplevel/Tk window background to the palette (avoids default white around ttk on Windows)."""
    top = win.winfo_toplevel()
    bg = merged["bg"]
    try:
        top.configure(background=bg)
    except tk.TclError:
        try:
            top.configure(bg=bg)
        except tk.TclError:
            pass


def _menu_font_for_root(root: tk.Misc) -> tkfont.Font:
    """Use Tk menu font when available so dropdowns match scaled UI text."""
    for name in ("TkMenuFont", "TkDefaultFont"):
        try:
            return tkfont.nametofont(name, root=root)
        except tk.TclError:
            continue
    return tkfont.Font(root=root)


def _apply_windows_titlebar_theme(root: tk.Tk, merged: Dict[str, str]) -> None:
    """Best-effort native titlebar theming on Windows."""
    if os.name != "nt":
        return
    bg = merged["bg"]
    border = merged["border"]
    text = merged["text"]
    # Dark titlebar generally looks best with dark backgrounds.
    use_dark = 1 if _relative_luminance(bg) < 0.45 else 0

    def _hex_to_colorref(hex6: str) -> int:
        h = hex6.lstrip("#")
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        # Windows COLORREF is 0x00BBGGRR.
        return (b << 16) | (g << 8) | r

    try:
        hwnd = int(root.winfo_id())
        if not hwnd:
            return
        # DWM attributes:
        # 20/19 = immersive dark mode
        # 35 = caption color, 36 = text color, 34 = border color (Win11+)
        hwnd_c = ctypes.c_void_p(hwnd)
        dwmapi = ctypes.windll.dwmapi
        dark_value = ctypes.c_int(use_dark)

        def _set_attr(attr: int, value_ptr, value_size: int) -> bool:
            hr = dwmapi.DwmSetWindowAttribute(
                hwnd_c,
                ctypes.c_uint(attr),
                value_ptr,
                ctypes.c_uint(value_size),
            )
            return int(hr) == 0

        # Prefer exact caption/text/border colors first when supported.
        color_ok = False
        for attr, color_hex in ((35, bg), (36, text), (34, border)):
            color = ctypes.c_uint32(_hex_to_colorref(color_hex))
            ok = _set_attr(attr, ctypes.byref(color), ctypes.sizeof(color))
            color_ok = color_ok or ok

        # Always apply dark-mode hint as compatibility fallback.
        for attr in (20, 19):
            _set_attr(attr, ctypes.byref(dark_value), ctypes.sizeof(dark_value))
        # If exact color attributes are unsupported, the OS will keep its own caption color
        # (often accent-tinted). Dark-mode hint above is the best available fallback.
    except Exception:
        # Native titlebar theming is optional; ignore when unsupported.
        pass


def apply_theme_to_popup_menus(
    menus: List[tk.Menu],
    merged: Dict[str, str],
    root: Optional[tk.Misc] = None,
) -> None:
    """Style tk.Menu dropdowns to match the current palette (native top menu bar ignores this on some OSes)."""
    if not menus:
        return
    bg_elev = merged["bg_elev"]
    border = merged["border"]
    text = merged["text"]
    accent = merged["accent"]
    muted = merged["muted"]
    sel_fg = contrast_text_on_accent(accent)
    menu_font = _menu_font_for_root(root) if root is not None else None
    for m in menus:
        try:
            m.configure(
                bg=bg_elev,
                fg=text,
                activebackground=accent,
                activeforeground=sel_fg,
                disabledforeground=muted,
                bd=0,
                borderwidth=0,
                relief=tk.FLAT,
                activeborderwidth=0,
            )
        except tk.TclError:
            continue
        if menu_font is not None:
            try:
                m.configure(font=menu_font)
            except tk.TclError:
                pass
        for extra in ({"selectcolor": bg_elev}, {"separatorforeground": border}):
            try:
                m.configure(**extra)
            except tk.TclError:
                pass


def _augment_merged(merged: Dict[str, str]) -> Dict[str, str]:
    """Return ``merged`` extended with stable aliases custom widgets rely on.

    Presets only define ``bg``, ``bg_elev``, ``border``, ``text``, ``muted``,
    ``accent`` and ``danger``. Custom widgets expect a richer, stable key set
    (``fg``, ``muted_fg``, ``success``, ``warning``) regardless of preset, so we
    synthesize them here without touching the saved palette or existing API.
    """
    augmented = dict(merged)
    augmented.setdefault("fg", merged.get("text", "#ffffff"))
    augmented.setdefault("muted_fg", merged.get("muted", "#9d9d9d"))
    augmented.setdefault("success", "#22c55e")
    augmented.setdefault("warning", "#f59e0b")
    return augmented


def _apply_widget_module_styles(style: ttk.Style, merged: Dict[str, str]) -> None:
    """Refresh the shared ttk styles owned by :mod:`faraday.gui.widgets`.

    ``FaradayAccent/Danger/Ghost.TButton`` and ``FaradaySearch.TEntry`` derive
    from the accent, so they must be re-derived on every theme change even when
    no instance of those widgets currently exists (a live instance would
    otherwise be the only thing that ever refreshes them).
    """
    try:  # imported lazily: widgets.inputs imports this module
        from .widgets.inputs import apply_shared_input_styles
    except Exception:
        return
    try:
        apply_shared_input_styles(style, merged)
    except Exception:
        # Widget styling must never break global theme application.
        pass


def apply_ttk_styles(style: ttk.Style, merged: Dict[str, str]) -> None:
    """(Re)configure every ttk style from ``merged``.

    Called on *every* theme change (startup, quick preset, settings dialog), so
    accent-dependent state maps (buttons, notebook tabs, treeview selection,
    scrollbar thumbs) always follow the palette that is being applied.
    """
    bg = merged["bg"]
    bg_elev = merged["bg_elev"]
    border = merged["border"]
    text = merged["text"]
    muted = merged["muted"]
    accent = merged["accent"]
    sel_fg = contrast_text_on_accent(accent)

    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=bg, foreground=text, fieldbackground=bg_elev)
    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=text)
    style.configure("TLabelframe", background=bg, foreground=text, bordercolor=border)
    style.configure("TLabelframe.Label", background=bg, foreground=text)
    style.configure("TButton", background=bg_elev, foreground=text, bordercolor=border, focusthickness=1, focuscolor=accent)
    style.map(
        "TButton",
        background=[("active", accent), ("pressed", border)],
        foreground=[("active", sel_fg), ("pressed", text)],
    )
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=bg_elev, foreground=text, bordercolor=border, padding=[10, 4])
    style.map("TNotebook.Tab", background=[("selected", accent)], foreground=[("selected", sel_fg)])
    style.configure("TEntry", fieldbackground=bg_elev, foreground=text, bordercolor=border, insertcolor=text)
    style.configure("TCombobox", fieldbackground=bg_elev, foreground=text, bordercolor=border, arrowcolor=text)
    style.map("TCombobox", fieldbackground=[("readonly", bg_elev)], foreground=[("readonly", text)])
    style.configure("Horizontal.TScale", background=bg, troughcolor=bg_elev, bordercolor=border)
    for _sb in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(_sb, background=bg_elev, troughcolor=bg, bordercolor=border, arrowcolor=text)
        # Without an explicit map the clam theme falls back to its own light
        # grey for the hovered/pressed thumb, which reads as "unthemed".
        style.map(
            _sb,
            background=[("disabled", bg_elev), ("pressed", accent), ("active", accent)],
            arrowcolor=[("disabled", muted)],
        )
    style.configure(
        "Treeview",
        background=bg_elev,
        fieldbackground=bg_elev,
        foreground=text,
        bordercolor=border,
        rowheight=22,
    )
    style.map("Treeview", background=[("selected", accent)], foreground=[("selected", sel_fg)])
    style.configure("Treeview.Heading", background=border, foreground=text, bordercolor=border)
    style.map("Treeview.Heading", background=[("active", accent)])
    style.configure("TCheckbutton", background=bg, foreground=text, focusthickness=1, focuscolor=accent)
    style.configure("TRadiobutton", background=bg, foreground=text, focusthickness=1, focuscolor=accent)
    style.configure("TMenubutton", background=bg_elev, foreground=text, bordercolor=border)
    style.configure("TSeparator", background=border)
    try:
        style.configure(
            "TSpinbox",
            fieldbackground=bg_elev,
            foreground=text,
            bordercolor=border,
            insertcolor=text,
            arrowcolor=text,
            background=bg,
        )
        style.map("TSpinbox", fieldbackground=[("readonly", bg_elev), ("disabled", bg_elev)])
    except tk.TclError:
        pass

    # Shared styles defined by the widgets package (accent-derived buttons and
    # the flat search entry) are part of the same "full ttk re-apply".
    _apply_widget_module_styles(style, merged)


def apply_option_database(root: tk.Misc, merged: Dict[str, str]) -> None:
    """(Re)install the global ``option_add`` defaults for classic Tk widgets.

    Runs on every theme change. Note that the option database only seeds
    widgets created *afterwards*; widgets that already exist are refreshed by
    :func:`retheme_classic_widgets`.
    """
    bg = merged["bg"]
    bg_elev = merged["bg_elev"]
    text = merged["text"]
    muted = merged["muted"]
    accent = merged["accent"]
    sel_fg = contrast_text_on_accent(accent)

    # Classic Tk Text / dialogs (ScrolledText, etc.)
    root.option_add("*Text.background", bg_elev)
    root.option_add("*Text.foreground", text)
    root.option_add("*Text.insertBackground", text)
    root.option_add("*Text.selectBackground", accent)
    root.option_add("*Text.selectForeground", sel_fg)
    root.option_add("*Dialog.background", bg)
    root.option_add("*Menu.background", bg_elev)
    root.option_add("*Menu.foreground", text)
    root.option_add("*Menu.activeBackground", accent)
    root.option_add("*Menu.activeForeground", sel_fg)
    root.option_add("*Menu.disabledForeground", muted)
    root.option_add("*Menu.borderWidth", "0")
    root.option_add("*Menu.activeBorderWidth", "0")
    root.option_add("*Menu.relief", "flat")
    # Classic tk.Scrollbar (ScrolledText wrappers) and bare tk.Frame containers.
    root.option_add("*Scrollbar.background", bg_elev)
    root.option_add("*Scrollbar.troughColor", bg)
    root.option_add("*Scrollbar.activeBackground", accent)
    root.option_add("*Scrollbar.highlightBackground", bg)
    root.option_add("*Scrollbar.borderWidth", "0")
    root.option_add("*Frame.background", bg)
    # ttk.Combobox drops down a classic Tk listbox that ignores ttk styling.
    root.option_add("*TCombobox*Listbox.background", bg_elev)
    root.option_add("*TCombobox*Listbox.foreground", text)
    root.option_add("*TCombobox*Listbox.selectBackground", accent)
    root.option_add("*TCombobox*Listbox.selectForeground", sel_fg)


def _iter_widget_tree(widget: tk.Misc):
    """Yield ``widget`` and every descendant Tkinter knows about.

    Widgets created straight from Tcl (a combobox popdown, for instance) are
    unknown to Tkinter and skipped by ``winfo_children``; those are rebuilt from
    the option database anyway.
    """
    stack: List[tk.Misc] = [widget]
    while stack:
        current = stack.pop()
        yield current
        try:
            stack.extend(current.winfo_children())
        except tk.TclError:
            continue


def retheme_classic_widgets(
    root: tk.Misc,
    merged: Dict[str, str],
    previous: Optional[Dict[str, str]] = None,
) -> None:
    """Repaint already-created classic (non-ttk) widgets from ``merged``.

    ``option_add`` only seeds widgets created after it runs, so everything built
    under the previous preset keeps that preset's colors — most visibly its
    accent (scrollbar thumbs, Text selection, menu highlight). Walking the live
    tree re-applies the very values :func:`apply_option_database` installs, so a
    theme switch reaches those widgets too.

    ``previous`` is the palette that was active before this change. Plain frames
    are only remapped when they still carry one of its colors, so surfaces a
    custom widget paints itself are left untouched (they are repainted right
    afterwards by :func:`apply_theme_to_custom`).
    """
    bg = merged["bg"]
    bg_elev = merged["bg_elev"]
    text = merged["text"]
    accent = merged["accent"]
    sel_fg = contrast_text_on_accent(accent)

    frame_remap: Dict[str, str] = {}
    for key in ("bg", "bg_elev"):
        old = str((previous or {}).get(key, "")).strip().lower()
        if old and old != merged[key].lower():
            frame_remap[old] = merged[key]

    menus: List[tk.Menu] = []
    for widget in _iter_widget_tree(root):
        try:
            if isinstance(widget, ttk.Widget):
                continue  # ttk widgets follow the style database, not options
            if isinstance(widget, tk.Menu):
                menus.append(widget)
            elif isinstance(widget, tk.Scrollbar):
                widget.configure(
                    background=bg_elev,
                    troughcolor=bg,
                    activebackground=accent,
                    highlightbackground=bg,
                    borderwidth=0,
                )
            elif isinstance(widget, tk.Text):
                widget.configure(
                    background=bg_elev,
                    foreground=text,
                    insertbackground=text,
                    selectbackground=accent,
                    selectforeground=sel_fg,
                )
            elif isinstance(widget, tk.Frame) and frame_remap:
                current = str(widget.cget("background")).strip().lower()
                replacement = frame_remap.get(current)
                if replacement:
                    widget.configure(background=replacement)
        except (tk.TclError, ReferenceError, KeyError):
            continue
    if menus:
        apply_theme_to_popup_menus(menus, merged, root=root)


def apply_theme_to_root(
    root: tk.Tk,
    style: ttk.Style,
    merged: Dict[str, str],
    font_scale: int,
    menus: Optional[List[tk.Menu]] = None,
) -> None:
    """Apply ``merged`` everywhere: ttk styles, option database, live widgets.

    This is the single entry point used by startup (:func:`apply_saved_theme`),
    the quick preset menu (:func:`quick_apply_preset`) and the settings dialog,
    so every theme change re-derives all accent-dependent styling instead of
    leaving the previous preset's accent behind.
    """
    global _SCALING_BASELINE, _LAST_APPLIED_PALETTE
    previous = _LAST_APPLIED_PALETTE
    bg = merged["bg"]

    root.configure(bg=bg)
    # Apply now and once again after idle so Windows gets a realized HWND.
    _apply_windows_titlebar_theme(root, merged)
    root.after_idle(lambda r=root, m=merged: _apply_windows_titlebar_theme(r, m))

    apply_ttk_styles(style, merged)
    apply_option_database(root, merged)

    if _SCALING_BASELINE is None:
        try:
            _SCALING_BASELINE = float(root.tk.call("tk", "scaling", "-displayof", root))
        except tk.TclError:
            _SCALING_BASELINE = 1.0
    try:
        root.tk.call("tk", "scaling", "-displayof", root, _SCALING_BASELINE * (font_scale / 100.0))
    except tk.TclError:
        pass

    if menus:
        apply_theme_to_popup_menus(menus, merged, root=root)

    # Widgets created under the previous preset never re-read the option
    # database, so refresh them explicitly before the custom broadcast.
    retheme_classic_widgets(root, merged, previous)
    _LAST_APPLIED_PALETTE = dict(merged)

    # Push the merged palette to all registered custom/drawn widgets so presets
    # and per-color overrides update every surface live. The augmented dict adds
    # stable aliases (fg, muted_fg, success, warning) on top of the raw merged
    # palette (bg, bg_elev, border, text/muted=fg/muted_fg, accent, danger).
    apply_theme_to_custom(_augment_merged(merged))


def apply_saved_theme(root: tk.Tk, style: ttk.Style, menus: Optional[List[tk.Menu]] = None) -> Dict[str, str]:
    cfg = load_theme_config()
    if not cfg:
        cfg = {"preset": "dark", "colors": {}, "font_scale": 100, "reduced_motion": False}
    preset, merged, font_scale, _ = config_to_merged(cfg)
    apply_theme_to_root(root, style, merged, font_scale, menus=menus)
    return merged


class ThemeSettingsDialog:
    """FTP-style theme panel: preset, per-color overrides, font scale, reduced motion."""

    def __init__(
        self,
        parent: tk.Misc,
        root: tk.Tk,
        style: ttk.Style,
        menus: Optional[List[tk.Menu]] = None,
        on_applied=None,
    ):
        self.root = root
        self.style = style
        self._menus = menus
        self.on_applied = on_applied
        self._win = tk.Toplevel(parent.winfo_toplevel())
        self._win.title("Theme")
        self._win.transient(parent.winfo_toplevel())
        self._win.grab_set()
        set_window_icon(self._win)
        # Paint the raw Toplevel with the active palette (otherwise Windows
        # shows a white slab around the ttk content).
        try:
            theme_toplevel_window(self._win, get_active_merged())
        except Exception:
            pass
        cfg = load_theme_config()
        if not cfg:
            cfg = {"preset": "dark", "colors": {}, "font_scale": 100, "reduced_motion": False}
        self._id_by_label = {lbl: pid for pid, lbl in PRESET_LABELS}
        self._label_by_id = {pid: lbl for pid, lbl in PRESET_LABELS}
        pid0 = normalize_preset_id(cfg.get("preset"))
        self._preset_label_var = tk.StringVar(value=self._label_by_id.get(pid0, "Dark"))
        _, merged, _, _ = config_to_merged(cfg)
        self._color_vars: Dict[str, tk.StringVar] = {}
        main = ttk.Frame(self._win, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main, text="Pick a preset, then adjust colors. Saving stores your palette on this computer.").pack(anchor=tk.W)
        row = ttk.Frame(main)
        row.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(row, text="Preset:").pack(side=tk.LEFT, padx=(0, 8))
        preset_combo = ttk.Combobox(row, textvariable=self._preset_label_var, state="readonly", width=22)
        preset_combo["values"] = [lbl for _, lbl in PRESET_LABELS]
        preset_combo.pack(side=tk.LEFT)

        def on_preset_change(_evt=None):
            pid = self._id_by_label.get(preset_combo.get(), "dark")
            base = THEME_PRESETS.get(pid, THEME_PRESETS["dark"])
            for key, _ in COLOR_KEYS:
                self._color_vars[key].set(base[key])

        preset_combo.bind("<<ComboboxSelected>>", on_preset_change)

        colors_fr = ttk.LabelFrame(main, text="Colors", padding=8)
        colors_fr.pack(fill=tk.BOTH, expand=True, pady=8)
        for key, label in COLOR_KEYS:
            r = ttk.Frame(colors_fr)
            r.pack(fill=tk.X, pady=2)
            ttk.Label(r, text=label + ":", width=14).pack(side=tk.LEFT)
            var = tk.StringVar(value=merged.get(key, "#000000"))
            self._color_vars[key] = var
            swatch = tk.Label(r, text="   ", width=3, relief=tk.GROOVE, cursor="hand2")

            def pick(k=key, v=var, s=swatch):
                init = v.get()
                c = colorchooser.askcolor(color=init, title="Color", parent=self._win)
                if c and c[1]:
                    v.set(c[1].lower())
                    s.configure(bg=c[1])

            swatch.bind("<Button-1>", lambda e, pick_fn=pick: pick_fn())
            swatch.pack(side=tk.LEFT, padx=4)

            def upd_swatch(*_a, s=swatch, v=var):
                try:
                    s.configure(bg=v.get())
                except tk.TclError:
                    pass

            var.trace("w", lambda *_x, fn=upd_swatch: fn())
            upd_swatch()
            ent = ttk.Entry(r, textvariable=var, width=10)
            ent.pack(side=tk.LEFT, padx=4)

        opt_fr = ttk.LabelFrame(main, text="Display", padding=8)
        opt_fr.pack(fill=tk.X, pady=4)
        ttk.Label(opt_fr, text="Font scale (%):").pack(anchor=tk.W)
        self._scale_var = tk.IntVar(value=int(cfg.get("font_scale", 100)))
        sc = ttk.Scale(opt_fr, from_=90, to=130, variable=self._scale_var, orient=tk.HORIZONTAL, length=220)
        sc.pack(anchor=tk.W, pady=4)
        self._scale_lbl = ttk.Label(opt_fr, text="")
        self._scale_lbl.pack(anchor=tk.W)

        def upd_lbl(*_):
            self._scale_lbl.configure(text=str(self._scale_var.get()) + "%")

        self._scale_var.trace("w", lambda *_: upd_lbl())
        upd_lbl()
        self._motion_var = tk.BooleanVar(value=bool(cfg.get("reduced_motion", False)))
        ttk.Checkbutton(opt_fr, text="Reduced motion (reserved for future use)", variable=self._motion_var).pack(anchor=tk.W, pady=6)

        btns = ttk.Frame(main)
        btns.pack(fill=tk.X, pady=10)
        ttk.Button(btns, text="Use preset colors only", command=self._reset_colors).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text="Save", command=self._save).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btns, text="Cancel", command=self._win.destroy).pack(side=tk.RIGHT)

    def _reset_colors(self):
        pid = self._id_by_label.get(self._preset_label_var.get(), "dark")
        base = THEME_PRESETS.get(pid, THEME_PRESETS["dark"])
        for key, _ in COLOR_KEYS:
            self._color_vars[key].set(base[key])

    def _save(self) -> None:
        pid = normalize_preset_id(self._id_by_label.get(self._preset_label_var.get(), "dark"))
        colors = {key: self._color_vars[key].get().strip() for key, _ in COLOR_KEYS}
        hex6 = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for k, v in list(colors.items()):
            if not hex6.match(v):
                messagebox.showerror("Theme", f"Invalid hex color for {k}: {v}", parent=self._win)
                return
        payload = {
            "preset": pid,
            "colors": colors,
            "font_scale": max(90, min(130, int(self._scale_var.get()))),
            "reduced_motion": self._motion_var.get(),
        }
        merged = merge_theme(pid, colors)
        save_theme_config(payload)
        apply_theme_to_root(self.root, self.style, merged, payload["font_scale"], menus=self._menus)
        if self.on_applied:
            self.on_applied(payload)
        messagebox.showinfo("Theme", "Theme saved.", parent=self._win)
        self._win.destroy()


def quick_apply_preset(
    root: tk.Tk,
    style: ttk.Style,
    preset_id: str,
    menus: Optional[List[tk.Menu]] = None,
    on_applied=None,
) -> None:
    pid = normalize_preset_id(preset_id)
    cfg = load_theme_config()
    font_scale = int(cfg.get("font_scale", 100)) if cfg else 100
    font_scale = max(90, min(130, font_scale))
    reduced_motion = bool(cfg.get("reduced_motion", False)) if cfg else False
    payload = {"preset": pid, "colors": {}, "font_scale": font_scale, "reduced_motion": reduced_motion}
    merged = merge_theme(pid, {})
    save_theme_config(payload)
    apply_theme_to_root(root, style, merged, font_scale, menus=menus)
    if on_applied:
        on_applied(payload)
