"""
Shared reusable widgets for the Faraday 3.0.0 GUI redesign.

Every custom widget registers itself with :func:`faraday.gui.ui_theme.register_themed`
and implements ``apply_theme(merged)`` so live theme changes (presets, color
overrides, font scale) recolor it without recreation.

Public API
----------
surfaces   : RoundedSurface, Panel
navigation : Sidebar, NavItem
inputs     : SearchBar, PrimaryButton, GhostButton, IconButton, DangerButton,
             LabeledEntry, SecretField, LabeledText
feedback   : EmptyState, show_status, ConfirmDialog
lists      : CardList, EntryCard, SectionHeader
dialogs    : Dialog, ThemedPasswordDialog, AboutDialog, open_theme_settings
windows    : AccessLogDialog (lazily re-exported from
             :mod:`faraday.gui.access_log_window`)
"""

from __future__ import annotations

from .surface import RoundedSurface, Panel
from .nav import Sidebar, NavItem
from .inputs import (
    SearchBar,
    PrimaryButton,
    GhostButton,
    IconButton,
    DangerButton,
    LabeledEntry,
    SecretField,
    LabeledText,
)
from .feedback import EmptyState, show_status, ConfirmDialog
from .lists import CardList, EntryCard, SectionHeader
from .dialogs import (
    Dialog,
    ThemedPasswordDialog,
    AboutDialog,
    open_theme_settings,
)

__all__ = [
    "RoundedSurface",
    "Panel",
    "Sidebar",
    "NavItem",
    "SearchBar",
    "PrimaryButton",
    "GhostButton",
    "IconButton",
    "DangerButton",
    "LabeledEntry",
    "SecretField",
    "LabeledText",
    "EmptyState",
    "show_status",
    "ConfirmDialog",
    "CardList",
    "EntryCard",
    "SectionHeader",
    "Dialog",
    "ThemedPasswordDialog",
    "AboutDialog",
    "open_theme_settings",
    "AccessLogDialog",
]


def __getattr__(name: str):
    """Lazily resolve widgets that live outside this package.

    ``AccessLogDialog`` (``faraday.gui.access_log_window``) imports from this
    package, so importing it eagerly here would be circular. PEP 562 module
    ``__getattr__`` defers the import until the name is actually used, so
    ``from .widgets import AccessLogDialog`` keeps working either way.
    """
    if name == "AccessLogDialog":
        from ..access_log_window import AccessLogDialog as _AccessLogDialog

        globals()[name] = _AccessLogDialog
        return _AccessLogDialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals().keys()) + ["AccessLogDialog"])
