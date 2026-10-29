"""
Shared application services handed to every view.

Pages subclass :class:`Page`; the shell calls ``on_show()`` each time a page
becomes visible and destroys every page when the vault locks, so pages never
need to clear secrets themselves beyond not storing them in long-lived objects.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..settings import AppSettings, save_settings
from .services.clipboard import ClipboardService
from .services.guard import Guard
from .services.vault_service import VaultService


@dataclass
class AppContext:
    app: QApplication
    settings: AppSettings
    service: VaultService
    clipboard: ClipboardService
    guard: Guard
    # Filled in by the main window:
    window: Optional[QWidget] = None
    _toast: Optional[Callable[..., None]] = None
    _navigate: Optional[Callable[..., None]] = None
    _settings_applied: Optional[Callable[[], None]] = None
    extra: dict = field(default_factory=dict)

    def toast(self, message: str, kind: str = "success", countdown: int = 0) -> None:
        if self._toast:
            self._toast(message, kind, countdown)

    def navigate(self, page_key: str, entry_id: Optional[str] = None) -> None:
        """Go to a page: 'overview', 'all', a type id such as 'credential', 'generator',
        'backups', 'access_log', 'threat', 'settings' or 'about'."""
        if self._navigate:
            self._navigate(page_key, entry_id)

    def save_settings(self) -> None:
        """Persist settings and apply them app-wide (theme, idle timer, capture protection)."""
        save_settings(self.settings)
        if self._settings_applied:
            self._settings_applied()

    def copy_secret(self, parent: QWidget, text: str, label: str) -> None:
        from .services.guard import SENSITIVE
        if self.guard.require(SENSITIVE, parent, f"copy the {label.lower()}"):
            self.clipboard.copy(text, f"{label} copied", secret=True)


class Page(QWidget):
    """Base for a shell page. ``key``, ``title`` and ``icon`` identify it in the sidebar."""

    key = ""
    title = ""
    icon = "layout-grid"
    needs_vault = True

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx

    def on_show(self, entry_id: Optional[str] = None) -> None:
        """Called whenever the page becomes visible. Refresh data here."""


def scroll_page(widget: QWidget, max_width: int = 880) -> QScrollArea:
    """Wrap page content in a scroll area with a centred, width-capped column."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(32, 28, 32, 32)
    row.addStretch(1)
    widget.setMaximumWidth(max_width)
    row.addWidget(widget, 100)
    row.addStretch(1)
    area.setWidget(holder)
    return area


def page_layout(page: QWidget, content: QWidget, max_width: int = 880) -> None:
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(scroll_page(content, max_width))
