"""
Design tokens and the application stylesheet.

Widgets opt into styles with dynamic properties rather than hard-coded
colours, e.g. ``button.setProperty("variant", "primary")`` or
``label.setProperty("role", "muted")``. Call :func:`apply_theme` again after
any settings change; it rebuilds the stylesheet and palette and emits
``theme_changed`` so painters (icons, delegates) can refresh.
"""

import string
import sys
from dataclasses import dataclass
from typing import Dict, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from .. import themes

SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADIUS = {"sm": 6, "md": 10, "lg": 14}

ACCENTS = (
    ("Faraday blue", "#4F7CFF"),
    ("Sky", "#66C0F4"),
    ("Cobalt", "#2563EB"),
    ("Mint", "#4ADE80"),
    ("Lime", "#9FD12A"),
    ("Sunset", "#FB923C"),
    ("Rose", "#F43F5E"),
    ("Violet", "#8B5CF6"),
    ("Ice", "#7DD3FC"),
    ("Gold", "#D4A72C"),
)


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    surface: str
    surface_alt: str
    hover: str
    border: str
    text: str
    text_muted: str
    accent: str
    on_accent: str
    accent_soft: str
    danger: str
    warning: str
    success: str


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    ).name()


def _on_color(hex_color: str) -> str:
    c = QColor(hex_color)
    luminance = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
    return "#111317" if luminance > 0.6 else "#FFFFFF"


def resolve_theme_id(mode: str) -> str:
    """The concrete theme for a setting value; ``system`` follows Windows light/dark."""
    if mode == themes.SYSTEM:
        try:
            scheme = QGuiApplication.styleHints().colorScheme()
        except Exception:
            scheme = Qt.ColorScheme.Dark
        return "light" if scheme == Qt.ColorScheme.Light else "dark"
    return mode if mode in themes.THEMES else "dark"


def build_palette(mode: str, accent: str = "", overrides: Optional[Dict[str, str]] = None) -> Palette:
    theme_id = resolve_theme_id(mode)
    c = themes.colors(theme_id, overrides)
    dark = themes.is_dark(theme_id)
    accent = QColor(accent).name() if accent and QColor(accent).isValid() else c["accent"]
    return Palette(
        dark=dark,
        bg=c["bg"],
        surface=c["surface"],
        surface_alt=c.get("surface_alt") or _mix(c["surface"], c["text"], 0.06 if dark else 0.04),
        hover=c.get("hover") or _mix(c["surface"], c["text"], 0.11 if dark else 0.08),
        border=c["border"],
        text=c["text"],
        text_muted=c["muted"],
        accent=accent,
        on_accent=_on_color(accent),
        accent_soft=_mix(c["surface"], accent, 0.20 if dark else 0.14),
        danger=c["danger"],
        warning="#F2B55C" if dark else "#B7791F",
        success="#4CC38A" if dark else "#23955F",
    )


DARK = build_palette("dark")
LIGHT = build_palette("light")


_QSS = string.Template("""
* { outline: 0; }
QWidget { color: $text; font-size: ${fs}px; }
QMainWindow, QDialog, #Shell, #UnlockView, QStackedWidget#Pages > QWidget { background: $bg; }
QToolTip { background: $surface_alt; color: $text; border: 1px solid $border; padding: 4px 8px; border-radius: 6px; }

/* Text roles */
QLabel[role="display"] { font-size: ${fs_display}px; font-weight: 700; }
QLabel[role="title"] { font-size: ${fs_title}px; font-weight: 600; }
QLabel[role="heading"] { font-size: ${fs_heading}px; font-weight: 600; }
QLabel[role="muted"] { color: $text_muted; }
QLabel[role="small"] { color: $text_muted; font-size: ${fs_small}px; }
QLabel[role="overline"] { color: $text_muted; font-size: ${fs_small}px; font-weight: 600; }
QLabel[role="error"] { color: $danger; }
QLabel[role="warning"] { color: $warning; }
QLabel[role="success"] { color: $success; }
QLabel[role="mono"], QLineEdit[mono="true"], QPlainTextEdit[mono="true"] { font-family: "Cascadia Mono", "Consolas", monospace; }
QLabel[role="secret"] { font-family: "Cascadia Mono", "Consolas", monospace; }

/* Surfaces */
QFrame[card="true"] { background: $surface; border: 1px solid $border; border-radius: ${r_lg}px; }
QFrame[card="soft"] { background: $surface_alt; border: none; border-radius: ${r_md}px; }
QFrame[banner="info"] { background: $accent_soft; border-radius: ${r_md}px; }
QFrame[banner="warning"] { background: ${warning_soft}; border-radius: ${r_md}px; }
QFrame[banner="danger"] { background: ${danger_soft}; border-radius: ${r_md}px; }
QFrame#Sidebar { background: $surface; border-right: 1px solid $border; }
QFrame#TopBar { background: $bg; border-bottom: 1px solid $border; }
QFrame[divider="true"] { background: $border; max-height: 1px; min-height: 1px; border: none; }

/* Buttons */
QPushButton, QToolButton {
    background: $surface_alt; border: 1px solid $border; border-radius: ${r_sm}px;
    padding: 7px 14px; color: $text;
}
QPushButton:hover, QToolButton:hover { background: $hover; }
QPushButton:pressed, QToolButton:pressed { background: $border; }
QPushButton:disabled, QToolButton:disabled { color: $text_muted; background: $surface; }
QPushButton:focus, QToolButton:focus { border: 1px solid $accent; }
QPushButton[variant="primary"] { background: $accent; color: $on_accent; border: 1px solid $accent; font-weight: 600; }
QPushButton[variant="primary"]:hover { background: $accent_hover; }
QPushButton[variant="primary"]:disabled { background: $accent_soft; color: $text_muted; border-color: $accent_soft; }
QPushButton[variant="danger"] { background: transparent; color: $danger; border: 1px solid $danger; }
QPushButton[variant="danger"]:hover { background: ${danger_soft}; }
QPushButton[variant="ghost"], QToolButton[variant="ghost"] { background: transparent; border: 1px solid transparent; }
QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover { background: $hover; }
QPushButton[variant="link"] { background: transparent; border: none; color: $accent; padding: 2px 0; }
QPushButton[variant="link"]:hover { text-decoration: underline; }
QToolButton[variant="icon"] { background: transparent; border: 1px solid transparent; padding: 5px; border-radius: ${r_sm}px; }
QToolButton[variant="icon"]:hover { background: $hover; }
QToolButton[variant="icon"]:checked { background: $accent_soft; }
QPushButton[variant="swatch"] { border-radius: 14px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; padding: 0; border: 2px solid transparent; }
QPushButton[variant="swatch"]:checked { border: 2px solid $text; }

/* Inputs */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {
    background: $surface; border: 1px solid $border; border-radius: ${r_sm}px;
    padding: 7px 10px; selection-background-color: $accent; selection-color: $on_accent;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid $accent; }
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] { border: 1px solid $danger; }
QLineEdit:read-only { background: $surface_alt; }
QLineEdit#SearchBox { background: $surface_alt; border: 1px solid transparent; border-radius: 9px; padding: 7px 12px; }
QLineEdit#SearchBox:focus { border: 1px solid $accent; background: $surface; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border; selection-background-color: $accent_soft; selection-color: $text; padding: 4px; }
QCheckBox, QRadioButton { spacing: 8px; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QCheckBox::indicator { border: 1px solid $border; border-radius: 4px; background: $surface; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($check_icon); }
QRadioButton::indicator { border: 1px solid $border; border-radius: 9px; background: $surface; width: 16px; height: 16px; }
QRadioButton::indicator:checked { background: $surface; border: 5px solid $accent; border-radius: 9px; width: 8px; height: 8px; }
QSlider::groove:horizontal { height: 4px; background: $border; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal { background: $accent; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }
QProgressBar { background: $surface_alt; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; text-align: center; }
QProgressBar::chunk { border-radius: 3px; background: $accent; }

/* Lists and tables */
QListView, QListWidget, QTableView, QTableWidget, QTreeView {
    background: $surface; border: 1px solid $border; border-radius: ${r_md}px; padding: 4px;
    alternate-background-color: $surface_alt;
}
QListView::item, QListWidget::item { border-radius: ${r_sm}px; padding: 6px; }
QListView::item:hover, QListWidget::item:hover { background: $hover; }
QListView::item:selected, QListWidget::item:selected { background: $accent_soft; color: $text; }
QListWidget#Nav { background: transparent; border: none; padding: 0; }
QListWidget#Nav::item { padding: 7px 10px; margin: 1px 0; color: $text_muted; }
QListWidget#Nav::item:selected { background: $accent_soft; color: $text; font-weight: 600; }
QListWidget#Nav::item:hover:!selected { background: $hover; color: $text; }
QHeaderView::section { background: $surface; color: $text_muted; border: none; border-bottom: 1px solid $border; padding: 6px 8px; font-weight: 600; }
QTableView { gridline-color: transparent; selection-background-color: $accent_soft; selection-color: $text; }

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $text_muted; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: none; border: none; width: 0; height: 0; }
QSplitter::handle { background: $border; width: 1px; }
QMenu { background: $surface; border: 1px solid $border; border-radius: ${r_md}px; padding: 4px; }
QMenu::item { padding: 6px 22px 6px 12px; border-radius: ${r_sm}px; }
QMenu::item:selected { background: $accent_soft; }
QMenu::separator { height: 1px; background: $border; margin: 4px 8px; }

/* Toast */
QFrame#Toast { background: $toast_bg; border-radius: ${r_md}px; border: 1px solid $border; }
QFrame#Toast QLabel { color: $toast_text; }
""")


class _ThemeBus(QObject):
    theme_changed = Signal()


bus = _ThemeBus()
_current: Palette = DARK
_font_scale: float = 1.0


def current() -> Palette:
    return _current


def font_px(base: float = 13.0) -> int:
    return round(base * _font_scale)


def stylesheet(p: Palette, font_scale: float = 1.0, check_icon: str = "") -> str:
    fs = 13 * font_scale
    return _QSS.substitute(
        **{k: v for k, v in p.__dict__.items() if isinstance(v, str)},
        fs=round(fs), fs_small=round(fs * 0.86), fs_heading=round(fs * 1.15),
        fs_title=round(fs * 1.5), fs_display=round(fs * 2.1),
        r_sm=RADIUS["sm"], r_md=RADIUS["md"], r_lg=RADIUS["lg"],
        accent_hover=_mix(p.accent, "#FFFFFF" if p.dark else "#000000", 0.12),
        warning_soft=_mix(p.surface, p.warning, 0.16),
        danger_soft=_mix(p.surface, p.danger, 0.14),
        toast_bg=p.text if not p.dark else p.surface_alt,
        toast_text=p.bg if not p.dark else p.text,
        check_icon=check_icon,
    )


def apply_theme(app: QApplication, mode: str = "system", accent: str = "", font_scale: float = 1.0,
                overrides: Optional[Dict[str, str]] = None) -> Palette:
    global _current, _font_scale
    _font_scale = font_scale
    _current = build_palette(mode, accent, overrides)
    from . import icons
    icons.clear_cache()
    check_icon = icons.icon_file("check", _current.on_accent)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in (
        (QPalette.Window, _current.bg), (QPalette.WindowText, _current.text),
        (QPalette.Base, _current.surface), (QPalette.AlternateBase, _current.surface_alt),
        (QPalette.Text, _current.text), (QPalette.Button, _current.surface_alt),
        (QPalette.ButtonText, _current.text), (QPalette.Highlight, _current.accent),
        (QPalette.HighlightedText, _current.on_accent), (QPalette.ToolTipBase, _current.surface_alt),
        (QPalette.ToolTipText, _current.text), (QPalette.PlaceholderText, _current.text_muted),
        (QPalette.Link, _current.accent),
    ):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    font = QFont(ui_font_family(app))
    font.setPixelSize(font_px(13))
    app.setFont(font)
    app.setStyleSheet(stylesheet(_current, font_scale, check_icon.replace("\\", "/")))
    for w in app.topLevelWidgets():
        set_dark_title_bar(w, _current.dark)
    bus.theme_changed.emit()
    return _current


def ui_font_family(app: QApplication) -> str:
    """Windows 11's Segoe UI Variable, then Segoe UI, else the platform default.

    Qt lists the variable font as the family "Segoe UI Variable"; asking for
    "Segoe UI Variable Text" silently falls back to Tahoma.
    """
    from PySide6.QtGui import QFontDatabase
    available = set(QFontDatabase.families())
    for family in ("Segoe UI Variable", "Segoe UI"):
        if family in available:
            return family
    return app.font().family()


def set_dark_title_bar(widget: QWidget, dark: bool) -> None:
    """Match the native Windows title bar to the theme (no-op elsewhere)."""
    if sys.platform != "win32" or not widget.isWindow():
        return
    try:
        import ctypes
        value = ctypes.c_int(1 if dark else 0)
        hwnd = int(widget.winId())
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after changing a dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
